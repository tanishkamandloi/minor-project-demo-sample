import os
from pathlib import Path

from flask import Flask, jsonify, render_template, send_from_directory

from database import get_connection, init_db
from registration import registration_blueprint


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "data" / "campus_security.db"
PHOTO_FOLDER = BASE_DIR / "registered_photos"
ALERT_FOLDER = BASE_DIR / "unknown_alerts"


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get(
        "FLASK_SECRET_KEY", "development-only-change-this-secret"
    )
    app.config["DATABASE_PATH"] = str(DATABASE_PATH)
    app.config["PHOTO_FOLDER"] = str(PHOTO_FOLDER)
    app.config["ALERT_FOLDER"] = str(ALERT_FOLDER)
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PHOTO_FOLDER.mkdir(parents=True, exist_ok=True)
    ALERT_FOLDER.mkdir(parents=True, exist_ok=True)
    init_db(DATABASE_PATH)
    app.register_blueprint(registration_blueprint)

    @app.get("/dashboard")
    def dashboard():
        with get_connection(DATABASE_PATH) as connection:
            logs = connection.execute(
                """
                SELECT name, status, logged_at
                FROM entry_logs
                ORDER BY id DESC
                LIMIT 100
                """
            ).fetchall()
        alert_photos = sorted(
            (
                path
                for path in ALERT_FOLDER.iterdir()
                if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        return render_template("dashboard.html", logs=logs, alert_photos=alert_photos)

    @app.get("/api/entry-logs")
    def entry_logs():
        with get_connection(DATABASE_PATH) as connection:
            logs = connection.execute(
                """
                SELECT name, status, logged_at
                FROM entry_logs
                ORDER BY id DESC
                LIMIT 100
                """
            ).fetchall()
        return jsonify(
            [
                {
                    "name": row["name"],
                    "status": row["status"],
                    "time": row["logged_at"],
                }
                for row in logs
            ]
        )

    @app.get("/alerts/<path:filename>")
    def alert_photo(filename):
        return send_from_directory(ALERT_FOLDER, filename)

    @app.get("/")
    def index():
        return jsonify(
            {
                "message": "Campus security face recognition API",
                "status": "ready",
            }
        )

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
