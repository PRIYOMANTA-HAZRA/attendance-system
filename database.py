import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'attendance.db') if '__file__' in globals() else 'attendance.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT UNIQUE,
            name TEXT NOT NULL,
            email TEXT,
            whatsapp TEXT,
            dob TEXT,
            profile_image TEXT,
            role TEXT DEFAULT 'employee',
            status TEXT DEFAULT 'pending'
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            date TEXT NOT NULL,
            login_time TEXT,
            logout_time TEXT,
            work_hours TEXT,
            login_lat REAL,
            login_lng REAL,
            logout_lat REAL,
            logout_lng REAL,
            status TEXT DEFAULT 'green',
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leaves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            leave_type TEXT NOT NULL,
            date TEXT NOT NULL,
            message TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_name TEXT DEFAULT 'Admin',
            to_user_id TEXT NOT NULL,
            title TEXT,
            message TEXT NOT NULL,
            date TEXT,
            created_at TEXT,
            read_status INTEGER DEFAULT 0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')

    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('allow_registration', 'true')")
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('admin_username', 'priyomanta')")
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('admin_password', 'BDO@8389')")
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('admin_email', 'prempriyomanta@gmail.com')")
    
    # Run safe column migrations in case columns do not exist
    for col, definition in [
        ('email', 'TEXT'),
        ('whatsapp', 'TEXT'),
        ('dob', 'TEXT'),
        ('profile_image', 'TEXT'),
        ('id_card_data', 'TEXT')
    ]:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
        except sqlite3.OperationalError:
            pass

    try:
        cursor.execute("ALTER TABLE attendance ADD COLUMN work_hours TEXT")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()
    print("Database initialized successfully with updated tables.")

if __name__ == '__main__':
    init_db()
