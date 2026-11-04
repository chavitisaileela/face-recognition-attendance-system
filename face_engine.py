"""
Face Detection and Recognition Engine using OpenCV (Haar Cascades + LBPH).
Performance-optimized: separate camera thread, frame skipping, multi-frame confirmation,
in-memory face cache, single model load, and proper camera lifecycle management.

Modes:
  'test'       – Recognition testing without marking attendance.
  'attendance' – Recognition with automatic attendance recording.
"""

import os
import cv2
import time
import base64
import logging
import threading
import queue
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime

import database
import sheet_sync

logger = logging.getLogger("face_engine")

BASE_DIR = os.path.dirname(__file__)
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
MODELS_DIR = os.path.join(BASE_DIR, "models")
MODEL_FILE = os.path.join(MODELS_DIR, "trainer.yml")
LOCAL_CASCADE = os.path.join(MODELS_DIR, "haarcascade_frontalface_default.xml")

if os.path.exists(LOCAL_CASCADE):
    CASCADE_PATH = LOCAL_CASCADE
elif hasattr(cv2, "data") and hasattr(cv2.data, "haarcascades") and os.path.exists(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"):
    CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
else:
    CASCADE_PATH = LOCAL_CASCADE

# Multi-frame confirmation: number of consecutive frames a student must be
# recognized before attendance is actually marked.
CONFIRM_FRAMES_REQUIRED = 3
# Interval between recognition predictions (skip this many frames between predictions)
RECOGNITION_EVERY_N_FRAMES = 4
# Cooldown after marking attendance so we don't re-alert for same student
ATTENDANCE_COOLDOWN_SECONDS = 10.0


class FaceEngine:
    def __init__(self):
        self.lock = threading.Lock()

        # Initialize cascade and LBPH recognizer once
        self.face_cascade = cv2.CascadeClassifier(CASCADE_PATH)
        self.recognizer = cv2.face.LBPHFaceRecognizer_create(
            radius=1, neighbors=8, grid_x=8, grid_y=8
        )
        self.is_trained = False

        # CLAHE instance – created once, not per-frame
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

        # In-memory student id → student dict cache (loaded once per session start)
        self._student_cache: Dict[int, Dict[str, Any]] = {}

        # Debounce: {prn: timestamp_last_marked}
        self.attendance_cooldown: Dict[str, float] = {}

        # Multi-frame confirmation buffer: {prn: consecutive_frame_count}
        self._confirm_buffer: Dict[str, int] = {}

        # Cooldown for unknown face voice alerts
        self._last_unknown_event_time: float = 0.0

        # Recent events ring-buffer for UI
        self.recent_events: List[Dict[str, Any]] = []

        # Stream / session control
        self.stream_mode: str = "attendance"   # 'attendance' or 'test'
        self._stream_active: bool = False       # True while MJPEG stream is running
        self._cap: Optional[cv2.VideoCapture] = None
        self._stream_lock = threading.Lock()

        # Frame counter for frame-skipping
        self._frame_counter: int = 0

        # Load existing model if available
        self.load_model()

    # ------------------------------------------------------------------
    # Student cache management
    # ------------------------------------------------------------------

    def _load_student_cache(self):
        """Load all students into memory once so we don't query DB per frame."""
        students = database.get_all_students()
        self._student_cache = {s["id"]: dict(s) for s in students}
        logger.info("Loaded %d students into face engine cache.", len(self._student_cache))

    def get_student_from_cache(self, student_id: int) -> Optional[Dict[str, Any]]:
        if not self._student_cache:
            self._load_student_cache()
        return self._student_cache.get(student_id)

    def reload_cache(self):
        """Force reload cache (call after training or DB changes)."""
        self._student_cache = {}
        self._load_student_cache()

    # ------------------------------------------------------------------
    # Threshold helper
    # ------------------------------------------------------------------

    def get_threshold(self) -> float:
        try:
            val = float(database.get_setting("confidence_threshold", "72"))
            return val
        except (ValueError, TypeError):
            return 72.0

    # ------------------------------------------------------------------
    # Model load / train
    # ------------------------------------------------------------------

    def load_model(self) -> bool:
        """Load trained LBPH model from disk (runs once at startup)."""
        with self.lock:
            if os.path.exists(MODEL_FILE):
                try:
                    self.recognizer.read(MODEL_FILE)
                    self.is_trained = True
                    self._load_student_cache()
                    logger.info("LBPH model loaded from %s", MODEL_FILE)
                    return True
                except Exception as e:
                    logger.error("Failed to read model: %s", e)
                    self.is_trained = False
            else:
                self.is_trained = False
            return False

    def train_model(self) -> Tuple[bool, str, int]:
        """Train LBPH on all student images in dataset/. Reloads cache afterwards."""
        with self.lock:
            os.makedirs(DATASET_DIR, exist_ok=True)
            os.makedirs(MODELS_DIR, exist_ok=True)

            students = {s["prn"].upper(): s["id"] for s in database.get_all_students()}
            if not students:
                return False, "No students registered in database.", 0

            faces, labels = [], []
            total_samples = 0
            trained_prns = set()
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

            for prn_folder in os.listdir(DATASET_DIR):
                folder_path = os.path.join(DATASET_DIR, prn_folder)
                if not os.path.isdir(folder_path):
                    continue
                prn_key = prn_folder.strip().upper()
                if prn_key not in students:
                    logger.warning("Folder %s has no PDF student match. Skipping.", prn_folder)
                    continue
                student_id = students[prn_key]
                student_samples = 0

                for img_name in os.listdir(folder_path):
                    if not img_name.lower().endswith((".jpg", ".jpeg", ".png")):
                        continue
                    img_path = os.path.join(folder_path, img_name)
                    try:
                        gray_img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
                        if gray_img is None:
                            continue
                        detected = self.face_cascade.detectMultiScale(
                            gray_img, scaleFactor=1.1, minNeighbors=4, minSize=(50, 50)
                        )
                        face_roi = gray_img[detected[0][1]:detected[0][1] + detected[0][3],
                                            detected[0][0]:detected[0][0] + detected[0][2]] if len(detected) > 0 else gray_img
                        face_resized = cv2.resize(face_roi, (200, 200))
                        faces.append(clahe.apply(face_resized))
                        labels.append(student_id)
                        total_samples += 1
                        student_samples += 1
                    except Exception as e:
                        logger.warning("Error processing %s: %s", img_path, e)

                if student_samples > 0:
                    trained_prns.add(prn_key)
                    database.update_student_face_status(prn_key, "Training Completed", count=student_samples)

            if not faces:
                self.is_trained = False
                return False, "No face samples found. Please capture photos first.", 0

            try:
                self.recognizer = cv2.face.LBPHFaceRecognizer_create(
                    radius=1, neighbors=8, grid_x=8, grid_y=8
                )
                self.recognizer.train(faces, np.array(labels, dtype=np.int32))
                self.recognizer.write(MODEL_FILE)
                self.is_trained = True
                msg = f"Trained {total_samples} samples across {len(trained_prns)} students."
                logger.info(msg)
            except Exception as e:
                self.is_trained = False
                return False, f"Training error: {e}", 0

        # Reload student cache outside the lock
        self.reload_cache()
        self._confirm_buffer.clear()
        return True, msg, total_samples

    # ------------------------------------------------------------------
    # Face sample capture
    # ------------------------------------------------------------------

    def add_face_samples(self, prn: str, image_bytes_list: List[bytes]) -> int:
        prn_dir = os.path.join(DATASET_DIR, prn.strip().upper())
        os.makedirs(prn_dir, exist_ok=True)
        saved_count = 0
        existing_count = len(os.listdir(prn_dir))

        for idx, img_bytes in enumerate(image_bytes_list):
            try:
                nparr = np.frombuffer(img_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is None:
                    continue
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                faces = self.face_cascade.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=4, minSize=(60, 60)
                )
                if len(faces) == 0:
                    face_roi = gray
                else:
                    x, y, w, h = faces[0]
                    pad = int(0.12 * w)
                    y1, y2 = max(0, y - pad), min(gray.shape[0], y + h + pad)
                    x1, x2 = max(0, x - pad), min(gray.shape[1], x + w + pad)
                    face_roi = gray[y1:y2, x1:x2]
                face_resized = cv2.resize(face_roi, (200, 200))
                fname = f"sample_{existing_count + saved_count + 1}_{int(time.time() * 1000)}.jpg"
                cv2.imwrite(os.path.join(prn_dir, fname), face_resized)
                saved_count += 1
            except Exception as e:
                logger.warning("Failed to save face sample: %s", e)

        total_now = len(os.listdir(prn_dir))
        database.update_student_face_status(prn, "Photos Captured", count=total_now)
        return saved_count

    # ------------------------------------------------------------------
    # Core frame processing
    # ------------------------------------------------------------------

    def process_frame(
        self,
        frame: np.ndarray,
        active_subject: str,
        mode: str = "attendance",
        session_id: Optional[str] = None,
        faculty_name: Optional[str] = None,
        force_recognize: bool = True
    ) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
        """
        Detect and recognize faces in a single frame.

        force_recognize=False enables frame-skip logic (used by MJPEG stream).
        force_recognize=True always runs recognition (used by browser /api/process_frame).
        """
        detections = []
        if frame is None or frame.size == 0:
            return frame, detections

        # Resize for faster processing if frame is large
        h, w = frame.shape[:2]
        scale = 1.0
        if w > 640:
            scale = 640 / w
            frame = cv2.resize(frame, (640, int(h * scale)))

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Always detect faces (cheap), but skip recognition on some frames
        detected_faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.15,
            minNeighbors=5,
            minSize=(60, 60),
            flags=cv2.CASCADE_SCALE_IMAGE
        )

        # Should we run recognition this frame?
        self._frame_counter += 1
        run_recognition = force_recognize or (self._frame_counter % RECOGNITION_EVERY_N_FRAMES == 0)

        threshold = self.get_threshold()
        current_time = time.time()
        now_dt = datetime.now()
        date_str = now_dt.strftime("%Y-%m-%d")
        time_str = now_dt.strftime("%H:%M:%S")

        # Track which PRNs are visible this frame (for confirm buffer cleanup)
        visible_prns = set()

        for (x, y, fw, fh) in detected_faces:
            detection_info = {
                "box": [int(x), int(y), int(fw), int(fh)],
                "recognized": False,
                "name": "Unknown",
                "prn": "N/A",
                "section": "N/A",
                "confidence": 0,
                "status": "Unknown Face",
                "attendance_action": "None",
                "mode": mode
            }

            if self.is_trained and run_recognition:
                try:
                    face_roi = gray[y:y + fh, x:x + fw]
                    face_resized = cv2.resize(face_roi, (200, 200))
                    face_eq = self.clahe.apply(face_resized)

                    with self.lock:
                        label_id, distance = self.recognizer.predict(face_eq)

                    confidence_pct = max(5, min(99, int(100 - (distance * 0.7))))

                    if distance <= threshold:
                        student = self.get_student_from_cache(label_id)
                        if student:
                            prn = student["prn"]
                            name = student["name"]
                            sec = student["section"]
                            visible_prns.add(prn)

                            detection_info["recognized"] = True
                            detection_info["name"] = name
                            detection_info["prn"] = prn
                            detection_info["section"] = sec
                            detection_info["confidence"] = confidence_pct

                            if mode == "test":
                                detection_info["attendance_action"] = "Testing Only"
                                detection_info["status"] = f"Recognized – {confidence_pct}% (Test)"
                            else:
                                # Multi-frame confirmation
                                self._confirm_buffer[prn] = self._confirm_buffer.get(prn, 0) + 1
                                confirmed = self._confirm_buffer[prn] >= CONFIRM_FRAMES_REQUIRED

                                last_marked = self.attendance_cooldown.get(prn, 0)
                                already_cooled = (current_time - last_marked) > ATTENDANCE_COOLDOWN_SECONDS

                                if confirmed and already_cooled:
                                    res = database.mark_attendance(
                                        prn, active_subject, date_str, time_str,
                                        session_id=session_id, faculty_name=faculty_name
                                    )
                                    self.attendance_cooldown[prn] = current_time
                                    self._confirm_buffer[prn] = 0  # Reset buffer

                                    if res["status"] == "success":
                                        detection_info["attendance_action"] = "Marked PRESENT"
                                        detection_info["status"] = "✔ Marked PRESENT"
                                        sheet_sync.sync_attendance_record(res["record"])
                                        self._push_event({
                                            "name": name, "prn": prn, "section": sec,
                                            "date": date_str, "time": time_str,
                                            "subject": active_subject, "status": "PRESENT",
                                            "action": "new_attendance", "timestamp": time_str,
                                            "confidence": confidence_pct
                                        })
                                    elif res["status"] == "already_marked":
                                        detection_info["attendance_action"] = "Already Marked"
                                        detection_info["status"] = "Already PRESENT"
                                        self._push_event({
                                            "name": name, "prn": prn, "section": sec,
                                            "date": date_str, "time": time_str,
                                            "subject": active_subject, "status": "PRESENT",
                                            "action": "already_marked", "timestamp": time_str
                                        })
                                else:
                                    # Waiting for confirmation frames
                                    frames_left = max(0, CONFIRM_FRAMES_REQUIRED - self._confirm_buffer.get(prn, 0))
                                    detection_info["attendance_action"] = "Confirming..."
                                    detection_info["status"] = f"Hold still... ({frames_left} frames)"
                    else:
                        detection_info["confidence"] = confidence_pct
                        detection_info["status"] = "Unknown Face"
                        if mode == "attendance" and (current_time - self._last_unknown_event_time) > 6.0:
                            self._last_unknown_event_time = current_time
                            self._push_event({
                                "name": "Unknown",
                                "prn": "UNKNOWN",
                                "section": "N/A",
                                "date": date_str,
                                "time": time_str,
                                "subject": active_subject,
                                "status": "ABSENT",
                                "action": "unknown_face",
                                "timestamp": time_str,
                                "confidence": confidence_pct
                            })
                except Exception as e:
                    logger.warning("Face prediction error: %s", e)
                    detection_info["status"] = "Error"
            elif not self.is_trained:
                detection_info["name"] = "Model Not Trained"
                detection_info["status"] = "Train face data first"

            detections.append(detection_info)
            self._draw_hud(frame, x, y, fw, fh, detection_info)

        # Decay confirm buffer for students not visible this frame
        for prn in list(self._confirm_buffer.keys()):
            if prn not in visible_prns:
                self._confirm_buffer[prn] = max(0, self._confirm_buffer[prn] - 1)

        self._draw_top_bar(frame, active_subject, time_str, len(detected_faces), mode)
        return frame, detections

    # ------------------------------------------------------------------
    # HUD drawing
    # ------------------------------------------------------------------

    def _draw_hud(self, frame: np.ndarray, x: int, y: int, w: int, h: int, info: Dict[str, Any]):
        if info["recognized"]:
            box_color = (16, 185, 129)
            main_label = f"{info['name']} ({info['prn']}) Sec {info.get('section', 'B')}"
            sub_label = f"{info['status']} | {info['confidence']}% match"
        else:
            box_color = (37, 99, 235)
            main_label = "Unknown Face"
            sub_label = "Unregistered – Attendance Ignored"

        corner_len = int(min(w, h) * 0.22)
        cv2.rectangle(frame, (x, y), (x + w, y + h), box_color, 1, cv2.LINE_AA)
        for (x1, y1), (x2, y2) in [
            ((x, y), (x + corner_len, y)), ((x, y), (x, y + corner_len)),
            ((x + w, y), (x + w - corner_len, y)), ((x + w, y), (x + w, y + corner_len)),
            ((x, y + h), (x + corner_len, y + h)), ((x, y + h), (x, y + h - corner_len)),
            ((x + w, y + h), (x + w - corner_len, y + h)), ((x + w, y + h), (x + w, y + h - corner_len)),
        ]:
            cv2.line(frame, (x1, y1), (x2, y2), box_color, 2)

        label_h = 42
        label_y1 = max(0, y - label_h)
        tag_w = max(w, 280)
        cv2.rectangle(frame, (x, label_y1), (x + tag_w, y), (15, 23, 42), -1)
        cv2.rectangle(frame, (x, label_y1), (x + tag_w, y), box_color, 1)
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(frame, main_label, (x + 8, label_y1 + 18), font, 0.48, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(frame, sub_label, (x + 8, label_y1 + 34), font, 0.40,
                    (52, 211, 153) if info["recognized"] else (148, 163, 184), 1, cv2.LINE_AA)

    def _draw_top_bar(self, frame: np.ndarray, subject: str, time_str: str, faces_count: int, mode: str):
        fw = frame.shape[1]
        cv2.rectangle(frame, (0, 0), (fw, 32), (15, 23, 42), -1)
        cv2.line(frame, (0, 32), (fw, 32), (51, 65, 85), 1)
        font = cv2.FONT_HERSHEY_SIMPLEX
        if mode == "test":
            cv2.circle(frame, (16, 16), 5, (245, 158, 11), -1)
            cv2.putText(frame, "TESTING (NO ATTENDANCE)", (28, 20), font, 0.44, (253, 230, 138), 1, cv2.LINE_AA)
        else:
            cv2.circle(frame, (16, 16), 5, (16, 185, 129), -1)
            cv2.putText(frame, "LIVE ATTENDANCE ACTIVE", (28, 20), font, 0.44, (241, 245, 249), 1, cv2.LINE_AA)
        cv2.putText(frame, f"Subject: {subject[:30]}", (250, 20), font, 0.42, (147, 197, 253), 1, cv2.LINE_AA)
        info_text = f"Faces: {faces_count} | {time_str}"
        (tw, _), _ = cv2.getTextSize(info_text, font, 0.42, 1)
        cv2.putText(frame, info_text, (fw - tw - 16, 20), font, 0.42, (203, 213, 225), 1, cv2.LINE_AA)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _push_event(self, event: Dict[str, Any]):
        self.recent_events.append(event)
        if len(self.recent_events) > 20:
            self.recent_events.pop(0)

    def get_recent_events(self) -> List[Dict[str, Any]]:
        return list(reversed(self.recent_events[-10:]))

    # ------------------------------------------------------------------
    # MJPEG hardware camera stream (with frame skipping)
    # ------------------------------------------------------------------

    def start_stream(self, camera_index: int = 0, mode: str = "attendance"):
        """Start the hardware camera stream in the current thread (generator)."""
        with self._stream_lock:
            if self._stream_active:
                logger.warning("Stream already active – stopping previous.")
                self._stop_camera()

        cap = None
        try:
            with self._stream_lock:
                self._stream_active = True

            cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap = cv2.VideoCapture(camera_index)

            if not cap.isOpened():
                logger.warning("Hardware webcam %d unavailable. Generating placeholder.", camera_index)
                while self._stream_active:
                    placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
                    cv2.putText(placeholder, "Camera Unavailable – Use Browser Webcam", (60, 220),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
                    cv2.putText(placeholder, "Click 'Browser Webcam' button above", (110, 255),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.50, (147, 197, 253), 1, cv2.LINE_AA)
                    _, buf = cv2.imencode(".jpg", placeholder)
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
                    time.sleep(0.5)
                return

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)

            with self._stream_lock:
                self._cap = cap

            local_frame_count = 0

            while self._stream_active:
                success, frame = cap.read()
                if not success:
                    time.sleep(0.05)
                    continue

                local_frame_count += 1

                # Read session info from DB only every 30 frames (not every frame)
                if local_frame_count % 30 == 1:
                    active_subject = database.get_setting("active_subject", "Fundamentals of Computing")
                    session_id = database.get_setting("active_session_id", "")
                    faculty_name = database.get_setting("active_faculty_name", "")

                run_recog = (local_frame_count % RECOGNITION_EVERY_N_FRAMES == 0)
                annotated_frame, _ = self.process_frame(
                    frame, active_subject, mode=mode, session_id=session_id,
                    faculty_name=faculty_name or None,
                    force_recognize=run_recog
                )

                ret, jpeg = cv2.imencode(".jpg", annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if not ret:
                    continue

                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
                time.sleep(0.033)  # ~30 fps max

        except GeneratorExit:
            pass
        except Exception as e:
            logger.error("Video stream error: %s", e)
        finally:
            with self._stream_lock:
                self._stream_active = False
                if cap and cap.isOpened():
                    cap.release()
                self._cap = None
            logger.info("Camera stream stopped and released.")

    def stop_stream(self):
        """Signal the running stream generator to stop."""
        with self._stream_lock:
            self._stream_active = False
            if self._cap and self._cap.isOpened():
                self._cap.release()
                self._cap = None
        logger.info("Stream stop requested.")

    def _stop_camera(self):
        """Internal helper – must be called while holding _stream_lock or before acquiring."""
        self._stream_active = False
        if self._cap and self._cap.isOpened():
            self._cap.release()
            self._cap = None

    # Backward-compat alias used by old main.py (kept so import doesn't break)
    def get_video_stream(self, camera_index: int = 0, mode: str = "attendance"):
        return self.start_stream(camera_index, mode)

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def reset_session(self):
        """Clear confirm buffer and cooldown when a new attendance session starts."""
        self._confirm_buffer.clear()
        self.attendance_cooldown.clear()
        logger.info("Session reset: confirmation buffer and cooldown cleared.")


# Global singleton
engine = FaceEngine()
