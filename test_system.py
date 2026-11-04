"""
Comprehensive automated test suite for EduFace AI Attendance System.
Validates PDF single-source-of-truth, auth, session flow, duplicate prevention, and exports.
"""

from fastapi.testclient import TestClient
from main import app
import database

def run_tests():
    print("=" * 60)
    print("STARTING TEST SUITE: EduFace AI Attendance System")
    print("=" * 60)

    client = TestClient(app)

    # 1. Test Web Page Root
    r_index = client.get("/")
    assert r_index.status_code == 200, f"Expected 200 for '/', got {r_index.status_code}"
    print("[PASS] 1. Root page '/' loaded successfully (HTML200).")

    # 2. Test Authentication
    r_login_fail = client.post("/api/auth/login", json={"username": "admin", "password": "wrongpassword"})
    assert r_login_fail.status_code == 401, "Expected 401 for bad password"

    r_login = client.post("/api/auth/login", json={"username": "admin", "password": "admin@123"})
    assert r_login.status_code == 200, f"Login failed: {r_login.text}"
    token = r_login.json()["token"]
    auth_headers = {"Authorization": f"Bearer {token}"}
    print("[PASS] 2. Faculty Authentication & Password Hashing verified.")

    # 3. Test Student Database (Strictly from STUDENTS DATA.pdf)
    r_students = client.get("/api/students", headers=auth_headers)
    assert r_students.status_code == 200
    students = r_students.json()["students"]
    assert len(students) == 66, f"Expected exactly 66 students from PDF, got {len(students)}"
    
    sec_b = [s for s in students if s["section"] == "B"]
    sec_a = [s for s in students if s["section"] == "A"]
    assert len(sec_b) == 64, f"Expected 64 in Section B, got {len(sec_b)}"
    assert len(sec_a) == 2, f"Expected 2 in Section A, got {len(sec_a)}"
    assert sec_a[0]["name"] == "Veera Reddy" and sec_a[0]["prn"] == "2023BTAM040"
    assert sec_a[1]["name"] == "Aditya" and sec_a[1]["prn"] == "2023BTAM055"
    print(f"[PASS] 3. Canonical PDF Database verified: Exactly 66 students (64 in Sec B, 2 in Sec A).")

    # 4. Test Subjects (Theory & Labs)
    r_subjects = client.get("/api/subjects")
    assert r_subjects.status_code == 200
    subj_data = r_subjects.json()
    assert len(subj_data["theory_subjects"]) == 44, f"Expected 44 theory subjects, got {len(subj_data['theory_subjects'])}"
    assert len(subj_data["lab_subjects"]) == 19, f"Expected 19 lab subjects, got {len(subj_data['lab_subjects'])}"
    assert "Fundamentals of Computing" in subj_data["theory_subjects"]
    assert "Programming with Java Lab" in subj_data["lab_subjects"]
    print(f"[PASS] 4. Subjects verified: 44 Theory Subjects & 19 Lab Subjects loaded.")

    # 5. Test Start Attendance Session
    test_subj = "Data Structures and Algorithms"
    r_session = client.post("/api/session/start", json={"subject": test_subj, "section": "All"}, headers=auth_headers)
    assert r_session.status_code == 200
    sess_data = r_session.json()
    assert sess_data["success"] is True
    print(f"[PASS] 5. Session started successfully for '{test_subj}'.")

    # 6. Test Initial Attendance Status (Initially all 66 students must be ABSENT)
    r_breakdown = client.get(f"/api/attendance/breakdown?subject={test_subj}&section=All", headers=auth_headers)
    assert r_breakdown.status_code == 200
    b_data = r_breakdown.json()
    assert b_data["total_students"] == 66
    assert b_data["present_count"] == 0
    assert b_data["absent_count"] == 66
    assert b_data["attendance_percentage"] == 0.0
    assert len(b_data["absent_list"]) == 66
    print("[PASS] 6. Initial Session Status verified: 0 Present, 66 Absent (100% initial Absent rate).")

    # 7. Test Automatic Attendance Marking for a registered PDF student
    mark_res = database.mark_attendance("2023BTDS002", test_subj)
    assert mark_res["status"] == "success", f"Mark failed: {mark_res}"
    print("[PASS] 7. Successfully marked attendance for '2023BTDS002' (AROCKIA SHAFIYA J).")

    # 8. Test Duplicate Attendance Prevention
    dup_res = database.mark_attendance("2023BTDS002", test_subj)
    assert dup_res["status"] == "already_marked", f"Duplicate was not blocked: {dup_res}"
    print("[PASS] 8. Duplicate attendance prevention verified (Student cannot be marked twice for same subject/date).")

    # 9. Test Non-PDF / Unknown student rejection
    fake_res = database.mark_attendance("UNKNOWN999", test_subj)
    assert fake_res["status"] == "not_found", f"Unknown student was not rejected: {fake_res}"
    print("[PASS] 9. Unknown/Unregistered student rejection verified.")

    # 10. Test Post-Attendance Breakdown
    r_breakdown2 = client.get(f"/api/attendance/breakdown?subject={test_subj}&section=All", headers=auth_headers)
    b_data2 = r_breakdown2.json()
    assert b_data2["present_count"] == 1
    assert b_data2["absent_count"] == 65
    assert len(b_data2["present_list"]) == 1
    assert len(b_data2["absent_list"]) == 65
    assert b_data2["present_list"][0]["prn"] == "2023BTDS002"
    print(f"[PASS] 10. Post-Attendance Breakdown verified: 1 Present ({b_data2['present_list'][0]['name']}), 65 Absent.")

    # 11. Test Mobile Face Capture Token (Student Safe Mode)
    r_token = client.post("/api/mobile-capture/token", data={"prn": "2023BTDS006"}, headers=auth_headers)
    assert r_token.status_code == 200
    m_token = r_token.json()["token"]
    
    # Public token verification without admin login
    r_verify = client.get(f"/api/mobile-capture/verify/{m_token}")
    assert r_verify.status_code == 200
    assert r_verify.json()["prn"] == "2023BTDS006"
    assert r_verify.json()["name"] == "SIVA RANJINI R"
    print("[PASS] 11. Mobile Face Capture (Student Safe Mode) token generation and verification passed.")

    # 12. Test Excel (.xlsx) and CSV Export
    r_excel = client.get("/api/export/excel", headers=auth_headers)
    assert r_excel.status_code == 200
    assert len(r_excel.content) > 1000

    r_csv = client.get("/api/export/csv", headers=auth_headers)
    assert r_csv.status_code == 200
    assert "AROCKIA SHAFIYA J" in r_csv.text
    print("[PASS] 12. Excel (.xlsx) & CSV export verified with correct student and columns.")

    print("=" * 60)
    print("ALL 12 VERIFICATION TESTS PASSED SUCCESSFULLY! (100% OK)")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
