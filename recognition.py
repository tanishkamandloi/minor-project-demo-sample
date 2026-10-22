import argparse
import os
import smtplib
import sqlite3
import threading
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

import cv2
import face_recognition
import numpy as np

try:
    import winsound
except ImportError:
    winsound = None

from database import add_entry_log


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "data" / "campus_security.db"
ALERT_FOLDER = BASE_DIR / "unknown_alerts"
DEFAULT_TOLERANCE = 0.6
FRAME_SCALE = 0.25
ALERT_COOLDOWN_SECONDS = 30


def load_known_students(
    database_path: str | Path,
) -> tuple[list[np.ndarray], list[str]]:
    """Load valid face encodings and names from the SQLite database."""
    known_encodings = []
    known_names = []

    connection = sqlite3.connect(database_path)
    try:
        rows = connection.execute(
            "SELECT student_name, face_encoding FROM students"
        ).fetchall()
    finally:
        connection.close()

    for student_name, encoding_blob in rows:
        encoding = np.frombuffer(encoding_blob, dtype=np.float64)
        if encoding.shape != (128,):
            print(
                f"Skipping invalid face encoding for student "
                f"{student_name!r}."
            )
            continue
        known_names.append(student_name)
        known_encodings.append(encoding)

    return known_encodings, known_names


def identify_face(
    face_encoding: np.ndarray,
    known_encodings: list[np.ndarray],
    known_names: list[str],
    tolerance: float = DEFAULT_TOLERANCE,
) -> str:
    """Return the closest known name when it is within the tolerance."""
    if not known_encodings:
        return "Unknown"

    distances = face_recognition.face_distance(known_encodings, face_encoding)
    best_match_index = int(np.argmin(distances))
    if distances[best_match_index] <= tolerance:
        return known_names[best_match_index]
    return "Unknown"


def play_alarm() -> None:
    """Play a short local alarm on Windows."""
    if winsound is None:
        print("Alarm unavailable: this computer does not provide winsound.")
        return
    try:
        winsound.Beep(1200, 400)
        winsound.Beep(900, 400)
    except RuntimeError as error:
        print(f"Alarm could not be played: {error}")


def send_unknown_alert(
    photo_path: Path,
    timestamp: datetime,
) -> None:
    """Email an unknown-face photo to the configured administrator."""
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_username = os.environ.get("SMTP_USERNAME")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    admin_email = os.environ.get("ADMIN_EMAIL")

    missing = [
        name
        for name, value in (
            ("SMTP_HOST", smtp_host),
            ("SMTP_USERNAME", smtp_username),
            ("SMTP_PASSWORD", smtp_password),
            ("ADMIN_EMAIL", admin_email),
        )
        if not value
    ]
    if missing:
        print(
            "Email alert skipped; missing environment variable(s): "
            + ", ".join(missing)
        )
        return

    message = EmailMessage()
    message["Subject"] = f"Unknown face detected - {timestamp.isoformat()}"
    message["From"] = smtp_username
    message["To"] = admin_email
    message.set_content(
        "An unknown face was detected by the campus security system.\n\n"
        f"Timestamp: {timestamp.isoformat()}\n"
    )
    message.add_attachment(
        photo_path.read_bytes(),
        maintype="image",
        subtype="jpeg",
        filename=photo_path.name,
    )

    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as server:
            server.login(smtp_username, smtp_password)
            server.send_message(message)
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_username, smtp_password)
            server.send_message(message)

    print(f"Unknown-face email sent to {admin_email}.")


def alert_for_unknown(frame: np.ndarray, last_alert_time: float) -> float:
    """Save an unknown frame, sound the alarm, and email it in the background."""
    now = time.monotonic()
    if now - last_alert_time < ALERT_COOLDOWN_SECONDS:
        return last_alert_time

    timestamp = datetime.now().astimezone()
    ALERT_FOLDER.mkdir(parents=True, exist_ok=True)
    filename = timestamp.strftime("unknown_%Y%m%d_%H%M%S_%f.jpg")
    photo_path = ALERT_FOLDER / filename
    if not cv2.imwrite(str(photo_path), frame):
        print(f"Could not save unknown-face photo: {photo_path}")
        return last_alert_time

    play_alarm()

    def send_alert_email() -> None:
        try:
            send_unknown_alert(photo_path, timestamp)
        except (OSError, ValueError, smtplib.SMTPException) as error:
            print(f"Could not send unknown-face email alert: {error}")

    threading.Thread(target=send_alert_email, daemon=True).start()
    print(f"Unknown face captured at {timestamp.isoformat()}.")
    return now


def log_detected_names(
    database_path: str | Path,
    names: list[str],
) -> None:
    """Persist one entry event for each newly displayed face name."""
    for name in names:
        status = "Unknown" if name == "Unknown" else "Known"
        add_entry_log(database_path, name, status)


def recognize_frame(
    frame: np.ndarray,
    known_encodings: list[np.ndarray],
    known_names: list[str],
    tolerance: float = DEFAULT_TOLERANCE,
) -> tuple[list[tuple[int, int, int, int]], list[str]]:
    """Detect and identify faces in one BGR OpenCV frame."""
    small_frame = cv2.resize(frame, (0, 0), fx=FRAME_SCALE, fy=FRAME_SCALE)
    rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
    small_locations = face_recognition.face_locations(rgb_small_frame)
    face_encodings = face_recognition.face_encodings(
        rgb_small_frame, small_locations
    )

    locations = []
    names = []
    for location, face_encoding in zip(small_locations, face_encodings):
        top, right, bottom, left = location
        locations.append(
            (
                int(top / FRAME_SCALE),
                int(right / FRAME_SCALE),
                int(bottom / FRAME_SCALE),
                int(left / FRAME_SCALE),
            )
        )
        names.append(
            identify_face(
                face_encoding, known_encodings, known_names, tolerance
            )
        )

    return locations, names


def run_webcam(
    database_path: str | Path,
    camera_index: int = 0,
    tolerance: float = DEFAULT_TOLERANCE,
) -> None:
    """Open the webcam and display live face-recognition results."""
    known_encodings, known_names = load_known_students(database_path)
    print(f"Loaded {len(known_names)} registered student encoding(s).")

    camera = cv2.VideoCapture(camera_index)
    if not camera.isOpened():
        raise RuntimeError(
            f"Could not open webcam at camera index {camera_index}."
        )

    last_displayed_names = None
    last_alert_time = float("-inf")
    try:
        while True:
            success, frame = camera.read()
            if not success:
                raise RuntimeError("Could not read a frame from the webcam.")

            locations, names = recognize_frame(
                frame, known_encodings, known_names, tolerance
            )
            if names != last_displayed_names:
                for name in names:
                    print(name)
                log_detected_names(database_path, names)
                last_displayed_names = names
            if "Unknown" in names:
                last_alert_time = alert_for_unknown(frame, last_alert_time)

            for (top, right, bottom, left), name in zip(locations, names):
                color = (0, 180, 0) if name != "Unknown" else (0, 0, 255)
                cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
                cv2.rectangle(
                    frame,
                    (left, bottom - 35),
                    (right, bottom),
                    color,
                    cv2.FILLED,
                )
                cv2.putText(
                    frame,
                    name,
                    (left + 6, bottom - 8),
                    cv2.FONT_HERSHEY_DUPLEX,
                    0.7,
                    (255, 255, 255),
                    1,
                )

            cv2.imshow("Campus Security - Face Recognition", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        camera.release()
        cv2.destroyAllWindows()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recognize registered students using a webcam."
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        help="OpenCV camera index (default: 0)",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_TOLERANCE,
        help="Maximum face distance for a match (default: 0.6)",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DATABASE_PATH,
        help="Path to the SQLite database",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    run_webcam(arguments.database, arguments.camera, arguments.tolerance)
