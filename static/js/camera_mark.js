// camera_mark.js - Face Recognition with Blink Detection (Anti-Spoofing)
// FIXED VERSION with better error handling

const video = document.getElementById('markVideo');
const statusDiv = document.getElementById('markStatus');
const recognizedList = document.getElementById('recognizedList');
const startBtn = document.getElementById('startMarkBtn');
const stopBtn = document.getElementById('stopMarkBtn');

let stream = null;
let capturing = false;
let recognitionInterval = null;
const recognizedSet = new Set(); // Track who's been recognized this session

// Blink detection state
let blinkVerified = false;
let blinkCheckInProgress = false;
let lastBlinkEarValue = 0.0; // Store EAR value for database

// Start camera and recognition
startBtn.addEventListener('click', async () => {
  console.log('[CAMERA] Start button clicked');
  
  try {
    // Update status immediately
    statusDiv.textContent = '📹 Requesting camera access...';
    statusDiv.className = 'mt-2 small text-info';
    
    console.log('[CAMERA] Requesting camera permissions...');
    
    // Request camera with specific constraints
    stream = await navigator.mediaDevices.getUserMedia({ 
      video: { 
        width: { ideal: 640 },
        height: { ideal: 480 },
        facingMode: 'user'
      },
      audio: false
    });
    
    console.log('[CAMERA] ✅ Camera access granted');
    console.log('[CAMERA] Stream:', stream);
    
    // Set video source
    video.srcObject = stream;
    
    // Wait for video to be ready
    video.onloadedmetadata = () => {
      console.log('[CAMERA] Video metadata loaded');
      video.play().then(() => {
        console.log('[CAMERA] ✅ Video playing');
        
        startBtn.disabled = true;
        stopBtn.disabled = false;
        capturing = true;
        
        statusDiv.textContent = '👁️ Please blink naturally to verify you are real...';
        statusDiv.className = 'mt-2 small text-primary fw-bold';
        
        // Start recognition loop (every 2 seconds)
        recognitionInterval = setInterval(captureAndProcess, 2000);
        
      }).catch(err => {
        console.error('[CAMERA] ❌ Video play error:', err);
        statusDiv.textContent = '❌ Error: Could not start video playback';
        statusDiv.className = 'mt-2 small text-danger';
      });
    };
    
    video.onerror = (err) => {
      console.error('[CAMERA] ❌ Video element error:', err);
      statusDiv.textContent = '❌ Error: Video element failed';
      statusDiv.className = 'mt-2 small text-danger';
    };
    
  } catch (err) {
    console.error('[CAMERA] ❌ Camera error:', err);
    console.error('[CAMERA] Error name:', err.name);
    console.error('[CAMERA] Error message:', err.message);
    
    // Detailed error messages
    let errorMsg = 'Error: ';
    
    if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
      errorMsg += 'Camera permission denied. Please allow camera access and refresh the page.';
    } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
      errorMsg += 'No camera found. Please connect a webcam and try again.';
    } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
      errorMsg += 'Camera is being used by another application. Please close other apps using the camera.';
    } else if (err.name === 'OverconstrainedError') {
      errorMsg += 'Camera does not meet requirements. Trying again with lower settings...';
      
      // Try again with lower constraints
      setTimeout(async () => {
        try {
          stream = await navigator.mediaDevices.getUserMedia({ video: true });
          video.srcObject = stream;
          statusDiv.textContent = '✅ Camera started with basic settings';
          statusDiv.className = 'mt-2 small text-success';
          startBtn.disabled = true;
          stopBtn.disabled = false;
          capturing = true;
          recognitionInterval = setInterval(captureAndProcess, 2000);
        } catch (e) {
          statusDiv.textContent = 'Error: Could not start camera with any settings';
          statusDiv.className = 'mt-2 small text-danger';
        }
      }, 1000);
      return;
    } else if (err.name === 'TypeError') {
      errorMsg += 'Browser does not support camera access. Please use Chrome, Firefox, or Edge.';
    } else {
      errorMsg += err.message || 'Unknown error occurred';
    }
    
    statusDiv.textContent = errorMsg;
    statusDiv.className = 'mt-2 small text-danger';
    
    // Show help text
    const helpText = document.createElement('div');
    helpText.className = 'mt-2 small text-muted';
    helpText.innerHTML = `
      <strong>Troubleshooting:</strong><br>
      1. Check camera icon in browser address bar (click to allow)<br>
      2. Make sure no other apps are using the camera<br>
      3. Try refreshing the page (F5)<br>
      4. Check if camera works in other apps
    `;
    statusDiv.appendChild(helpText);
  }
});

// Stop camera and recognition
stopBtn.addEventListener('click', () => {
  console.log('[CAMERA] Stop button clicked');
  stopCapture();
});

function stopCapture() {
  capturing = false;
  blinkVerified = false;
  blinkCheckInProgress = false;
  
  if (recognitionInterval) {
    clearInterval(recognitionInterval);
    recognitionInterval = null;
  }
  
  if (stream) {
    stream.getTracks().forEach(track => {
      console.log('[CAMERA] Stopping track:', track.label);
      track.stop();
    });
    stream = null;
  }
  
  video.srcObject = null;
  startBtn.disabled = false;
  stopBtn.disabled = true;
  statusDiv.textContent = 'Stopped.';
  statusDiv.className = 'mt-2 small text-muted';
  
  console.log('[CAMERA] ✅ Camera stopped');
}

// Main processing function - handles blink check then face recognition
async function captureAndProcess() {
  if (!capturing) return;
  
  // Check if video is actually playing
  if (video.readyState !== video.HAVE_ENOUGH_DATA) {
    console.log('[PROCESSING] Video not ready yet, skipping frame');
    return;
  }
  
  try {
    // Step 1: Check for blink (liveness detection)
    if (!blinkVerified && !blinkCheckInProgress) {
      await checkForBlink();
    }
    
    // Step 2: Face recognition (only after blink verified)
    else if (blinkVerified) {
      await recognizeFace();
    }
    
  } catch (err) {
    console.error('[PROCESSING] Error:', err);
    statusDiv.textContent = 'Error during processing: ' + err.message;
    statusDiv.className = 'mt-2 small text-danger';
  }
}

// Step 1: Check for blink (liveness detection)
async function checkForBlink() {
  if (blinkCheckInProgress) return;
  
  blinkCheckInProgress = true;
  
  try {
    statusDiv.textContent = '👁️ Checking for blink...';
    statusDiv.className = 'mt-2 small text-info';
    
    // Capture frame from video
    const blob = await captureFrame();
    
    // Send to blink detection endpoint
    const formData = new FormData();
    formData.append('image', blob, 'blink_check.jpg');
    
    console.log('[BLINK] Sending image to server...');
    const response = await fetch('/check_blink', {
      method: 'POST',
      body: formData
    });
    
    const data = await response.json();
    console.log('[BLINK] Server response:', data);
    
    if (data.success && data.blink_detected) {
      // Blink detected! Mark as verified
      blinkVerified = true;
      lastBlinkEarValue = data.ear_value; // Store for database
      
      statusDiv.textContent = '✓ Liveness confirmed! Blink detected. Starting face recognition...';
      statusDiv.className = 'mt-2 small text-success fw-bold';
      
      // Flash green border
      video.style.border = '4px solid #22c55e';
      setTimeout(() => {
        video.style.border = '2px solid #e2e8f0';
      }, 1000);
      
      // Small delay before starting face recognition
      setTimeout(() => {
        statusDiv.textContent = 'Ready for face recognition...';
        statusDiv.className = 'mt-2 small text-success';
      }, 2000);
      
    } else {
      // Blink not detected yet
      const earValue = data.ear_value || 0;
      statusDiv.textContent = `👁️ Please blink naturally (EAR: ${earValue.toFixed(3)})`;
      statusDiv.className = 'mt-2 small text-warning';
    }
    
  } catch (err) {
    console.error('[BLINK] Error:', err);
    statusDiv.textContent = 'Error checking for blink: ' + err.message;
    statusDiv.className = 'mt-2 small text-danger';
  } finally {
    blinkCheckInProgress = false;
  }
}

// Step 2: Face recognition (after blink verified)
async function recognizeFace() {
  try {
    statusDiv.textContent = '🔍 Analyzing face...';
    statusDiv.className = 'mt-2 small text-info';
    
    // Capture frame from video
    const blob = await captureFrame();
    
    // Send to recognition endpoint WITH blink_verified flag
    const formData = new FormData();
    formData.append('image', blob, 'face.jpg');
    formData.append('blink_verified', 'true'); // Important: Tell backend blink was verified
    formData.append('blink_ear_value', lastBlinkEarValue || '0.0'); // Send EAR value for database
    
    console.log('[RECOGNITION] Sending image to server...');
    const response = await fetch('/recognize_face', {
      method: 'POST',
      body: formData
    });
    
    const data = await response.json();
    console.log('[RECOGNITION] Server response:', data);
    
    // Handle response
    if (data.recognized) {
      // Success - attendance marked
      const studentKey = `${data.student_id}_${data.name}`;
      
      if (!recognizedSet.has(studentKey)) {
        recognizedSet.add(studentKey);
        addToRecognizedList(data.name, data.confidence, 'success');
      }
      
      statusDiv.textContent = `✓ ${data.name} recognized (${(data.confidence * 100).toFixed(1)}%) - Attendance marked!`;
      statusDiv.className = 'mt-2 small text-success fw-bold';
      
      // Flash green border
      video.style.border = '4px solid #22c55e';
      setTimeout(() => {
        video.style.border = '2px solid #e2e8f0';
      }, 1000);
      
      // Reset blink verification for next student
      setTimeout(() => {
        blinkVerified = false;
        statusDiv.textContent = '👁️ Please blink naturally to verify you are real...';
        statusDiv.className = 'mt-2 small text-primary fw-bold';
      }, 3000);
      
    } else {
      // Not recognized or error
      handleRecognitionError(data);
    }
    
  } catch (err) {
    console.error('[RECOGNITION] Error:', err);
    statusDiv.textContent = 'Error during recognition: ' + err.message;
    statusDiv.className = 'mt-2 small text-danger';
  }
}

// Helper: Capture frame from video as blob
async function captureFrame() {
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0);
  
  return new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.95));
}

// Handle different types of recognition failures
function handleRecognitionError(data) {
  if (data.reason === 'too_soon') {
    // Attendance already marked recently
    statusDiv.textContent = `⚠️ ${data.name}: ${data.message}`;
    statusDiv.className = 'mt-2 small text-warning fw-bold';
    
    // Flash orange border
    video.style.border = '4px solid #f59e0b';
    setTimeout(() => {
      video.style.border = '2px solid #e2e8f0';
    }, 1000);
    
    // Reset blink for next attempt
    setTimeout(() => {
      blinkVerified = false;
      statusDiv.textContent = '👁️ Please blink naturally to verify you are real...';
      statusDiv.className = 'mt-2 small text-primary fw-bold';
    }, 3000);
    
  } else if (data.reason === 'low_confidence') {
    // Face detected but confidence too low
    statusDiv.textContent = `✗ ${data.message}`;
    statusDiv.className = 'mt-2 small text-warning';
    
    // Reset blink for retry
    setTimeout(() => {
      blinkVerified = false;
      statusDiv.textContent = '👁️ Please blink naturally to verify you are real...';
      statusDiv.className = 'mt-2 small text-primary fw-bold';
    }, 3000);
    
  } else if (data.error === 'no face detected') {
    // No face in frame
    statusDiv.textContent = 'No face detected. Position yourself in frame.';
    statusDiv.className = 'mt-2 small text-muted';
    
  } else if (data.error === 'model not trained') {
    // Model not trained yet
    statusDiv.textContent = '⚠️ Model not trained. Please train the model first.';
    statusDiv.className = 'mt-2 small text-danger fw-bold';
    stopCapture();
    
  } else if (data.error === 'Liveness check not completed') {
    // Backend rejected because blink not verified
    statusDiv.textContent = '⚠️ Liveness check failed. Please blink again.';
    statusDiv.className = 'mt-2 small text-danger';
    blinkVerified = false;
    
  } else {
    // Generic error
    statusDiv.textContent = `Error: ${data.error || data.message || 'Unknown error'}`;
    statusDiv.className = 'mt-2 small text-danger';
  }
}

// Add recognized student to the list
function addToRecognizedList(name, confidence, status) {
  const li = document.createElement('li');
  li.className = `list-group-item list-group-item-${status}`;
  
  const now = new Date().toLocaleTimeString();
  li.innerHTML = `
    <div class="d-flex justify-content-between align-items-center">
      <div>
        <strong>${name}</strong>
        <br>
        <small class="text-muted">Confidence: ${(confidence * 100).toFixed(1)}%</small>
        <br>
        <small class="badge bg-success">✓ Liveness Verified</small>
      </div>
      <small class="text-muted">${now}</small>
    </div>
  `;
  
  recognizedList.prepend(li);
  
  // Limit list to 10 items
  while (recognizedList.children.length > 10) {
    recognizedList.removeChild(recognizedList.lastChild);
  }
}

// Clean up on page unload
window.addEventListener('beforeunload', () => {
  stopCapture();
});

// Check if browser supports camera on page load
window.addEventListener('load', () => {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    statusDiv.textContent = '❌ Your browser does not support camera access. Please use Chrome, Firefox, or Edge.';
    statusDiv.className = 'mt-2 small text-danger';
    startBtn.disabled = true;
  } else {
    console.log('[CAMERA] ✅ Browser supports camera API');
  }
});