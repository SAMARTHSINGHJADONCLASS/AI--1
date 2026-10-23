# 🦾 Robotic Hand AI Vision & Embedded Control Master Platform

An enterprise-grade, unified web platform engineered with **Gradio 6**, **MediaPipe**, **scikit-learn**, **FastAPI**, **Three.js**, and a production-ready **Thread-Safe Serial Bridge** for the 10-Servo AI Robotic Hand system.

---

## 🚀 Quick Start

Run the unified master platform from PyCharm's terminal or PowerShell:

### Option 1: From the Project Root
```powershell
# Using the project's virtual environment
.\.venv1\Scripts\python.exe dashboard.py
# Or
.\.venv1\Scripts\python.exe fg.py
```

### Option 2: From `robotic_hand_project1`
```powershell
cd robotic_hand_project1
..\.venv1\Scripts\python.exe dashboard.py
```

Open your browser to:
👉 **`http://127.0.0.1:7860`**  
*(Note: If port 7860 is occupied by an existing process, the system automatically binds to the next free port, e.g. `7861`, preventing startup collisions).*

---

## 🌟 Master Platform Architecture & Pages

### 1. 🖐️ Live Vision Tracker (Continuous Real-Time)
- **Continuous Live Streaming**: Click the webcam icon to start real-time inference without clicking snapshot buttons.
- **Biometric Pipeline Resilience**: Robust zero-division and missing keypoint guards (`wrist-to-fingertip / wrist-to-middle-base`) that safely handle boundary edge cases.
- **7-Frame Voting Filter**: Enforces temporal smoothing ($4/7$ majority threshold) and strict hysteresis ($Open > 1.35, Closed < 1.15$) to prevent servo chatter.
- **On-Frame High-Visibility HUD**: Live FPS counter, `STATE: OPEN` / `STATE: CLOSED` banner, and biometric extension ratios rendered directly on stream.
- **🖥️ Zero-Latency Desktop Window**: Button to launch a native DirectShow 30 FPS OpenCV window with keyboard controls (`Q` to quit).

### 2. 📸 Photo Inspection
- Inspect high-resolution static images or snapshots.
- Full breakdown of normalized fingertip distance ratios and probability distributions.

### 3. 🎥 Video Analyzer
- Upload pre-recorded `.mp4` or `.avi` gesture clips for batch frame-by-frame analysis with exportable annotated video output.

### 4. 🧪 Feature Simulator & What-If Explorer
- Interactive sliders for the 5 finger distance ratios to test decision boundaries without a camera.
- Continuous 10-servo angle estimation ($10^\circ$ to $170^\circ$).

### 5. 📊 ML Training Studio
- Inspect current `hand_dataset.npz` with 2D PCA cluster visualization and class balance charts.
- 1-Click Synthetic Biometric Generator (400 samples).
- Supervised SVM Training with hyperparameter tuning, Confusion Matrix heatmap, and direct model hot-reloading into `user_hand_model.pkl`.

### 6. 🤖 Arduino Hardware Bridge & Diagnostics
- **Dynamic Port Discovery & Priority Auto-Scanner**: Background daemon scanning for Arduino Uno/Mega (`0x2341`, `0x2A03`), CH340 (`0x1A86`), FTDI (`0x0403`), and CP2102 (`0x10C4`).
- **Non-Blocking Thread-Safe Queue**: Decouples 30 FPS camera inference from USB serial writes (`queue.Queue` with `threading.Lock`).
- **Automatic Reconnection & Virtual Simulation Mode**: If no Arduino is connected or if a board is unplugged mid-stream, the bridge switches to Virtual Simulation Mode automatically, allowing full testing without hardware.

### 7. 📽️ Page 7: Interactive Presentation Deck (`robotic_hand_ai_presentation.html`)
- **Master Presentation Deck Integration**: Full interactive 10-slide presentation deck embedded with 100% styling isolation.
- **10-Speaker Slide Stepper (S1 through S10)**: Dynamic transcripts and speech synthesis.
- **Three.js 3D Robotic Hand Digital Twin**: Resilient `ResizeObserver` responsive canvas with WebGL context restoration.
- **Audio Context Resilience**: Explicit user-gesture triggers bypass browser autoplay restrictions.
- **Direct Fullscreen Stage Mode**: Available at `http://127.0.0.1:7860/presentation`.

### 8. 📘 Wiring & Pinout Reference
- Arduino Uno/Nano PWM servo pinout (Pins 2–11).
- External 5V 5A power supply, common GND, and 470µF–1000µF capacitor wiring guidelines.

---

## 📁 File Structure

```text
PyCharmMiscProject/
├── .venv1/                                 # Python virtual environment (Gradio, MediaPipe, Scikit-Learn)
├── dashboard.py                            # Root launcher (dynamic port selection)
├── fg.py                                   # Quick launcher
├── README_DASHBOARD.md                     # Documentation
├── user_hand_model.pkl                     # Active trained SVM model
├── hand_dataset.npz                        # Biometric dataset
├── robotic_hand_ai_presentation.html       # Master Presentation Deck
└── robotic_hand_project1/
    ├── dashboard.py                        # Master Gradio Platform & FastAPI application
    ├── serial_bridge.py                    # Robust Thread-Safe Serial Bridge (Queue + Scanner + Sim)
    ├── hand_tracker_ai.py                  # OpenCV / MediaPipe camera tracker
    ├── mediator_brigde.py                  # CLI camera-to-Arduino bridge
    ├── train_user_hand.py                  # Keyboard data recorder & trainer
    ├── user_hand_model.pkl                 # Model copy
    ├── hand_dataset.npz                    # Dataset copy
    ├── robotic_hand_ai_presentation.html   # Presentation copy
    └── robot_hand_servos/
        └── robot_hand_servos.ino           # Arduino firmware (smooth eased 10-servo control)
```
