"""
auth_simple.py - Simple Authentication System (FIXED)
Handles login/registration with SQLite lock safety
"""

import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "attendance.db")


    # ============================================================
    # INTERNAL HELPER: SAFE DB CONNECTION
    # ============================================================

def get_db_connection():
    """
        Create a SQLite connection with:
        - timeout to avoid 'database is locked'
        - WAL mode for concurrent access
    """
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("PRAGMA journal_mode=WAL;")
    return conn


    # ============================================================
    # INIT AUTH TABLE
    # ============================================================

def init_auth_tables():
    """Create users table safely"""
    conn = get_db_connection()
    c = conn.cursor()

    c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('student', 'teacher')),
                full_name TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now', 'utc'))
            )
    """)

    conn.commit()
    conn.close()
    print("[AUTH] ✅ Users table ready")


    # ============================================================
    # REGISTER USER
    # ============================================================

def create_user(username, password, role, full_name):
    """Register a new user"""
    try:
        conn = get_db_connection()
        c = conn.cursor()

        password_hash = generate_password_hash(password)

        c.execute("""
                INSERT INTO users (username, password_hash, role, full_name)
                VALUES (?, ?, ?, ?)
        """, (username, password_hash, role, full_name))

        conn.commit()
        user_id = c.lastrowid
        conn.close()

        return {"success": True, "user_id": user_id}

    except sqlite3.IntegrityError:
        return {"success": False, "error": "Username already exists"}

    except Exception as e:
        return {"success": False, "error": str(e)}


    # ============================================================
    # VERIFY LOGIN
    # ============================================================

def verify_user(username, password):
    """Verify login credentials"""
    try:
        conn = get_db_connection()
        c = conn.cursor()

        c.execute("""
                SELECT id, password_hash, role, full_name
                FROM users
                WHERE username = ?
        """, (username,))

        row = c.fetchone()
        conn.close()

        if not row:
            return {"success": False, "error": "Invalid username"}

        if check_password_hash(row["password_hash"], password):
            return {
                    "success": True,
                    "user_id": row["id"],
                    "role": row["role"],
                    "full_name": row["full_name"]
            }

        return {"success": False, "error": "Invalid password"}

    except Exception as e:
        return {"success": False, "error": str(e)}


    # ============================================================
    # GET USER BY ID
    # ============================================================

def get_user_by_id(user_id):
    """Get user details by ID"""
    try:
        conn = get_db_connection()
        c = conn.cursor()

        c.execute("""
                SELECT id, username, role, full_name
                FROM users
                WHERE id = ?
        """, (user_id,))

        row = c.fetchone()
        conn.close()

        if row:
            return {
                    "id": row["id"],
                    "username": row["username"],
                    "role": row["role"],
                    "full_name": row["full_name"]
            }

        return None

    except Exception as e:
        print(f"[ERROR] get_user_by_id: {e}")
        return None
