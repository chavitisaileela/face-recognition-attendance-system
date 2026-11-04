# 🎓 EduFace AI: Automatic Face Recognition Attendance System
### Certified Implementation using `STUDENTS DATA.pdf` as the Single Source of Truth

A complete, beginner-friendly, production-grade **AI Automatic Facial Recognition Attendance System** built with **Python, OpenCV, FastAPI, SQLite, HTML5, CSS3, JavaScript, Excel (.xlsx & .csv), and Google Sheets**.

---

## 📌 Single Source of Truth Guarantee

- The student database is strictly populated **ONLY from the uploaded `STUDENTS DATA.pdf`**.
- Exactly **66 students** (64 in Section B, 2 in Section A: Veera Reddy & Aditya).
- No students outside the PDF can be created, added, removed, or renamed.
- All 13 student portrait photographs present in the PDF were automatically extracted and initialized directly into their training datasets.

---

## 🚀 Complete Workflow Architecture

```
[ STUDENTS DATA.pdf ]
         │
         ▼
[ Canonical Student List (66) ]
         │
         ▼
[ Select Student ] ──► [ Admin Webcam / Mobile Capture Link ]
         │
         ▼
[ Capture Face Photos (15-20 frames) ]
         │
         ▼
[ Train Face Data (OpenCV LBPH + CLAHE) ]
         │
         ▼
[ Face Recognition Testing Stage ] ──► (Verify detection & confidence without marking attendance)
         │
         ▼
[ Select Subject & Section ] ──► (44 Theory Courses or 19 Practical Labs)
         │
         ▼
[ Start Attendance Session ]
         │
         ├───► Initially: All 66 students are ABSENT
         ├───► Live Camera detects student
         ├───► LBPH matches face against PDF student
         ├───► Automatically mark PRESENT (Name, PRN, Section, Date, Subject, Exact Time)
         ├───► Duplicate attendance blocked for same class/date
         └───► Unknown faces tagged "Unknown Face" and ignored
         │
         ▼
[ End Session & Reports ]
         ├───► Real-time Present & Absent student lists
         ├───► SQLite Database updated
         ├───► Excel (.xlsx) & CSV (.csv) synchronized
         └───► Google Sheets Webhook pushed in real time
```

---

## 🖥️ Separate Application Pages

1. **Login Page (`#login`)**:
   - Secure faculty/admin authentication with PBKDF2 password hashing.
   - Prevents unauthorized student access to admin features.
   - Default credentials: Username: `admin` | Password: `admin@123`.

2. **Dashboard Page (`#dashboard`)**:
   - Live camera scanner with OpenCV hardware streaming & browser webcam mode.
   - Statistical Counters: Total Class Students (66), Present Today, Absent Today, Attendance Percentage.
   - Real-time student card displaying recognized Name, PRN, Section, Status, and Exact Attendance Time.
   - Instant audio chime and green toast alert on recognition.

3. **Student List Page (`#students`)**:
   - Displays all 66 students from `STUDENTS DATA.pdf`: `S.No`, `PRN/ID`, `Name`, `Section`.
   - Registration status badge: `Face Not Registered`, `Photos Captured`, or `Training Completed`.
   - Action buttons: Admin Photo Capture or Quick Mobile Link generation.

4. **Student Face Capture Page (`#face-capture`)**:
   - Select student from PDF roster.
   - Option A: 15-frame webcam burst capture with visual progress bar.
   - Option B: Photo file upload.
   - Option C: Generate secure Mobile Camera Link.

5. **Mobile Face Capture Page (`#mobile-capture`)**:
   - **Student Safe Mode**: Opened by the student on their smartphone.
   - Tokenized, temporary access (expires in 2 hours).
   - Allows granting camera permission, capturing 15 face angles, and submitting.
   - **Students cannot edit attendance, subjects, student details, or other students' data.**

6. **Face Training Page (`#face-training`)**:
   - Reviews captured photos across students.
   - 1-click execution: trains OpenCV LBPH Face Recognizer with CLAHE lighting normalization.
   - Saves model to `models/trainer.yml`.

7. **Face Recognition Testing Stage (`#face-testing`)**:
   - Dedicated stage before starting an attendance session.
   - Continuously recognizes registered students and displays Name, PRN, Section, and Match Confidence.
   - **Crucial Rule: NO attendance records are marked or saved during this stage.**

8. **Subjects Page (`#subjects`)**:
   - Complete curriculum browser with separate tabs:
     - **44 Theory Subjects**: Fundamentals of Computing, Introduction to Programming, Mathematics 1, Mathematics 2, Physics 1, Physics 2, First Aid Basics, Effective Communications, Arts and Sports, Discrete Structures for Computer Science, English for Career Development, Environmental Studies, Artificial Intelligence, Signals and Systems, Digital Design, Data Structures and Algorithms, Object Oriented Programming, Professional Ethics, Indian Constitution, Introduction to Data Science and Data Analytics, DBMS, DAA, Computer Organization, Operating Systems, Economics, Deep Learning, Computer Networking, Computer Architecture, Software Engineering, Programming with Java, Theory of Computation, Principles of Management, AI in Human Resources, Predictive Analysis, Compiler Design, Cryptography and Network Security, Data Visualization, Computer Vision, High Performance Computing, Pattern Recognition, Web Technology, Digital Marketing, AI Ethics and Policy, NPTEL Extra Class.
     - **19 Practical Labs**: Fundamentals of Computing Lab, Introduction to Programming Lab, Python Programming Lab, Physics 1 Lab, Physics 2 Lab, Digital Design Lab, DSA Lab, OOPS Lab, Introduction to Data Science Lab, DBMS Lab, DAA Lab, Deep Learning Lab, Computer Networks Lab, Java Lab, AR/VR Lab, Predictive Analysis Lab, Compiler Design Lab, Web Technology Lab, HPC Lab.

9. **Start Attendance Page (`#start-attendance`)**:
   - Session launcher: select Subject (Theory / Lab) and Section (All / Section B / Section A).
   - Initializes active attendance session.

10. **Attendance Records Page (`#attendance-records`)**:
    - Filter by Subject, Date, and Section.
    - Separate **Present Students Tab** (Only recognized students from the PDF).
    - Separate **Absent Students Tab** (Students from the PDF pending recognition).
    - Raw attendance logs table.

11. **Export Page (`#export`)**:
    - 📥 Download Excel (`attendance_records.xlsx`) with columns:
      `Name, PRN/Roll Number, Section, Date, Subject, Time, Attendance Status`.
    - 📄 Download CSV (`attendance_records.csv`).
    - 📊 Download Detailed Session Report with separate Present and Absent sheets.
    - 🌐 Real-time Google Sheets Webhook Configuration.

---

## ⚡ Installation & Execution Guide

### 1. Navigate to Project Directory:
```powershell
cd "C:\Users\chavi\.gemini\antigravity\scratch\ai-attendance-system"
```

### 2. Install Required Packages:
```powershell
pip install -r requirements.txt
```

### 3. Run the Automated Verification Suite:
```powershell
python test_system.py
```
*(All 12 automated verification tests will run and display `100% OK`)*

### 4. Start the Application:
```powershell
python main.py
```
*(Or run `uvicorn main:app --reload --host 127.0.0.1 --port 8000`)*

### 5. Access the Web Dashboard:
Open your browser and navigate to:
```
http://127.0.0.1:8000
```

---

## 🌐 2-Minute Google Sheets Real-Time Sync

1. Open [Google Sheets](https://sheets.new) and name the spreadsheet **Attendance Records**.
2. Click **Extensions** > **Apps Script**.
3. Replace the script editor content with:
```javascript
function doPost(e) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var data = JSON.parse(e.postData.contents);
  sheet.appendRow([data.name, data.prn, data.section, data.date, data.subject, data.time, data.status]);
  return ContentService.createTextOutput(JSON.stringify({status: "success"})).setMimeType(ContentService.MimeType.JSON);
}
```
4. Click **Deploy** > **New deployment** > Type: **Web app** > Access: **Anyone** > Deploy.
5. Copy the generated Web App URL, paste it into the **Export & Settings** page in the EduFace dashboard, and click **Save Synchronization Settings**.
6. Every recognized student will instantly be inserted into your Google Sheet in real time!

---

## 🎓 College Viva & Defense Questions

| Question | Examiner Answer |
| :--- | :--- |
| **How is the student database locked to `STUDENTS DATA.pdf`?** | The canonical database is initialized exclusively from `pdf_students.py` which extracts and seeds all 66 students. Endpoints to add, edit, or remove students are prohibited, ensuring absolute immutability. |
| **Why is there a separate Face Testing stage before Attendance?** | The testing stage allows the faculty to verify camera illumination, bounding box alignment, and recognition confidence without writing accidental false records into the attendance database or spreadsheet. |
| **How does Mobile Face Capture maintain security?** | Students receive a scoped temporary token (`/mobile-capture?token=...`). The mobile interface exposes ONLY camera permission and photo submission for that specific student. The student has zero access to attendance records, subjects, or other students' information. |
| **How are duplicates prevented?** | At the database layer, SQLite enforces `UNIQUE(prn, date, subject)`. At the engine layer, an in-memory 8-second debounce suppresses repeated database writes when a student remains in front of the camera. |
| **How are absent students determined?** | For any selected subject and class section, all students in `STUDENTS DATA.pdf` are initially marked as `ABSENT`. When a student's face is recognized, their record is added to SQLite as `PRESENT`. Students without a matching record for that subject and date remain in the `Absent List`. |
