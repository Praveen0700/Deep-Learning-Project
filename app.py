import os
import csv
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory, session
from PIL import Image, UnidentifiedImageError
from werkzeug.security import check_password_hash, generate_password_hash
from train import CLASS_NAMES, load_classifier, load_threshold, load_training_metrics, load_validation_accuracy, predict_image


ROOT = Path(__file__).resolve().parent
UPLOAD_DIR = ROOT / "uploads"
DATABASE = ROOT / "banana_tree.sqlite3"
PREDICTION_OUTPUT = ROOT / "prediction_results.csv"
OUTPUT_COLUMNS = ("analysis_id", "user_id", "created_at", "original_filename", "predicted_class", "score_pct")
CLASS_DETAILS = {
    "fusarium_wilt": ("Fusarium wilt", "Disease", "A fungal disease that can cause yellowing and wilting."),
    "healthy": ("Healthy leaf", "Healthy", "No disease is indicated by this dataset class."),
    "natural_death_leaf": ("Natural leaf aging", "Natural", "Leaf senescence can resemble disease; inspect the whole plant."),
    "rhizome_root": ("Rhizome / root", "Not a leaf", "This class contains root or rhizome images rather than leaf images."),
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
_output_file_lock = threading.Lock()

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "local-development-key-change-before-deploying"),
    MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
UPLOAD_DIR.mkdir(exist_ok=True)

_model = load_classifier()
_confidence_threshold = load_threshold()
_validation_accuracy = load_validation_accuracy()
_training_metrics = load_training_metrics()


def classifier_metrics():
    return {
        "classifier_ready": _model is not None and _confidence_threshold is not None,
        "validation_accuracy": _validation_accuracy,
        "confidence_threshold": _confidence_threshold,
    }


def database_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def sync_prediction_output():
    temporary_path = PREDICTION_OUTPUT.with_name("prediction_results.csv.tmp")
    with _output_file_lock:
        with database_connection() as connection:
            rows = connection.execute(
                "SELECT id, user_id, created_at, original_name, label, score "
                "FROM analyses ORDER BY id"
            ).fetchall()
        with temporary_path.open("w", newline="", encoding="utf-8") as output_file:
            writer = csv.writer(output_file)
            writer.writerow(OUTPUT_COLUMNS)
            writer.writerows(
                (row["id"], row["user_id"], row["created_at"], row["original_name"], row["label"], row["score"])
                for row in rows
            )
        temporary_path.replace(PREDICTION_OUTPUT)


def initialize_database():
    with database_connection() as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS users ("
            "id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, "
            "password_hash TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS analyses ("
            "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, filename TEXT NOT NULL, "
            "original_name TEXT NOT NULL, label TEXT NOT NULL, score REAL NOT NULL, "
            "created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id))"
        )
        demo = connection.execute("SELECT id FROM users WHERE email = ?", ("demo@bananatree.local",)).fetchone()
        if demo is None:
            connection.execute(
                "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                ("demo@bananatree.local", generate_password_hash("banana123"), datetime.now(timezone.utc).isoformat()),
            )


initialize_database()
sync_prediction_output()


def login_required(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify(error="Please sign in to continue."), 401
        return handler(*args, **kwargs)

    return wrapped


def display_name(class_name):
    return CLASS_DETAILS[class_name][0]


def analyze_image(image):
    if _model is None or _confidence_threshold is None:
        raise RuntimeError("The classifier is not trained yet. Run python train.py before analyzing images.")
    return predict_image(image, _model)


def dataset_counts():
    counts = {}
    for class_name in CLASS_NAMES:
        folder = ROOT / class_name
        counts[class_name] = sum(1 for path in folder.glob("*.jpg") if re.fullmatch(r"\d+", path.stem))
    return counts


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify(status="ok", service="banana-tree", **classifier_metrics())


@app.get("/api/session")
def session_info():
    if not session.get("user_id"):
        return jsonify(authenticated=False)
    return jsonify(authenticated=True, email=session.get("email"))


@app.post("/api/register")
def register():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        return jsonify(error="Enter a valid email address."), 400
    if len(password) < 8:
        return jsonify(error="Use a password with at least 8 characters."), 400
    try:
        with database_connection() as connection:
            cursor = connection.execute(
                "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                (email, generate_password_hash(password), datetime.now(timezone.utc).isoformat()),
            )
            session["user_id"] = cursor.lastrowid
            session["email"] = email
    except sqlite3.IntegrityError:
        return jsonify(error="An account with that email already exists."), 409
    return jsonify(authenticated=True, email=email), 201


@app.post("/api/login")
def login():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    with database_connection() as connection:
        user = connection.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if user is None or not check_password_hash(user["password_hash"], password):
        return jsonify(error="Email or password is incorrect."), 401
    session.clear()
    session["user_id"] = user["id"]
    session["email"] = user["email"]
    return jsonify(authenticated=True, email=user["email"])


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(authenticated=False)


@app.get("/api/classes")
def classes():
    counts = dataset_counts()
    return jsonify(
        classes=[
            {
                "name": class_name,
                "title": CLASS_DETAILS[class_name][0],
                "type": CLASS_DETAILS[class_name][1],
                "description": CLASS_DETAILS[class_name][2],
                "count": counts[class_name],
                "image_url": f"/dataset/{class_name}/1.jpg",
            }
            for class_name in CLASS_NAMES
        ],
        total=sum(counts.values()),
        **classifier_metrics(),
    )


@app.get("/api/dashboard")
@login_required
def dashboard():
    user_id = session["user_id"]
    with database_connection() as connection:
        totals = connection.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN label != 'healthy' THEN 1 ELSE 0 END) AS flagged "
            "FROM analyses WHERE user_id = ?", (user_id,)
        ).fetchone()
        latest = connection.execute(
            "SELECT label, created_at FROM analyses WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)
        ).fetchone()
    return jsonify(
        scans=totals["total"] or 0,
        flagged=totals["flagged"] or 0,
        classes=len(CLASS_NAMES),
        latest=display_name(latest["label"]) if latest else None,
        dataset_images=sum(dataset_counts().values()),
        **classifier_metrics(),
    )


@app.get("/api/history")
@login_required
def history():
    with database_connection() as connection:
        rows = connection.execute(
            "SELECT id, filename, original_name, label, score, created_at FROM analyses "
            "WHERE user_id = ? ORDER BY id DESC LIMIT 100", (session["user_id"],)
        ).fetchall()
    return jsonify(
        history=[
            {
                "id": row["id"], "name": row["original_name"], "label": row["label"],
                "title": display_name(row["label"]), "type": CLASS_DETAILS[row["label"]][1],
                "score": row["score"], "created_at": row["created_at"],
                "image_url": f"/uploads/{row['filename']}",
            }
            for row in rows
        ]
    )


@app.get("/api/analytics")
@login_required
def analytics():
    user_id = session["user_id"]
    today = datetime.now(timezone.utc).date()
    first_day = today - timedelta(days=13)
    with database_connection() as connection:
        total_row = connection.execute(
            "SELECT COUNT(*) AS total FROM analyses WHERE user_id = ?", (user_id,)
        ).fetchone()
        class_rows = connection.execute(
            "SELECT label, COUNT(*) AS count FROM analyses WHERE user_id = ? GROUP BY label",
            (user_id,),
        ).fetchall()
        daily_rows = connection.execute(
            "SELECT date(created_at) AS scan_date, COUNT(*) AS count FROM analyses "
            "WHERE user_id = ? AND date(created_at) >= ? GROUP BY date(created_at)",
            (user_id, first_day.isoformat()),
        ).fetchall()

    counts_by_class = {row["label"]: row["count"] for row in class_rows}
    counts_by_day = {row["scan_date"]: row["count"] for row in daily_rows}
    days = [first_day + timedelta(days=offset) for offset in range(14)]
    return jsonify(
        validation_metrics=_training_metrics,
        prediction_distribution=[
            {
                "name": class_name,
                "title": CLASS_DETAILS[class_name][0],
                "count": counts_by_class.get(class_name, 0),
            }
            for class_name in CLASS_NAMES
        ],
        history={
            "total": total_row["total"],
            "daily_scans": [
                {"date": day.isoformat(), "count": counts_by_day.get(day.isoformat(), 0)} for day in days
            ],
            "labeled_ground_truth_available": False,
        },
    )


@app.post("/api/predict")
@login_required
def predict():
    uploaded = request.files.get("image")
    if uploaded is None or not uploaded.filename:
        return jsonify(error="Choose an image to analyze."), 400
    if Path(uploaded.filename).suffix.lower() not in IMAGE_EXTENSIONS:
        return jsonify(error="Use a JPG, PNG, WebP, or BMP image."), 400
    try:
        uploaded.stream.seek(0, os.SEEK_END)
        size = uploaded.stream.tell()
        uploaded.stream.seek(0)
        if size > MAX_UPLOAD_BYTES:
            return jsonify(error="Image must be smaller than 12 MB."), 413
        with Image.open(uploaded.stream) as image:
            image.verify()
        uploaded.stream.seek(0)
        with Image.open(uploaded.stream) as image:
            image = image.convert("RGB")
            label, score = analyze_image(image)
            stored_filename = f"{uuid.uuid4().hex}.jpg"
            image.save(UPLOAD_DIR / stored_filename, format="JPEG", quality=90, optimize=True)
    except (UnidentifiedImageError, OSError, ValueError):
        return jsonify(error="That file could not be read as an image."), 400
    except RuntimeError as error:
        return jsonify(error=str(error)), 503

    original_name = Path(uploaded.filename).name[:180]
    created_at = datetime.now(timezone.utc).isoformat()
    with database_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO analyses (user_id, filename, original_name, label, score, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session["user_id"], stored_filename, original_name, label, score, created_at),
        )
        analysis_id = cursor.lastrowid
    sync_prediction_output()
    title, kind, description = CLASS_DETAILS[label]
    accepted = score >= _confidence_threshold
    review_note = (
        "The score clears the validation-derived cutoff."
        if accepted
        else "The score is below the cutoff; review this image manually."
    )
    return jsonify(
        id=analysis_id,
        label=label,
        title=title,
        type=kind,
        description=description,
        score=score,
        accepted=accepted,
        confidence_threshold=_confidence_threshold,
        validation_accuracy=_validation_accuracy,
        image_url=f"/uploads/{stored_filename}",
        created_at=created_at,
        note=(
            f"{review_note} Confidence cutoff: {_confidence_threshold:.1f}%. "
            f"Validation accuracy: {_validation_accuracy:.1f}% on a held-out split. "
            "The model score is not a disease probability or a guarantee. Confirm concerning symptoms "
            "with an agricultural specialist."
        ),
    ), 201


@app.delete("/api/history/<int:analysis_id>")
@login_required
def delete_history(analysis_id):
    with database_connection() as connection:
        row = connection.execute(
            "SELECT filename FROM analyses WHERE id = ? AND user_id = ?", (analysis_id, session["user_id"])
        ).fetchone()
        if row is None:
            return jsonify(error="Analysis was not found."), 404
        connection.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
    (UPLOAD_DIR / row["filename"]).unlink(missing_ok=True)
    sync_prediction_output()
    return jsonify(deleted=True)


@app.get("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    with database_connection() as connection:
        owner = connection.execute(
            "SELECT 1 FROM analyses WHERE filename = ? AND user_id = ?", (filename, session["user_id"])
        ).fetchone()
    if owner is None:
        return jsonify(error="Image was not found."), 404
    return send_from_directory(UPLOAD_DIR, filename, max_age=0)


@app.get("/dataset/<class_name>/<filename>")
def dataset_image(class_name, filename):
    if class_name not in CLASS_NAMES or not re.fullmatch(r"\d+\.jpg", filename):
        return jsonify(error="Image was not found."), 404
    return send_from_directory(ROOT / class_name, filename, max_age=3600)


@app.errorhandler(413)
def too_large(_error):
    return jsonify(error="Image must be smaller than 12 MB."), 413


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)