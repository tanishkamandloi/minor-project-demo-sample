import sqlite3
from pathlib import Path
from uuid import uuid4

import numpy as np
from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from database import get_connection


registration_blueprint = Blueprint("registration", __name__)
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}


def allowed_file(filename: str) -> bool:
    """Return whether the filename has a supported image extension."""
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def save_student(
    student_name: str,
    roll_number: str,
    department: str,
    photo: FileStorage,
) -> None:
    """Encode one face, save the photo, and insert the student record."""
    import face_recognition

    original_filename = secure_filename(photo.filename or "")
    if not original_filename or not allowed_file(original_filename):
        raise ValueError("Upload a JPG, JPEG, or PNG image.")

    photo_folder = Path(current_app.config["PHOTO_FOLDER"])
    photo_filename = f"{uuid4().hex}_{original_filename}"
    photo_path = photo_folder / photo_filename
    saved_to_database = False
    try:
        photo.save(photo_path)
        image = face_recognition.load_image_file(photo_path)
        face_locations = face_recognition.face_locations(image)
        if len(face_locations) != 1:
            raise ValueError(
                "The photo must contain exactly one clearly visible face."
            )

        encodings = face_recognition.face_encodings(image, face_locations)
        if len(encodings) != 1:
            raise ValueError("Could not compute a face encoding for this photo.")

        encoding_blob = np.asarray(encodings[0], dtype=np.float64).tobytes()
        with get_connection(current_app.config["DATABASE_PATH"]) as connection:
            connection.execute(
                """
                INSERT INTO students
                    (student_name, roll_number, department, face_encoding,
                     photo_filename)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    student_name,
                    roll_number,
                    department,
                    encoding_blob,
                    photo_filename,
                ),
            )
        saved_to_database = True
    finally:
        if not saved_to_database and photo_path.exists():
            photo_path.unlink()


@registration_blueprint.route("/register", methods=["GET", "POST"])
def register_student():
    """Display the registration form and process new student registrations."""
    if request.method == "GET":
        return render_template("register.html")

    student_name = request.form.get("student_name", "").strip()
    roll_number = request.form.get("roll_number", "").strip()
    department = request.form.get("department", "").strip()
    photo = request.files.get("photo")

    if not all((student_name, roll_number, department)):
        flash("Name, roll number, and department are required.", "error")
        return redirect(url_for("registration.register_student"))
    if photo is None or not photo.filename:
        flash("Please select a student photo.", "error")
        return redirect(url_for("registration.register_student"))

    try:
        save_student(student_name, roll_number, department, photo)
    except ValueError as error:
        flash(str(error), "error")
    except sqlite3.IntegrityError as error:
        if "UNIQUE constraint failed: students.roll_number" in str(error):
            flash("That roll number is already registered.", "error")
        else:
            current_app.logger.exception("Student registration failed")
            flash("Registration failed while saving the student.", "error")
    except (OSError, RuntimeError):
        current_app.logger.exception("Student registration failed")
        flash("Registration failed while processing the photo.", "error")
    else:
        flash("Student registered successfully.", "success")
        return redirect(url_for("registration.register_student"))

    return redirect(url_for("registration.register_student"))


@registration_blueprint.app_errorhandler(RequestEntityTooLarge)
def handle_large_upload(error):
    del error
    flash("The photo is too large. Maximum upload size is 10 MB.", "error")
    return redirect(url_for("registration.register_student"))
