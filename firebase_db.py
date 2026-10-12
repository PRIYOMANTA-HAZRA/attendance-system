import os
import random
import datetime

def get_key_path():
    base = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base, 'firebase-key.json'),
        os.path.join(base, 'firebase-key.json.json')
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None

db = None
firebase_initialized = False

def init_firebase():
    global db, firebase_initialized
    key_path = get_key_path()
    if not key_path:
        print("Warning: Firebase service account key not found (checked firebase-key.json and firebase-key.json.json)")
        return False
    
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        
        if not firebase_admin._apps:
            cred = credentials.Certificate(key_path)
            firebase_admin.initialize_app(cred)
        
        db = firestore.client()
        firebase_initialized = True
        
        # Ensure default settings document exists
        settings_ref = db.collection('settings').document('general')
        if not settings_ref.get().exists:
            settings_ref.set({
                'allow_registration': True,
                'admin_username': 'priyomanta',
                'admin_password': 'BDO@8389',
                'admin_email': 'prempriyomanta@gmail.com'
            })
            
        print("Google Firebase Firestore initialized successfully!")
        return True
    except Exception as e:
        print(f"Error initializing Firebase Firestore: {e}")
        return False

def is_connected():
    return firebase_initialized and db is not None

# Settings & Admin Auth
def get_settings():
    if not is_connected():
        return {'allow_registration': True, 'admin_username': 'priyomanta', 'admin_password': 'BDO@8389', 'admin_email': 'prempriyomanta@gmail.com'}
    doc = db.collection('settings').document('general').get()
    if doc.exists:
        data = doc.to_dict()
        return {
            'allow_registration': bool(data.get('allow_registration', True)),
            'admin_username': data.get('admin_username', 'priyomanta'),
            'admin_password': data.get('admin_password', 'BDO@8389'),
            'admin_email': data.get('admin_email', 'prempriyomanta@gmail.com')
        }
    return {'allow_registration': True, 'admin_username': 'priyomanta', 'admin_password': 'BDO@8389', 'admin_email': 'prempriyomanta@gmail.com'}

def get_allow_registration():
    return get_settings()['allow_registration']

def set_allow_registration(allow: bool):
    if not is_connected():
        return
    db.collection('settings').document('general').set({'allow_registration': allow}, merge=True)

def update_admin_password(new_password: str):
    if not is_connected():
        return
    db.collection('settings').document('general').set({'admin_password': new_password}, merge=True)

# Users
def get_total_users_count():
    if not is_connected():
        return 0
    return len(list(db.collection('users').stream()))

def get_user_by_6digit_id(user_id: str):
    if not is_connected():
        return None
    docs = list(db.collection('users').where('user_id', '==', str(user_id)).where('status', '==', 'approved').limit(1).stream())
    if docs:
        d = docs[0].to_dict()
        d['id'] = docs[0].id
        return d
    return None

def create_user_request(data: dict):
    if not is_connected():
        return None
    doc_ref = db.collection('users').document()
    payload = {
        'name': data.get('name', ''),
        'email': data.get('email', ''),
        'whatsapp': data.get('whatsapp', ''),
        'dob': data.get('dob', ''),
        'profile_image': data.get('profile_image', ''),
        'role': 'employee',
        'status': 'pending',
        'user_id': None,
        'created_at': datetime.datetime.now().isoformat()
    }
    doc_ref.set(payload)
    payload['id'] = doc_ref.id
    return payload

def create_initial_owner(data: dict, new_id: str):
    if not is_connected():
        return None
    doc_ref = db.collection('users').document()
    payload = {
        'name': data.get('name', ''),
        'email': data.get('email', ''),
        'whatsapp': data.get('whatsapp', ''),
        'dob': data.get('dob', ''),
        'profile_image': data.get('profile_image', ''),
        'role': 'owner',
        'status': 'approved',
        'user_id': str(new_id),
        'created_at': datetime.datetime.now().isoformat()
    }
    doc_ref.set(payload)
    payload['id'] = doc_ref.id
    return payload

def is_user_id_taken(new_id: str):
    if not is_connected():
        return False
    docs = list(db.collection('users').where('user_id', '==', str(new_id)).limit(1).stream())
    return len(docs) > 0

def generate_unique_user_id():
    while True:
        candidate = str(random.randint(100000, 999999))
        if not is_user_id_taken(candidate):
            return candidate

def approve_user_request(doc_id: str):
    if not is_connected():
        return None
    new_id = generate_unique_user_id()
    doc_ref = db.collection('users').document(str(doc_id))
    doc_ref.update({
        'status': 'approved',
        'user_id': new_id
    })
    return new_id

def delete_user(doc_id: str):
    if not is_connected():
        return
    db.collection('users').document(str(doc_id)).delete()

def set_user_role(doc_id: str, role: str):
    if not is_connected():
        return
    db.collection('users').document(str(doc_id)).update({'role': role})

def get_approved_users():
    if not is_connected():
        return []
    docs = db.collection('users').where('status', '==', 'approved').stream()
    result = []
    for d in docs:
        item = d.to_dict()
        item['id'] = d.id
        result.append(item)
    return result

def get_pending_requests():
    if not is_connected():
        return []
    docs = db.collection('users').where('status', '==', 'pending').stream()
    result = []
    for d in docs:
        item = d.to_dict()
        item['id'] = d.id
        result.append(item)
    return result

def get_stats():
    if not is_connected():
        return {'total_employees': 0, 'pending_requests': 0}
    approved = len(list(db.collection('users').where('status', '==', 'approved').stream()))
    pending = len(list(db.collection('users').where('status', '==', 'pending').stream()))
    return {'total_employees': approved, 'pending_requests': pending}

# Attendance
def get_user_status_today(user_id: str, date_today: str):
    if not is_connected():
        return {'status': 'none', 'login_time': None, 'logout_time': None, 'work_hours': None}
    docs = list(db.collection('attendance')
                .where('user_id', '==', str(user_id))
                .where('date', '==', str(date_today))
                .stream())
    if docs:
        items = [d.to_dict() for d in docs]
        items.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        latest = items[0]
        return {
            'status': latest.get('status', 'none'),
            'login_time': latest.get('login_time'),
            'logout_time': latest.get('logout_time'),
            'work_hours': latest.get('work_hours')
        }
    return {'status': 'none', 'login_time': None, 'logout_time': None, 'work_hours': None}

def record_login(user_id: str, name: str, lat, lng, date_today: str, time_now: str):
    if not is_connected():
        return None
    docs = list(db.collection('attendance')
                .where('user_id', '==', str(user_id))
                .where('date', '==', str(date_today))
                .where('status', '==', 'green')
                .limit(1)
                .stream())
    if docs:
        return docs[0].id
        
    doc_ref = db.collection('attendance').document()
    doc_ref.set({
        'user_id': str(user_id),
        'name': name,
        'date': date_today,
        'login_time': time_now,
        'logout_time': None,
        'work_hours': None,
        'login_lat': lat,
        'login_lng': lng,
        'logout_lat': None,
        'logout_lng': None,
        'status': 'green',
        'timestamp': datetime.datetime.now().timestamp()
    })
    return doc_ref.id

def record_logout(user_id: str, lat, lng, date_today: str, time_now: str, work_hours: str):
    if not is_connected():
        return False
    docs = list(db.collection('attendance')
                .where('user_id', '==', str(user_id))
                .where('date', '==', str(date_today))
                .where('status', '==', 'green')
                .limit(1)
                .stream())
    if docs:
        doc_id = docs[0].id
        db.collection('attendance').document(doc_id).update({
            'logout_time': time_now,
            'logout_lat': lat,
            'logout_lng': lng,
            'work_hours': work_hours,
            'status': 'red'
        })
        return True
    return False

def get_employee_attendance_records(user_id: str):
    if not is_connected():
        return []
    docs = list(db.collection('attendance').where('user_id', '==', str(user_id)).stream())
    records = []
    for d in docs:
        item = d.to_dict()
        item['id'] = d.id
        records.append(item)
    records.sort(key=lambda x: (x.get('date', ''), x.get('login_time', '') or ''), reverse=True)
    return records

def get_grouped_attendance(date_filter=None):
    if not is_connected():
        return {}
    query = db.collection('attendance')
    if date_filter:
        query = query.where('date', '==', str(date_filter))
    
    docs = query.stream()
    records = []
    for d in docs:
        item = d.to_dict()
        item['id'] = d.id
        records.append(item)
    
    records.sort(key=lambda x: (x.get('date', ''), x.get('login_time', '') or ''), reverse=True)
    
    grouped = {}
    for r in records:
        d = r.get('date', '')
        if d not in grouped:
            grouped[d] = []
        grouped[d].append(r)
    return grouped

def get_attendance_export_data(start_date=None, end_date=None):
    if not is_connected():
        return []
    docs = db.collection('attendance').stream()
    rows = []
    for d in docs:
        r = d.to_dict()
        date_val = r.get('date', '')
        if start_date and date_val < start_date:
            continue
        if end_date and date_val > end_date:
            continue
        
        login_lat = r.get('login_lat')
        login_lng = r.get('login_lng')
        logout_lat = r.get('logout_lat')
        logout_lng = r.get('logout_lng')
        
        login_map = f"https://maps.google.com/?q={login_lat},{login_lng}" if login_lat and login_lng else ""
        logout_map = f"https://maps.google.com/?q={logout_lat},{logout_lng}" if logout_lat and logout_lng else ""
        
        rows.append({
            'Date': date_val,
            'User ID': r.get('user_id', ''),
            'Name': r.get('name', ''),
            'Login Time': r.get('login_time', '') or '-',
            'Logout Time': r.get('logout_time', '') or '-',
            'Work Duration': r.get('work_hours', '') or '-',
            'Login Latitude': login_lat,
            'Login Longitude': login_lng,
            'Logout Latitude': logout_lat,
            'Logout Longitude': logout_lng,
            'Login Map': login_map,
            'Logout Map': logout_map
        })
    rows.sort(key=lambda x: (x['Date'], x['Login Time']), reverse=True)
    return rows

# Leaves Management
def create_leave_request(user_id: str, name: str, leave_type: str, date_str: str, message: str):
    if not is_connected():
        return None
    doc_ref = db.collection('leaves').document()
    payload = {
        'user_id': str(user_id),
        'name': name,
        'leave_type': leave_type,
        'date': date_str,
        'message': message,
        'status': 'Pending',
        'created_at': datetime.datetime.now().isoformat()
    }
    doc_ref.set(payload)
    payload['id'] = doc_ref.id
    return payload

def get_all_leaves():
    if not is_connected():
        return []
    docs = db.collection('leaves').stream()
    result = []
    for d in docs:
        item = d.to_dict()
        item['id'] = d.id
        result.append(item)
    result.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return result

def get_user_leaves(user_id: str):
    if not is_connected():
        return []
    docs = db.collection('leaves').where('user_id', '==', str(user_id)).stream()
    result = []
    for d in docs:
        item = d.to_dict()
        item['id'] = d.id
        result.append(item)
    result.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return result

def update_leave_status(leave_id: str, status: str):
    if not is_connected():
        return False
    db.collection('leaves').document(str(leave_id)).update({'status': status})
    return True

# Office Messages (Admin -> Employee)
def send_office_message(from_name: str, to_user_id: str, title: str, message: str, date_str: str):
    if not is_connected():
        return None
    doc_ref = db.collection('messages').document()
    payload = {
        'from_name': from_name or 'Admin',
        'to_user_id': str(to_user_id),
        'title': title or 'Office Notice',
        'message': message,
        'date': date_str,
        'created_at': datetime.datetime.now().isoformat(),
        'read_status': False
    }
    doc_ref.set(payload)
    payload['id'] = doc_ref.id
    return payload

def get_user_messages(user_id: str):
    if not is_connected():
        return []
    docs = db.collection('messages').stream()
    result = []
    for d in docs:
        item = d.to_dict()
        item['id'] = d.id
        # Include messages for specific user or broadcast 'ALL'
        if item.get('to_user_id') in [str(user_id), 'ALL']:
            result.append(item)
    result.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return result

def get_all_messages():
    if not is_connected():
        return []
    docs = db.collection('messages').stream()
    result = []
    for d in docs:
        item = d.to_dict()
        item['id'] = d.id
        result.append(item)
    result.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return result
