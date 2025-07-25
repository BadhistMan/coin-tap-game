from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import hmac
import hashlib
import time
import os
from urllib.parse import unquote
from datetime import datetime, timedelta
from database import get_db_connection, create_tables

# --- CONFIGURATION ---
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8246236846:AAHW_hPy5wALCrnjip1iX_Gr-MnBYZneTko') # From @BotFather
DAILY_REWARD_AMOUNT = 500
MIN_WITHDRAWAL_BALANCE = 50000
REFERRAL_BONUS = 1000
UPGRADE_COST_BASE = 50
TAP_RATE_LIMIT = 10  # Taps per second

# --- FLASK APP INITIALIZATION ---
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}}) # Allow CORS for Telegram Web App

# --- HELPER FUNCTIONS ---
def validate_telegram_data(init_data):
    """Validates the data received from the Telegram Web App."""
    try:
        encoded_data = unquote(init_data)
        data_check_string = '\n'.join(sorted([
            f"{k}={v}" for k, v in [part.split('=', 1) for part in encoded_data.split('&') if k != 'hash']
        ]))
        secret_key = hmac.new("WebAppData".encode(), BOT_TOKEN.encode(), hashlib.sha256).digest()
        h = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256)
        received_hash = next((v for k, v in (part.split('=', 1) for part in encoded_data.split('&')) if k == 'hash'), None)
        
        return h.hexdigest() == received_hash
    except Exception:
        return False

# --- API ROUTES ---
@app.route('/api/user/<int:telegram_id>', methods=['GET'])
def get_user(telegram_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM Users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    
    if not user:
        # Create a new user if not found
        username = request.args.get('username', f'user_{telegram_id}')
        referral_code = f"ref_{telegram_id}"
        referrer_id = request.args.get('referrer_id')
        
        conn.execute('INSERT INTO Users (telegram_id, username, referral_code, referrer_id) VALUES (?, ?, ?, ?)',
                     (telegram_id, username, referral_code, referrer_id))
        conn.commit()
        
        if referrer_id:
            # Reward the referrer
            conn.execute('UPDATE Users SET coins = coins + ? WHERE telegram_id = ?', (REFERRAL_BONUS, referrer_id))
            conn.execute('INSERT INTO Referrals (referrer_id, referred_id, reward_status) VALUES (?, ?, ?)', (referrer_id, telegram_id, 'claimed'))
            conn.commit()

        user = conn.execute('SELECT * FROM Users WHERE telegram_id = ?', (telegram_id,)).fetchone()

    conn.close()
    return jsonify(dict(user)) if user else ({}, 404)

@app.route('/api/tap', methods=['POST'])
def tap():
    data = request.json
    telegram_id = data.get('telegram_id')
    
    # Basic anti-cheat: Rate limit taps
    conn = get_db_connection()
    last_tap = conn.execute('SELECT timestamp FROM Taps WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1', (telegram_id,)).fetchone()
    if last_tap and (datetime.now() - datetime.fromisoformat(last_tap['timestamp'])).total_seconds() < 1.0 / TAP_RATE_LIMIT:
        return jsonify({'message': 'Tapping too fast!'}), 429
    
    user = conn.execute('SELECT tap_power FROM Users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    if not user:
        return jsonify({'message': 'User not found'}), 404

    tap_power = user['tap_power']
    conn.execute('UPDATE Users SET coins = coins + ? WHERE telegram_id = ?', (tap_power, telegram_id))
    conn.execute('INSERT INTO Taps (user_id) VALUES (?)', (telegram_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'message': f'Added {tap_power} coins!'})

@app.route('/api/upgrade', methods=['POST'])
def upgrade():
    telegram_id = request.json.get('telegram_id')
    conn = get_db_connection()
    user = conn.execute('SELECT coins, tap_power FROM Users WHERE telegram_id = ?', (telegram_id,)).fetchone()

    if not user:
        conn.close()
        return jsonify({'message': 'User not found'}), 404

    cost = UPGRADE_COST_BASE * user['tap_power']
    if user['coins'] < cost:
        conn.close()
        return jsonify({'message': 'Not enough coins'}), 400
    
    new_power = user['tap_power'] + 1
    conn.execute('UPDATE Users SET coins = coins - ?, tap_power = ? WHERE telegram_id = ?', (cost, new_power, telegram_id))
    conn.execute('INSERT INTO Upgrades (user_id, power_level, coins_spent) VALUES (?, ?, ?)', (telegram_id, new_power, cost))
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Upgrade successful!', 'new_power': new_power, 'new_cost': UPGRADE_COST_BASE * new_power})

@app.route('/api/daily-reward', methods=['POST'])
def daily_reward():
    telegram_id = request.json.get('telegram_id')
    conn = get_db_connection()
    user = conn.execute('SELECT last_daily_claim FROM Users WHERE telegram_id = ?', (telegram_id,)).fetchone()

    if not user:
        conn.close()
        return jsonify({'message': 'User not found'}), 404

    if user['last_daily_claim']:
        last_claim_time = datetime.fromisoformat(user['last_daily_claim'])
        if datetime.now() < last_claim_time + timedelta(hours=24):
            conn.close()
            return jsonify({'message': 'Daily reward already claimed'}), 400
    
    now_iso = datetime.now().isoformat()
    conn.execute('UPDATE Users SET coins = coins + ?, last_daily_claim = ? WHERE telegram_id = ?', (DAILY_REWARD_AMOUNT, now_iso, telegram_id))
    conn.commit()
    conn.close()
    
    return jsonify({'message': f'Claimed {DAILY_REWARD_AMOUNT} coins!'})

@app.route('/api/leaderboard', methods=['GET'])
def leaderboard():
    conn = get_db_connection()
    users = conn.execute('SELECT username, coins FROM Users ORDER BY coins DESC LIMIT 10').fetchall()
    conn.close()
    return jsonify([dict(user) for user in users])

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    telegram_id = data.get('telegram_id')
    method = data.get('method')
    address = data.get('address')
    amount = data.get('amount')
    
    conn = get_db_connection()
    user = conn.execute('SELECT coins FROM Users WHERE telegram_id = ?', (telegram_id,)).fetchone()

    if not user or user['coins'] < MIN_WITHDRAWAL_BALANCE or user['coins'] < amount:
        conn.close()
        return jsonify({'message': 'Insufficient balance'}), 400
    
    conn.execute('UPDATE Users SET coins = coins - ? WHERE telegram_id = ?', (amount, telegram_id))
    conn.execute('INSERT INTO Withdrawals (user_id, method, address, amount) VALUES (?, ?, ?, ?)',
                 (telegram_id, method, address, amount))
    conn.commit()
    conn.close()
    
    # Log withdrawal request for admin review
    with open("withdrawal_log.txt", "a") as log_file:
        log_file.write(f"[{datetime.now()}] User {telegram_id} requested to withdraw {amount} via {method} to {address}\n")

    return jsonify({'message': 'Withdrawal request submitted!'})
    
@app.route('/api/referral', methods=['POST'])
def referral():
    # This endpoint is simplified as the referral logic is handled in user creation
    return jsonify({'message': 'Referral tracked.'})

if __name__ == '__main__':
    create_tables()
    # For local development, not used by Render
    app.run(port=5000, debug=True)
