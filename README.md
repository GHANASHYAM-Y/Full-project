# Secure Face Recognition Attendance System

## Overview

This project is a **secure AI-based attendance management system** that uses **face recognition, liveness detection, geolocation verification, and two-factor authentication (TOTP)** to prevent proxy attendance and identity spoofing.

Traditional attendance systems allow students to mark attendance for others. This system eliminates that problem by verifying:

1. **User authentication**
2. **Physical location**
3. **Liveness (blink detection)**
4. **Face recognition**

Only when all checks pass will the attendance be recorded.

The system is built using **Python, Flask, OpenCV, and the face_recognition deep learning library**.

---

# Key Features

### Face Recognition Attendance

Students mark attendance using their face captured from a webcam.

### Blink Detection (Liveness Check)

The system verifies that the user is a real person by detecting a **blink using Eye Aspect Ratio (EAR)**. This prevents attacks using photos or videos.

### Geolocation Verification

Students must allow location access before marking attendance to ensure they are physically present at the required location.

### Two-Factor Authentication (TOTP)

The system uses **Time-Based One Time Password (TOTP)** authentication generated via Google Authenticator.

### Secure Authentication

Passwords are stored using **hashed encryption**.

### Automated Model Training

Face recognition models are trained automatically from student images stored in the dataset.

### Attendance Analytics

Teachers can view attendance records and export them as CSV files.

---

# System Architecture

The system follows a **Flask-based web architecture**.

```
Client (Browser)
       |
       v
Flask Web Server
       |
       +--- Authentication Module
       |
       +--- Face Recognition Engine
       |
       +--- Blink Detection System
       |
       +--- Geolocation Verification
       |
       +--- SQLite Database
```

---

# Project Structure

```
face-detection-attendance-system
│
├── app.py
├── auth_simple.py
├── model.py
├── attendance.db
├── model.pkl
│
├── dataset/
│   ├── student_id_1/
│   ├── student_id_2/
│
├── templates/
│   ├── index.html
│   ├── login_page.html
│   ├── register.html
│   ├── add_student.html
│   ├── mark_attendance.html
│   ├── attendance_record.html
│
├── static/
│   ├── css/
│   ├── js/
│   ├── images/
│
├── requirements.txt
└── README.md
```

---

# Technologies Used

### Backend

* Python
* Flask
* SQLite

### Computer Vision / AI

* OpenCV
* face_recognition
* NumPy
* Pillow

### Security

* PyOTP (Two Factor Authentication)
* Werkzeug Password Hashing
* Blink Detection using Eye Aspect Ratio

### Frontend

* HTML
* CSS
* JavaScript

---

# How the System Works

### Step 1: User Login

Users log in using their username and password.

### Step 2: Geolocation Verification

The system checks if the user is physically present at the required location.

### Step 3: TOTP Verification

A time-based OTP is generated using Google Authenticator.

### Step 4: Blink Detection

The system captures a frame and verifies a blink using **Eye Aspect Ratio (EAR)**.

### Step 5: Face Recognition

The captured image is converted into a **128-dimensional face embedding** and compared with stored embeddings.

### Step 6: Attendance Recording

If the face is recognized with sufficient confidence, the attendance is recorded in the database.

---

# Face Recognition Method

The system uses the **face_recognition** deep learning library which converts faces into **128-dimensional embeddings**.

Face similarity is calculated using **Euclidean distance** between embeddings.

If the confidence score is above a threshold (0.70), the face is considered a match.

---

# Blink Detection (Liveness Detection)

The system calculates **Eye Aspect Ratio (EAR)** from facial landmarks.

```
EAR = (A + B) / (2 × C)
```

Where:

A and B → vertical eye distances
C → horizontal eye distance

If the EAR falls below a threshold, the system detects a **blink**, confirming the user is a real person.

---

# Database Schema

### Users Table

Stores login credentials.

Fields:

* id
* username
* password_hash
* role
* full_name
* created_at

---

### Students Table

Stores student details.

Fields:

* id
* name
* roll
* department
* section
* created_at

---

### Attendance Table

Stores attendance records.

Fields:

* id
* student_id
* timestamp
* confidence
* liveness_verified

---

# Installation

Clone the repository:

```
git clone https://github.com/yourusername/your-repository-name.git
```

Navigate to the project folder:

```
cd your-repository-name
```

Install dependencies:

```
pip install -r requirements.txt
```

Run the application:

```
python app.py
```

Open the browser:

```
http://127.0.0.1:5000
```

---

# Training the Face Recognition Model

1. Add student images to the dataset folder:

```
dataset/
   student_id/
       image1.jpg
       image2.jpg
```

2. Start training from the web interface or call the training endpoint.

The system generates a trained model:

```
model.pkl
```

---

# Export Attendance Records

Attendance records can be exported as CSV for reporting and analysis.

---

# Security Features

* Password hashing
* Two-factor authentication
* Geolocation verification
* Blink-based liveness detection
* Face recognition identity verification

These layers prevent **proxy attendance and identity spoofing**.

---

# Future Improvements

* Cloud deployment
* Mobile app integration
* Multi-camera support
* Face mask recognition
* Deep learning model improvements
* Role-based dashboards

---

# Author

Developed by **Ghanashyam**

Computer Science Project
