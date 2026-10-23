"""
mediator_bridge.py
Mirror hand gestures to Arduino robot hand with Robust Serial Bridge & Virtual Simulation Fallback.
Webcam -> MediaPipe -> OPEN/CLOSED -> Robust Thread-Safe Queue -> Arduino / Simulation.
"""

import argparse
import sys
import os
import time
from typing import Optional, Set

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import cv2
from hand_tracker_ai import HandTrackerAI, ResilientCamera
from serial_bridge import RobustSerialBridge

BAUD_RATE = 9600


def draw_status(frame, hand_state: Optional[str], bridge: RobustSerialBridge) -> None:
    h = frame.shape[0]

    # Hand State Badge
    if hand_state:
        color = (0, 255, 0) if hand_state == "OPEN" else (0, 0, 255)
        cv2.putText(
            frame,
            f"HAND: {hand_state}",
            (10, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            color,
            3,
        )
    else:
        cv2.putText(
            frame,
            "HAND: not detected",
            (10, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (180, 180, 180),
            2,
        )

    # Hardware / Simulation Mode Badge
    status = bridge.get_status_dict()
    if status["mode"] == "HARDWARE":
        text = f"Hardware: {status['port']} @ {status['baud']}"
        color = (0, 255, 0)
    elif status["mode"] == "SIMULATION":
        text = "Hardware: VIRTUAL SIMULATION (Auto-Scanner Active)"
        color = (255, 0, 255)
    else:
        text = "Hardware: DISCONNECTED"
        color = (0, 0, 255)

    cv2.putText(
        frame,
        text,
        (10, h - 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        color,
        2,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mirror hand gestures to Arduino robot hand with robust serial bridge."
    )
    parser.add_argument("--port", default=None, help="Target serial port, e.g. COM3 or COM4.")
    parser.add_argument("--baud", type=int, default=BAUD_RATE, help="Serial baud rate (default: 9600).")
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default: 0).")
    parser.add_argument("--scan", action="store_true", help="Auto scan camera indexes 0-3.")
    parser.add_argument("--model", default="user_hand_model.pkl", help="Model file path.")
    args = parser.parse_args()

    # Initialize Robust Serial Bridge with Auto-Scanner & Simulation Fallback
    bridge = RobustSerialBridge(
        baud=args.baud,
        auto_scan=True,
        auto_reconnect=True,
        simulate_if_missing=True,
    )

    if args.port:
        bridge.connect(args.port, args.baud)

    camera = ResilientCamera(
        args.camera,
        auto_index=args.scan,
    )

    tracker = HandTrackerAI(model_path=args.model)
    last_sent: Optional[str] = None

    print("[SYSTEM READY] Press Q or ESC to quit.")

    try:
        while True:
            frame = camera.read()

            if frame is None:
                if cv2.waitKey(30) & 0xFF in (ord("q"), 27):
                    break
                continue

            frame = cv2.flip(frame, 1)
            frame, state = tracker.process_frame(frame)
            hand_state = state["hand_state"] if state else None

            # Non-blocking state transition trigger
            if hand_state and hand_state != last_sent:
                bridge.send_gesture(hand_state)
                last_sent = hand_state

            draw_status(frame, hand_state, bridge)

            cv2.imshow("Hand Tracker to Arduino Mediator", frame)

            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break

    except KeyboardInterrupt:
        print("\n[SYSTEM] Interrupted.")

    finally:
        bridge.close()
        camera.release()
        cv2.destroyAllWindows()
        tracker.close()
        print("[SYSTEM] Shut down cleanly.")


if __name__ == "__main__":
    main()
