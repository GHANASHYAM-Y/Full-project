// static/js/camera_add_student.js
(() => {
  // Config
  const MAX_IMAGES = 50;
  const CAPTURE_INTERVAL_MS = 180; // ~5.5 fps -> ~18 seconds for 100 images
  const UPLOAD_BATCH_SIZE = 20;
  const CREATE_STUDENT_URL = '/add_student';
  const UPLOAD_URL = '/upload_face';

  // Elements (matched to your template)
  const formEl = document.getElementById('studentForm');
  const saveInfoBtn = document.getElementById('saveInfoBtn'); // submit button inside form
  const startCaptureBtn = document.getElementById('startCaptureBtn');
  const addStudentBtn = document.getElementById('addStudentBtn');
  const videoEl = document.getElementById('video');
  const captureStatusEl = document.getElementById('captureStatus');
  const progressBarEl = document.getElementById('progressBar');

  // State
  let studentId = null;
  let stream = null;
  let capturing = false;
  let capturedBlobs = [];
  let captureTimer = null;

  // Helpers
  function setStatus(text) {
    if (captureStatusEl) captureStatusEl.textContent = text;
  }
  function setProgress(count, total = MAX_IMAGES) {
    const pct = Math.round((count / total) * 100);
    if (progressBarEl) {
      progressBarEl.style.width = pct + '%';
      progressBarEl.setAttribute('aria-valuenow', pct);
    }
    setStatus(`Captured ${count} / ${total}`);
  }

  async function createStudentOnServer() {
    // Use FormData from the form and POST to CREATE_STUDENT_URL
    const fd = new FormData(formEl);
    const resp = await fetch(CREATE_STUDENT_URL, { method: 'POST', body: fd });
    if (!resp.ok) {
      const txt = await resp.text().catch(()=>null);
      throw new Error('Student creation failed: ' + resp.status + ' ' + (txt||''));
    }
    const json = await resp.json();
    if (!json.student_id) throw new Error('No student_id returned from server');
    return json.student_id;
  }

  async function startCamera() {
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 }, audio: false });
      videoEl.srcObject = stream;
      await videoEl.play();
      return true;
    } catch (err) {
      console.error('Camera start failed', err);
      setStatus('Camera permission denied or unavailable.');
      return false;
    }
  }

  function stopCamera() {
    if (stream) {
      stream.getTracks().forEach(t => t.stop());
      stream = null;
    }
    try { videoEl.pause(); videoEl.srcObject = null; } catch (e) {}
  }

  function captureFrameDataURL() {
    const w = videoEl.videoWidth || 640;
    const h = videoEl.videoHeight || 480;
    const canvas = document.createElement('canvas');
    canvas.width = w; canvas.height = h;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(videoEl, 0, 0, w, h);
    return canvas.toDataURL('image/jpeg', 0.9);
  }

  function dataURLtoBlob(dataURL) {
    const parts = dataURL.split(';base64,');
    const contentType = parts[0].split(':')[1];
    const raw = atob(parts[1]);
    const uInt8Array = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; ++i) uInt8Array[i] = raw.charCodeAt(i);
    return new Blob([uInt8Array], { type: contentType });
  }

  async function uploadBatch(student_id, blobArray) {
    const fd = new FormData();
    fd.append('student_id', String(student_id));
    blobArray.forEach((b, i) => fd.append('images[]', b, `img_${Date.now()}_${i}.jpg`));
    const resp = await fetch(UPLOAD_URL, { method: 'POST', body: fd });
    if (!resp.ok) {
      const txt = await resp.text().catch(()=>null);
      throw new Error('Upload failed: ' + resp.status + ' ' + (txt||''));
    }
    return resp.json();
  }

  // Capture loop
  function beginCapture() {
    capturedBlobs = [];
    capturing = true;
    setProgress(0);
    captureTimer = setInterval(() => {
      try {
        if (!capturing) return;
        if (capturedBlobs.length >= MAX_IMAGES) {
          finishCaptureAndUpload();
          return;
        }
        const dataUrl = captureFrameDataURL();
        const blob = dataURLtoBlob(dataUrl);
        capturedBlobs.push(blob);
        setProgress(capturedBlobs.length);
      } catch (err) {
        console.error('Capture error', err);
      }
    }, CAPTURE_INTERVAL_MS);
  }

  async function finishCaptureAndUpload() {
    if (!capturing) return;
    capturing = false;
    if (captureTimer) { clearInterval(captureTimer); captureTimer = null; }
    stopCamera();
    startCaptureBtn.disabled = true;
    addStudentBtn.disabled = true;
    setStatus(`Captured ${capturedBlobs.length} images. Uploading...`);

    let uploaded = 0;
    try {
      for (let i = 0; i < capturedBlobs.length; i += UPLOAD_BATCH_SIZE) {
        const batch = capturedBlobs.slice(i, i + UPLOAD_BATCH_SIZE);
        setStatus(`Uploading ${i+1} to ${i + batch.length}...`);
        await uploadBatch(studentId, batch);
        uploaded += batch.length;
        setProgress(uploaded);
      }
      setStatus(`Upload complete. Saved ${uploaded} images for student ${studentId}.`);
    } catch (err) {
      console.error('Upload error', err);
      setStatus('Upload failed: ' + (err.message || err));
      // allow retry: enable start & add buttons
      startCaptureBtn.disabled = false;
      addStudentBtn.disabled = false;
      return;
    }

    // Done
    startCaptureBtn.disabled = false;
    addStudentBtn.disabled = false;
    // Optionally reset capturedBlobs to free memory
    capturedBlobs = [];
  }

  function abortCapture() {
    capturing = false;
    if (captureTimer) { clearInterval(captureTimer); captureTimer = null; }
    stopCamera();
    setStatus(`Capture aborted. ${capturedBlobs.length} images captured (not uploaded).`);
    startCaptureBtn.disabled = false;
    addStudentBtn.disabled = false;
  }

  // UI wiring
  // Form submission - create student
  formEl.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    // disable UI while creating
    saveInfoBtn.disabled = true;
    startCaptureBtn.disabled = true;
    addStudentBtn.disabled = true;
    setStatus('Creating student...');

    try {
      studentId = await createStudentOnServer();
      setStatus(`Student created: id=${studentId}. You can start capture.`);
      startCaptureBtn.disabled = false;
      addStudentBtn.disabled = false;
    } catch (err) {
      console.error('Create student failed', err);
      setStatus('Failed to create student: ' + (err.message || err));
    } finally {
      saveInfoBtn.disabled = false;
    }
  });

  // Start capture button
  startCaptureBtn.addEventListener('click', async (ev) => {
    ev.preventDefault();
    if (!studentId) {
      setStatus('Create student info first.');
      return;
    }
    startCaptureBtn.disabled = true;
    addStudentBtn.disabled = true;
    setStatus('Starting camera...');
    const ok = await startCamera();
    if (!ok) {
      startCaptureBtn.disabled = false;
      addStudentBtn.disabled = false;
      return;
    }
    setStatus('Capturing images...');
    beginCapture();
  });

  // Add Student (reset form/UI)
  addStudentBtn.addEventListener('click', (ev) => {
    ev.preventDefault();
    // if currently capturing, abort
    if (capturing) abortCapture();
    // reset form and UI
    try { formEl.reset(); } catch (e) {}
    studentId = null;
    capturedBlobs = [];
    setProgress(0);
    setStatus('Ready to add new student. Fill the form and Save Info.');
    startCaptureBtn.disabled = true;
    addStudentBtn.disabled = true;
  });

  // cleanup on unload
  window.addEventListener('beforeunload', () => {
    if (captureTimer) clearInterval(captureTimer);
    if (stream) stopCamera();
  });

  // initialize UI state
  startCaptureBtn.disabled = true;
  addStudentBtn.disabled = true;
  setProgress(0);
  setStatus('Fill student info and click Save Info.');
})();
