import os
import random
import datetime
import json
import base64

def get_key_path():
    base = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base, 'firebase-key.json'),
        os.path.join(base, 'firebase-key.json.json'),
        '/etc/secrets/firebase-key.json',
        '/etc/secrets/firebase-key.json.json'
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None

db = None
firebase_initialized = False

def init_firebase():
    global db, firebase_initialized
    cred = None

    # 1. Try file paths (local or Render Secret Files at /etc/secrets/firebase-key.json)
    key_path = get_key_path()
    if key_path:
        try:
            import firebase_admin
            from firebase_admin import credentials
            cred = credentials.Certificate(key_path)
            print(f">>> Found Firebase key file at: {key_path} <<<")
        except Exception as e:
            print(f"Error loading Firebase key file: {e}")

    # 2. Try FIREBASE_KEY_JSON environment variable (useful on Render/Cloud)
    if not cred and os.environ.get('FIREBASE_KEY_JSON'):
        try:
            import firebase_admin
            from firebase_admin import credentials
            raw_key = os.environ.get('FIREBASE_KEY_JSON').strip()
            if not raw_key.startswith('{'):
                raw_key = base64.b64decode(raw_key).decode('utf-8')
            key_dict = json.loads(raw_key)
            cred = credentials.Certificate(key_dict)
            print(">>> Loaded Firebase credentials from FIREBASE_KEY_JSON environment variable! <<<")
        except Exception as e:
            print(f"Error loading FIREBASE_KEY_JSON env var: {e}")

    if not cred:
        print("Warning: Firebase service account key not found (checked file paths and FIREBASE_KEY_JSON env var)")
        return False
    
    try:
        import firebase_admin
        from firebase_admin import firestore
        
        if not firebase_admin._apps:
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
    default_cfg = {
        'allow_registration': True,
        'allow_id_cards': True,
        'admin_username': 'priyomanta',
        'admin_password': 'BDO@8389',
        'admin_email': 'prempriyomanta@gmail.com',
        'geofence_enabled_all': False,
        'office_lat': '',
        'office_lng': '',
        'geofence_radius_meters': 200,
        'late_tracking_all': False,
        'office_start_time': '10:00 AM',
        'grace_period_mins': 0,
        'standard_work_hours': 8.0
    }
    if not is_connected():
        return default_cfg
    doc = db.collection('settings').document('general').get()
    if doc.exists:
        data = doc.to_dict()
        return {
            'allow_registration': bool(data.get('allow_registration', True)),
            'allow_id_cards': bool(data.get('allow_id_cards', True)),
            'admin_username': data.get('admin_username', 'priyomanta'),
            'admin_password': data.get('admin_password', 'BDO@8389'),
            'admin_email': data.get('admin_email', 'prempriyomanta@gmail.com'),
            'geofence_enabled_all': bool(data.get('geofence_enabled_all', False)),
            'office_lat': str(data.get('office_lat', '')),
            'office_lng': str(data.get('office_lng', '')),
            'geofence_radius_meters': int(data.get('geofence_radius_meters', 200)),
            'late_tracking_all': bool(data.get('late_tracking_all', False)),
            'office_start_time': str(data.get('office_start_time', '10:00 AM')),
            'grace_period_mins': int(data.get('grace_period_mins', 0)),
            'standard_work_hours': float(data.get('standard_work_hours', 8.0))
        }
    return default_cfg

def set_office_policy(policy_data: dict):
    if not is_connected():
        return None
    clean = {}
    if 'office_lat' in policy_data: clean['office_lat'] = str(policy_data['office_lat'])
    if 'office_lng' in policy_data: clean['office_lng'] = str(policy_data['office_lng'])
    if 'geofence_radius_meters' in policy_data: clean['geofence_radius_meters'] = int(policy_data['geofence_radius_meters'])
    if 'geofence_enabled_all' in policy_data: clean['geofence_enabled_all'] = bool(policy_data['geofence_enabled_all'])
    if 'office_start_time' in policy_data: clean['office_start_time'] = str(policy_data['office_start_time'])
    if 'grace_period_mins' in policy_data: clean['grace_period_mins'] = int(policy_data['grace_period_mins'])
    if 'standard_work_hours' in policy_data: clean['standard_work_hours'] = float(policy_data['standard_work_hours'])
    if 'late_tracking_all' in policy_data: clean['late_tracking_all'] = bool(policy_data['late_tracking_all'])
    db.collection('settings').document('general').set(clean, merge=True)
    return get_settings()

def get_allow_registration():
    return get_settings()['allow_registration']

def set_allow_registration(allow: bool):
    if not is_connected():
        return
    db.collection('settings').document('general').set({'allow_registration': allow}, merge=True)

def get_allow_id_cards():
    return get_settings().get('allow_id_cards', True)

def set_allow_id_cards(allow: bool):
    if not is_connected():
        return
    db.collection('settings').document('general').set({'allow_id_cards': allow}, merge=True)

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

def update_user_id_card(doc_id: str, card_data: dict):
    if not is_connected():
        return False
    db.collection('users').document(str(doc_id)).set({'id_card_data': card_data}, merge=True)
    return True

def toggle_user_id_card(doc_id: str, enabled: bool):
    if not is_connected():
        return False
    db.collection('users').document(str(doc_id)).set({'id_card_enabled': enabled}, merge=True)
    return True

def set_user_paid_status(user_id_or_doc_id: str, is_paid: bool):
    if not is_connected():
        return None
    # Check if doc exists by ID directly
    try:
        doc_ref = db.collection('users').document(str(user_id_or_doc_id))
        doc = doc_ref.get()
        if doc.exists:
            doc_ref.set({'is_paid': bool(is_paid)}, merge=True)
            u = doc.to_dict()
            u['id'] = doc.id
            u['is_paid'] = bool(is_paid)
            return u
    except Exception:
        pass
    # Otherwise find by 6-digit user_id
    docs = list(db.collection('users').where('user_id', '==', str(user_id_or_doc_id)).limit(1).stream())
    if docs:
        db.collection('users').document(docs[0].id).set({'is_paid': bool(is_paid)}, merge=True)
        u = docs[0].to_dict()
        u['id'] = docs[0].id
        u['is_paid'] = bool(is_paid)
        return u
    return None

def get_paid_users():
    if not is_connected():
        return []
    docs = db.collection('users').where('status', '==', 'approved').where('is_paid', '==', True).stream()
    result = []
    for d in docs:
        item = d.to_dict()
        item['id'] = d.id
        result.append(item)
    return result

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
            'work_hours': latest.get('work_hours'),
            'is_late': latest.get('is_late', False),
            'late_minutes': latest.get('late_minutes', 0),
            'late_text': latest.get('late_text', ''),
            'overtime_hours': latest.get('overtime_hours', ''),
            'is_overtime': latest.get('is_overtime', False)
        }
    return {'status': 'none', 'login_time': None, 'logout_time': None, 'work_hours': None, 'is_late': False, 'late_minutes': 0, 'late_text': '', 'overtime_hours': '', 'is_overtime': False}

def record_login(user_id: str, name: str, lat, lng, date_today: str, time_now: str, is_late=False, late_minutes=0, late_text=''):
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
        'is_late': bool(is_late),
        'late_minutes': int(late_minutes or 0),
        'late_text': str(late_text or ''),
        'overtime_hours': None,
        'is_overtime': False,
        'timestamp': datetime.datetime.now().timestamp()
    })
    return doc_ref.id

def record_logout(user_id: str, lat, lng, date_today: str, time_now: str, work_hours: str, overtime_hours='', is_overtime=False):
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
            'overtime_hours': overtime_hours or None,
            'is_overtime': bool(is_overtime),
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

def delete_attendance_record(record_id: str):
    if not is_connected():
        return False
    db.collection('attendance').document(str(record_id)).delete()
    return True

def delete_attendance_by_date(date_str: str):
    if not is_connected():
        return False
    docs = list(db.collection('attendance').where('date', '==', str(date_str)).stream())
    batch = db.batch()
    count = 0
    for d in docs:
        batch.delete(d.reference)
        count += 1
        if count % 400 == 0:
            batch.commit()
            batch = db.batch()
    if count % 400 != 0:
        batch.commit()
    return True

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
            'Late Status': r.get('late_text', '') or ('Late' if r.get('is_late') else 'On Time'),
            'Overtime': r.get('overtime_hours', '') or '-',
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

def delete_leave_request(leave_id: str):
    if not is_connected():
        return False
    db.collection('leaves').document(str(leave_id)).delete()
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
    now = datetime.datetime.now()
    for d in docs:
        item = d.to_dict()
        item['id'] = d.id
        # 12-Hour Auto Delete
        c_at = item.get('created_at')
        if c_at:
            try:
                msg_time = datetime.datetime.fromisoformat(c_at)
                if (now - msg_time).total_seconds() > 12 * 3600:
                    try:
                        db.collection('messages').document(d.id).delete()
                    except Exception:
                        pass
                    continue
            except Exception:
                pass
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
    now = datetime.datetime.now()
    for d in docs:
        item = d.to_dict()
        item['id'] = d.id
        # 12-Hour Auto Delete
        c_at = item.get('created_at')
        if c_at:
            try:
                msg_time = datetime.datetime.fromisoformat(c_at)
                if (now - msg_time).total_seconds() > 12 * 3600:
                    try:
                        db.collection('messages').document(d.id).delete()
                    except Exception:
                        pass
                    continue
            except Exception:
                pass
        result.append(item)
    result.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return result

# Master Control (Sub-Admin / Manager Accounts)
def get_subadmins():
    if not is_connected():
        return []
    docs = db.collection('subadmins').stream()
    result = []
    for d in docs:
        item = d.to_dict()
        item['id'] = d.id
        result.append(item)
    result.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return result

def create_subadmin(username: str, password: str, name: str):
    if not is_connected():
        return None
    # Check if username already exists
    existing = list(db.collection('subadmins').where('username', '==', str(username).strip()).limit(1).stream())
    if existing:
        return None
    doc_ref = db.collection('subadmins').document()
    payload = {
        'username': str(username).strip(),
        'password': str(password).strip(),
        'name': str(name).strip() or str(username).strip(),
        'created_at': datetime.datetime.now().isoformat()
    }
    doc_ref.set(payload)
    payload['id'] = doc_ref.id
    return payload

def delete_subadmin(doc_id: str):
    if not is_connected():
        return False
    db.collection('subadmins').document(str(doc_id)).delete()
    return True

def verify_subadmin_login(username: str, password: str):
    if not is_connected():
        return None
    docs = list(db.collection('subadmins').where('username', '==', str(username).strip()).where('password', '==', str(password).strip()).limit(1).stream())
    if docs:
        d = docs[0].to_dict()
        d['id'] = docs[0].id
        return d
    return None
