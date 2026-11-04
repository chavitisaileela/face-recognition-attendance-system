"""
FastAPI Server for AI Automatic Face Recognition Attendance System.
Strictly uses STUDENTS DATA.pdf as the single source of truth.
v2: Faculty name, period support, stop-session endpoint, camera lifecycle control.
"""

import os
import secrets
import base64
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException, Depends, Header
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import cv2
import numpy as np
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

import database
import sheet_sync
from face_engine import engine, DATASET_DIR
from pdf_students import THEORY_SUBJECTS, LAB_SUBJECTS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("attendance_api")

app = FastAPI(title="AI Automatic Attendance System", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(BASE_DIR, "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Active authenticated sessions: {token: {username, role, name, login_time}}
ACTIVE_SESSIONS: Dict[str, Dict[str, Any]] = {}


# --- Request/Response Models ---

class LoginRequest(BaseModel):
    username: str
    password: str


class ProcessFrameRequest(BaseModel):
    image: str
    subject: Optional[str] = None
    mode: Optional[str] = "attendance"


class MobileSubmitRequest(BaseModel):
    token: str
    images: List[str]


class RegisterPhotosRequest(BaseModel):
    prn: str
    images: List[str]


class StartSessionRequest(BaseModel):
    subject: str
    section: Optional[str] = "All"
    faculty_name: Optional[str] = ""
    period: Optional[int] = 1


class SettingsRequest(BaseModel):
    confidence_threshold: Optional[str] = None
    google_sheets_webhook: Optional[str] = None


# --- Authentication Dependency ---

def require_admin(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Unauthorized: Faculty login required.")
    token = authorization.replace("Bearer ", "").strip()
    if token not in ACTIVE_SESSIONS:
        raise HTTPException(status_code=401, detail="Session expired or invalid. Please log in again.")
    return ACTIVE_SESSIONS[token]


# --- Web Page Route ---

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    with open(os.path.join(STATIC_DIR, "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


# --- Authentication ---


class RegisterRequest(BaseModel):
    username: str
    password: str
    name: str
    role: Optional[str] = "faculty"
    admin_secret: str


@app.post("/api/auth/register")
async def register_faculty(req: RegisterRequest):
    if req.admin_secret.strip() != "eduface2024":
        raise HTTPException(status_code=403, detail="Invalid registration code. Ask your administrator.")
    if len(req.username.strip()) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters.")
    if len(req.password.strip()) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
    existing = database.get_user_by_username(req.username.strip())
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken.")
    with database.get_connection() as conn:
        from database import hash_password
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        role = "admin" if req.role == "admin" else "faculty"
        conn.execute(
            "INSERT INTO users (username, password_hash, name, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (req.username.strip(), hash_password(req.password.strip()), req.name.strip(), role, now)
        )
        conn.commit()
    return {"success": True, "message": f"Account created for {req.name}. You can now log in."}

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    user = database.authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    token = secrets.token_hex(24)
    ACTIVE_SESSIONS[token] = {
        "username": user["username"],
        "name": user["name"],
        "role": user["role"],
        "login_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    return {"success": True, "token": token, "user": user, "message": f"Welcome, {user['name']}!"}


@app.post("/api/auth/logout")
async def logout(authorization: Optional[str] = Header(None)):
    if authorization:
        token = authorization.replace("Bearer ", "").strip()
        ACTIVE_SESSIONS.pop(token, None)
    return {"success": True, "message": "Logged out successfully."}


@app.get("/api/auth/me")
async def get_current_user(user: dict = Depends(require_admin)):
    return {"user": user}


# --- Student Management ---

@app.get("/api/students")
async def list_students(section: Optional[str] = "All", user: dict = Depends(require_admin)):
    students = database.get_all_students(section=section)
    result = []
    for s in students:
        prn = s["prn"].upper()
        folder = os.path.join(DATASET_DIR, prn)
        count = 0
        if os.path.exists(folder):
            count = len([f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".png", ".jpeg"))])
        s_dict = dict(s)
        s_dict["photo_count"] = count
        if count == 0:
            s_dict["face_status"] = "Face Not Registered"
        elif engine.is_trained:
            s_dict["face_status"] = "Training Completed"
        else:
            s_dict["face_status"] = "Photos Captured"
        result.append(s_dict)
    return {"students": result, "total": len(result)}


@app.get("/api/students/{prn}")
async def get_student_detail(prn: str, user: dict = Depends(require_admin)):
    student = database.get_student_by_prn(prn)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found in database.")
    folder = os.path.join(DATASET_DIR, prn.upper())
    photos = []
    if os.path.exists(folder):
        photos = [f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".png", ".jpeg"))]
    res = dict(student)
    res["photos"] = photos
    res["photo_count"] = len(photos)
    return res


@app.post("/api/students/photos")
async def register_student_photos(req: RegisterPhotosRequest, user: dict = Depends(require_admin)):
    prn = req.prn.strip().upper()
    student = database.get_student_by_prn(prn)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found in database.")
    image_bytes_list = []
    for data_url in req.images:
        try:
            if "," in data_url:
                data_url = data_url.split(",")[1]
            image_bytes_list.append(base64.b64decode(data_url))
        except Exception:
            continue
    saved = engine.add_face_samples(prn, image_bytes_list)
    return {
        "success": True, "prn": prn, "name": student["name"],
        "saved_count": saved,
        "message": f"Saved {saved} photos for {student['name']}. Please retrain the model."
    }


# --- Mobile Face Capture ---

@app.post("/api/mobile-capture/token")
async def generate_mobile_token(prn: str = Form(...), user: dict = Depends(require_admin)):
    prn = prn.strip().upper()
    student = database.get_student_by_prn(prn)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    token = database.create_mobile_token(prn, expiry_minutes=120)
    return {
        "success": True, "token": token, "prn": prn,
        "name": student["name"], "section": student["section"],
        "capture_url": f"/#mobile-capture?token={token}"
    }


@app.get("/api/mobile-capture/verify/{token}")
async def verify_mobile_access(token: str):
    student_info = database.verify_mobile_token(token)
    if not student_info:
        raise HTTPException(status_code=400, detail="Invalid or expired mobile capture token.")
    return {"valid": True, "prn": student_info["prn"], "name": student_info["name"], "section": student_info["section"]}


@app.post("/api/mobile-capture/submit")
async def submit_mobile_capture(req: MobileSubmitRequest):
    student_info = database.verify_mobile_token(req.token)
    if not student_info:
        raise HTTPException(status_code=400, detail="Session expired or invalid token.")
    prn = student_info["prn"]
    image_bytes_list = []
    for data_url in req.images:
        try:
            if "," in data_url:
                data_url = data_url.split(",")[1]
            image_bytes_list.append(base64.b64decode(data_url))
        except Exception:
            continue
    saved = engine.add_face_samples(prn, image_bytes_list)
    return {
        "success": True, "name": student_info["name"], "prn": prn,
        "saved_count": saved,
        "message": f"Thank you, {student_info['name']}! {saved} photos submitted successfully."
    }


# --- Face Training ---

@app.post("/api/train")
async def train_face_data(user: dict = Depends(require_admin)):
    success, message, count = engine.train_model()
    return {"success": success, "message": message, "samples_trained": count, "is_trained": engine.is_trained}


# --- Subjects & Periods ---

@app.get("/api/subjects")
def get_subjects():
    return {"theory_subjects": THEORY_SUBJECTS, "lab_subjects": LAB_SUBJECTS}


@app.get("/api/periods")
def get_periods():
    return {"periods": database.PERIODS}


# --- Session Management ---

@app.post("/api/session/start")
async def start_attendance_session(req: StartSessionRequest, user: dict = Depends(require_admin)):
    """Start a new attendance session. Resets face engine confirm buffer."""
    session_id = f"SES_{int(datetime.now().timestamp())}"
    faculty_name = req.faculty_name.strip() if req.faculty_name else user.get("name", "")
    period = req.period or 1

    # Persist to settings (fast in-memory key for engine reads)
    database.set_setting("active_subject", req.subject.strip())
    database.set_setting("active_section", req.section.strip())
    database.set_setting("active_session_id", session_id)
    database.set_setting("active_faculty_name", faculty_name)
    database.set_setting("active_period", str(period))

    # Record in attendance_sessions table
    database.create_attendance_session(
        session_id=session_id,
        subject=req.subject.strip(),
        section=req.section.strip(),
        faculty_name=faculty_name,
        period=period
    )

    # Reset engine per-session state
    engine.reset_session()
    engine.stream_mode = "attendance"

    return {
        "success": True,
        "session_id": session_id,
        "subject": req.subject,
        "section": req.section,
        "faculty_name": faculty_name,
        "period": period,
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


@app.post("/api/session/stop")
async def stop_attendance_session(user: dict = Depends(require_admin)):
    """Stop active session, stop camera stream, clear session ID."""
    session_id = database.get_setting("active_session_id", "")
    if session_id:
        database.end_attendance_session(session_id)

    engine.stop_stream()
    database.set_setting("active_session_id", "")
    engine.stream_mode = "test"

    return {"success": True, "message": "Attendance session stopped.", "session_id": session_id}


@app.get("/api/session/status")
async def get_session_status():
    subject = database.get_setting("active_subject", "Fundamentals of Computing")
    section = database.get_setting("active_section", "All")
    session_id = database.get_setting("active_session_id", "")
    faculty_name = database.get_setting("active_faculty_name", "")
    period = int(database.get_setting("active_period", "1") or "1")
    breakdown = database.get_attendance_breakdown(
        subject=subject, section=section,
        period=period if session_id else None,
        faculty_name=faculty_name if session_id else None
    )
    return {
        "active_subject": subject,
        "active_section": section,
        "session_id": session_id,
        "faculty_name": faculty_name,
        "period": period,
        "is_session_active": bool(session_id),
        "is_model_trained": engine.is_trained,
        "stats": breakdown
    }


# --- Live Video Streaming ---

@app.get("/api/video_feed")
async def video_feed(mode: str = "attendance", session: Optional[str] = None):
    """
    MJPEG stream. Only starts when called explicitly.
    The frontend must set img.src only after attendance session is started.
    """
    return StreamingResponse(
        engine.start_stream(camera_index=0, mode=mode),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.post("/api/video_feed/stop")
async def stop_video_feed(user: dict = Depends(require_admin)):
    """Stop the active hardware camera stream."""
    engine.stop_stream()
    return {"success": True, "message": "Camera stream stopped."}


@app.post("/api/process_frame")
async def process_frame(req: ProcessFrameRequest):
    """
    Browser webcam frame processor.
    mode='test': Recognition testing only.
    mode='attendance': Mark attendance automatically.
    """
    try:
        data_url = req.image
        if "," in data_url:
            data_url = data_url.split(",")[1]
        img_bytes = base64.b64decode(data_url)
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            raise HTTPException(status_code=400, detail="Invalid frame")

        subject = req.subject or database.get_setting("active_subject", "Fundamentals of Computing")
        session_id = database.get_setting("active_session_id", "")
        faculty_name = database.get_setting("active_faculty_name", "")
        period = int(database.get_setting("active_period", "1") or "1")
        mode = req.mode or "attendance"

        annotated_frame, detections = engine.process_frame(
            frame, subject, mode=mode, session_id=session_id,
            faculty_name=faculty_name, force_recognize=True
        )

        _, buffer = cv2.imencode(".jpg", annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        encoded = base64.b64encode(buffer).decode("utf-8")

        return {
            "success": True, "detections": detections, "mode": mode,
            "annotated_image": f"data:image/jpeg;base64,{encoded}"
        }
    except Exception as e:
        logger.error("process_frame error: %s", e)
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.get("/api/recent_events")
async def get_recent_events():
    return {"events": engine.get_recent_events()}


# --- Attendance Records & Breakdowns ---

@app.get("/api/attendance/breakdown")
async def get_breakdown(
    subject: Optional[str] = None,
    section: Optional[str] = "All",
    date: Optional[str] = None,
    period: Optional[int] = None,
    faculty_name: Optional[str] = None,
    user: dict = Depends(require_admin)
):
    if not subject:
        subject = database.get_setting("active_subject", "Fundamentals of Computing")
    return database.get_attendance_breakdown(
        subject=subject, date_str=date, section=section,
        period=period, faculty_name=faculty_name
    )


@app.get("/api/attendance/records")
async def get_records(
    subject: Optional[str] = None,
    section: Optional[str] = "All",
    date: Optional[str] = None,
    faculty_name: Optional[str] = None,
    period: Optional[int] = None,
    user: dict = Depends(require_admin)
):
    records = database.get_attendance_records(
        date_str=date, subject=subject, section=section,
        faculty_name=faculty_name, period=period
    )
    return {"records": records, "count": len(records)}


# --- Export ---

@app.get("/api/export/excel")
async def export_excel(user: dict = Depends(require_admin)):
    sheet_sync.rebuild_excel_from_db()
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    return FileResponse(
        path=sheet_sync.EXCEL_PATH,
        filename=f"attendance_records_{now_str}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.get("/api/export/csv")
async def export_csv(user: dict = Depends(require_admin)):
    sheet_sync.rebuild_csv_from_db()
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    return FileResponse(
        path=sheet_sync.CSV_PATH,
        filename=f"attendance_records_{now_str}.csv",
        media_type="text/csv"
    )


@app.get("/api/export/session_report")
async def export_session_report(
    subject: str,
    section: Optional[str] = "All",
    date: Optional[str] = None,
    period: Optional[int] = None,
    faculty_name: Optional[str] = None,
    user: dict = Depends(require_admin)
):
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    breakdown = database.get_attendance_breakdown(
        subject=subject, date_str=date, section=section,
        period=period, faculty_name=faculty_name
    )

    wb = openpyxl.Workbook()
    ws_present = wb.active
    ws_present.title = "Present Students"
    headers = ["S.No", "PRN", "Name", "Section", "Subject", "Date", "Period", "Faculty", "Time", "Status"]
    ws_present.append(headers)

    hdr_fill = PatternFill(start_color="166534", end_color="166534", fill_type="solid")
    hdr_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    for col in range(1, len(headers) + 1):
        cell = ws_present.cell(row=1, column=col)
        cell.fill = hdr_fill
        cell.font = hdr_font

    for s in breakdown["present_list"]:
        ws_present.append([
            s["s_no"], s["prn"], s["name"], s["section"], subject, date,
            s.get("period", 1), s.get("faculty_name", ""), s["time"], "PRESENT"
        ])

    ws_absent = wb.create_sheet("Absent Students")
    ws_absent.append(headers)
    abs_fill = PatternFill(start_color="991B1B", end_color="991B1B", fill_type="solid")
    for col in range(1, len(headers) + 1):
        cell = ws_absent.cell(row=1, column=col)
        cell.fill = abs_fill
        cell.font = hdr_font

    for s in breakdown["absent_list"]:
        ws_absent.append([
            s["s_no"], s["prn"], s["name"], s["section"], subject, date,
            s.get("period", 1), s.get("faculty_name", ""), "--:--:--", "ABSENT"
        ])

    report_path = os.path.join(BASE_DIR, "data", "session_report.xlsx")
    wb.save(report_path)
    return FileResponse(
        path=report_path,
        filename=f"attendance_session_{subject.replace(' ', '_')}_{date}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# --- Settings ---

@app.get("/api/settings")
async def get_settings(user: dict = Depends(require_admin)):
    return {
        "confidence_threshold": database.get_setting("confidence_threshold", "72"),
        "google_sheets_webhook": database.get_setting("google_sheets_webhook", ""),
        "active_subject": database.get_setting("active_subject", "Fundamentals of Computing"),
        "active_section": database.get_setting("active_section", "All"),
        "active_faculty_name": database.get_setting("active_faculty_name", ""),
        "active_period": database.get_setting("active_period", "1")
    }


@app.post("/api/settings")
async def update_settings(req: SettingsRequest, user: dict = Depends(require_admin)):
    if req.confidence_threshold:
        database.set_setting("confidence_threshold", req.confidence_threshold.strip())
    if req.google_sheets_webhook is not None:
        database.set_setting("google_sheets_webhook", req.google_sheets_webhook.strip())
    return {"success": True, "message": "Settings saved."}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("main:app", host=host, port=port, reload=False)
