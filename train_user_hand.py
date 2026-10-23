"""
train_user_hand.py
Records OPEN/CLOSED examples and trains user_hand_model.pkl.
"""

import argparse
import os
from collections import Counter
from typing import List, Optional, Tuple

import cv2
import joblib
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from hand_tracker_ai import FEATURE_NAMES, FEATURE_VERSION, HandTrackerAI, ResilientCamera

GESTURE_KEYS = {
    "o": "OPEN",
    "c": "CLOSED",
}

SAMPLES_PER_ROUND = 200
MIN_SAMPLES_PER_CLASS = 30
DATASET_PATH = "hand_dataset.npz"
MODEL_PATH = "user_hand_model.pkl"


def load_dataset() -> Tuple[List[List[float]], List[str]]:
    if not os.path.exists(DATASET_PATH):
        return [], []

    try:
        data = np.load(DATASET_PATH, allow_pickle=False)
        X, y = data["X"], data["y"]

        if X.ndim != 2 or X.shape[1] != len(FEATURE_NAMES):
            print("[TRAIN WARN] Dataset feature layout changed; starting empty.")
            return [], []

        return X.tolist(), [str(label) for label in y.tolist()]
    except Exception as err:
        print(f"[TRAIN ERROR] Dataset read failed: {err}")
        return [], []


def save_dataset(X: List[List[float]], y: List[str]) -> None:
    if not y:
        return

    try:
        np.savez(
            DATASET_PATH,
            X=np.asarray(X, dtype=np.float32),
            y=np.asarray(y),
        )
    except OSError as err:
        print(f"[TRAIN ERROR] Dataset save failed: {err}")


def train_and_save(X: List[List[float]], y: List[str]) -> bool:
    counts = Counter(y)
    print("[TRAIN] Samples:", dict(counts))

    if len(counts) < 2:
        print("[TRAIN ERROR] Record both OPEN and CLOSED first.")
        return False

    too_few = [label for label, n in counts.items() if n < MIN_SAMPLES_PER_CLASS]
    if too_few:
        print(f"[TRAIN ERROR] Need at least {MIN_SAMPLES_PER_CLASS}: {too_few}")
        return False

    X_arr = np.asarray(X, dtype=np.float32)
    y_arr = np.asarray(y)

    X_tr, X_te, y_tr, y_te = train_test_split(
        X_arr,
        y_arr,
        test_size=0.2,
        stratify=y_arr,
        random_state=42,
    )

    scaler_check = StandardScaler().fit(X_tr)
    clf_check = SVC(kernel="rbf", C=3.0, gamma="scale")
    clf_check.fit(scaler_check.transform(X_tr), y_tr)

    acc = clf_check.score(scaler_check.transform(X_te), y_te)
    print(f"[TRAIN] Hold-out accuracy: {acc * 100:.1f}%")

    scaler = StandardScaler().fit(X_arr)
    clf = SVC(kernel="rbf", C=3.0, gamma="scale")
    clf.fit(scaler.transform(X_arr), y_arr)

    try:
        joblib.dump(
            {
                "model": clf,
                "scaler": scaler,
                "labels": sorted(counts),
                "feature_names": FEATURE_NAMES,
                "feature_version": FEATURE_VERSION,
            },
            MODEL_PATH,
        )
    except OSError as err:
        print(f"[TRAIN ERROR] Model save failed: {err}")
        return False

    print(f"[TRAIN OK] Saved {MODEL_PATH}")
    return True


def draw_hud(
    frame,
    counts: Counter,
    rec_label: Optional[str],
    remaining: int,
    hand_seen: bool,
) -> None:
    cv2.putText(
        frame,
        "[O] OPEN  [C] CLOSED  [T] TRAIN  [Q] QUIT",
        (10, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (255, 255, 255),
        2,
    )

    cv2.putText(
        frame,
        "OPEN={} CLOSED={}".format(
            counts.get("OPEN", 0),
            counts.get("CLOSED", 0),
        ),
        (10, 58),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (255, 255, 0),
        2,
    )

    if rec_label:
        text = f"RECORDING {rec_label}: {remaining}"
        if not hand_seen:
            text += " - SHOW HAND"
        cv2.putText(
            frame,
            text,
            (10, 90),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--scan", action="store_true")
    args = parser.parse_args()

    tracker = HandTrackerAI(load_model=False)
    camera = ResilientCamera(args.camera, auto_index=args.scan)

    X, y = load_dataset()
    rec_label: Optional[str] = None
    remaining = 0

    print("[TRAIN] Camera ready.")
    print("[TRAIN] O=OPEN, C=CLOSED, T=TRAIN, Q=QUIT")

    try:
        while True:
            frame = camera.read()

            if frame is None:
                if cv2.waitKey(30) & 0xFF in (ord("q"), 27):
                    break
                continue

            frame = cv2.flip(frame, 1)
            frame, features = tracker.detect_features(frame)

            if rec_label and features is not None:
                X.append(features)
                y.append(rec_label)
                remaining -= 1

                if remaining <= 0:
                    print(
                        f"[TRAIN] Finished {rec_label}: "
                        f"{dict(Counter(y))}"
                    )
                    rec_label = None
                    save_dataset(X, y)

            draw_hud(
                frame,
                Counter(y),
                rec_label,
                remaining,
                features is not None,
            )

            cv2.imshow("Train Your Hand Model", frame)
            key = cv2.waitKey(1) & 0xFF

            if key in (ord("q"), 27):
                break

            if key == ord("o"):
                rec_label = "OPEN"
                remaining = SAMPLES_PER_ROUND
                print("[TRAIN] Recording OPEN...")

            elif key == ord("c"):
                rec_label = "CLOSED"
                remaining = SAMPLES_PER_ROUND
                print("[TRAIN] Recording CLOSED...")

            elif key == ord("t"):
                rec_label = None
                save_dataset(X, y)
                train_and_save(X, y)

    finally:
        save_dataset(X, y)
        camera.release()
        cv2.destroyAllWindows()
        tracker.close()


if __name__ == "__main__":
    main()
