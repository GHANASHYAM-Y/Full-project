import os
import io
import threading
import sqlite3
import datetime
import json
import pyotp
import qrcode
import base64
from datetime import timedelta

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_file,
    session,
    redirect,
    url_for
)

from auth_simple import (
    init_auth_tables,
    create_user,
    verify_user,
    get_user_by_id
)

from model import (
    train_model_background,
    extract_embedding_for_image,
    detect_blink_in_image,
    load_model_if_exists,
    predict_with_model,
    MODEL_PATH
)

# ============================================================
# PATHS & APP CONFIG
# ============================================================

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "attendance.db")
DATASET_DIR = os.path.join(APP_DIR, "dataset")
TRAIN_STATUS_FILE = os.path.join(APP_DIR, "train_status.json")

os.makedirs(DATASET_DIR, exist_ok=True)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = "CHANGE_THIS_SECRET_KEY"

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=1 )

# In-memory TOTP secrets (OK for demo)

# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():
    # Auth tables (unchanged)
    init_auth_tables()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Students
    c.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        roll TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        department TEXT,
        section TEXT,
        created_at TEXT NOT NULL
    )
    """)

    # Face training status
    c.execute("""
    CREATE TABLE IF NOT EXISTS face_training_status (
        student_id INTEGER PRIMARY KEY,
        face_trained INTEGER DEFAULT 0,
        face_images_count INTEGER DEFAULT 0,
        last_trained_at TEXT,
        model_version TEXT,
        FOREIGN KEY(student_id) REFERENCES students(id)
    )
    """)

    # Attendance
    c.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        timestamp TEXT NOT NULL,
        date TEXT NOT NULL,
        time TEXT NOT NULL,
        confidence REAL,
        liveness_verified INTEGER,
        blink_ear_value REAL,
        model_version TEXT,
        FOREIGN KEY(student_id) REFERENCES students(id)
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ============================================================
# TRAIN STATUS HELPERS
# ============================================================

def write_train_status(data):
    with open(TRAIN_STATUS_FILE, "w") as f:
        json.dump(data, f)

def read_train_status():
    if not os.path.exists(TRAIN_STATUS_FILE):
        return {"running": False, "progress": 0, "message": "Not started"}
    with open(TRAIN_STATUS_FILE, "r") as f:
        return json.load(f)

write_train_status({"running": False, "progress": 0, "message": "Idle"})

# ============================================================
# ROOT ROUTE
# ============================================================
@app.route("/")
def home():

    if "user_id" not in session:
        return redirect(url_for("login_page"))

    # STUDENT FLOW
    if session.get("role") == "student":
        if not session.get("location_verified"):
            return redirect(url_for("geolocation_check"))

        if not session.get("totp_verified"):
            return redirect(url_for("totp_setup"))

        # ✅ FINAL DESTINATION: STUDENT DASHBOARD
        stats = get_security_dashboard_stats()
        return render_template("index.html", stats=stats)

    # TEACHER FLOW
    return redirect(url_for("attendance_record"))

#           Stats
def get_security_dashboard_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Total attendance attempts
    c.execute("SELECT COUNT(*) FROM attendance")
    total = c.fetchone()[0]

    # Liveness verified entries
    c.execute("""
        SELECT COUNT(*) FROM attendance
        WHERE liveness_verified = 1
    """)
    liveness_ok = c.fetchone()[0]

    # Average confidence (valid entries only)
    c.execute("""
        SELECT AVG(confidence) FROM attendance
        WHERE confidence IS NOT NULL
    """)
    avg_conf = c.fetchone()[0]
    avg_conf = round(avg_conf * 100, 1) if avg_conf else 0

    # Blocked / low confidence attempts
    c.execute("""
        SELECT COUNT(*) FROM attendance
        WHERE confidence < 0.70
    """)
    blocked = c.fetchone()[0]

    conn.close()

    return {
        "total": total,
        "liveness_ok": liveness_ok,
        "avg_conf": avg_conf,
        "blocked": blocked
    }

# ============================================================
# AUTHENTICATION ROUTES
# ============================================================

@app.route("/login", methods=["GET"])
def login_page():
    return render_template("login_page.html")

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    username = data.get("username")
    password = data.get("password")

    result = verify_user(username, password)

    if not result["success"]:
        return jsonify(result), 401

    session.permanent = True
    session["user_id"] = result["user_id"]
    session["role"] = result["role"]
    session["full_name"] = result["full_name"]

    session.pop("location_verified", None)
    session.pop("totp_verified", None)


    redirect_url = (
        url_for("geolocation_check")
        if result["role"] == "student"
        else url_for("attendance_record")
    )

    return jsonify({
        "success": True,
        "redirect": redirect_url,
        "role": result["role"]
    })

@app.route("/register", methods=["GET"])
def register_page():
    return render_template("register.html")

@app.route("/register", methods=["POST"])
def register():
    data = request.json

    full_name = data.get("full_name")
    username = data.get("username")
    password = data.get("password")
    role = data.get("role")

    if not all([full_name, username, password, role]):
        return jsonify({"success": False, "error": "All fields required"}), 400

    if role not in ["student", "teacher"]:
        return jsonify({"success": False, "error": "Invalid role"}), 400

    result = create_user(username, password, role, full_name)
    return jsonify(result)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))

# ============================================================
# GEOLOCATION (STUDENT ONLY)
# ============================================================

@app.route("/geolocation_check")
def geolocation_check():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    if session.get("role") != "student":
        return redirect(url_for("attendance_record"))

    return render_template("geolocation.html")

@app.route("/verify_location", methods=["POST"])
def verify_location():
    if session.get("role") != "student":
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    data = request.json
    lat = data.get("latitude")
    lon = data.get("longitude")

    if not lat or not lon:
        return jsonify({"success": False, "error": "Location not available"}), 400

    session["location_verified"] = True

    return jsonify({
        "success": True,
        "message": "Location verified",
        "next_step": url_for("totp_setup")
    })

# ============================================================
# TOTP SETUP & VERIFY
# ============================================================
@app.route("/totp-setup")
def totp_setup():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    # Student must finish geo verification first
    if session.get("role") == "student" and not session.get("location_verified"):
        return redirect(url_for("geolocation_check"))

    user_id = session["user_id"]

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Check if TOTP secret already exists
    c.execute("""
        SELECT secret FROM totp_credentials
        WHERE user_id = ? AND enabled = 1
    """, (user_id,))
    row = c.fetchone()

    if row:
        secret = row[0]
    else:
        secret = pyotp.random_base32()
        c.execute("""
            INSERT INTO totp_credentials
            (user_id, secret, created_at)
            VALUES (?, ?, ?)
        """, (
            user_id,
            secret,
            datetime.datetime.utcnow().isoformat()
        ))
        conn.commit()

    conn.close()

    # Generate TOTP URI and QR code
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(
        name=str(user_id),
        issuer_name="SecureAuth"
    )

    qr = qrcode.make(uri)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return render_template(
        "totp_setup.html",
        secret=secret,
        qr_code=qr_b64
    )

@app.route("/totp-verify", methods=["POST"])
def totp_verify():
    if "user_id" not in session:
        return jsonify({"success": False, "message": "Not logged in"})

    user_id = session["user_id"]
    otp_code = request.json.get("otp_code")

    if not otp_code:
        return jsonify({"success": False, "message": "OTP required"})

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT secret FROM totp_credentials
        WHERE user_id = ? AND enabled = 1
    """, (user_id,))
    row = c.fetchone()

    conn.close()

    if not row:
        return jsonify({"success": False, "message": "TOTP not set up"})

    secret = row[0]
    totp = pyotp.TOTP(secret)

    # allow slight clock drift
    if totp.verify(otp_code, valid_window=1):
        session["totp_verified"] = True

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            UPDATE totp_credentials
            SET last_verified = ?
            WHERE user_id = ?
        """, (
            datetime.datetime.utcnow().isoformat(),
            user_id
        ))
        conn.commit()
        conn.close()

        return jsonify({
            "success": True,
            "next_step": url_for("home")
        })

    return jsonify({"success": False, "message": "Invalid OTP"})

# ============================================================
# BLINK / LIVENESS CHECK
# ============================================================

@app.route("/check_blink", methods=["POST"])
def check_blink():
    if not session.get("totp_verified"):
        return jsonify({"success": False, "error": "TOTP not verified"}), 403

    if "image" not in request.files:
        return jsonify({"success": False, "error": "No image provided"}), 400

    try:
        result = detect_blink_in_image(request.files["image"].stream)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "Blink detection failed"
        }), 500
# ============================================================
# STUDENT MANAGEMENT
# ============================================================

@app.route("/add_student", methods=["GET", "POST"])
def add_student():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    if request.method == "GET":
        return render_template("add_student.html")

    name = request.form.get("name", "").strip()
    roll = request.form.get("roll", "").strip()
    department = request.form.get("department", "").strip()
    section = request.form.get("section", "").strip()

    if not name:
        return jsonify({"error": "Name required"}), 400

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()

    try:
        c.execute("""
            INSERT INTO students
            (name, roll, department, section, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (name, roll, department, section, now))

        sid = c.lastrowid

        c.execute("""
            INSERT INTO face_training_status (student_id)
            VALUES (?)
        """, (sid,))

        conn.commit()

        os.makedirs(os.path.join(DATASET_DIR, str(sid)), exist_ok=True)

        return jsonify({"student_id": sid})

    except sqlite3.IntegrityError:
        return jsonify({"error": "Roll already exists"}), 400

    finally:
        conn.close()

@app.route("/students", methods=["GET"])
def students_list():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT s.id, s.name, s.roll, s.department, s.section,
               COALESCE(f.face_trained, 0),
               COALESCE(f.face_images_count, 0),
               f.last_trained_at,
               s.created_at
        FROM students s
        LEFT JOIN face_training_status f
               ON s.id = f.student_id
        ORDER BY s.roll
    """)

    rows = c.fetchall()
    conn.close()

    data = [{
        "id": r[0],
        "name": r[1],
        "roll": r[2],
        "department": r[3],
        "section": r[4],
        "face_trained": r[5],
        "face_images_count": r[6],
        "last_trained_at": r[7],
        "created_at": r[8]
    } for r in rows]

    return jsonify({"students": data})

@app.route("/students/<int:sid>", methods=["DELETE"])
def delete_student(sid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("DELETE FROM students WHERE id=?", (sid,))
    c.execute("DELETE FROM attendance WHERE student_id=?", (sid,))
    conn.commit()
    conn.close()

    folder = os.path.join(DATASET_DIR, str(sid))
    if os.path.isdir(folder):
        import shutil
        shutil.rmtree(folder, ignore_errors=True)

    return jsonify({"deleted": True})


# ============================================================
# FACE IMAGE UPLOAD
# ============================================================

@app.route("/upload_face", methods=["POST"])
def upload_face():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 403

    student_id = request.form.get("student_id")
    files = request.files.getlist("images[]")

    if not student_id or not files:
        return jsonify({"error": "Missing data"}), 400

    folder = os.path.join(DATASET_DIR, student_id)
    os.makedirs(folder, exist_ok=True)

    saved = 0
    for f in files:
        filename = f"{datetime.datetime.utcnow().timestamp()}_{saved}.jpg"
        f.save(os.path.join(folder, filename))
        saved += 1

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("PRAGMA table_info(students)")
    columns = [col[1] for col in c.fetchall()]
    if "face_images_count" in columns:
        c.execute(
            "UPDATE students SET face_images_count=? WHERE id=?",
            (saved, int(student_id))
        )

    conn.commit()
    conn.close()

    return jsonify({"saved": saved})


# ============================================================
# MODEL TRAINING (BACKGROUND THREAD)
# ============================================================

@app.route("/train_model", methods=["GET"])
def train_model_route():
    status = read_train_status()
    if status.get("running"):
        return jsonify({"status": "already_running"}), 202

    write_train_status({
        "running": True,
        "progress": 0,
        "message": "Training started"
    })

    def callback(progress, message):
        write_train_status({
            "running": progress < 100,
            "progress": progress,
            "message": message
        })
        if progress == 100:
            update_training_metadata()

    t = threading.Thread(
        target=train_model_background,
        args=(DATASET_DIR, callback)
    )
    t.daemon = True
    t.start()

    return jsonify({"status": "started"}), 202


@app.route("/train_status", methods=["GET"])
def train_status():
    return jsonify(read_train_status())


def update_training_metadata():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("PRAGMA table_info(students)")
    columns = [col[1] for col in c.fetchall()]
    if "face_trained" not in columns:
        conn.close()
        return

    for sid in os.listdir(DATASET_DIR):
        path = os.path.join(DATASET_DIR, sid)
        if not os.path.isdir(path):
            continue

        images = [
            f for f in os.listdir(path)
            if f.lower().endswith((".jpg", ".png", ".jpeg"))
        ]

        c.execute("""
            UPDATE students
            SET face_trained=1,
                face_images_count=?,
                last_trained_at=?
            WHERE id=?
        """, (
            len(images),
            datetime.datetime.utcnow().isoformat(),
            int(sid)
        ))

    conn.commit()
    conn.close()


# ============================================================
# DEBUG MODEL
# ============================================================

@app.route("/debug_model")
def debug_model():
    return jsonify({
        "model_path": MODEL_PATH,
        "exists": os.path.exists(MODEL_PATH),
        "size": os.path.getsize(MODEL_PATH) if os.path.exists(MODEL_PATH) else 0,
        "loaded": load_model_if_exists() is not None
    })

# ============================================================
# ATTENDANCE MARKING PAGE
# ============================================================

@app.route("/mark_attendance", methods=["GET"])
def mark_attendance_page():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    if session.get("role") != "student":
        return redirect(url_for("attendance_record"))

    if not session.get("totp_verified"):
        return redirect(url_for("totp_setup"))

    return render_template("mark_attendance.html")


# ============================================================
# FACE RECOGNITION + ATTENDANCE LOGIC
# ============================================================

@app.route("/recognize_face", methods=["POST"])
def recognize_face():
    if not session.get("totp_verified"):
        return jsonify({"recognized": False, "error": "TOTP not verified"}), 403

    blink_verified = request.form.get("blink_verified", "false").lower() == "true"
    blink_ear = float(request.form.get("blink_ear_value", "0.0"))

    if not blink_verified:
        return jsonify({
            "recognized": False,
            "error": "Blink not verified",
            "message": "Please complete blink detection first"
        }), 400

    if "image" not in request.files:
        return jsonify({"recognized": False, "error": "No image"}), 400

    emb = extract_embedding_for_image(request.files["image"].stream)
    if emb is None:
        return jsonify({"recognized": False, "error": "No face detected"}), 200

    clf = load_model_if_exists()
    if clf is None:
        return jsonify({"recognized": False, "error": "Model not trained"}), 200

    pred_label, confidence = predict_with_model(clf, emb)

    if pred_label is None or confidence < 0.70:
        return jsonify({
            "recognized": False,
            "confidence": float(confidence),
            "message": "Low confidence"
        }), 200

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT name FROM students WHERE id=?", (int(pred_label),))
    row = c.fetchone()

    if not row:
        conn.close()
        return jsonify({"recognized": False, "error": "Student not found"}), 200

    name = row[0]

    # Cooldown check (1 hour)
    c.execute("""
        SELECT timestamp FROM attendance
        WHERE student_id=?
        ORDER BY timestamp DESC LIMIT 1
    """, (int(pred_label),))
    last = c.fetchone()

    now = datetime.datetime.utcnow()

    if last and last[0]:
        try:
            last_ts = datetime.datetime.fromisoformat(last[0])
            diff = (now - last_ts).total_seconds()
            if diff < 3600:
                minutes_left = int((3600 - diff) // 60) + 1
                conn.close()
                return jsonify({
                    "recognized": False,
                    "reason": "cooldown",
                    "message": f"Try again after {minutes_left} minute(s)"
                }), 200
        except Exception:
            pass

    # Detect schema
    c.execute("PRAGMA table_info(attendance)")
    columns = [col[1] for col in c.fetchall()]
    migrated = "liveness_verified" in columns

    ts = now.isoformat()

    if migrated:
        c.execute("""
            INSERT INTO attendance
            (student_id, date, time, timestamp,
             liveness_verified, blink_ear_value, confidence)
            VALUES (?, ?, ?, ?, 1, ?, ?)
        """, (
            int(pred_label),
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M:%S"),
            ts,
            blink_ear,
            float(confidence)
        ))
    else:
        c.execute("""
            INSERT INTO attendance
            (student_id, name, timestamp)
            VALUES (?, ?, ?)
        """, (int(pred_label), name, ts))

    conn.commit()
    conn.close()

    return jsonify({
        "recognized": True,
        "student_id": int(pred_label),
        "name": name,
        "confidence": float(confidence),
        "liveness_verified": True
    })


# ============================================================
# ATTENDANCE RECORDS (VIEW)
# ============================================================
@app.route("/attendance_record", methods=["GET"])
def attendance_record():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT a.id, a.student_id, s.name,
               a.timestamp, a.liveness_verified, a.confidence
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        ORDER BY a.timestamp DESC
        LIMIT 5000
    """)

    rows = c.fetchall()
    conn.close()

    formatted = []
    for r in rows:
        rid, sid, name, ts, live, conf = r
        try:
            ts = datetime.datetime.fromisoformat(ts).strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            )
        except Exception:
            pass
        formatted.append((rid, sid, name, ts, live, conf))

    return render_template(
        "attendance_record.html",
        records=formatted,
        period="all"
    )

# ============================================================
# ATTENDANCE STATS (CHART)
# ============================================================

@app.route("/attendance_stats")
def attendance_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT timestamp FROM attendance")
    rows = c.fetchall()
    conn.close()

    counts = {}
    for (ts,) in rows:
        try:
            date = ts.split("T")[0]
            counts[date] = counts.get(date, 0) + 1
        except Exception:
            continue

    dates = sorted(counts.keys())[-30:]
    values = [counts[d] for d in dates]

    return jsonify({"dates": dates, "counts": values})


# ============================================================
# CSV EXPORT
# ============================================================

@app.route("/download_csv", methods=["GET"])
def download_csv():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("PRAGMA table_info(attendance)")
    columns = [col[1] for col in c.fetchall()]
    migrated = "liveness_verified" in columns

    if migrated:
        c.execute("""
            SELECT a.id, a.student_id, s.name,
                   a.timestamp, a.liveness_verified, a.confidence
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            ORDER BY a.timestamp DESC
        """)
    else:
        c.execute("""
            SELECT id, student_id, name, timestamp, 0, 0.0
            FROM attendance
            ORDER BY timestamp DESC
        """)

    rows = c.fetchall()
    conn.close()

    output = io.StringIO()
    output.write("id,student_id,name,timestamp,liveness_verified,confidence\n")

    for r in rows:
        output.write(",".join(map(str, r)) + "\n")

    mem = io.BytesIO(output.getvalue().encode("utf-8"))
    mem.seek(0)

    return send_file(
        mem,
        as_attachment=True,
        download_name="attendance.csv",
        mimetype="text/csv"
    )


# ============================================================
# APP RUNNER
# ============================================================

if __name__ == "__main__":
    app.run(debug=True)
