from flask import Flask, request, jsonify, render_template, send_file
import sqlite3
import random
import datetime
import pandas as pd
import io
import os
from database import init_db, get_db_connection
import firebase_db

# Ensure working directory is the script folder (fixes PythonAnywhere CWD issues)
os.chdir(os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__, template_folder='templates', static_folder='static')

# Initialize Firebase if firebase-key.json exists, otherwise fallback to SQLite
USE_FIREBASE = firebase_db.init_firebase()
if USE_FIREBASE:
    print(">>> Running with Google Firebase Firestore backend <<<")
else:
    print(">>> Running with local SQLite backend (firebase-key.json not found) <<<")
    if not os.path.exists('attendance.db'):
        init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/api/backend-status', methods=['GET'])
def backend_status():
    return jsonify({
        'database': 'Google Firebase Firestore' if USE_FIREBASE else 'SQLite (Local)',
        'firebase_active': USE_FIREBASE
    })

@app.route('/api/settings', methods=['GET', 'POST'])
def manage_settings():
    if request.method == 'GET':
        if USE_FIREBASE:
            return jsonify({'allow_registration': firebase_db.get_allow_registration()})
        else:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key='allow_registration'")
            result = cursor.fetchone()
            conn.close()
            return jsonify({'allow_registration': result['value'] == 'true'})
            
    elif request.method == 'POST':
        data = request.json
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

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    name = data.get('name')
    if not name:
        return jsonify({'error': 'Name is required.'}), 400

    if USE_FIREBASE:
        if not firebase_db.get_allow_registration():
            return jsonify({'error': 'Registration is currently disabled.'}), 403

        count = firebase_db.get_total_users_count()
        if count == 0:
            new_id = firebase_db.generate_unique_user_id()
            firebase_db.create_initial_owner(name, new_id)
            return jsonify({
                'success': True, 
                'approved': True, 
                'user_id': new_id, 
                'message': f'First user created. ID: {new_id} (Role: Owner)'
            })
        else:
            firebase_db.create_user_request(name)
            return jsonify({
                'success': True, 
                'approved': False, 
                'message': 'Registration request submitted. Please wait for admin approval to get your ID.'
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
        
        if count == 0:
            role = 'owner'
            status = 'approved'
            while True:
                new_id = str(random.randint(100000, 999999))
                cursor.execute("SELECT user_id FROM users WHERE user_id=?", (new_id,))
                if not cursor.fetchone():
                    break
            cursor.execute("INSERT INTO users (user_id, name, role, status) VALUES (?, ?, ?, ?)", (new_id, name, role, status))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'approved': True, 'user_id': new_id, 'message': f'First user created. ID: {new_id}'})
        else:
            cursor.execute("INSERT INTO users (name, role, status) VALUES (?, ?, ?)", (name, 'employee', 'pending'))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'approved': False, 'message': 'Registration request submitted. Please wait for admin approval to get your ID.'})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user_id = data.get('user_id')
    lat = data.get('lat')
    lng = data.get('lng')
    
    date_today = datetime.datetime.now().strftime('%Y-%m-%d')
    time_now = datetime.datetime.now().strftime('%H:%M:%S')

    if USE_FIREBASE:
        user = firebase_db.get_user_by_6digit_id(user_id)
        if not user:
            return jsonify({'error': 'Invalid or Unapproved ID.'}), 401
        
        firebase_db.record_login(user_id, user.get('name', ''), lat, lng, date_today, time_now)
        return jsonify({
            'success': True, 
            'user': user, 
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
            cursor.execute("INSERT INTO attendance (user_id, date, login_time, login_lat, login_lng, status) VALUES (?, ?, ?, ?, ?, ?)",
                           (user_id, date_today, time_now, lat, lng, 'green'))
            
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'user': dict(user), 'status': 'green'})

@app.route('/api/logout', methods=['POST'])
def logout():
    data = request.json
    user_id = data.get('user_id')
    lat = data.get('lat')
    lng = data.get('lng')
    
    date_today = datetime.datetime.now().strftime('%Y-%m-%d')
    time_now = datetime.datetime.now().strftime('%H:%M:%S')

    if USE_FIREBASE:
        firebase_db.record_logout(user_id, lat, lng, date_today, time_now)
        return jsonify({'success': True, 'status': 'red'})
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM attendance WHERE user_id=? AND date=? AND status='green' ORDER BY id DESC LIMIT 1", (user_id, date_today))
        attendance = cursor.fetchone()
        
        if attendance:
            cursor.execute("UPDATE attendance SET logout_time=?, logout_lat=?, logout_lng=?, status='red' WHERE id=?", 
                           (time_now, lat, lng, attendance['id']))
            conn.commit()
            
        conn.close()
        return jsonify({'success': True, 'status': 'red'})

@app.route('/api/status/<user_id>', methods=['GET'])
def get_status(user_id):
    date_today = datetime.datetime.now().strftime('%Y-%m-%d')
    if USE_FIREBASE:
        status = firebase_db.get_user_status_today(user_id, date_today)
        return jsonify({'status': status})
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM attendance WHERE user_id=? AND date=? ORDER BY id DESC LIMIT 1", (user_id, date_today))
        attendance = cursor.fetchone()
        conn.close()
        return jsonify({'status': attendance['status'] if attendance else 'none'})

@app.route('/api/admin/stats', methods=['GET'])
def get_stats():
    if USE_FIREBASE:
        return jsonify(firebase_db.get_stats())
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE status='approved'")
        total_employees = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE status='pending'")
        pending_requests = cursor.fetchone()['count']
        conn.close()
        return jsonify({'total_employees': total_employees, 'pending_requests': pending_requests})

@app.route('/api/admin/users', methods=['GET'])
def get_users():
    if USE_FIREBASE:
        return jsonify(firebase_db.get_approved_users())
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE status='approved'")
        users = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(users)

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

@app.route('/api/admin/role', methods=['POST'])
def set_role():
    data = request.json
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
                SELECT a.*, u.name 
                FROM attendance a 
                JOIN users u ON a.user_id = u.user_id 
                WHERE a.date = ?
                ORDER BY a.login_time DESC
            ''', (date,))
        else:
            cursor.execute('''
                SELECT a.*, u.name 
                FROM attendance a 
                JOIN users u ON a.user_id = u.user_id 
                ORDER BY a.date DESC, a.login_time DESC
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
            
        query += ' ORDER BY a.date DESC, a.login_time ASC'
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
    app.run(debug=True, port=5000)
