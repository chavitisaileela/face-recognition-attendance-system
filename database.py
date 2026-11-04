"""
Database management for AI Automatic Attendance System.
Uses SQLite for transactional, local storage.
Strictly populated using 'STUDENTS DATA.pdf' as the single source of truth.

Schema v2 additions:
  - attendance.period          : class period number (1-8)
  - attendance.faculty_name    : faculty who took attendance
  - attendance_sessions table  : full session lifecycle records
  - settings.active_faculty_name
  - settings.active_period
"""

import sqlite3
import os
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any

from pdf_students import PDF_STUDENTS, THEORY_SUBJECTS, LAB_SUBJECTS

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "attendance.db")

# Class periods definition
PERIODS = [
    {"id": 1, "label": "Period 1 (08:00 – 08:50)", "start": "08:00", "end": "08:50", "is_break": False},
    {"id": 2, "label": "Period 2 (08:55 – 09:45)", "start": "08:55", "end": "09:45", "is_break": False},
    {"id": 3, "label": "Period 3 (09:50 – 10:40)", "start": "09:50", "end": "10:40", "is_break": False},
    {"id": 4, "label": "Break   (10:40 – 11:00)", "start": "10:40", "end": "11:00", "is_break": True},
    {"id": 5, "label": "Period 4 (11:00 – 11:50)", "start": "11:00", "end": "11:50", "is_break": False},
    {"id": 6, "label": "Period 5 (11:55 – 12:45)", "start": "11:55", "end": "12:45", "is_break": False},
    {"id": 7, "label": "Lunch   (12:45 – 13:30)", "start": "12:45", "end": "13:30", "is_break": True},
    {"id": 8, "label": "Period 6 (13:30 – 14:20)", "start": "13:30", "end": "14:20", "is_break": False},
    {"id": 9, "label": "Period 7 (14:25 – 15:15)", "start": "14:25", "end": "15:15", "is_break": False},
    {"id": 10, "label": "Period 8 (15:20 – 16:10)", "start": "15:20", "end": "16:10", "is_break": False},
]


def hash_password(password: str, salt: Optional[str] = None) -> str:
    if not salt:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return f"{salt}:{key.hex()}"


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        salt, key_hex = stored_hash.split(":")
        new_key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
        return secrets.compare_digest(key_hex, new_key.hex())
    except Exception:
        return False


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Initialize database tables, run migrations, and seed data."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # 1. Users / Faculty Authentication Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'faculty',
                created_at TEXT NOT NULL
            )
        """)

        # 2. Students Table (ONLY from STUDENTS DATA.pdf)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                s_no INTEGER NOT NULL,
                prn TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                section TEXT NOT NULL,
                face_status TEXT NOT NULL DEFAULT 'Face Not Registered',
                photo_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)

        # 3. Attendance Sessions Table (new in v2)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attendance_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                subject TEXT NOT NULL,
                section TEXT NOT NULL DEFAULT 'All',
                faculty_name TEXT NOT NULL DEFAULT '',
                period INTEGER NOT NULL DEFAULT 1,
                date TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                status TEXT NOT NULL DEFAULT 'active'
            )
        """)

        # 4. Attendance Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                prn TEXT NOT NULL,
                name TEXT NOT NULL,
                section TEXT NOT NULL,
                date TEXT NOT NULL,
                subject TEXT NOT NULL,
                time TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PRESENT',
                session_id TEXT,
                faculty_name TEXT DEFAULT '',
                period INTEGER DEFAULT 1,
                FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE SET NULL
            )
        """)

        # --- Migrations: add columns if they don't already exist ---
        _add_column_if_missing(cursor, "attendance", "faculty_name", "TEXT DEFAULT ''")
        _add_column_if_missing(cursor, "attendance", "period", "INTEGER DEFAULT 1")

        # Rebuild unique index to include period and faculty_name
        # Drop old unique constraint and create new one via unique index
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_attendance_unique
            ON attendance (prn, date, subject, period, faculty_name)
        """)

        # 5. Mobile Capture Tokens
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mobile_tokens (
                token TEXT PRIMARY KEY,
                prn TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                is_used INTEGER DEFAULT 0,
                FOREIGN KEY(prn) REFERENCES students(prn) ON DELETE CASCADE
            )
        """)

        # 6. Settings Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # Seed default admin user
        cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
        if cursor.fetchone()[0] == 0:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "INSERT INTO users (username, password_hash, name, role, created_at) VALUES (?, ?, ?, ?, ?)",
                ("admin", hash_password("admin@123"), "Administrator / Faculty Incharge", "admin", now)
            )

        # Seed PDF students
        cursor.execute("SELECT COUNT(*) FROM students")
        if cursor.fetchone()[0] == 0:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for student in PDF_STUDENTS:
                cursor.execute("""
                    INSERT INTO students (s_no, prn, name, section, face_status, photo_count, created_at)
                    VALUES (?, ?, ?, ?, 'Face Not Registered', 0, ?)
                """, (student["s_no"], student["prn"], student["name"], student["section"], now))

        # Default settings
        defaults = {
            "active_subject": "Fundamentals of Computing",
            "active_section": "All",
            "confidence_threshold": "72",
            "google_sheets_webhook": "",
            "active_session_id": "",
            "active_faculty_name": "",
            "active_period": "1"
        }
        for k, v in defaults.items():
            cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

        conn.commit()


def _add_column_if_missing(cursor, table: str, column: str, col_def: str):
    """Migration helper: add column if it doesn't exist."""
    cursor.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in cursor.fetchall()]
    if column not in cols:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")


# --- User & Auth Operations ---

def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone()
        return dict(row) if row else None


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    user = get_user_by_username(username)
    if not user:
        return None
    if verify_password(user["password_hash"], password):
        return {"id": user["id"], "username": user["username"], "name": user["name"], "role": user["role"]}
    return None


# --- Student Operations (Strictly PDF-based) ---

def get_all_students(section: Optional[str] = None) -> List[Dict[str, Any]]:
    query = "SELECT * FROM students"
    params = []
    if section and section.strip() and section != "All":
        query += " WHERE UPPER(section) = UPPER(?)"
        params.append(section.strip())
    query += " ORDER BY s_no ASC"
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def get_student_by_prn(prn: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM students WHERE UPPER(prn) = UPPER(?)", (prn.strip(),)).fetchone()
        return dict(row) if row else None


def get_student_by_id(student_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        return dict(row) if row else None


def update_student_face_status(prn: str, status: str, count: Optional[int] = None):
    with get_connection() as conn:
        if count is not None:
            conn.execute(
                "UPDATE students SET face_status = ?, photo_count = ? WHERE UPPER(prn) = UPPER(?)",
                (status, count, prn.strip())
            )
        else:
            conn.execute(
                "UPDATE students SET face_status = ? WHERE UPPER(prn) = UPPER(?)",
                (status, prn.strip())
            )
        conn.commit()


# --- Mobile Capture Token Operations ---

def create_mobile_token(prn: str, expiry_minutes: int = 60) -> str:
    token = secrets.token_urlsafe(16)
    now = datetime.now()
    expires_at = (now + timedelta(minutes=expiry_minutes)).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO mobile_tokens (token, prn, created_at, expires_at, is_used) VALUES (?, ?, ?, ?, 0)",
            (token, prn.strip().upper(), now.strftime("%Y-%m-%d %H:%M:%S"), expires_at)
        )
        conn.commit()
    return token


def verify_mobile_token(token: str) -> Optional[Dict[str, Any]]:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        row = conn.execute("""
            SELECT mt.*, s.name, s.section, s.s_no
            FROM mobile_tokens mt
            JOIN students s ON UPPER(mt.prn) = UPPER(s.prn)
            WHERE mt.token = ? AND mt.expires_at > ?
        """, (token.strip(), now_str)).fetchone()
        return dict(row) if row else None


# --- Attendance Session Operations (new in v2) ---

def create_attendance_session(
    session_id: str, subject: str, section: str,
    faculty_name: str, period: int
) -> Dict[str, Any]:
    """Record a new attendance session start."""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    started_at = now.strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO attendance_sessions
            (session_id, subject, section, faculty_name, period, date, started_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
        """, (session_id, subject, section, faculty_name, period, date_str, started_at))
        conn.commit()
    return {
        "session_id": session_id, "subject": subject, "section": section,
        "faculty_name": faculty_name, "period": period,
        "date": date_str, "started_at": started_at
    }


def end_attendance_session(session_id: str):
    """Mark session as ended."""
    ended_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute(
            "UPDATE attendance_sessions SET ended_at = ?, status = 'ended' WHERE session_id = ?",
            (ended_at, session_id)
        )
        conn.commit()


def get_active_session() -> Optional[Dict[str, Any]]:
    """Get the currently active session details."""
    session_id = get_setting("active_session_id", "")
    if not session_id:
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM attendance_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None


# --- Attendance Operations ---

def mark_attendance(
    prn: str, subject: str, date_str: Optional[str] = None, time_str: Optional[str] = None,
    session_id: Optional[str] = None, faculty_name: Optional[str] = None,
    period: Optional[int] = None
) -> Dict[str, Any]:
    """
    Mark student attendance as PRESENT.
    Unique per: prn + date + subject + period + faculty_name
    """
    now = datetime.now()
    if not date_str:
        date_str = now.strftime("%Y-%m-%d")
    if not time_str:
        time_str = now.strftime("%H:%M:%S")

    # Read period/faculty from settings if not provided
    if period is None:
        try:
            period = int(get_setting("active_period", "1"))
        except (ValueError, TypeError):
            period = 1
    if not faculty_name:
        faculty_name = get_setting("active_faculty_name", "")

    student = get_student_by_prn(prn)
    if not student:
        return {
            "status": "not_found",
            "message": f"Student '{prn}' not in PDF database.",
            "record": None
        }

    try:
        with get_connection() as conn:
            # Check duplicate using (prn, date, subject, period, faculty_name)
            existing = conn.execute(
                "SELECT * FROM attendance WHERE UPPER(prn) = UPPER(?) AND date = ? AND subject = ? AND period = ? AND faculty_name = ?",
                (prn.strip(), date_str, subject.strip(), period, faculty_name)
            ).fetchone()
            if existing:
                return {
                    "status": "already_marked",
                    "message": f"{student['name']} ({prn}) already PRESENT for {subject} Period {period}.",
                    "record": dict(existing)
                }

            conn.execute("""
                INSERT INTO attendance (student_id, prn, name, section, date, subject, time, status, session_id, faculty_name, period)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'PRESENT', ?, ?, ?)
            """, (student["id"], student["prn"], student["name"], student["section"],
                  date_str, subject.strip(), time_str, session_id, faculty_name, period))
            new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.commit()

            record = dict(conn.execute("SELECT * FROM attendance WHERE id = ?", (new_id,)).fetchone())
            return {
                "status": "success",
                "message": f"{student['name']} ({prn}) marked PRESENT.",
                "record": record
            }
    except Exception as e:
        return {"status": "error", "message": f"Failed: {e}", "record": None}


def get_attendance_breakdown(
    subject: str,
    date_str: Optional[str] = None,
    section: Optional[str] = None,
    period: Optional[int] = None,
    faculty_name: Optional[str] = None
) -> Dict[str, Any]:
    """Calculate Present/Absent breakdown for all PDF students."""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    all_students = get_all_students(section=section)

    # Build query – filter by period/faculty only if provided (non-None, non-zero, non-empty)
    query = "SELECT * FROM attendance WHERE subject = ? AND date = ?"
    params: list = [subject.strip(), date_str]
    if period and period > 0:
        query += " AND period = ?"
        params.append(period)
    if faculty_name and faculty_name.strip():
        query += " AND faculty_name = ?"
        params.append(faculty_name.strip())

    with get_connection() as conn:
        marked_rows = conn.execute(query, params).fetchall()
        present_prns = {row["prn"].upper(): dict(row) for row in marked_rows}

    present_list, absent_list = [], []
    for s in all_students:
        prn_key = s["prn"].upper()
        if prn_key in present_prns:
            att = present_prns[prn_key]
            present_list.append({
                "s_no": s["s_no"], "prn": s["prn"], "name": s["name"],
                "section": s["section"], "status": "PRESENT",
                "time": att["time"], "date": att["date"], "subject": subject,
                "faculty_name": att.get("faculty_name", ""), "period": att.get("period", 1)
            })
        else:
            absent_list.append({
                "s_no": s["s_no"], "prn": s["prn"], "name": s["name"],
                "section": s["section"], "status": "ABSENT",
                "time": "--:--:--", "date": date_str, "subject": subject,
                "faculty_name": faculty_name or "", "period": period or 1
            })

    total = len(all_students)
    present_count = len(present_list)
    absent_count = len(absent_list)
    pct = round((present_count / total * 100), 1) if total > 0 else 0.0

    return {
        "subject": subject, "section": section or "All", "date": date_str,
        "period": period or 0, "faculty_name": faculty_name or "",
        "total_students": total, "present_count": present_count,
        "absent_count": absent_count, "attendance_percentage": pct,
        "present_list": present_list, "absent_list": absent_list
    }


def get_attendance_records(
    date_str: Optional[str] = None,
    subject: Optional[str] = None,
    section: Optional[str] = None,
    faculty_name: Optional[str] = None,
    period: Optional[int] = None
) -> List[Dict[str, Any]]:
    query = "SELECT * FROM attendance WHERE 1=1"
    params = []
    if date_str:
        query += " AND date = ?"; params.append(date_str)
    if subject and subject != "All Subjects":
        query += " AND subject = ?"; params.append(subject.strip())
    if section and section != "All":
        query += " AND section = ?"; params.append(section.strip())
    if faculty_name and faculty_name.strip():
        query += " AND faculty_name = ?"; params.append(faculty_name.strip())
    if period and period > 0:
        query += " AND period = ?"; params.append(period)
    query += " ORDER BY id DESC"
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


# --- Settings Operations ---

def get_setting(key: str, default: str = "") -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default


def set_setting(key: str, value: str):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value)
        )
        conn.commit()


# Initialize database on import
init_db()
