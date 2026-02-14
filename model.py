import os
import cv2
import numpy as np
import pickle
import json
import face_recognition
import traceback
from PIL import Image

# Get the directory where model.py is located
APP_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(APP_DIR, "model.pkl")
TRAINED_STUDENTS_FILE = os.path.join(APP_DIR, "trained_students.json")

print(f"[DEBUG] Model will be saved to: {MODEL_PATH}")
print(f"[DEBUG] Trained students file: {TRAINED_STUDENTS_FILE}")

# ============= BLINK DETECTION FUNCTIONS =============

def eye_aspect_ratio(eye):
    """
    Calculate Eye Aspect Ratio (EAR) for blink detection
    
    Args:
        eye: Array of 6 (x, y) coordinates representing eye landmarks
        
    Returns:
        float: Eye Aspect Ratio value
    """
    # Compute vertical distances using numpy
    A = np.linalg.norm(eye[1] - eye[5])
    B = np.linalg.norm(eye[2] - eye[4])
    
    # Compute horizontal distance
    C = np.linalg.norm(eye[0] - eye[3])
    
    # Calculate EAR
    ear = (A + B) / (2.0 * C)
    return ear

def detect_blink_in_image(image_bytes):
    """
    Detect if a blink occurred in the provided image
    
    Args:
        image_bytes: Image data as bytes or file stream
        
    Returns:
        dict: {
            'blink_detected': bool,
            'ear_value': float,
            'message': str,
            'left_ear': float,
            'right_ear': float
        }
    """
    try:
        # Read image
        data = image_bytes.read()
        arr = np.frombuffer(data, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        
        if img is None:
            return {
                'blink_detected': False,
                'message': 'Failed to decode image',
                'ear_value': 0.0
            }
        
        # Convert to RGB (ensure proper format)
        if len(img.shape) == 2:  # Grayscale
            rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        elif img.shape[2] == 4:  # RGBA
            rgb = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
        elif img.shape[2] == 3:  # BGR
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        else:
            return {
                'blink_detected': False,
                'message': 'Unsupported image format',
                'ear_value': 0.0
            }
        
        # Ensure 8-bit
        if rgb.dtype != np.uint8:
            rgb = np.uint8(rgb)
        
        # Get face landmarks
        face_landmarks_list = face_recognition.face_landmarks(rgb)
        
        if len(face_landmarks_list) == 0:
            return {
                'blink_detected': False,
                'message': 'No face detected',
                'ear_value': 0.0
            }
        
        # Get first face's landmarks
        landmarks = face_landmarks_list[0]
        
        # Extract eye coordinates
        left_eye = np.array(landmarks['left_eye'])
        right_eye = np.array(landmarks['right_eye'])
        
        # Calculate EAR for both eyes
        left_ear = eye_aspect_ratio(left_eye)
        right_ear = eye_aspect_ratio(right_eye)
        
        # Average EAR
        avg_ear = (left_ear + right_ear) / 2.0
        
        # EAR threshold for blink detection
        # Typical values: Eyes open ~0.25-0.35, Eyes closed <0.20
        EAR_THRESHOLD = 0.24
        
        print(f"[BLINK DEBUG] Left EAR: {left_ear:.3f}, Right EAR: {right_ear:.3f}, Avg EAR: {avg_ear:.3f}")
        
        if avg_ear < EAR_THRESHOLD:
            return {
                "success": True,                 # ✅ REQUIRED
                "blink_detected": True,
                "message": "Blink detected",
                "ear_value": float(avg_ear),
                "left_ear": float(left_ear),
                "right_ear": float(right_ear),
                "threshold": EAR_THRESHOLD
        }

        else:
            return {
                'blink_detected': False,
                'message': f'Eyes open (EAR: {avg_ear:.3f})',
                'ear_value': float(avg_ear),
                'left_ear': float(left_ear),
                'right_ear': float(right_ear),
                'threshold': EAR_THRESHOLD
            }
    
    except Exception as e:
        print(f"[ERROR] Blink detection failed: {e}")
        traceback.print_exc()
        return {
            'blink_detected': False,
            'message': f'Error: {str(e)}',
            'ear_value': 0.0
        }

def verify_liveness_sequence(image_sequence):
    """
    Verify liveness by detecting a blink via EAR drop
    (robust for real-world webcams)
    """
    try:
        if len(image_sequence) < 3:
            return {
                'liveness_confirmed': False,
                'message': 'Not enough frames (minimum 3 required)',
                'frames_analyzed': len(image_sequence)
            }

        EAR_THRESHOLD = 0.25   # relaxed & realistic
        ear_values = []
        blink_frames = []

        for idx, img_bytes in enumerate(image_sequence):
            result = detect_blink_in_image(img_bytes)
            ear = result.get('ear_value', 0.0)
            ear_values.append(ear)

            print(f"[LIVENESS] Frame {idx+1}: EAR={ear:.3f}")

            # ✅ Accept blink if EAR dips once
            if ear < EAR_THRESHOLD:
                blink_frames.append(idx)

        if len(blink_frames) >= 1:
            return {
                'liveness_confirmed': True,
                'frames_analyzed': len(image_sequence),
                'blink_frames': blink_frames,
                'ear_values': ear_values,
                'message': 'Liveness confirmed: Blink detected'
            }

        return {
            'liveness_confirmed': False,
            'frames_analyzed': len(image_sequence),
            'blink_frames': [],
            'ear_values': ear_values,
            'message': 'No blink detected. Please blink normally.'
        }

    except Exception as e:
        print(f"[ERROR] Liveness verification failed: {e}")
        traceback.print_exc()
        return {
            'liveness_confirmed': False,
            'message': f'Error: {str(e)}',
            'frames_analyzed': 0
        }

# ============= MODEL MANAGEMENT FUNCTIONS =============

def load_trained_students():
    """Load the list of students who have been trained"""
    if os.path.exists(TRAINED_STUDENTS_FILE):
        try:
            with open(TRAINED_STUDENTS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to load trained students: {e}")
            return {}
    return {}

def save_trained_students(trained):
    """Save the list of trained students"""
    try:
        with open(TRAINED_STUDENTS_FILE, 'w') as f:
            json.dump(trained, f, indent=2)
        print(f"[DEBUG] Trained students saved: {list(trained.keys())}")
    except Exception as e:
        print(f"[ERROR] Failed to save trained students: {e}")

def extract_embedding_for_image(stream_or_bytes):
    """
    Extract 128-D face encoding from image stream
    USING PIL FOR MAXIMUM COMPATIBILITY
    """
    try:
        # Use PIL to read image (more reliable than OpenCV for various formats)
        img_pil = Image.open(stream_or_bytes)
        
        # Convert to RGB
        if img_pil.mode != 'RGB':
            img_pil = img_pil.convert('RGB')
        
        # Convert to numpy array
        rgb = np.array(img_pil)
        
        # Ensure proper format
        if rgb.dtype != np.uint8:
            rgb = rgb.astype(np.uint8)
        
        # Ensure contiguous array (required by face_recognition)
        if not rgb.flags['C_CONTIGUOUS']:
            rgb = np.ascontiguousarray(rgb)
        
        encodings = face_recognition.face_encodings(rgb)
        
        if len(encodings) == 0:
            print("[DEBUG] No face detected in image")
            return None
        
        print(f"[DEBUG] Face encoding extracted successfully")
        return encodings[0]
    
    except Exception as e:
        print(f"[ERROR] extract_embedding_for_image failed: {e}")
        traceback.print_exc()
        return None

def load_model_if_exists():
    """Load the trained model if it exists"""
    model_path = os.path.abspath(MODEL_PATH)
    print(f"[DEBUG] Looking for model at: {model_path}")
    
    if not os.path.exists(model_path):
        print(f"[DEBUG] Model not found at {model_path}")
        return None
    
    try:
        print(f"[DEBUG] Loading model from {model_path}")
        with open(model_path, "rb") as f:
            model = pickle.load(f)
        
        print(f"[DEBUG] Model loaded successfully!")
        print(f"[DEBUG] Students in model: {len(set(model['labels']))}")
        print(f"[DEBUG] Total faces: {len(model['encodings'])}")
        return model
    
    except Exception as e:
        print(f"[ERROR] Failed to load model: {e}")
        traceback.print_exc()
        return None

def predict_with_model(clf, emb):
    """Predict student ID and confidence from face embedding"""
    try:
        if clf is None or 'encodings' not in clf or 'labels' not in clf:
            print("[DEBUG] Invalid model structure")
            return None, 0.0
        
        if len(clf['encodings']) == 0:
            print("[DEBUG] No encodings in model")
            return None, 0.0
        
        distances = face_recognition.face_distance(clf['encodings'], emb)
        best_match_idx = np.argmin(distances)
        
        print(f"[DEBUG] Best match distance: {distances[best_match_idx]:.4f}")
        
        if distances[best_match_idx] > 0.6:
            print(f"[DEBUG] Face too different (distance > 0.6)")
            return None, 0.0
        
        confidence = 1 - distances[best_match_idx]
        label = clf['labels'][best_match_idx]
        
        print(f"[DEBUG] Predicted label: {label}, confidence: {confidence:.2%}")
        return label, float(confidence)
    
    except Exception as e:
        print(f"[ERROR] predict_with_model failed: {e}")
        traceback.print_exc()
        return None, 0.0

def train_model_background(dataset_dir, progress_callback=None, full_retrain=False):
    """
    Train face recognition model with AUTOMATIC IMAGE FORMAT CORRECTION.
    - If full_retrain=False: Only trains NEW students (fast)
    - If full_retrain=True: Retrains ALL students (slow but thorough)
    """
    
    print(f"\n{'='*60}")
    print(f"[TRAINING START] Mode: {'FULL RETRAIN' if full_retrain else 'INCREMENTAL'}")
    print(f"[TRAINING START] Dataset directory: {dataset_dir}")
    print(f"{'='*60}\n")
    
    try:
        if full_retrain:
            encodings = []
            labels = []
            trained_students = {}
            if progress_callback:
                progress_callback(0, "Starting full retrain of all students...")
            print("[INFO] Full retrain mode - starting fresh")
        else:
            existing_model = load_model_if_exists()
            if existing_model:
                encodings = existing_model.get('encodings', [])
                labels = existing_model.get('labels', [])
                print(f"[INFO] Loaded existing model with {len(encodings)} faces")
            else:
                encodings = []
                labels = []
                print("[INFO] No existing model found, starting fresh")
            
            trained_students = load_trained_students()
            print(f"[INFO] Previously trained students: {list(trained_students.keys())}")
        
        if not os.path.exists(dataset_dir):
            print(f"[ERROR] Dataset directory not found: {dataset_dir}")
            if progress_callback:
                progress_callback(0, "Dataset directory not found")
            return
        
        student_dirs = [d for d in os.listdir(dataset_dir) 
                       if os.path.isdir(os.path.join(dataset_dir, d))]
        
        print(f"[INFO] Found {len(student_dirs)} student directories: {student_dirs}")
        
        if not full_retrain:
            new_students = [s for s in student_dirs if s not in trained_students]
            
            if len(new_students) == 0:
                print("[INFO] No new students to train")
                if progress_callback:
                    progress_callback(100, "No new students to train")
                return
            
            students_to_process = new_students
            message_prefix = "new"
            print(f"[INFO] New students to train: {new_students}")
        else:
            students_to_process = student_dirs
            message_prefix = "total"
            print(f"[INFO] Training all students: {students_to_process}")
        
        total = len(students_to_process)
        processed = 0
        
        if progress_callback:
            progress_callback(0, f"Processing {total} {message_prefix} student(s)...")
        
        for sid in students_to_process:
            folder = os.path.join(dataset_dir, sid)
            files = [f for f in os.listdir(folder) 
                    if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp"))]
            
            print(f"\n[PROCESSING] Student {sid}: Found {len(files)} image files")
            
            student_encodings_count = 0
            
            for idx, fn in enumerate(files):
                path = os.path.join(folder, fn)
                
                try:
                    # USE PIL DIRECTLY (more reliable than OpenCV for various formats)
                    pil_img = Image.open(path)
                    
                    # Convert to RGB
                    if pil_img.mode != 'RGB':
                        original_mode = pil_img.mode
                        pil_img = pil_img.convert('RGB')
                        print(f"  [FIX] {fn} - Converted from {original_mode} to RGB")
                    
                    # Convert PIL to numpy array
                    rgb = np.array(pil_img)
                    
                    # Validate shape
                    if len(rgb.shape) != 3 or rgb.shape[2] != 3:
                        print(f"  [SKIP] {fn} - Invalid shape after conversion: {rgb.shape}")
                        continue
                    
                    # Ensure 8-bit unsigned integer
                    if rgb.dtype != np.uint8:
                        rgb = rgb.astype(np.uint8)
                        print(f"  [FIX] {fn} - Converted to 8-bit uint8")
                    
                    # Ensure contiguous array (required by face_recognition)
                    if not rgb.flags['C_CONTIGUOUS']:
                        rgb = np.ascontiguousarray(rgb)
                        print(f"  [FIX] {fn} - Made array contiguous")
                    
                    # Extract face encodings
                    face_encodings = face_recognition.face_encodings(rgb)
                    
                    if len(face_encodings) > 0:
                        encodings.append(face_encodings[0])
                        labels.append(int(sid))
                        student_encodings_count += 1
                        if (idx + 1) % 10 == 0:
                            print(f"  [PROGRESS] Processed {idx + 1}/{len(files)} images")
                    else:
                        print(f"  [SKIP] {fn} - No face detected")
                
                except Exception as e:
                    print(f"  [ERROR] {fn} - {str(e)}")
                    traceback.print_exc()
                    continue
            
            trained_students[sid] = True
            
            processed += 1
            print(f"[COMPLETE] Student {sid}: {student_encodings_count} faces extracted")
            
            if progress_callback:
                pct = int((processed / total) * 100)
                progress_callback(
                    pct, 
                    f"Processed {processed}/{total} {message_prefix} student(s) " +
                    f"(Student {sid}: {student_encodings_count} faces)"
                )
        
        if len(encodings) == 0:
            print("[ERROR] No training data found!")
            if progress_callback:
                progress_callback(0, "No training data found - no faces detected in images")
            return
        
        print(f"\n[SAVING] Preparing to save model with {len(encodings)} face encodings")
        
        model = {
            'encodings': encodings, 
            'labels': labels
        }
        
        try:
            print(f"[SAVING] Model path: {MODEL_PATH}")
            with open(MODEL_PATH, "wb") as f:
                pickle.dump(model, f)
            
            if os.path.exists(MODEL_PATH):
                file_size = os.path.getsize(MODEL_PATH)
                print(f"[SUCCESS] ✓ Model saved successfully!")
                print(f"[SUCCESS] ✓ File size: {file_size:,} bytes")
                print(f"[SUCCESS] ✓ Location: {MODEL_PATH}")
            else:
                print("[ERROR] ✗ Model file not found after save!")
                if progress_callback:
                    progress_callback(0, "Error: Model file not created")
                return
                
        except Exception as e:
            print(f"[ERROR] ✗ Failed to save model: {e}")
            traceback.print_exc()
            if progress_callback:
                progress_callback(0, f"Error saving model: {str(e)}")
            return
        
        try:
            save_trained_students(trained_students)
            print(f"[SUCCESS] ✓ Trained students tracker saved")
        except Exception as e:
            print(f"[ERROR] ✗ Failed to save trained students: {e}")
        
        total_students = len(set(labels))
        total_faces = len(encodings)
        
        print(f"\n{'='*60}")
        print(f"[TRAINING COMPLETE]")
        print(f"  Total students: {total_students}")
        print(f"  Total faces: {total_faces}")
        print(f"  Model saved: {MODEL_PATH}")
        print(f"{'='*60}\n")
        
        if progress_callback:
            progress_callback(
                100, 
                f"Training complete! {total_students} students, {total_faces} faces trained"
            )
    
    except Exception as e:
        print(f"\n[FATAL ERROR] Training failed: {e}")
        traceback.print_exc()
        if progress_callback:
            progress_callback(0, f"Training failed: {str(e)}")


# ============= STANDALONE EXECUTION =============

def main():
    """Main function to train the model when script is run directly"""
    print("\n🎓 Face Recognition Model Training Tool")
    print("="*60)
    
    dataset_dir = os.path.join(APP_DIR, "dataset")
    
    if not os.path.exists(dataset_dir):
        print(f"❌ Error: 'dataset' folder not found at {dataset_dir}!")
        print("\nPlease create a 'dataset' folder with structure:")
        print("  dataset/")
        print("    student_id_1/")
        print("      image1.jpg")
        print("      image2.jpg")
        print("    student_id_2/")
        print("      image1.jpg")
        print("      image2.jpg")
        return
    
    print(f"\n📂 Dataset directory: {dataset_dir}")
    print("\n🔄 Starting training...")
    
    def print_progress(percent, message):
        print(f"[{percent}%] {message}")
    
    train_model_background(dataset_dir, progress_callback=print_progress, full_retrain=True)


if __name__ == "__main__":
    main()