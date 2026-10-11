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
            settings_ref.set({'allow_registration': True})
            
        print("Google Firebase Firestore initialized successfully!")
        return True
    except Exception as e:
        print(f"Error initializing Firebase Firestore: {e}")
        return False

def is_connected():
    return firebase_initialized and db is not None

# Settings
def get_allow_registration():
    if not is_connected():
        return True
    doc = db.collection('settings').document('general').get()
    if doc.exists:
        return bool(doc.to_dict().get('allow_registration', True))
    return True

def set_allow_registration(allow: bool):
    if not is_connected():
        return
    db.collection('settings').document('general').set({'allow_registration': allow}, merge=True)

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

def create_user_request(name: str):
    if not is_connected():
        return None
    doc_ref = db.collection('users').document()
    data = {
        'name': name,
        'role': 'employee',
        'status': 'pending',
        'user_id': None,
        'created_at': datetime.datetime.now().isoformat()
    }
    doc_ref.set(data)
    data['id'] = doc_ref.id
    return data

def create_initial_owner(name: str, new_id: str):
    if not is_connected():
        return None
    doc_ref = db.collection('users').document()
    data = {
        'name': name,
        'role': 'owner',
        'status': 'approved',
        'user_id': str(new_id),
        'created_at': datetime.datetime.now().isoformat()
    }
    doc_ref.set(data)
    data['id'] = doc_ref.id
    return data

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
        return 'none'
    docs = list(db.collection('attendance')
                .where('user_id', '==', str(user_id))
                .where('date', '==', str(date_today))
                .stream())
    if docs:
        # Sort by timestamp in python to avoid index requirement
        items = [d.to_dict() for d in docs]
        items.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        return items[0].get('status', 'none')
    return 'none'

def record_login(user_id: str, name: str, lat, lng, date_today: str, time_now: str):
    if not is_connected():
        return None
    # Check if user already has an active session today
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
        'login_lat': lat,
        'login_lng': lng,
        'logout_lat': None,
        'logout_lng': None,
        'status': 'green',
        'timestamp': datetime.datetime.now().timestamp()
    })
    return doc_ref.id

def record_logout(user_id: str, lat, lng, date_today: str, time_now: str):
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
            'status': 'red'
        })
        return True
    return False

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
    
    # Sort in memory by date desc and login_time desc
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
            'Login Latitude': login_lat,
            'Login Longitude': login_lng,
            'Logout Latitude': logout_lat,
            'Logout Longitude': logout_lng,
            'Login Map': login_map,
            'Logout Map': logout_map
        })
    rows.sort(key=lambda x: (x['Date'], x['Login Time']), reverse=True)
    return rows
