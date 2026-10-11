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
            login_lat REAL,
            login_lng REAL,
            logout_lat REAL,
            logout_lng REAL,
            status TEXT DEFAULT 'green',
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')

    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('allow_registration', 'true')")
    
    conn.commit()
    conn.close()
    print("Database initialized successfully.")

if __name__ == '__main__':
    init_db()
