"""
serial_bridge.py
Production-grade Thread-Safe Serial Bridge for Robotic Hand Arduino Communication.

Features:
- Dynamic Port Discovery & Auto-Scanner (Background thread with hardware VID/PID & keyword prioritization)
- Non-Blocking Thread-Safe Queue (Decouples 30 FPS vision loop from USB serial I/O)
- Automatic Reconnection & Virtual Simulation Mode Fallback (Gracefully survives disconnects & missing hardware)
- Rate-limiting & Serial Buffer Overflow Protection
"""

import os
import sys
import time
import queue
import logging
import threading
from collections import deque
from typing import Dict, List, Optional, Tuple, Any

import serial
from serial.tools import list_ports

logger = logging.getLogger("RoboticHandSerial")

# Known Arduino / USB-to-UART Bridge Vendor & Product IDs
KNOWN_HARDWARE_IDS = [
    # (VID, PID, Description)
    (0x2341, None, "Official Arduino (Uno/Mega/Nano)"),
    (0x2A03, None, "Arduino.org Board"),
    (0x1A86, 0x7523, "CH340 USB-Serial (Common Arduino Nano/Uno Clone)"),
    (0x1A86, 0x5523, "CH341 USB-Serial"),
    (0x10C4, 0xEA60, "Silicon Labs CP2102 USB-to-UART Bridge"),
    (0x0403, 0x6001, "FTDI FT232R USB UART"),
    (0x0403, 0x6015, "FTDI FT230X"),
    (0x1B4F, 0x9205, "SparkFun Pro Micro / ATmega32U4"),
]

# Descriptor keywords for heuristic matching
HARDWARE_KEYWORDS = (
    "arduino",
    "ch340",
    "ch341",
    "cp210",
    "ftdi",
    "usb-serial",
    "usb serial",
    "wch",
    "nano",
    "uno",
    "mega",
    "silicon labs",
)


class BoardDescriptor:
    description: str

    def __init__(self, device: str, description: str, hwid: str, vid: Optional[int], pid: Optional[int], priority: int):
        self.device = device
        self.description = description
        self.hwid = hwid
        self.vid = vid
        self.pid = pid
        self.priority = priority  # Higher means stronger likelihood of being Arduino

    def __repr__(self) -> str:
        return f"{self.device} - {self.description} (Priority: {self.priority})"


class RobustSerialBridge:
    def __init__(
        self,
        baud: int = 9600,
        auto_scan: bool = True,
        auto_reconnect: bool = True,
        simulate_if_missing: bool = True,
    ):
        self.baud = baud
        self.auto_scan = auto_scan
        self.auto_reconnect = auto_reconnect
        self.simulate_if_missing = simulate_if_missing

        self.ser: Optional[serial.Serial] = None
        self.active_port: Optional[str] = None
        self.mode: str = "INITIALIZING"  # "HARDWARE" | "SIMULATION" | "DISCONNECTED"

        # Thread synchronization
        self.lock = threading.Lock()
        self.send_queue: queue.Queue = queue.Queue(maxsize=40)
        self.log_buffer: deque = deque(maxlen=80)
        self.discovered_boards: List[BoardDescriptor] = []

        # Background worker lifecycle
        self._stop_event = threading.Event()
        self._last_sent_command: Optional[str] = None
        self._last_send_time: float = 0.0

        # Start background threads
        self._worker_thread = threading.Thread(target=self._serial_worker_loop, daemon=True, name="SerialWorkerThread")
        self._worker_thread.start()

        if self.auto_scan:
            self._scanner_thread = threading.Thread(target=self._auto_scanner_loop, daemon=True, name="PortScannerThread")
            self._scanner_thread.start()

    def log(self, message: str, level: str = "INFO"):
        timestamp = time.strftime("%H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}"
        with self.lock:
            self.log_buffer.append(entry)
        if level in ("ERROR", "WARN"):
            print(entry)

    # --------------------------------------------------------------------------
    # 1. DYNAMIC PORT DISCOVERY & AUTO-SCANNER
    # --------------------------------------------------------------------------
    def scan_ports(self) -> List[BoardDescriptor]:
        """Scans all system COM ports and ranks them by Arduino likelihood."""
        boards: List[BoardDescriptor] = []
        try:
            for p in list_ports.comports():
                device = p.device or ""
                desc = p.description or ""
                hwid = p.hwid or ""
                vid = p.vid
                pid = p.pid

                priority = 0
                combined_text = f"{desc} {hwid} {device}".lower()

                # Check known VID/PID
                for k_vid, k_pid, _ in KNOWN_HARDWARE_IDS:
                    if vid == k_vid:
                        priority += 50
                        if k_pid is None or pid == k_pid:
                            priority += 50
                        break

                # Check keyword matches
                for kw in HARDWARE_KEYWORDS:
                    if kw in combined_text:
                        priority += 20

                # Generic COM port has priority 1
                if priority == 0 and "com" in device.lower():
                    priority = 5

                boards.append(BoardDescriptor(device, desc, hwid, vid, pid, priority))

            boards.sort(key=lambda b: b.priority, reverse=True)
        except Exception as err:
            self.log(f"Port scan exception: {err}", "WARN")

        with self.lock:
            self.discovered_boards = boards

        return boards

    def get_port_choices(self) -> List[str]:
        """Returns formatted string list of ports suitable for UI dropdowns."""
        boards = self.scan_ports()
        if not boards:
            return ["No Hardware COM Ports (Virtual Simulation Active)"]
        return [f"{b.device} - {b.description}" for b in boards]

    def _auto_scanner_loop(self):
        """Intelligent background thread that detects board plug/unplug events."""
        while not self._stop_event.is_set():
            try:
                boards = self.scan_ports()
                best_board = boards[0] if boards and boards[0].priority >= 20 else None

                with self.lock:
                    is_connected = (self.ser is not None and self.ser.is_open)

                # Case A: Board disconnected physically
                if is_connected:
                    # Verify our active port still exists in system
                    active_still_present = any(b.device.lower() == self.active_port.lower() for b in boards) if self.active_port else False
                    if not active_still_present:
                        self.log(f"Active board on {self.active_port} was unplugged! Switching to Virtual Simulation Mode.", "WARN")
                        self._disconnect_internal(fallback_to_simulation=True)

                # Case B: Board plugged in, auto-reconnect requested
                elif self.auto_reconnect and best_board and self.mode != "HARDWARE":
                    self.log(f"Auto-detected compatible board: {best_board.device} ({best_board.description}). Attempting connection...", "INFO")
                    self.connect(best_board.device, self.baud)

                # Case C: No boards at all, ensure simulation mode is active
                elif not is_connected and self.simulate_if_missing and self.mode != "SIMULATION":
                    with self.lock:
                        self.mode = "SIMULATION"
                    self.log("No physical Arduino detected. Virtual Simulation Mode is active.", "INFO")

            except Exception as err:
                self.log(f"Auto-scanner error: {err}", "WARN")

            # Scan interval (1.5 seconds)
            time.sleep(1.5)

    # --------------------------------------------------------------------------
    # 2. CONNECTION & DISCONNECTION MANAGEMENT
    # --------------------------------------------------------------------------
    def connect(self, port_name: Optional[str] = None, baud: Optional[int] = None) -> Tuple[bool, str]:
        """Connects to the specified port or best auto-detected port."""
        if baud:
            self.baud = baud

        # Find target port
        target_port = port_name
        if not target_port or "No Hardware" in target_port:
            boards = self.scan_ports()
            if boards and boards[0].priority >= 10:
                target_port = boards[0].device
            else:
                target_port = None

        if not target_port:
            with self.lock:
                self.mode = "SIMULATION"
            msg = "No physical hardware board available. Running in Virtual Simulation Mode."
            self.log(msg, "INFO")
            return True, msg

        # Extract COM port device name (e.g. 'COM4' from 'COM4 - Arduino Uno')
        device = target_port.split()[0].strip()

        with self.lock:
            # Close existing handle
            if self.ser and self.ser.is_open:
                try:
                    self.ser.close()
                except Exception:
                    pass
            self.ser = None

        try:
            self.log(f"Opening serial connection to {device} @ {self.baud} baud...", "INFO")
            ser = serial.Serial(
                device,
                self.baud,
                timeout=0.08,
                write_timeout=1.0,
            )
            # Give Arduino Uno/Nano 1.8 seconds to reset after DTR toggle
            time.sleep(1.8)
            ser.reset_input_buffer()
            ser.reset_output_buffer()

            with self.lock:
                self.ser = ser
                self.active_port = device
                self.mode = "HARDWARE"

            msg = f"Connected successfully to {device} @ {self.baud} baud."
            self.log(msg, "INFO")
            return True, msg

        except (serial.SerialException, OSError) as err:
            self.log(f"Failed to open {device}: {err}", "WARN")
            if self.simulate_if_missing:
                with self.lock:
                    self.mode = "SIMULATION"
                    self.active_port = f"{device} (Simulated)"
                msg = f"Hardware open failed ({err}). Switched to Virtual Simulation Mode."
                self.log(msg, "WARN")
                return True, msg
            else:
                with self.lock:
                    self.mode = "DISCONNECTED"
                    self.active_port = None
                return False, f"Could not connect to {device}: {err}"

    def disconnect(self) -> Tuple[bool, str]:
        """Manual disconnect called by user."""
        return self._disconnect_internal(fallback_to_simulation=self.simulate_if_missing)

    def _disconnect_internal(self, fallback_to_simulation: bool = True) -> Tuple[bool, str]:
        with self.lock:
            if self.ser:
                try:
                    self.ser.close()
                except Exception:
                    pass
            self.ser = None
            self.active_port = None
            self.mode = "SIMULATION" if fallback_to_simulation else "DISCONNECTED"

        msg = "Disconnected from physical serial port." + (" (Simulation Active)" if fallback_to_simulation else "")
        self.log(msg, "INFO")
        return True, msg

    # --------------------------------------------------------------------------
    # 3. NON-BLOCKING THREAD-SAFE QUEUE WORKER
    # --------------------------------------------------------------------------
    def send_gesture(self, gesture_name: str, force: bool = False) -> bool:
        """
        Fast, non-blocking method for vision/camera loop.
        Places gesture in thread-safe queue. Returns immediately.
        """
        cmd = "O" if gesture_name.upper() == "OPEN" else "C"
        return self.queue_command(cmd, force=force)

    def queue_command(self, cmd_char: str, force: bool = False) -> bool:
        """Enqueues command char ('O' or 'C') with rate-limiting and deduplication."""
        cmd = cmd_char.upper()
        now = time.monotonic()

        # Suppress duplicate commands unless forced or 1.5 seconds have elapsed
        if not force and cmd == self._last_sent_command and (now - self._last_send_time < 1.5):
            return True

        try:
            # Drop older pending commands if queue is backing up to prevent servo command lag
            while self.send_queue.qsize() > 2:
                try:
                    self.send_queue.get_nowait()
                except queue.Empty:
                    break

            self.send_queue.put_nowait(cmd)
            self._last_sent_command = cmd
            self._last_send_time = now
            return True
        except queue.Full:
            self.log("Serial write queue full; command dropped.", "WARN")
            return False

    def _serial_worker_loop(self):
        """Dedicated worker thread handling serial writes & reads."""
        while not self._stop_event.is_set():
            # 1. Process outgoing commands from queue
            try:
                cmd = self.send_queue.get(timeout=0.08)
                self._dispatch_command(cmd)
                self.send_queue.task_done()
            except queue.Empty:
                pass

            # 2. Poll incoming serial responses from physical Arduino
            self._poll_incoming_serial()

    def _dispatch_command(self, cmd: str):
        """Executes write to physical serial or simulated hardware."""
        with self.lock:
            current_mode = self.mode
            ser_handle = self.ser

        # Hardware Mode Dispatch
        if current_mode == "HARDWARE" and ser_handle and ser_handle.is_open:
            try:
                data = cmd.encode("ascii")
                ser_handle.write(data)
                ser_handle.flush()
                self.log(f"TX -> Hardware '{cmd}' ({'OPEN 10°' if cmd == 'O' else 'CLOSED 170°'})", "INFO")
                return
            except (serial.SerialException, OSError) as err:
                self.log(f"Write failed to {self.active_port}: {err}. Switching to Simulation Mode.", "WARN")
                self._disconnect_internal(fallback_to_simulation=True)

        # Virtual Simulation Mode Dispatch (Graceful fallback)
        if current_mode == "SIMULATION":
            state_text = "OPEN (Target: 10° on Pins 2..11)" if cmd == "O" else "CLOSED (Target: 170° on Pins 2..11)"
            self.log(f"[VIRTUAL ARDUINO] Command '{cmd}' executed -> Servos {state_text}", "INFO")

    def _poll_incoming_serial(self):
        """Reads incoming characters/lines from Arduino hardware buffer."""
        with self.lock:
            ser_handle = self.ser
            is_hw = (self.mode == "HARDWARE" and ser_handle and ser_handle.is_open)

        if not is_hw:
            return

        try:
            while ser_handle.in_waiting > 0:
                line = ser_handle.readline().decode("utf-8", errors="ignore").strip()
                if line:
                    self.log(f"[RX ARDUINO] {line}", "INFO")
        except (serial.SerialException, OSError) as err:
            self.log(f"Serial read error on {self.active_port}: {err}", "WARN")
            self._disconnect_internal(fallback_to_simulation=True)

    # --------------------------------------------------------------------------
    # 4. DIAGNOSTICS & TELEMETRY ACCESSORS
    # --------------------------------------------------------------------------
    def get_status_dict(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "mode": self.mode,
                "port": self.active_port,
                "baud": self.baud,
                "is_connected": (self.ser is not None and self.ser.is_open),
                "is_simulated": (self.mode == "SIMULATION"),
                "queue_size": self.send_queue.qsize(),
                "discovered_count": len(self.discovered_boards),
            }

    def get_logs_text(self) -> str:
        with self.lock:
            return "\n".join(self.log_buffer) if self.log_buffer else "Serial logging initialized. Awaiting commands..."

    def close(self):
        self._stop_event.set()
        with self.lock:
            if self.ser:
                try:
                    self.ser.close()
                except Exception:
                    pass
            self.ser = None
            self.mode = "DISCONNECTED"
