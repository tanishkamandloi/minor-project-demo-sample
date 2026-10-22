import sqlite3
from pathlib import Path


CREATE_STUDENTS_TABLE = """
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_name TEXT NOT NULL,
    roll_number TEXT NOT NULL UNIQUE,
    department TEXT NOT NULL,
    face_encoding BLOB NOT NULL,
    photo_filename TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_ENTRY_LOGS_TABLE = """
CREATE TABLE IF NOT EXISTS entry_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('Known', 'Unknown')),
    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def get_connection(database_path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection and return rows that support column access."""
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(database_path: str | Path) -> None:
    """Create the database and students table if they do not exist."""
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection(database_path) as connection:
        connection.execute(CREATE_STUDENTS_TABLE)
        connection.execute(CREATE_ENTRY_LOGS_TABLE)


def add_entry_log(
    database_path: str | Path,
    name: str,
    status: str,
) -> None:
    """Record a recognized or unknown face event."""
    with get_connection(database_path) as connection:
        connection.execute(
            "INSERT INTO entry_logs (name, status) VALUES (?, ?)",
            (name, status),
        )
