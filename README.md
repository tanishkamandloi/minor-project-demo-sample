# Campus Security Face Recognition System

This is the initial Python project structure for a college campus security
system using face recognition.

## Project structure

```text
.
├── app.py
├── database.py
├── recognition.py
├── registration.py
├── requirements.txt
├── README.md
├── templates/
│   ├── dashboard.html
│   └── register.html
├── static/
│   └── style.css
├── data/
│   └── campus_security.db       # Created automatically at first startup
├── registered_photos/           # Registered student photos
└── unknown_alerts/              # Captured unknown-face alert photos
```

## Files and folders

- `app.py` creates the Flask application, configures paths, creates required
  folders, initializes the database, and exposes `/` and `/health` routes.
- `database.py` owns SQLite setup. The `students` table stores the student
  name, unique roll number, department, face encoding as a `BLOB`, the
  registered photo filename, and a creation timestamp.
- `registration.py` defines the `/register` page and registration workflow. It
  validates the form and image, requires exactly one detected face, computes
  the encoding with `face_recognition`, stores the encoding as a NumPy
  `float64` byte array in SQLite, and saves the photo in
  `registered_photos/`.
- `recognition.py` opens the OpenCV webcam, detects faces in each frame,
  compares them with the encodings in SQLite, and displays the matching
  student name or `Unknown`. For unknown faces, it saves a timestamped
  capture, plays a Windows alarm, and sends the capture to the configured
  administrator by email. Press `q` to close the webcam window.
- `templates/register.html` is the browser form for entering student details
  and uploading a photo.
- `requirements.txt` lists the third-party packages needed by the project.
  `smtplib` is part of Python's standard library, so it is not listed.
- `data/` stores the local SQLite database. The database file is generated
  automatically and should not be committed to source control.
- `entry_logs` records recognized and unknown face events for the dashboard.
- `registered_photos/` is the location for photos uploaded during student
  registration.

## Run locally

Create and activate a virtual environment, then install dependencies:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000/health` to verify the backend is running.

Open `http://127.0.0.1:5000/dashboard` to view the monitoring dashboard. It
polls the entry log every five seconds while `recognition.py` is running.

Open `http://127.0.0.1:5000/register` to register a student. The uploaded
photo must contain exactly one detectable face. Images larger than 10 MB and
unsupported file types are rejected.

After registering at least one student, start real-time recognition in a
separate terminal:

```powershell
python recognition.py
```

Use `--camera 1` if the default camera is not the desired webcam. The default
matching tolerance is `0.6`; a lower value makes matching stricter:

```powershell
python recognition.py --camera 0 --tolerance 0.55
```

## Unknown-face email alerts

Configure SMTP credentials in the shell before starting recognition. These
values are read from environment variables and are never stored in source
code:

```powershell
$env:SMTP_HOST = "smtp.example.com"
$env:SMTP_PORT = "587"
$env:SMTP_USERNAME = "security@example.com"
$env:SMTP_PASSWORD = "your-app-password"
$env:ADMIN_EMAIL = "admin@example.com"
py recognition.py
```

Port `587` uses STARTTLS; port `465` uses SMTP over SSL. The local alarm uses
Windows `winsound`, which is part of Python and requires no extra dependency.
Unknown-face alerts are rate-limited to one alert every 30 seconds to avoid
repeated emails while the same person remains in view.

Face encodings produced by `face_recognition.face_encodings()` are NumPy
arrays. Store them in SQLite with `encoding.tobytes()` and reconstruct them
with `numpy.frombuffer(..., dtype=numpy.float64)` when matching faces.
