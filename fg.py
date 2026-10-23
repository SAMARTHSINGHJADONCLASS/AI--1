"""
fg.py
Quick launcher for the Robotic Hand Machine Learning & Vision Dashboard.
Run via:
    python fg.py
"""

import os
import sys
import importlib.util

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.join(ROOT_DIR, "robotic_hand_project1")
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

module_path = os.path.join(PROJECT_DIR, "dashboard.py")
spec = importlib.util.spec_from_file_location("robotic_hand_dashboard", module_path)
rh_dash = importlib.util.module_from_spec(spec)
sys.modules["robotic_hand_dashboard"] = rh_dash
spec.loader.exec_module(rh_dash)

if __name__ == "__main__":
    rh_dash.main()
