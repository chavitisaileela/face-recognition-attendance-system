/**
 * EduFace AI Attendance System — Frontend v3
 * Performance optimized: camera OFF by default, frame skipping, dynamic-only updates.
 */

// ─── Application State ─────────────────────────────────────────────────────
const state = {
  authToken: localStorage.getItem("auth_token") || null,
  currentUser: null,
  activeSubject: "",
  activeSection: "All",
  activeFaculty: "",
  activePeriod: 1,
  sessionId: "",
  isSessionActive: false,
  allStudents: [],
  theorySubjects: [],
  labSubjects: [],
  periods: [],
  dashCamMode: "hardware",   // "hardware" | "browser"
  testCamMode: "hardware",
  audioEnabled: true,
  lastEventKey: null,
  pollTimer: null,
  browserStream: null,
  testBrowserStream: null,
  isProcessingBrowser: false,
  browserFrameCounter: 0,    // For frame skipping in browser mode
  cameraRunning: false       // True when img.src or browser stream is active
};

// ─── API Helper ─────────────────────────────────────────────────────────────
async function apiFetch(url, options = {}) {
  options.headers = options.headers || {};
  if (state.authToken) {
    options.headers["Authorization"] = `Bearer ${state.authToken}`;
  }
  const res = await fetch(url, options);
  if (res.status === 401 && !location.hash.startsWith("#mobile-capture")) {
    state.authToken = null;
    localStorage.removeItem("auth_token");
    navigateTo("pageLogin");
  }
  return res;
}

// ─── Audio Chime ─────────────────────────────────────────────────────────────
function playAttendanceChime() {
  if (!state.audioEnabled) return;
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const playTone = (freq, start, dur) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(freq, ctx.currentTime + start);
      gain.gain.setValueAtTime(0, ctx.currentTime + start);
      gain.gain.linearRampToValueAtTime(0.3, ctx.currentTime + start + 0.03);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + start + dur);
      osc.connect(gain); gain.connect(ctx.destination);
      osc.start(ctx.currentTime + start);
      osc.stop(ctx.currentTime + start + dur);
    };
    playTone(698.46, 0.0, 0.35);
    playTone(880.00, 0.12, 0.55);
  } catch (e) {}
}

// ─── Live Clock ─────────────────────────────────────────────────────────────
// ─── Voice Speech Synthesis ───────────────────────────────────────────────
function speakText(text) {
  if (!state.audioEnabled) return;
  if (!("speechSynthesis" in window)) return;
  try {
    window.speechSynthesis.cancel(); // Stop any pending speech
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;
    utterance.volume = 1.0;
    window.speechSynthesis.speak(utterance);
  } catch (e) {
    console.warn("Speech synthesis error:", e);
  }
}

// ─── Live Clock ─────────────────────────────────────────────────────────────
function initLiveClock() {
  const clockEl = document.getElementById("liveClock");
  const update = () => {
    const now = new Date();
    clockEl.innerHTML = `<span class="live-dot"></span> ${now.toLocaleTimeString()}`;
  };
  update();
  setInterval(update, 1000);
}

// ─── Navigation / Router ─────────────────────────────────────────────────────
function navigateTo(pageId) {
  // Allow public access to Login, Register, About, and Mobile Capture
  const publicPages = ["pageLogin", "pageRegister", "pageAbout", "pageMobileCapture"];
  if (!state.authToken && !publicPages.includes(pageId)) {
    pageId = "pageLogin";
  }
  document.querySelectorAll(".page-view").forEach(p => p.classList.remove("active"));
  const target = document.getElementById(pageId);
  if (target) target.classList.add("active");

  document.querySelectorAll(".nav-link").forEach(l => {
    l.classList.toggle("active", l.dataset.page === pageId);
  });

  // Lifecycle hooks
  if (pageId === "pageDashboard")       loadDashboardSession();
  if (pageId === "pageStudents")        loadStudentList();
  if (pageId === "pageCapture")         initCapturePage();
  if (pageId === "pageSubjects")        loadSubjects();
  if (pageId === "pageStartAttendance") initStartSessionPage();
  if (pageId === "pageRecords")         loadAttendanceBreakdown();
  if (pageId === "pageTraining")        loadTrainingStats();
}

function handleHashChange() {
  const rawHash = location.hash || "#dashboard";
  let hash = rawHash, params = new URLSearchParams();
  if (rawHash.includes("?")) {
    const parts = rawHash.split("?");
    hash = parts[0];
    params = new URLSearchParams(parts[1]);
  }

  const map = {
    "#login": "pageLogin", "#register": "pageRegister", "#about": "pageAbout",
    "#dashboard": "pageDashboard", "#students": "pageStudents",
    "#face-capture": "pageCapture", "#face-training": "pageTraining",
    "#face-testing": "pageTesting", "#subjects": "pageSubjects",
    "#start-attendance": "pageStartAttendance", "#attendance-records": "pageRecords",
    "#export": "pageExport"
  };
  if (hash === "#mobile-capture") {
    navigateTo("pageMobileCapture");
    initMobileCapturePage(params.get("token"));
  } else {
    navigateTo(map[hash] || (state.authToken ? "pageDashboard" : "pageLogin"));
  }
}

// ─── Authentication & Registration ──────────────────────────────────────────
function setupAuth() {
  // Login Form
  document.getElementById("loginForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const u = document.getElementById("loginUsername").value.trim();
    const p = document.getElementById("loginPassword").value.trim();
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: u, password: p })
      });
      const data = await res.json();
      if (res.ok) {
        state.authToken = data.token;
        state.currentUser = data.user;
        localStorage.setItem("auth_token", data.token);
        document.getElementById("navUserName").textContent = data.user.name;
        showToast(data.message, "success");
        speakText(`Welcome ${data.user.name}`);
        location.hash = "#dashboard";
      } else {
        showToast(data.detail || "Authentication failed", "error");
      }
    } catch (err) {
      showToast("Login error: " + err.message, "error");
    }
  });

  // Register Form
  const regForm = document.getElementById("registerForm");
  if (regForm) {
    regForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const name = document.getElementById("regFullName").value.trim();
      const username = document.getElementById("regUsername").value.trim();
      const password = document.getElementById("regPassword").value.trim();
      const admin_secret = document.getElementById("regAdminSecret").value.trim();

      try {
        const res = await fetch("/api/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, username, password, admin_secret })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(data.message || "Registration successful! Signing you in...", "success");
          speakText("Registration successful");
          // Automatically log the new faculty in
          const loginRes = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password })
          });
          const loginData = await loginRes.json();
          if (loginRes.ok) {
            state.authToken = loginData.token;
            state.currentUser = loginData.user;
            localStorage.setItem("auth_token", loginData.token);
            document.getElementById("navUserName").textContent = loginData.user.name;
            location.hash = "#dashboard";
          } else {
            location.hash = "#login";
          }
        } else {
          showToast(data.detail || "Registration failed", "error");
        }
      } catch (err) {
        showToast("Registration error: " + err.message, "error");
      }
    });
  }

  // Sample Trial Voice Buttons on About Page
  const btnVoicePresent = document.getElementById("btnTestVoicePresent");
  if (btnVoicePresent) {
    btnVoicePresent.onclick = () => speakText("Aman Kumar Present");
  }
  const btnVoiceWrong = document.getElementById("btnTestVoiceWrong");
  if (btnVoiceWrong) {
    btnVoiceWrong.onclick = () => speakText("Absent, wrong face detected");
  }

  // Top Nav Menu Toggle Button
  const btnMenu = document.getElementById("btnNavMenuToggle");
  const navGrid = document.getElementById("adminNavLinks");
  if (btnMenu && navGrid) {
    btnMenu.onclick = (e) => {
      e.stopPropagation();
      navGrid.classList.toggle("open");
    };
    document.addEventListener("click", (e) => {
      if (!navGrid.contains(e.target) && !btnMenu.contains(e.target)) {
        navGrid.classList.remove("open");
      }
    });
    navGrid.querySelectorAll(".nav-link").forEach(link => {
      link.addEventListener("click", () => {
        navGrid.classList.remove("open");
      });
    });
  }

  document.getElementById("btnLogout").addEventListener("click", async () => {
    stopAllCameras();
    await apiFetch("/api/auth/logout", { method: "POST" });
    state.authToken = null;
    state.isSessionActive = false;
    localStorage.removeItem("auth_token");
    showToast("Logged out.", "info");
    location.hash = "#login";
  });
}

// ─── Dashboard ────────────────────────────────────────────────────────────────
async function loadDashboardSession() {
  try {
    const res = await fetch("/api/session/status");
    if (!res.ok) return;
    const data = await res.json();

    state.activeSubject = data.active_subject;
    state.activeSection = data.active_section;
    state.activeFaculty = data.faculty_name;
    state.activePeriod = data.period;
    state.sessionId = data.session_id;
    state.isSessionActive = data.is_session_active;

    // Update stat cards
    document.getElementById("dashActiveSubject").textContent = data.active_subject || "No Active Session";
    document.getElementById("dashActiveSection").textContent = `Section: ${data.active_section}`;

    const st = data.stats;
    document.getElementById("dashTotalStudents").textContent = st.total_students;
    document.getElementById("dashPresentStudents").textContent = st.present_count;
    document.getElementById("dashAbsentStudents").textContent = st.absent_count;
    document.getElementById("dashAttendancePct").textContent = `${st.attendance_percentage}% Attendance`;

    // Update session banner
    const banner = document.getElementById("sessionBanner");
    if (data.is_session_active) {
      banner.style.display = "flex";
      document.getElementById("bannerSubject").textContent = data.active_subject;
      document.getElementById("bannerSection").textContent = data.active_section;
      document.getElementById("bannerPeriod").textContent = `Period ${data.period}`;
      document.getElementById("bannerFaculty").textContent = data.faculty_name || "—";
      document.getElementById("dashHudSubjectBadge").textContent = data.active_subject;
      document.getElementById("dashHudOverlay").style.display = "flex";
    } else {
      banner.style.display = "none";
      document.getElementById("dashHudOverlay").style.display = "none";
      // Turn off camera if no active session
      if (state.cameraRunning) {
        stopCameraStream();
      }
    }
  } catch (e) {
    console.warn("loadDashboardSession error:", e);
  }
}

// ─── Dashboard Polling ────────────────────────────────────────────────────────
async function pollDashboard() {
  const h = location.hash;
  if (h && h !== "#dashboard" && h !== "" && h !== "#") return;
  try {
    await loadDashboardSession();

    if (!state.isSessionActive) return;

    const evRes = await fetch("/api/recent_events");
    if (!evRes.ok) return;
    const evData = await evRes.json();
    const events = evData.events || [];
    if (events.length > 0) {
      const latest = events[0];
      const key = `${latest.prn}_${latest.time}_${latest.action}`;
      if (state.lastEventKey !== key) {
        state.lastEventKey = key;
        updateDashboardStudentCard(latest);
        if (latest.action === "new_attendance") {
          playAttendanceChime();
          speakText(`${latest.name} Present`);
          showPresentOverlay(latest.name, latest.prn, latest.confidence);
          showToast(`✔ PRESENT: ${latest.name} (${latest.prn}) – Sec ${latest.section}`, "success");
        } else if (latest.action === "already_marked") {
          showToast(`Already marked: ${latest.name} (${latest.prn})`, "warning");
        } else if (latest.action === "unknown_face") {
          speakText("Absent, wrong face detected");
          showToast(`⚠️ Absent: Wrong face detected!`, "warning");
        }
      }
    }
  } catch (err) {
    console.warn("Poll error:", err);
  }
}

function updateDashboardStudentCard(s) {
  document.getElementById("dashStudentName").textContent = s.name || "Unknown";
  document.getElementById("dashStudentPRN").textContent = `PRN: ${s.prn || "N/A"}`;
  document.getElementById("dashStudentSection").textContent = `Sec: ${s.section || "B"}`;
  document.getElementById("dashStudentTime").textContent = `PRESENT at ${s.time} — ${s.subject}`;
  document.getElementById("dashStudentAvatar").textContent = (s.name || "S").charAt(0).toUpperCase();
  const conf = s.confidence;
  document.getElementById("dashConfidenceBadge").textContent = conf ? `Match confidence: ${conf}%` : "";
  const card = document.getElementById("dashRecognitionCard");
  card.style.transform = "scale(1.02)";
  setTimeout(() => card.style.transform = "scale(1)", 200);
}

// PRESENT announcement overlay
let overlayTimer = null;
function showPresentOverlay(name, prn, confidence) {
  const overlay = document.getElementById("presentOverlay");
  document.getElementById("overlayStudentName").textContent = name;
  document.getElementById("overlayStudentPRN").textContent = `PRN: ${prn}`;
  overlay.style.display = "flex";
  if (overlayTimer) clearTimeout(overlayTimer);
  overlayTimer = setTimeout(() => { overlay.style.display = "none"; }, 3500);
}

// ─── Camera Management ────────────────────────────────────────────────────────
function startCameraStream(mode = "attendance") {
  const imgDash = document.getElementById("dashStreamImg");
  const cameraOff = document.getElementById("dashCameraOff");
  imgDash.src = `/api/video_feed?mode=${mode}&t=${Date.now()}`;
  imgDash.style.display = "block";
  cameraOff.style.display = "none";
  state.cameraRunning = true;
}

function stopCameraStream() {
  const imgDash = document.getElementById("dashStreamImg");
  const cameraOff = document.getElementById("dashCameraOff");
  imgDash.src = "";
  imgDash.style.display = "none";
  cameraOff.style.display = "flex";
  if (state.browserStream) {
    state.browserStream.getTracks().forEach(t => t.stop());
    state.browserStream = null;
  }
  state.cameraRunning = false;
  state.dashCamMode = "hardware";
  document.getElementById("btnDashHwCam").classList.add("active");
  document.getElementById("btnDashBrowserCam").classList.remove("active");
  const videoDash = document.getElementById("dashBrowserVideo");
  videoDash.srcObject = null;
  videoDash.style.display = "none";
}

function stopAllCameras() {
  stopCameraStream();
  stopTestCamera();
}

// ─── Session Control ──────────────────────────────────────────────────────────
async function stopAttendanceSession() {
  const res = await apiFetch("/api/session/stop", { method: "POST" });
  const data = await res.json();
  if (res.ok) {
    state.isSessionActive = false;
    state.sessionId = "";
    stopCameraStream();
    document.getElementById("sessionBanner").style.display = "none";
    document.getElementById("dashHudOverlay").style.display = "none";
    showToast("Attendance session stopped.", "info");
    await loadDashboardSession();
    // Update start-attendance page stop button visibility
    document.getElementById("btnStopSessionForm").style.display = "none";
    document.getElementById("activeSessionInfo").style.display = "none";
  }
}

// ─── Student List ─────────────────────────────────────────────────────────────
async function loadStudentList() {
  const sec = document.getElementById("studentListSectionFilter").value;
  const search = document.getElementById("studentListSearch").value.toLowerCase();
  try {
    const res = await apiFetch(`/api/students?section=${encodeURIComponent(sec)}`);
    const data = await res.json();
    state.allStudents = data.students || [];
    const filtered = state.allStudents.filter(s =>
      s.name.toLowerCase().includes(search) || s.prn.toLowerCase().includes(search)
    );
    const tbody = document.getElementById("studentListTableBody");
    tbody.innerHTML = "";
    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:2rem;">No students found.</td></tr>`;
      return;
    }
    filtered.forEach(s => {
      let sc = "status-not-registered";
      if (s.face_status === "Photos Captured") sc = "status-captured";
      if (s.face_status === "Training Completed") sc = "status-trained";
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${s.s_no}</td>
        <td><strong style="color:#93c5fd;font-family:monospace;">${escapeHtml(s.prn)}</strong></td>
        <td><strong>${escapeHtml(s.name)}</strong></td>
        <td><span class="section-badge">${escapeHtml(s.section)}</span></td>
        <td><span class="badge-status ${sc}">${escapeHtml(s.face_status)}</span></td>
        <td>${s.photo_count} photos</td>
        <td style="display:flex;gap:0.4rem;">
          <button class="btn btn-outline" style="font-size:0.75rem;padding:0.25rem 0.55rem;" onclick="selectStudentForCapture('${escapeHtml(s.prn)}')">📷 Capture</button>
          <button class="btn btn-primary" style="font-size:0.75rem;padding:0.25rem 0.55rem;" onclick="generateQuickMobileLink('${escapeHtml(s.prn)}')">📱 Mobile</button>
        </td>`;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("loadStudentList error:", err);
  }
}

function selectStudentForCapture(prn) {
  location.hash = "#face-capture";
  setTimeout(() => {
    const sel = document.getElementById("captureStudentSelect");
    sel.value = prn;
    sel.dispatchEvent(new Event("change"));
  }, 200);
}

async function generateQuickMobileLink(prn) {
  try {
    const fd = new FormData(); fd.append("prn", prn);
    const res = await apiFetch("/api/mobile-capture/token", { method: "POST", body: fd });
    const data = await res.json();
    if (res.ok) {
      const fullUrl = `${location.origin}/#mobile-capture?token=${data.token}`;
      navigator.clipboard.writeText(fullUrl);
      showToast(`Copied link for ${data.name}!`, "success");
    }
  } catch (e) { showToast("Error: " + e.message, "error"); }
}

// ─── Face Capture Page ────────────────────────────────────────────────────────
let adminCaptureStream = null;
let adminCapturedImages = [];

async function initCapturePage() {
  const sel = document.getElementById("captureStudentSelect");
  if (sel.options.length <= 1) {
    const res = await apiFetch("/api/students");
    const data = await res.json();
    sel.innerHTML = `<option value="">-- Choose a Student --</option>`;
    (data.students || []).forEach(s => {
      const opt = document.createElement("option");
      opt.value = s.prn;
      opt.textContent = `${s.s_no}. ${s.name} (${s.prn}) – Sec ${s.section}`;
      sel.appendChild(opt);
    });
  }

  // Remove old listener by replacing with clone
  const newSel = sel.cloneNode(true);
  sel.parentNode.replaceChild(newSel, sel);
  newSel.addEventListener("change", async () => {
    if (!newSel.value) return;
    const res = await apiFetch(`/api/students/${newSel.value}`);
    const data = await res.json();
    document.getElementById("capStudentName").textContent = data.name;
    document.getElementById("capStudentPRN").textContent = data.prn;
    document.getElementById("capStudentSection").textContent = data.section;
    document.getElementById("capStudentStatus").textContent = `${data.face_status} (${data.photo_count} photos)`;
  });

  // Webcam Capture
  const btnCapture = document.getElementById("btnAdminStartCapture");
  const video = document.getElementById("adminCaptureVideo");
  const canvas = document.getElementById("adminCaptureCanvas");
  const pBar = document.getElementById("adminCaptureProgressBar");
  const pBox = document.getElementById("adminCaptureProgress");
  const pStatus = document.getElementById("adminCaptureStatus");

  btnCapture.onclick = async () => {
    const prn = newSel.value;
    if (!prn) { showToast("Select a student first.", "warning"); return; }
    adminCapturedImages = [];
    pBox.style.display = "block"; pBar.style.width = "0%";
    pStatus.textContent = "Starting camera...";
    try {
      adminCaptureStream = await navigator.mediaDevices.getUserMedia({ video: { width: 480, height: 480 } });
      video.srcObject = adminCaptureStream; video.style.display = "block"; video.play();
      btnCapture.disabled = true;
      let count = 0; const total = 15;
      const interval = setInterval(async () => {
        if (count >= total) {
          clearInterval(interval);
          adminCaptureStream.getTracks().forEach(t => t.stop()); video.style.display = "none";
          btnCapture.disabled = false;
          pStatus.textContent = "Uploading photos...";
          const saveRes = await apiFetch("/api/students/photos", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ prn, images: adminCapturedImages })
          });
          const saveData = await saveRes.json();
          showToast(saveData.message, saveRes.ok ? "success" : "error");
          pStatus.innerHTML = saveRes.ok
            ? `<span style="color:#34d399;font-weight:600;">&#10003; ${saveData.saved_count} photos saved! Please train the model.</span>`
            : saveData.detail || "Upload error";
          newSel.dispatchEvent(new Event("change"));
          return;
        }
        canvas.width = 320; canvas.height = 320;
        canvas.getContext("2d").drawImage(video, 0, 0, 320, 320);
        adminCapturedImages.push(canvas.toDataURL("image/jpeg", 0.85));
        count++; pBar.style.width = `${Math.round(count / total * 100)}%`;
        pStatus.textContent = `Capturing ${count}/${total}...`;
      }, 200);
    } catch (err) {
      showToast("Camera error: " + err.message, "error");
      btnCapture.disabled = false; pBox.style.display = "none";
    }
  };

  document.getElementById("btnAdminUploadSubmit").onclick = async () => {
    const prn = newSel.value;
    const fileInput = document.getElementById("adminUploadPhotos");
    if (!prn) { showToast("Select a student first.", "warning"); return; }
    if (!fileInput.files.length) { showToast("Select photo files.", "warning"); return; }
    const b64List = [];
    for (let f of fileInput.files) { b64List.push(await toBase64(f)); }
    const saveRes = await apiFetch("/api/students/photos", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prn, images: b64List })
    });
    const saveData = await saveRes.json();
    showToast(saveData.message, "success");
    fileInput.value = ""; newSel.dispatchEvent(new Event("change"));
  };

  document.getElementById("btnGenMobileLink").onclick = async () => {
    const prn = newSel.value;
    if (!prn) { showToast("Select a student first.", "warning"); return; }
    const fd = new FormData(); fd.append("prn", prn);
    const res = await apiFetch("/api/mobile-capture/token", { method: "POST", body: fd });
    const data = await res.json();
    if (res.ok) {
      const fullUrl = `${location.origin}/#mobile-capture?token=${data.token}`;
      document.getElementById("mobileLinkInput").value = fullUrl;
      document.getElementById("mobileLinkOutput").style.display = "block";
    }
  };

  document.getElementById("btnCopyMobileLink").onclick = () => {
    navigator.clipboard.writeText(document.getElementById("mobileLinkInput").value);
    showToast("Mobile link copied!", "success");
  };
}

// ─── Mobile Capture Page ──────────────────────────────────────────────────────
let mobStream = null, mobCapturedImages = [];

async function initMobileCapturePage(token) {
  document.getElementById("adminNavLinks").style.display = "none";
  document.getElementById("userBadgeArea").style.display = "none";
  if (!token) { showToast("No authorization token.", "error"); return; }
  try {
    const res = await fetch(`/api/mobile-capture/verify/${token}`);
    const data = await res.json();
    if (!res.ok) {
      document.getElementById("mobStudentName").textContent = "Expired Token";
      showToast(data.detail || "Invalid link.", "error"); return;
    }
    document.getElementById("mobStudentName").textContent = data.name;
    document.getElementById("mobStudentPRN").textContent = data.prn;
    document.getElementById("mobStudentSection").textContent = data.section;

    const btnStart = document.getElementById("btnMobStartCamera");
    const btnCap = document.getElementById("btnMobCapture");
    const btnSub = document.getElementById("btnMobSubmit");
    const video = document.getElementById("mobCaptureVideo");
    const canvas = document.getElementById("mobCaptureCanvas");
    const pBar = document.getElementById("mobCaptureProgressBar");
    const pBox = document.getElementById("mobCaptureProgress");
    const pStatus = document.getElementById("mobCaptureStatus");

    btnStart.onclick = async () => {
      try {
        mobStream = await navigator.mediaDevices.getUserMedia({ video: { width: 480, height: 480, facingMode: "user" } });
        video.srcObject = mobStream; video.style.display = "block"; video.play();
        btnStart.style.display = "none"; btnCap.style.display = "flex";
      } catch (e) { showToast("Camera permission denied: " + e.message, "error"); }
    };

    btnCap.onclick = () => {
      mobCapturedImages = []; pBox.style.display = "block"; pBar.style.width = "0%"; btnCap.disabled = true;
      let count = 0; const total = 15;
      const interval = setInterval(() => {
        if (count >= total) {
          clearInterval(interval);
          pStatus.innerHTML = `<span style="color:#34d399;font-weight:600;">&#10003; ${total} photos captured! Click Submit below.</span>`;
          btnCap.style.display = "none"; btnSub.style.display = "flex"; return;
        }
        canvas.width = 300; canvas.height = 300;
        canvas.getContext("2d").drawImage(video, 0, 0, 300, 300);
        mobCapturedImages.push(canvas.toDataURL("image/jpeg", 0.85));
        count++; pBar.style.width = `${Math.round(count / total * 100)}%`;
        pStatus.textContent = `Capturing ${count}/${total}... Look slightly left, right, center.`;
      }, 200);
    };

    btnSub.onclick = async () => {
      btnSub.disabled = true; btnSub.textContent = "Submitting...";
      try {
        const subRes = await fetch("/api/mobile-capture/submit", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token, images: mobCapturedImages })
        });
        const subData = await subRes.json();
        if (subRes.ok) {
          if (mobStream) mobStream.getTracks().forEach(t => t.stop());
          video.style.display = "none"; btnSub.style.display = "none";
          pStatus.innerHTML = `<h3 style="color:#34d399;">${subData.message}</h3><p>You may close this page.</p>`;
        } else {
          showToast(subData.detail || "Submission failed", "error");
          btnSub.disabled = false; btnSub.textContent = "🚀 Submit Face Data";
        }
      } catch (err) { showToast("Error: " + err.message, "error"); btnSub.disabled = false; }
    };
  } catch (err) { showToast("Mobile error: " + err.message, "error"); }
}

// ─── Face Training Page ───────────────────────────────────────────────────────
async function loadTrainingStats() {
  const res = await apiFetch("/api/students");
  const data = await res.json();
  const students = data.students || [];
  const withPhotos = students.filter(s => s.photo_count > 0);
  const totalPhotos = withPhotos.reduce((a, b) => a + b.photo_count, 0);
  document.getElementById("trainStudentCount").textContent =
    `${withPhotos.length} students — ${totalPhotos} total photos`;

  document.getElementById("btnExecuteTraining").onclick = async () => {
    const btn = document.getElementById("btnExecuteTraining");
    const msg = document.getElementById("trainProgressMsg");
    btn.disabled = true; btn.textContent = "Training...";
    msg.textContent = "Training LBPH model — this may take 30–60 seconds...";
    try {
      const tRes = await apiFetch("/api/train", { method: "POST" });
      const tData = await tRes.json();
      if (tRes.ok && tData.success) {
        showToast(tData.message, "success");
        msg.innerHTML = `<strong style="color:#34d399;">&#10003; ${tData.message}</strong>`;
        document.getElementById("trainStatusBadge").innerHTML = "&#10003; Trained &amp; Ready";
      } else {
        showToast(tData.message || "Training error", "warning");
        msg.textContent = tData.message;
      }
    } catch (e) { showToast("Error: " + e.message, "error"); }
    finally { btn.disabled = false; btn.textContent = "🚀 Start Training"; }
  };
}

// ─── Subjects Page ────────────────────────────────────────────────────────────
async function loadSubjects() {
  if (state.theorySubjects.length && state.labSubjects.length) {
    renderSubjectCards(); return;
  }
  const res = await fetch("/api/subjects");
  const data = await res.json();
  state.theorySubjects = data.theory_subjects;
  state.labSubjects = data.lab_subjects;
  renderSubjectCards();
  document.getElementById("subjectSearchInput").oninput = e => renderSubjectCards(e.target.value.toLowerCase());
}

function renderSubjectCards(query = "") {
  const gT = document.getElementById("subjectsGridTheory");
  const gL = document.getElementById("subjectsGridLabs");
  gT.innerHTML = ""; gL.innerHTML = "";
  state.theorySubjects.filter(s => s.toLowerCase().includes(query)).forEach(s => {
    const card = document.createElement("div"); card.className = "subject-card";
    card.innerHTML = `<h4>${escapeHtml(s)}</h4><span class="sub-tag">Theory &bull; Click to select</span>`;
    card.onclick = () => selectSubjectAndLaunch(s, "theory");
    gT.appendChild(card);
  });
  state.labSubjects.filter(s => s.toLowerCase().includes(query)).forEach(s => {
    const card = document.createElement("div"); card.className = "subject-card";
    card.innerHTML = `<h4>${escapeHtml(s)}</h4><span class="sub-tag">Lab &bull; Click to select</span>`;
    card.onclick = () => selectSubjectAndLaunch(s, "lab");
    gL.appendChild(card);
  });
}

function switchSubjectTab(tab) {
  document.getElementById("tabBtnTheory").classList.toggle("active", tab === "theory");
  document.getElementById("tabBtnLabs").classList.toggle("active", tab === "labs");
  document.getElementById("subjectsGridTheory").style.display = tab === "theory" ? "grid" : "none";
  document.getElementById("subjectsGridLabs").style.display = tab === "labs" ? "grid" : "none";
}

function selectSubjectAndLaunch(subjName, cat) {
  location.hash = "#start-attendance";
  setTimeout(() => {
    document.getElementById("sessionCategorySelect").value = cat;
    document.getElementById("sessionCategorySelect").dispatchEvent(new Event("change"));
    document.getElementById("sessionSubjectSelect").value = subjName;
  }, 150);
}

// ─── Start Attendance Page ────────────────────────────────────────────────────
async function initStartSessionPage() {
  const catSel = document.getElementById("sessionCategorySelect");
  const subjSel = document.getElementById("sessionSubjectSelect");
  const periodSel = document.getElementById("sessionPeriodSelect");

  // Load subjects if needed
  if (!state.theorySubjects.length) await loadSubjects();

  const populateSubjects = () => {
    const list = catSel.value === "lab" ? state.labSubjects : state.theorySubjects;
    subjSel.innerHTML = "";
    list.forEach(s => { const o = document.createElement("option"); o.value = s; o.textContent = s; subjSel.appendChild(o); });
  };
  catSel.onchange = populateSubjects;
  populateSubjects();

  // Load periods
  if (!state.periods.length) {
    try {
      const res = await fetch("/api/periods");
      const data = await res.json();
      state.periods = data.periods || [];
    } catch (e) { state.periods = []; }
  }
  periodSel.innerHTML = "";
  (state.periods || []).forEach(p => {
    const o = document.createElement("option");
    o.value = p.id; o.textContent = p.label;
    if (p.is_break) { o.disabled = true; o.textContent += " (Break – No Class)"; }
    periodSel.appendChild(o);
  });

  // Pre-fill faculty name from logged in user
  const facultyInput = document.getElementById("sessionFacultyName");
  if (!facultyInput.value && state.currentUser) {
    facultyInput.value = state.currentUser.name || "";
  }

  // Show stop button if session already active
  const stopBtn = document.getElementById("btnStopSessionForm");
  const activeInfo = document.getElementById("activeSessionInfo");
  if (state.isSessionActive) {
    stopBtn.style.display = "flex";
    activeInfo.style.display = "block";
    document.getElementById("activeSessionDetails").textContent =
      ` ${state.activeSubject} | Sec ${state.activeSection} | Period ${state.activePeriod} | ${state.activeFaculty}`;
  } else {
    stopBtn.style.display = "none";
    activeInfo.style.display = "none";
  }

  stopBtn.onclick = async () => { await stopAttendanceSession(); };

  document.getElementById("startSessionForm").onsubmit = async (e) => {
    e.preventDefault();
    const subj = subjSel.value;
    const sec = document.getElementById("sessionSectionSelect").value;
    const faculty = facultyInput.value.trim() || (state.currentUser && state.currentUser.name) || "Faculty";
    const period = parseInt(periodSel.value);

    const res = await apiFetch("/api/session/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject: subj, section: sec, faculty_name: faculty, period })
    });
    const data = await res.json();
    if (res.ok) {
      state.isSessionActive = true;
      state.activeSubject = subj;
      state.activeSection = sec;
      state.activeFaculty = faculty;
      state.activePeriod = period;
      state.sessionId = data.session_id;
      showToast(`Session started: ${subj} — Period ${period}`, "success");
      location.hash = "#dashboard";
      // Start camera after navigation
      setTimeout(() => startCameraStream("attendance"), 400);
    } else {
      showToast(data.detail || "Failed to start session.", "error");
    }
  };
}

// ─── Webcam Controls (Dashboard) ─────────────────────────────────────────────
function setupWebcamControls() {
  const btnDashHw = document.getElementById("btnDashHwCam");
  const btnDashBr = document.getElementById("btnDashBrowserCam");
  const imgDash = document.getElementById("dashStreamImg");
  const videoDash = document.getElementById("dashBrowserVideo");
  const canvasDash = document.getElementById("dashBrowserCanvas");

  btnDashHw.onclick = () => {
    if (!state.isSessionActive) { showToast("Start an attendance session first.", "warning"); return; }
    state.dashCamMode = "hardware";
    btnDashHw.classList.add("active"); btnDashBr.classList.remove("active");
    if (state.browserStream) { state.browserStream.getTracks().forEach(t => t.stop()); state.browserStream = null; }
    videoDash.srcObject = null; videoDash.style.display = "none";
    imgDash.src = `/api/video_feed?mode=attendance&t=${Date.now()}`;
    imgDash.style.display = "block";
    document.getElementById("dashCameraOff").style.display = "none";
    state.cameraRunning = true;
  };

  btnDashBr.onclick = async () => {
    if (!state.isSessionActive) { showToast("Start an attendance session first.", "warning"); return; }
    state.dashCamMode = "browser";
    btnDashBr.classList.add("active"); btnDashHw.classList.remove("active");
    imgDash.src = ""; imgDash.style.display = "none";
    document.getElementById("dashCameraOff").style.display = "none";
    try {
      state.browserStream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
      videoDash.srcObject = state.browserStream; videoDash.play();
      videoDash.style.display = "block";
      state.browserFrameCounter = 0;
      loopBrowserFrames("attendance", videoDash, canvasDash, imgDash);
    } catch (e) {
      showToast("Camera error: " + e.message, "error");
      btnDashHw.click();
    }
  };

  // Stop session button in banner
  document.getElementById("btnStopSession").onclick = async () => { await stopAttendanceSession(); };
}

// Frame skipping for browser webcam (process every 4th frame)
async function loopBrowserFrames(mode, video, canvas, img) {
  if (state.dashCamMode !== "browser" || !state.browserStream) return;
  state.browserFrameCounter++;
  const shouldProcess = state.browserFrameCounter % 4 === 0;

  if (shouldProcess && !state.isProcessingBrowser && video.readyState === video.HAVE_ENOUGH_DATA) {
    state.isProcessingBrowser = true;
    canvas.width = 640; canvas.height = 480;
    canvas.getContext("2d").drawImage(video, 0, 0, 640, 480);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.75);
    try {
      const res = await fetch("/api/process_frame", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image: dataUrl, subject: state.activeSubject, mode })
      });
      const data = await res.json();
      if (res.ok && data.annotated_image) {
        img.src = data.annotated_image;
        img.style.display = "block";
      }
    } catch (e) {}
    state.isProcessingBrowser = false;
  }

  // Draw raw video on frames we skip
  if (!shouldProcess) {
    canvas.width = 640; canvas.height = 480;
    canvas.getContext("2d").drawImage(video, 0, 0, 640, 480);
  }

  if (state.dashCamMode === "browser") {
    setTimeout(() => loopBrowserFrames(mode, video, canvas, img), 33);
  }
}

// ─── Recognition Testing Page ─────────────────────────────────────────────────
function setupTestingPage() {
  const btnStartTest = document.getElementById("btnStartTestCam");
  const btnStopTest = document.getElementById("btnStopTestCam");
  const testImgHw = document.getElementById("testStreamImg");
  const testVideoEl = document.getElementById("testBrowserVideo");
  const testCanvas = document.getElementById("testBrowserCanvas");
  const testCameraOff = document.getElementById("testCameraOff");
  const testHud = document.getElementById("testHudOverlay");

  btnStartTest.onclick = () => {
    testCameraOff.style.display = "none";
    testImgHw.src = `/api/video_feed?mode=test&t=${Date.now()}`;
    testImgHw.style.display = "block";
    testHud.style.display = "flex";
    btnStartTest.style.display = "none";
    btnStopTest.style.display = "flex";
    state.testCamMode = "hardware";
  };

  btnStopTest.onclick = () => { stopTestCamera(); };
}

function stopTestCamera() {
  const testImgHw = document.getElementById("testStreamImg");
  const testCameraOff = document.getElementById("testCameraOff");
  const testHud = document.getElementById("testHudOverlay");
  testImgHw.src = ""; testImgHw.style.display = "none";
  testCameraOff.style.display = "flex";
  testHud.style.display = "none";
  if (state.testBrowserStream) {
    state.testBrowserStream.getTracks().forEach(t => t.stop());
    state.testBrowserStream = null;
  }
  const btnStart = document.getElementById("btnStartTestCam");
  const btnStop = document.getElementById("btnStopTestCam");
  if (btnStart) btnStart.style.display = "inline-flex";
  if (btnStop) btnStop.style.display = "none";
  state.testCamMode = "off";
}

// ─── Attendance Records Page ──────────────────────────────────────────────────
async function loadAttendanceBreakdown() {
  const subjFilter = document.getElementById("recordsSubjectFilter");
  const secFilter = document.getElementById("recordsSectionFilter").value;
  const dateFilter = document.getElementById("recordsDateFilter").value || new Date().toISOString().split("T")[0];
  document.getElementById("recordsDateFilter").value = dateFilter;

  if (!state.theorySubjects.length) await loadSubjects();
  if (subjFilter.options.length === 0) {
    state.theorySubjects.concat(state.labSubjects).forEach(s => {
      const o = document.createElement("option"); o.value = s; o.textContent = s;
      subjFilter.appendChild(o);
    });
    subjFilter.value = state.activeSubject || state.theorySubjects[0];
  }

  const subj = subjFilter.value || state.activeSubject;
  try {
    const res = await apiFetch(`/api/attendance/breakdown?subject=${encodeURIComponent(subj)}&section=${encodeURIComponent(secFilter)}&date=${encodeURIComponent(dateFilter)}`);
    const data = await res.json();
    document.getElementById("recTotalCount").textContent = data.total_students;
    document.getElementById("recPresentCount").textContent = data.present_count;
    document.getElementById("recAbsentCount").textContent = data.absent_count;
    document.getElementById("recPct").textContent = `${data.attendance_percentage}%`;
    document.getElementById("countPresentTab").textContent = data.present_count;
    document.getElementById("countAbsentTab").textContent = data.absent_count;

    const tbodyP = document.getElementById("tbodyPresent");
    tbodyP.innerHTML = "";
    if (!data.present_list.length) {
      tbodyP.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:2rem;">No students marked present yet.</td></tr>`;
    } else {
      data.present_list.forEach(s => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${s.s_no}</td>
          <td><strong style="color:#93c5fd;">${escapeHtml(s.prn)}</strong></td>
          <td><strong>${escapeHtml(s.name)}</strong></td>
          <td><span class="section-badge">${escapeHtml(s.section)}</span></td>
          <td>${escapeHtml(s.subject)}</td>
          <td>Period ${s.period || 1}</td>
          <td>${escapeHtml(s.faculty_name || "—")}</td>
          <td>${escapeHtml(s.time)}</td>
          <td><span class="badge-present">&#10003; PRESENT</span></td>`;
        tbodyP.appendChild(tr);
      });
    }

    const tbodyA = document.getElementById("tbodyAbsent");
    tbodyA.innerHTML = "";
    data.absent_list.forEach(s => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${s.s_no}</td>
        <td><span style="color:#94a3b8;">${escapeHtml(s.prn)}</span></td>
        <td>${escapeHtml(s.name)}</td>
        <td><span class="section-badge">${escapeHtml(s.section)}</span></td>
        <td>${escapeHtml(s.subject)}</td>
        <td><span class="badge-absent">&times; ABSENT</span></td>`;
      tbodyA.appendChild(tr);
    });
  } catch (e) { console.error("loadAttendanceBreakdown error:", e); }
}

function switchRecordsTab(tab) {
  ["present", "absent", "raw"].forEach(t => {
    document.getElementById(`btnTab${t.charAt(0).toUpperCase() + t.slice(1)}`).classList.toggle("active", t === tab);
    document.getElementById(`tableContainer${t.charAt(0).toUpperCase() + t.slice(1)}`).style.display = t === tab ? "block" : "none";
  });
  if (tab === "raw") loadRawRecords();
}

async function loadRawRecords() {
  const res = await apiFetch("/api/attendance/records");
  const data = await res.json();
  const tbody = document.getElementById("tbodyRaw");
  tbody.innerHTML = "";
  if (!data.records || !data.records.length) {
    tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;padding:2rem;">No records found.</td></tr>`; return;
  }
  (data.records || []).forEach(r => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${r.id}</td>
      <td><strong>${escapeHtml(r.prn)}</strong></td>
      <td>${escapeHtml(r.name)}</td>
      <td><span class="section-badge">${escapeHtml(r.section)}</span></td>
      <td>${escapeHtml(r.subject)}</td>
      <td>Period ${r.period || 1}</td>
      <td>${escapeHtml(r.faculty_name || "—")}</td>
      <td>${escapeHtml(r.date)}</td>
      <td>${escapeHtml(r.time)}</td>
      <td><span class="badge-present">&#10003; ${escapeHtml(r.status)}</span></td>`;
    tbody.appendChild(tr);
  });
}

// ─── Export Settings Form ─────────────────────────────────────────────────────
function setupExportPage() {
  const form = document.getElementById("exportSettingsForm");
  if (!form) return;
  // Load current settings
  apiFetch("/api/settings").then(r => r.json()).then(data => {
    if (data.google_sheets_webhook) document.getElementById("expWebhookUrl").value = data.google_sheets_webhook;
    if (data.confidence_threshold) document.getElementById("expThreshold").value = data.confidence_threshold;
  }).catch(() => {});

  form.onsubmit = async (e) => {
    e.preventDefault();
    const res = await apiFetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        confidence_threshold: document.getElementById("expThreshold").value,
        google_sheets_webhook: document.getElementById("expWebhookUrl").value
      })
    });
    const data = await res.json();
    showToast(data.message || "Settings saved.", "success");
  };
}

// ─── Utilities ────────────────────────────────────────────────────────────────
function toBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => resolve(reader.result);
    reader.onerror = err => reject(err);
  });
}

function showToast(msg, type = "success") {
  const container = document.getElementById("toastContainer");
  const toast = document.createElement("div");
  toast.className = `toast ${type === "warning" ? "toast-warning" : type === "error" ? "toast-error" : ""}`;
  toast.innerHTML = `<span><strong>${type === "success" ? "✓" : "!"}</strong> ${escapeHtml(msg)}</span>`;
  container.appendChild(toast);
  setTimeout(() => { toast.style.opacity = "0"; setTimeout(() => toast.remove(), 300); }, 3800);
}

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// ─── Initialization ───────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  initLiveClock();
  setupAuth();
  setupWebcamControls();
  setupTestingPage();
  setupExportPage();

  document.getElementById("btnToggleAudio").onclick = () => {
    state.audioEnabled = !state.audioEnabled;
    document.getElementById("btnToggleAudio").textContent =
      state.audioEnabled ? "🔔 Audio: ON" : "🔕 Audio: OFF";
  };

  document.getElementById("studentListSectionFilter").onchange = loadStudentList;
  document.getElementById("studentListSearch").oninput = loadStudentList;
  document.getElementById("recordsSubjectFilter").onchange = loadAttendanceBreakdown;
  document.getElementById("recordsSectionFilter").onchange = loadAttendanceBreakdown;
  document.getElementById("recordsDateFilter").onchange = loadAttendanceBreakdown;
  document.getElementById("btnRefreshRecords").onclick = loadAttendanceBreakdown;

  window.addEventListener("hashchange", handleHashChange);
  handleHashChange();

  // Restore session from server on load (in case of page refresh during active session)
  if (state.authToken) {
    fetch("/api/session/status").then(r => r.json()).then(data => {
      state.isSessionActive = data.is_session_active;
      state.activeSubject = data.active_subject;
      state.activeSection = data.active_section;
      state.activeFaculty = data.faculty_name;
      state.activePeriod = data.period;
      state.sessionId = data.session_id;
      if (data.is_session_active) {
        document.getElementById("sessionBanner").style.display = "flex";
        document.getElementById("bannerSubject").textContent = data.active_subject;
        document.getElementById("bannerSection").textContent = data.active_section;
        document.getElementById("bannerPeriod").textContent = `Period ${data.period}`;
        document.getElementById("bannerFaculty").textContent = data.faculty_name || "—";
      }
    }).catch(() => {});
  }

  // Poll dashboard every 2.5 seconds (less aggressive than original 1.5s)
  state.pollTimer = setInterval(pollDashboard, 2500);
});
