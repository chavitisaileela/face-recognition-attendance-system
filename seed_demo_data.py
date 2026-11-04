"""
Seed demo data for AI Automatic Attendance System.
Populates initial students, attendance records, and generates the initial Excel file.
"""

from datetime import datetime, timedelta
import database
import sheet_sync

def seed():
    print("Seeding database with demo students and attendance...")
    database.init_db()

    students = [
        ("CS2024-001", "Alex Johnson", "Computer Science"),
        ("CS2024-002", "Emily Watson", "Information Technology"),
        ("CS2024-003", "Rahul Sharma", "Computer Science"),
        ("CS2024-004", "Priya Patel", "Artificial Intelligence"),
        ("CS2024-005", "Michael Chang", "Computer Science")
    ]

    for roll, name, dept in students:
        sid, err = database.add_student(roll, name, dept)
        if sid:
            print(f"  + Added student: {name} ({roll})")
        else:
            print(f"  - Student {roll} already exists ({err})")

    # Add demo attendance records for today
    today = datetime.now().strftime("%Y-%m-%d")
    subject = "Computer Science 101"

    demo_records = [
        ("CS2024-001", "09:05:12"),
        ("CS2024-003", "09:12:44"),
        ("CS2024-004", "09:18:02")
    ]

    for roll, t_str in demo_records:
        res = database.mark_attendance(roll, subject, date_str=today, time_str=t_str)
        if res["status"] == "success":
            print(f"  + Marked attendance for {roll} at {t_str}")
            sheet_sync.sync_attendance_record(res["record"])
        elif res["status"] == "already_marked":
            print(f"  . {roll} already marked for today")

    print("\nDatabase and Excel files seeded successfully!")
    print(f"Excel file created at: {sheet_sync.EXCEL_PATH}")
    print(f"CSV file created at: {sheet_sync.CSV_PATH}")

if __name__ == "__main__":
    seed()
