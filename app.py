# app.py - Fixed Backend
import os
import logging
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
import sqlite3
import hashlib
import time

app = Flask(__name__)
CORS(app)  # Enable CORS

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Check for BOT_TOKEN (required for Telegram integration)
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    logging.warning("BOT_TOKEN is missing. Telegram features will be disabled.")

# Database setup
def init_db():
    conn = sqlite3.connect('tapswap.db')
    c = conn.cursor()
    
    # Create tables
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 user_id TEXT PRIMARY KEY,
                 taps INTEGER DEFAULT 0,
                 referrals INTEGER DEFAULT 0,
                 last_tap TIMESTAMP DEFAULT 0,
                 energy INTEGER DEFAULT 100,
                 upgrades TEXT DEFAULT '{}'
                 )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id TEXT,
                 amount REAL,
                 status TEXT,
                 timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                 )''')
    
    conn.commit()
    conn.close()

init_db()

# Helper functions
def get_user(user_id):
    conn = sqlite3.connect('tapswap.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    
    if user:
        return {
            'user_id': user[0],
            'taps': user[1],
            'referrals': user[2],
            'last_tap': user[3],
            'energy': user[4],
            'upgrades': eval(user[5])
        }
    return None

def create_user(user_id):
    conn = sqlite3.connect('tapswap.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # User already exists
    finally:
        conn.close()

def update_tap(user_id, tap_count=1):
    conn = sqlite3.connect('tapswap.db')
    c = conn.cursor()
    
    # Energy regeneration logic
    current_time = time.time()
    user = get_user(user_id)
    
    if not user:
        create_user(user_id)
        user = get_user(user_id)
    
    # Energy regeneration (1% per minute)
    time_diff = (current_time - user['last_tap']) / 60
    new_energy = min(100, user['energy'] + time_diff)
    
    # Apply taps if energy available
    if new_energy >= tap_count:
        new_energy -= tap_count
        c.execute("UPDATE users SET taps = taps + ?, last_tap = ?, energy = ? WHERE user_id = ?",
                  (tap_count, current_time, new_energy, user_id))
        conn.commit()
        success = True
    else:
        success = False
    
    conn.close()
    return success, new_energy

def add_referral(user_id, referrer_id):
    conn = sqlite3.connect('tapswap.db')
    c = conn.cursor()
    
    # Update referrer's count
    c.execute("UPDATE users SET referrals = referrals + 1 WHERE user_id = ?", (referrer_id,))
    
    # Bonus for referred user
    c.execute("UPDATE users SET taps = taps + 50 WHERE user_id = ?", (user_id,))
    
    conn.commit()
    conn.close()

# API Endpoints
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/user/<user_id>', methods=['GET', 'POST'])
def user_endpoint(user_id):
    if request.method == 'GET':
        user = get_user(user_id)
        if user:
            return jsonify({
                'status': 'success',
                'user': {
                    'taps': user['taps'],
                    'referrals': user['referrals'],
                    'energy': user['energy'],
                    'upgrades': user['upgrades']
                }
            })
        else:
            return jsonify({'status': 'user_not_found'}), 404

    elif request.method == 'POST':
        # Handle tap action
        success, new_energy = update_tap(user_id)
        if success:
            return jsonify({
                'status': 'success',
                'new_energy': new_energy,
                'taps': get_user(user_id)['taps']
            })
        else:
            return jsonify({
                'status': 'energy_low',
                'energy': new_energy
            }), 400

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    user_id = data.get('user_id')
    amount = data.get('amount')
    
    if not user_id or not amount:
        return jsonify({'status': 'missing_data'}), 400
    
    user = get_user(user_id)
    if not user:
        return jsonify({'status': 'user_not_found'}), 404
    
    if user['taps'] < amount:
        return jsonify({'status': 'insufficient_taps'}), 400
    
    # Process withdrawal (in a real app, integrate with payment gateway)
    conn = sqlite3.connect('tapswap.db')
    c = conn.cursor()
    
    # Deduct taps
    c.execute("UPDATE users SET taps = taps - ? WHERE user_id = ?", (amount, user_id))
    
    # Record transaction
    c.execute("INSERT INTO transactions (user_id, amount, status) VALUES (?, ?, 'pending')",
              (user_id, amount))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'status': 'success',
        'message': f'Withdrawal request for {amount} taps submitted'
    })

@app.route('/api/referral', methods=['POST'])
def referral():
    data = request.json
    user_id = data.get('user_id')
    referrer_id = data.get('referrer_id')
    
    if not user_id or not referrer_id:
        return jsonify({'status': 'missing_data'}), 400
    
    if user_id == referrer_id:
        return jsonify({'status': 'self_referral'}), 400
    
    add_referral(user_id, referrer_id)
    return jsonify({
        'status': 'success',
        'message': 'Referral added successfully'
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
