from flask import Flask, request, jsonify, render_template, send_file, send_from_directory
import sqlite3
import random
import datetime
import time
import pandas as pd
import io
import os
import urllib.request
import json
from dotenv import load_dotenv
load_dotenv()
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from database import init_db, get_db_connection
import firebase_db

# Ensure working directory is the script folder (fixes PythonAnywhere CWD issues)
os.chdir(os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Initialize Firebase if firebase-key.json exists, otherwise fallback to SQLite
USE_FIREBASE = firebase_db.init_firebase()
if USE_FIREBASE:
    print(">>> Running with Google Firebase Firestore backend <<<")
else:
    print(">>> Running with local SQLite backend (firebase-key.json not found) <<<")
    if not os.path.exists('attendance.db'):
        init_db()

# IST Timezone Helper (GMT+5:30 for Indian/Bangladesh Time)
def get_ist_now():
    tz_ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    return datetime.datetime.now(tz_ist)

def get_ist_time_str(dt=None):
    if dt is None:
        dt = get_ist_now()
    return dt.strftime('%I:%M:%S %p')

def get_ist_date_str(dt=None):
    if dt is None:
        dt = get_ist_now()
    return dt.strftime('%Y-%m-%d')

def calculate_work_duration(login_time_str, logout_time_str):
    if not login_time_str or not logout_time_str:
        return '-'
    try:
        t1, t2 = None, None
        for fmt in ('%I:%M:%S %p', '%H:%M:%S', '%I:%M %p'):
            try:
                t1 = datetime.datetime.strptime(login_time_str.strip(), fmt)
                break
            except ValueError:
                continue
        for fmt in ('%I:%M:%S %p', '%H:%M:%S', '%I:%M %p'):
            try:
                t2 = datetime.datetime.strptime(logout_time_str.strip(), fmt)
                break
            except ValueError:
                continue
        if not t1 or not t2:
            return '-'
        total_seconds = int((t2 - t1).total_seconds())
        if total_seconds < 0:
            total_seconds += 24 * 3600
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        if hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
    except Exception:
        return '-'

# Admin OTP Storage (In-memory simulation)
active_otps = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/api/backend-status', methods=['GET'])
def backend_status():
    return jsonify({
        'database': 'Google Firebase Firestore' if USE_FIREBASE else 'SQLite (Local)',
        'firebase_active': USE_FIREBASE,
        'server_time': get_ist_time_str(),
        'server_date': get_ist_date_str()
    })

# Email OTP Helper Function
def send_admin_otp_email(recipient_email, otp_code):
    smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    smtp_user = os.environ.get('SMTP_EMAIL', '')
    smtp_pass = os.environ.get('SMTP_PASSWORD', '').replace(' ', '')
    resend_api_key = os.environ.get('RESEND_API_KEY', '').strip()

    subject = f"Your Admin Access OTP: {otp_code}"
    body = f"""Hello Priyomanta,

Your 6-digit security OTP to access the Admin Panel is:

==============================
            {otp_code}
==============================

This OTP is valid for 5 minutes.
If you did not request this OTP, please change your admin password immediately.

Attendance Management System
"""

    print("\n" + "=" * 50, flush=True)
    print(f"[SECURITY OTP] Sent to Email: {recipient_email}", flush=True)
    print(f"[SECURITY OTP CODE]: {otp_code}", flush=True)
    print("=" * 50 + "\n", flush=True)

    # 1. First Priority: Resend HTTPS REST API (Works 100% on Render Free Tier via Port 443)
    if resend_api_key:
        try:
            payload = json.dumps({
                "from": "Attendance System <onboarding@resend.dev>",
                "to": [recipient_email],
                "subject": subject,
                "text": body
            }).encode('utf-8')
            req = urllib.request.Request(
                "https://api.resend.com/emails",
                data=payload,
                headers={
                    "Authorization": f"Bearer {resend_api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "AttendanceSystem/1.0"
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status in (200, 201):
                    print(f">>> [SUCCESS] Security OTP delivered to {recipient_email} via Resend API! <<<", flush=True)
                    return True, "delivered_resend"
        except Exception as e:
            print(f">>> [RESEND API NOTICE] Resend delivery failed ({e}). Falling back to SMTP... <<<", flush=True)

    # 2. Second Priority: Direct SMTP
    if smtp_user and smtp_pass:
        try:
            msg = MIMEMultipart()
            msg['From'] = smtp_user
            msg['To'] = recipient_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP(smtp_server, smtp_port, timeout=8)
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipient_email, msg.as_string())
            server.quit()
            print(f">>> [SUCCESS] Security OTP delivered to {recipient_email} via SMTP! <<<", flush=True)
            return True, "delivered_smtp"
        except Exception as e:
            print(f">>> [SMTP NOTICE] Cloud provider blocked outbound SMTP port ({e}). Check Render Logs or use Master PIN. <<<", flush=True)
            return False, str(e)
    else:
        print(">>> [NOTICE] Email credentials not configured. <<<", flush=True)
        return False, "not_configured"

# Admin Login & OTP Endpoints
@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.json or {}
    username = (data.get('username') or data.get('user_id') or '').strip()
    password = data.get('password', '').strip()

    # 1. Check Sub-Admins / Managers first (Direct login to dashboard without OTP)
    if USE_FIREBASE:
        subadmin = firebase_db.verify_subadmin_login(username, password)
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM subadmins WHERE username=? AND password=?", (username, password))
        row = cursor.fetchone()
        conn.close()
        subadmin = dict(row) if row else None

    if subadmin:
        return jsonify({
            'success': True,
            'direct_login': True,
            'user': {
                'name': subadmin.get('name') or username,
                'user_id': username,
                'role': 'subadmin',
                'is_master': False
            }
        })

    # 2. Check Primary Master Admin (requires OTP)
    valid = False
    admin_email = 'prempriyomanta@gmail.com'
    if USE_FIREBASE:
        settings = firebase_db.get_settings()
        admin_u = settings.get('admin_username', 'priyomanta')
        admin_p = settings.get('admin_password', 'BDO@8389')
        admin_email = settings.get('admin_email', 'prempriyomanta@gmail.com')
        if username == admin_u and password == admin_p:
            valid = True
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key='admin_username'")
        u_row = cursor.fetchone()
        cursor.execute("SELECT value FROM settings WHERE key='admin_password'")
        p_row = cursor.fetchone()
        cursor.execute("SELECT value FROM settings WHERE key='admin_email'")
        e_row = cursor.fetchone()
        conn.close()
        u_val = u_row['value'] if u_row else 'priyomanta'
        p_val = p_row['value'] if p_row else 'BDO@8389'
        admin_email = e_row['value'] if e_row else 'prempriyomanta@gmail.com'
        if username == u_val and password == p_val:
            valid = True

    if not valid:
        return jsonify({'error': 'Invalid Admin ID or Password.'}), 401

    otp = str(random.randint(100000, 999999))
    active_otps[username] = {
        'otp': otp,
        'expires': time.time() + 300
    }

    email_sent, status_reason = send_admin_otp_email(admin_email, otp)

    if email_sent:
        user_msg = f'A 6-digit OTP has been sent to your email {admin_email}. Please check your email inbox.'
    else:
        user_msg = 'Security OTP generated! Check your email inbox, Render Logs, or enter your Emergency Master PIN.'

    return jsonify({
        'success': True,
        'otp_sent': email_sent,
        'email': admin_email,
        'message': user_msg
    })

@app.route('/api/admin/verify-otp', methods=['POST'])
def verify_admin_otp():
    data = request.json or {}
    username = data.get('username', '').strip()
    otp = str(data.get('otp', '')).strip()

    # Emergency Master Backup PIN (Allows instant access if email or network is blocked)
    master_pin = os.environ.get("MASTER_ADMIN_PIN", "838900").strip()
    if master_pin and otp == master_pin:
        print(f">>> [SECURITY] Admin access granted via Master Backup PIN for user '{username}'! <<<", flush=True)
        if username in active_otps:
            del active_otps[username]
        return jsonify({
            'success': True,
            'user': {'name': 'Priyomanta', 'user_id': 'ADMIN', 'role': 'owner', 'is_master': True}
        })

    entry = active_otps.get(username)
    if not entry or time.time() > entry['expires']:
        return jsonify({'error': 'OTP expired or invalid. Please request again.'}), 400

    if entry['otp'] != otp:
        return jsonify({'error': 'Incorrect OTP.'}), 400

    del active_otps[username]
    return jsonify({
        'success': True,
        'user': {'name': 'Priyomanta', 'user_id': 'ADMIN', 'role': 'owner', 'is_master': True}
    })

@app.route('/api/settings', methods=['GET', 'POST'])
def manage_settings():
    if request.method == 'GET':
        if USE_FIREBASE:
            st = firebase_db.get_settings()
            return jsonify({
                'allow_registration': st.get('allow_registration', True),
                'allow_id_cards': st.get('allow_id_cards', True)
            })
        else:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM settings")
            rows = dict(cursor.fetchall())
            conn.close()
            return jsonify({
                'allow_registration': rows.get('allow_registration', 'true') == 'true',
                'allow_id_cards': rows.get('allow_id_cards', 'true') == 'true'
            })
            
    elif request.method == 'POST':
        data = request.json or {}
        setting_key = data.get('setting')
        if setting_key == 'allow_id_cards':
            allow = bool(data.get('allow'))
            if USE_FIREBASE:
                firebase_db.set_allow_id_cards(allow)
            else:
                allow_str = 'true' if allow else 'false'
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('allow_id_cards', ?)", (allow_str,))
                conn.commit()
                conn.close()
            return jsonify({'success': True, 'allow_id_cards': allow})
        else:
            allow = bool(data.get('allow'))
            if USE_FIREBASE:
                firebase_db.set_allow_registration(allow)
            else:
                allow_str = 'true' if allow else 'false'
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("UPDATE settings SET value=? WHERE key='allow_registration'", (allow_str,))
                conn.commit()
                conn.close()
            return jsonify({'success': True, 'allow_registration': allow})

# Registration
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json or {}
    name = data.get('name')
    if not name:
        return jsonify({'error': 'Name is required.'}), 400

    if USE_FIREBASE:
        if not firebase_db.get_allow_registration():
            return jsonify({'error': 'Registration is currently disabled.'}), 403

        count = firebase_db.get_total_users_count()
        if count == 0:
            new_id = firebase_db.generate_unique_user_id()
            firebase_db.create_initial_owner(data, new_id)
            return jsonify({
                'success': True, 
                'approved': True, 
                'user_id': new_id, 
                'message': f'First user created. ID: {new_id} (Role: Owner)'
            })
        else:
            firebase_db.create_user_request(data)
            return jsonify({
                'success': True, 
                'approved': False, 
                'message': 'Registration request submitted! Please wait for admin approval to get your ID.'
            })
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key='allow_registration'")
        setting = cursor.fetchone()
        if setting['value'] != 'true':
            conn.close()
            return jsonify({'error': 'Registration is currently disabled.'}), 403
        
        cursor.execute("SELECT COUNT(*) as count FROM users")
        count = cursor.fetchone()['count']
        
        email = data.get('email', '')
        whatsapp = data.get('whatsapp', '')
        dob = data.get('dob', '')
        profile_image = data.get('profile_image', '')

        if count == 0:
            role = 'owner'
            status = 'approved'
            while True:
                new_id = str(random.randint(100000, 999999))
                cursor.execute("SELECT user_id FROM users WHERE user_id=?", (new_id,))
                if not cursor.fetchone():
                    break
            cursor.execute('''
                INSERT INTO users (user_id, name, email, whatsapp, dob, profile_image, role, status) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (new_id, name, email, whatsapp, dob, profile_image, role, status))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'approved': True, 'user_id': new_id, 'message': f'First user created. ID: {new_id}'})
        else:
            cursor.execute('''
                INSERT INTO users (name, email, whatsapp, dob, profile_image, role, status) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (name, email, whatsapp, dob, profile_image, 'employee', 'pending'))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'approved': False, 'message': 'Registration request submitted! Please wait for admin approval to get your ID.'})

# Login & Logout
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    user_id = data.get('user_id')
    lat = data.get('lat')
    lng = data.get('lng')
    
    date_today = get_ist_date_str()
    time_now = get_ist_time_str()

    if USE_FIREBASE:
        user = firebase_db.get_user_by_6digit_id(user_id)
        if not user:
            return jsonify({'error': 'Invalid or Unapproved ID.'}), 401
        
        firebase_db.record_login(user_id, user.get('name', ''), lat, lng, date_today, time_now)
        return jsonify({
            'success': True, 
            'user': user, 
            'login_time': time_now,
            'status': 'green'
        })
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id=? AND status='approved'", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            conn.close()
            return jsonify({'error': 'Invalid or Unapproved ID.'}), 401
            
        cursor.execute("SELECT * FROM attendance WHERE user_id=? AND date=? ORDER BY id DESC LIMIT 1", (user_id, date_today))
        attendance = cursor.fetchone()
        
        if not (attendance and attendance['status'] == 'green'):
            cursor.execute("INSERT INTO attendance (user_id, date, login_time, login_lat, login_lng, status, work_hours) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (user_id, date_today, time_now, lat, lng, 'green', '-'))
            
        conn.commit()
        conn.close()
        return jsonify({
            'success': True, 
            'user': dict(user), 
            'login_time': time_now,
            'status': 'green'
        })

@app.route('/api/logout', methods=['POST'])
def logout():
    data = request.json or {}
    user_id = data.get('user_id')
    lat = data.get('lat')
    lng = data.get('lng')
    
    date_today = get_ist_date_str()
    time_now = get_ist_time_str()

    if USE_FIREBASE:
        details = firebase_db.get_user_status_today(user_id, date_today)
        login_time = details.get('login_time')
        work_hours = calculate_work_duration(login_time, time_now)
        firebase_db.record_logout(user_id, lat, lng, date_today, time_now, work_hours)
        return jsonify({'success': True, 'status': 'red', 'work_hours': work_hours, 'logout_time': time_now})
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM attendance WHERE user_id=? AND date=? AND status='green' ORDER BY id DESC LIMIT 1", (user_id, date_today))
        attendance = cursor.fetchone()
        
        work_hours = '-'
        if attendance:
            work_hours = calculate_work_duration(attendance['login_time'], time_now)
            cursor.execute("UPDATE attendance SET logout_time=?, logout_lat=?, logout_lng=?, work_hours=?, status='red' WHERE id=?", 
                           (time_now, lat, lng, work_hours, attendance['id']))
            conn.commit()
            
        conn.close()
        return jsonify({'success': True, 'status': 'red', 'work_hours': work_hours, 'logout_time': time_now})

@app.route('/api/status/<user_id>', methods=['GET'])
def get_status(user_id):
    date_today = get_ist_date_str()
    time_now = get_ist_time_str()
    
    if USE_FIREBASE:
        details = firebase_db.get_user_status_today(user_id, date_today)
        u = firebase_db.get_user_by_6digit_id(user_id)
        id_enabled = (u.get('id_card_enabled') is not False) if u else True
        return jsonify({
            'status': details.get('status', 'none'),
            'login_time': details.get('login_time'),
            'logout_time': details.get('logout_time'),
            'work_hours': details.get('work_hours'),
            'current_time': time_now,
            'date': date_today,
            'id_card_enabled': id_enabled
        })
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM attendance WHERE user_id=? AND date=? ORDER BY id DESC LIMIT 1", (user_id, date_today))
        attendance = cursor.fetchone()
        cursor.execute("SELECT id_card_enabled FROM users WHERE user_id=?", (str(user_id),))
        u_row = cursor.fetchone()
        id_enabled = (u_row['id_card_enabled'] != 0) if (u_row and 'id_card_enabled' in u_row.keys()) else True
        conn.close()
        if attendance:
            return jsonify({
                'status': attendance['status'],
                'login_time': attendance['login_time'],
                'logout_time': attendance['logout_time'],
                'work_hours': attendance['work_hours'],
                'current_time': time_now,
                'date': date_today,
                'id_card_enabled': id_enabled
            })
        return jsonify({
            'status': 'none',
            'login_time': None,
            'logout_time': None,
            'work_hours': None,
            'current_time': time_now,
            'date': date_today,
            'id_card_enabled': id_enabled
        })

@app.route('/api/employee/work-summary/<user_id>', methods=['GET'])
def employee_work_summary(user_id):
    if USE_FIREBASE:
        records = firebase_db.get_employee_attendance_records(user_id)
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM attendance WHERE user_id=? ORDER BY date DESC, id DESC", (str(user_id),))
        records = [dict(row) for row in cursor.fetchall()]
        conn.close()

    unique_days = len(set(r.get('date') for r in records if r.get('date')))
    
    total_minutes = 0
    import re
    for r in records:
        w = r.get('work_hours')
        if w and w != '-':
            m_h = re.search(r'(\d+)\s*h', str(w))
            m_m = re.search(r'(\d+)\s*m', str(w))
            h = int(m_h.group(1)) if m_h else 0
            m = int(m_m.group(1)) if m_m else 0
            total_minutes += (h * 60 + m)

    total_h = total_minutes // 60
    total_m = total_minutes % 60
    total_hours_str = f"{total_h}h {total_m}m"

    return jsonify({
        'total_days': unique_days,
        'total_hours': total_hours_str,
        'records': records
    })

@app.route('/api/employee/id-card/<user_id>', methods=['GET'])
def get_employee_id_card(user_id):
    if USE_FIREBASE:
        st = firebase_db.get_settings()
        if not st.get('allow_id_cards', True):
            return jsonify({'error': 'ID Card viewing is currently disabled by Admin.'}), 403
        u = firebase_db.get_user_by_6digit_id(user_id)
        if not u:
            return jsonify({'error': 'Employee profile not found.'}), 404
        if u.get('id_card_enabled') is False:
            return jsonify({'error': 'ID Card is currently disabled for your profile by Admin.'}), 403
        return jsonify({
            'success': True,
            'user': u,
            'card_data': u.get('id_card_data', {})
        })
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key='allow_id_cards'")
        row = cursor.fetchone()
        allow = (row and row['value'] == 'true')
        if not allow:
            conn.close()
            return jsonify({'error': 'ID Card viewing is currently disabled by Admin.'}), 403
        cursor.execute("SELECT * FROM users WHERE user_id=? AND status='approved'", (str(user_id),))
        row_user = cursor.fetchone()
        conn.close()
        if not row_user:
            return jsonify({'error': 'Employee profile not found.'}), 404
        u_dict = dict(row_user)
        if 'id_card_enabled' in u_dict and u_dict['id_card_enabled'] == 0:
            return jsonify({'error': 'ID Card is currently disabled for your profile by Admin.'}), 403
        card_data = {}
        if u_dict.get('id_card_data'):
            try:
                card_data = json.loads(u_dict['id_card_data'])
            except Exception:
                card_data = {}
        return jsonify({
            'success': True,
            'user': u_dict,
            'card_data': card_data
        })

# Leave Management Endpoints
@app.route('/api/leave/apply', methods=['POST'])
def apply_leave():
    data = request.json or {}
    user_id = data.get('user_id')
    name = data.get('name')
    leave_type = data.get('leave_type')
    date_val = data.get('date', get_ist_date_str())
    message = data.get('message', '')

    if not user_id or not leave_type:
        return jsonify({'error': 'User ID and Leave Type are required.'}), 400

    if USE_FIREBASE:
        leave_doc = firebase_db.create_leave_request(user_id, name, leave_type, date_val, message)
        return jsonify({'success': True, 'leave': leave_doc})
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        now_iso = datetime.datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO leaves (user_id, name, leave_type, date, message, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'Pending', ?)
        ''', (user_id, name, leave_type, date_val, message, now_iso))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

@app.route('/api/leave/my-leaves/<user_id>', methods=['GET'])
def my_leaves(user_id):
    if USE_FIREBASE:
        return jsonify(firebase_db.get_user_leaves(user_id))
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leaves WHERE user_id=? ORDER BY id DESC", (user_id,))
        records = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(records)

@app.route('/api/admin/leaves', methods=['GET'])
def admin_leaves():
    if USE_FIREBASE:
        return jsonify(firebase_db.get_all_leaves())
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leaves ORDER BY id DESC")
        records = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(records)

@app.route('/api/admin/leaves/<id>/action', methods=['POST'])
def admin_leave_action(id):
    data = request.json or {}
    status_val = data.get('status') # 'Approved' or 'Rejected'
    if not status_val:
        return jsonify({'error': 'Status is required.'}), 400

    if USE_FIREBASE:
        firebase_db.update_leave_status(id, status_val)
        return jsonify({'success': True})
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE leaves SET status=? WHERE id=?", (status_val, id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

@app.route('/api/admin/leaves/<id>', methods=['DELETE'])
def delete_leave(id):
    if USE_FIREBASE:
        firebase_db.delete_leave_request(id)
        return jsonify({'success': True})
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM leaves WHERE id=?", (id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

# Office Messages Endpoints
@app.route('/api/admin/message/send', methods=['POST'])
def send_message():
    data = request.json or {}
    to_user_id = data.get('to_user_id')
    title = data.get('title', 'Office Notice')
    message_text = data.get('message', '')
    from_name = data.get('from_name', 'Admin')
    date_val = get_ist_date_str()

    if not to_user_id or not message_text:
        return jsonify({'error': 'Recipient and message text are required.'}), 400

    if USE_FIREBASE:
        msg = firebase_db.send_office_message(from_name, to_user_id, title, message_text, date_val)
        return jsonify({'success': True, 'message': msg})
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        now_iso = datetime.datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO messages (from_name, to_user_id, title, message, date, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (from_name, to_user_id, title, message_text, date_val, now_iso))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

@app.route('/api/messages/<user_id>', methods=['GET'])
def get_user_messages(user_id):
    if USE_FIREBASE:
        return jsonify(firebase_db.get_user_messages(user_id))
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.datetime.now()
        cursor.execute("SELECT id, created_at FROM messages")
        all_msgs = cursor.fetchall()
        delete_ids = []
        for m in all_msgs:
            c_at = m['created_at']
            if c_at:
                try:
                    if (now - datetime.datetime.fromisoformat(c_at)).total_seconds() > 12 * 3600:
                        delete_ids.append(m['id'])
                except Exception:
                    pass
        if delete_ids:
            placeholders = ','.join('?' * len(delete_ids))
            cursor.execute(f"DELETE FROM messages WHERE id IN ({placeholders})", delete_ids)
            conn.commit()

        cursor.execute("SELECT * FROM messages WHERE to_user_id=? OR to_user_id='ALL' ORDER BY id DESC", (str(user_id),))
        records = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(records)

# Admin Management APIs
@app.route('/api/admin/stats', methods=['GET'])
def get_stats():
    if USE_FIREBASE:
        stats = firebase_db.get_stats()
        leaves_count = len(firebase_db.get_all_leaves())
        stats['total_leaves'] = leaves_count
        return jsonify(stats)
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE status='approved'")
        total_employees = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE status='pending'")
        pending_requests = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM leaves WHERE status='Pending'")
        pending_leaves = cursor.fetchone()['count']
        conn.close()
        return jsonify({
            'total_employees': total_employees, 
            'pending_requests': pending_requests,
            'pending_leaves': pending_leaves
        })

@app.route('/api/admin/users', methods=['GET'])
def get_users():
    if USE_FIREBASE:
        return jsonify(firebase_db.get_approved_users())
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE status='approved'")
        users = []
        for row in cursor.fetchall():
            d = dict(row)
            if 'id_card_data' in d and d['id_card_data']:
                try:
                    d['id_card_data'] = json.loads(d['id_card_data'])
                except Exception:
                    d['id_card_data'] = {}
            else:
                d['id_card_data'] = {}
            d['id_card_enabled'] = (d.get('id_card_enabled') != 0) if 'id_card_enabled' in d else True
            users.append(d)
        conn.close()
        return jsonify(users)

@app.route('/api/admin/users/<id>/id-card', methods=['POST'])
def save_id_card(id):
    data = request.json or {}
    card_data = data.get('card_data', {})
    if USE_FIREBASE:
        firebase_db.update_user_id_card(id, card_data)
        return jsonify({'success': True})
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET id_card_data=? WHERE id=?", (json.dumps(card_data), id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

@app.route('/api/admin/users/<id>/toggle-id-card', methods=['POST'])
def toggle_employee_id_card(id):
    data = request.json or {}
    enabled = bool(data.get('enabled', True))
    if USE_FIREBASE:
        firebase_db.toggle_user_id_card(id, enabled)
        return jsonify({'success': True, 'id_card_enabled': enabled})
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        val = 1 if enabled else 0
        cursor.execute("UPDATE users SET id_card_enabled=? WHERE id=?", (val, id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'id_card_enabled': enabled})

@app.route('/api/admin/users/<id>', methods=['DELETE'])
def delete_user(id):
    if USE_FIREBASE:
        firebase_db.delete_user(id)
        return jsonify({'success': True})
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id=?", (id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

# Master Control Sub-Admin Management
@app.route('/api/admin/subadmins', methods=['GET', 'POST'])
def manage_subadmins():
    if request.method == 'GET':
        if USE_FIREBASE:
            return jsonify(firebase_db.get_subadmins())
        else:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, password, name, created_at FROM subadmins ORDER BY id DESC")
            records = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return jsonify(records)
    elif request.method == 'POST':
        data = request.json or {}
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        name = data.get('name', '').strip() or username

        if not username or not password:
            return jsonify({'error': 'Manager ID and Password are required.'}), 400

        if USE_FIREBASE:
            sub = firebase_db.create_subadmin(username, password, name)
            if not sub:
                return jsonify({'error': f"Manager ID '{username}' already exists. Please choose a different ID."}), 400
            return jsonify({'success': True, 'subadmin': sub})
        else:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM subadmins WHERE username=?", (username,))
            if cursor.fetchone():
                conn.close()
                return jsonify({'error': f"Manager ID '{username}' already exists. Please choose a different ID."}), 400
            now_iso = datetime.datetime.now().isoformat()
            cursor.execute("INSERT INTO subadmins (username, password, name, created_at) VALUES (?, ?, ?, ?)",
                           (username, password, name, now_iso))
            conn.commit()
            sub_id = cursor.lastrowid
            conn.close()
            return jsonify({'success': True, 'subadmin': {'id': sub_id, 'username': username, 'name': name, 'created_at': now_iso}})

@app.route('/api/admin/subadmins/<id>', methods=['DELETE'])
def remove_subadmin(id):
    if USE_FIREBASE:
        firebase_db.delete_subadmin(id)
        return jsonify({'success': True})
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM subadmins WHERE id=?", (id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

@app.route('/api/admin/role', methods=['POST'])
def set_role():
    data = request.json or {}
    user_db_id = data.get('id')
    role = data.get('role')
    
    if USE_FIREBASE:
        firebase_db.set_user_role(user_db_id, role)
        return jsonify({'success': True})
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role=? WHERE id=?", (role, user_db_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

@app.route('/api/admin/requests', methods=['GET'])
def get_requests():
    if USE_FIREBASE:
        return jsonify(firebase_db.get_pending_requests())
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE status='pending'")
        users = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(users)

@app.route('/api/admin/approve/<id>', methods=['POST'])
def approve_request(id):
    if USE_FIREBASE:
        new_id = firebase_db.approve_user_request(id)
        return jsonify({'success': True, 'user_id': new_id})
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        while True:
            new_id = str(random.randint(100000, 999999))
            cursor.execute("SELECT user_id FROM users WHERE user_id=?", (new_id,))
            if not cursor.fetchone():
                break
                
        cursor.execute("UPDATE users SET status='approved', user_id=? WHERE id=?", (new_id, id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'user_id': new_id})

@app.route('/api/admin/attendance', methods=['GET'])
def get_attendance():
    date = request.args.get('date')
    if USE_FIREBASE:
        return jsonify(firebase_db.get_grouped_attendance(date))
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        if date:
            cursor.execute('''
                SELECT a.*, u.name, u.email, u.whatsapp 
                FROM attendance a 
                JOIN users u ON a.user_id = u.user_id 
                WHERE a.date = ?
                ORDER BY a.id DESC
            ''', (date,))
        else:
            cursor.execute('''
                SELECT a.*, u.name, u.email, u.whatsapp 
                FROM attendance a 
                JOIN users u ON a.user_id = u.user_id 
                ORDER BY a.date DESC, a.id DESC
            ''')
            
        records = [dict(row) for row in cursor.fetchall()]
        grouped = {}
        for r in records:
            d = r['date']
            if d not in grouped:
                grouped[d] = []
            grouped[d].append(r)
            
        conn.close()
        return jsonify(grouped)

@app.route('/api/admin/attendance/<id>', methods=['DELETE'])
def delete_attendance(id):
    if USE_FIREBASE:
        firebase_db.delete_attendance_record(id)
        return jsonify({'success': True})
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM attendance WHERE id=?", (id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})

@app.route('/api/admin/attendance/date/<date_str>', methods=['DELETE'])
def delete_attendance_by_date_route(date_str):
    if USE_FIREBASE:
        firebase_db.delete_attendance_by_date(date_str)
        return jsonify({'success': True, 'date': date_str})
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM attendance WHERE date=?", (date_str,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'date': date_str})

@app.route('/api/admin/export', methods=['GET'])
def export_excel():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if USE_FIREBASE:
        rows = firebase_db.get_attendance_export_data(start_date, end_date)
        df = pd.DataFrame(rows)
    else:
        conn = get_db_connection()
        query = '''
            SELECT a.date as Date, u.user_id as "User ID", u.name as Name, 
                   a.login_time as "Login Time", a.logout_time as "Logout Time",
                   a.work_hours as "Work Duration",
                   a.login_lat as "Login Latitude", a.login_lng as "Login Longitude",
                   a.logout_lat as "Logout Latitude", a.logout_lng as "Logout Longitude",
                   'https://maps.google.com/?q=' || a.login_lat || ',' || a.login_lng as "Login Map",
                   'https://maps.google.com/?q=' || a.logout_lat || ',' || a.logout_lng as "Logout Map"
            FROM attendance a 
            JOIN users u ON a.user_id = u.user_id 
        '''
        params = []
        if start_date and end_date:
            query += ' WHERE a.date BETWEEN ? AND ? '
            params = [start_date, end_date]
        elif start_date:
            query += ' WHERE a.date >= ? '
            params = [start_date]
        elif end_date:
            query += ' WHERE a.date <= ? '
            params = [end_date]
            
        query += ' ORDER BY a.date DESC, a.id DESC'
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Attendance')
        
    output.seek(0)
    filename = f"attendance_export_{start_date or 'all'}_to_{end_date or 'all'}.xlsx"
    return send_file(
        output,
        download_name=filename,
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
