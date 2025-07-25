import sqlite3
import os

DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'database.db')

def get_db_connection():
    """Establishes a connection to the database."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def create_tables():
    """Creates the necessary database tables if they don't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            coins INTEGER DEFAULT 0,
            tap_power INTEGER DEFAULT 1,
            referral_code TEXT UNIQUE,
            referrer_id INTEGER,
            last_daily_claim TIMESTAMP
        );
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Taps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES Users(telegram_id)
        );
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER,
            reward_status TEXT DEFAULT 'pending',
            FOREIGN KEY(referrer_id) REFERENCES Users(telegram_id),
            FOREIGN KEY(referred_id) REFERENCES Users(telegram_id)
        );
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            method TEXT,
            address TEXT,
            amount REAL,
            status TEXT DEFAULT 'pending',
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES Users(telegram_id)
        );
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Upgrades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            power_level INTEGER,
            coins_spent INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES Users(telegram_id)
        );
    ''')

    conn.commit()
    conn.close()

if __name__ == '__main__':
    create_tables()
    print("Database tables created successfully.")
