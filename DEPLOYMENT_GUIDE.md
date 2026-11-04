# Deployment Guide: FACE RECOGNITION BASED ATTENDANCE MONITORING SYSTEM

This guide explains how to deploy and run your attendance monitoring system for free using two approaches:
1. **Option 1: Free Cloud Hosting on Render.com** (Web dashboard & remote access)
2. **Option 2: Ngrok Free Tunnel** (Recommended if using your laptop/classroom webcam directly)

---

## ⚠️ Important Note About Webcams on Cloud Servers
- Cloud servers (like Render, Railway, or Heroku) **do not have a physical webcam plugged into them**.
- Therefore, camera capture via `cv2.VideoCapture(0)` on the server won't find a hardware camera in the cloud.
- However, with **Render**, the web portal, records, reports, Excel downloads, and browser-side video streaming via `/api/process_frame` work.
- If you want the camera on your college PC/laptop to monitor students while still letting anyone access the web app online from their phones or laptops, **Option 2 (Ngrok)** is the easiest and most practical solution.

---

## Option 1: Deploy on Render.com (100% Free)

### Step 1: Push your project to GitHub

1. Open PowerShell and navigate to your project:
   ```powershell
   cd F:\AI-Attendance-System
   ```
2. Initialize Git and commit all files:
   ```powershell
   git init
   git add .
   git commit -m "FACE RECOGNITION BASED ATTENDANCE MONITORING SYSTEM"
   ```
3. Go to [GitHub.com](https://github.com) and create a new repository named:
   `face-recognition-attendance-system`
4. Link and push your repository:
   ```powershell
   git branch -M main
   git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/face-recognition-attendance-system.git
   git push -u origin main
   ```

---

### Step 2: Deploy on Render.com

1. Go to [https://render.com](https://render.com) and sign up / log in with your GitHub account.
2. Click **New +** in the top right corner and select **Web Service**.
3. Choose **Build and deploy from a Git repository** and connect your GitHub repo `face-recognition-attendance-system`.
4. Fill in the following deployment settings:
   - **Name**: `face-attendance-system` (or any custom name)
   - **Region**: Choose the closest region (e.g., Singapore or Frankfurt)
   - **Branch**: `main`
   - **Root Directory**: Leave blank
   - **Runtime**: `Python 3`
   - **Build Command**:
     ```bash
     pip install -r requirements.txt
     ```
   - **Start Command**:
     ```bash
     uvicorn main:app --host 0.0.0.0 --port $PORT
     ```
   - **Instance Type**: Select **Free** (512 MB RAM, 0.1 CPU)
5. Under **Environment Variables**, add:
   - `PYTHON_VERSION` = `3.10.12` or `3.11.8`
6. Click **Create Web Service**.
7. Render will build the project and deploy it. In 2–3 minutes, you will get a live URL like:
   `https://face-attendance-system.onrender.com`

---

## Option 2: Run with Free Ngrok Tunnel (Fastest & Best for Webcam)

If you are running the system on a college laptop or PC with a real webcam attached and want everyone to access it over the internet for free:

### 1-Click Method:
Double click:
```
F:\AI-Attendance-System\START_WITH_NGROK.bat
```

### Manual Command Method:
1. Sign up for a free account at [https://ngrok.com](https://ngrok.com)
2. Get your free authtoken from:
   [https://dashboard.ngrok.com/get-started/your-authtoken](https://dashboard.ngrok.com/get-started/your-authtoken)
3. Run in PowerShell:
   ```powershell
   cd F:\AI-Attendance-System
   python ngrok_run.py --token YOUR_NGROK_TOKEN
   ```
4. Ngrok will generate a secure public URL (e.g. `https://xxxx-xx-xx.ngrok-free.app`).
5. Share this URL with students or teachers. Any device connected to the internet can open the dashboard!

---

## Default Login Credentials
- **Admin Username**: `admin`
- **Admin Password**: `admin@123`
- **Student Registration Code**: `eduface2024`
