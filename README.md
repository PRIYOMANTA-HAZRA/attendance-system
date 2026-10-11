# Employee Attendance Management System

A modern, responsive Employee Attendance Management System with 6-digit ID login, admin approvals, geolocation capture (Google Maps integration), date/month-wise Excel export, and real-time cloud data storage using **Google Firebase Firestore** (with fallback to SQLite).

## Features
- **6-Digit ID System:** Employees submit an account request; admin approves and issues a secure 6-digit ID.
- **Admin Controls:** Toggle registration on/off, promote/demote editors, view/delete employees.
- **Live Status:** Color-coded names (Green for active checked-in, Red for checked-out).
- **Google Maps Integration:** Clickable map links with coordinates for Check-in and Check-out.
- **Advanced Export:** Filter by custom date ranges and export directly to Microsoft Excel (`.xlsx`).
- **Google Firebase Firestore:** Real-time cloud storage with seamless local SQLite fallback.

## Quick Start

### 1. Clone & Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Firebase Setup (Optional but Recommended)
1. Download your Service Account Key JSON from the [Firebase Console](https://console.firebase.google.com/).
2. Rename it to `firebase-key.json` and place it in the project root directory.

### 3. Run the Application
```bash
python app.py
```
Visit `http://127.0.0.1:5000` in your browser.
