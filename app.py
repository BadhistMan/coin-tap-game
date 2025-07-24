import os
import sqlite3
import time
import json
import hashlib
import hmac
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, g, make_response

app = Flask(__name__)
app.config.from_pyfile('config.py')

DATABASE = os.path.join(app.instance_path, 'game.db')
SECRET_KEY = os.environ.get('SECRET_KEY')
BOT_TOKEN = os.environ.get('BOT_TOKEN')
MIN_WITHDRAW = 50000
DAILY_REWARD = 1000
BASE_UPGRADE_COST = 50
REFERRAL_BONUS = 500

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        # Create tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                coins INTEGER DEFAULT 0,
                tap_power INTEGER DEFAULT 1,
                referral_code TEXT,
                referrer_id INTEGER,
                last_daily_claim INTEGER,
                created_at INTEGER DEFAULT (strftime('%s', 'now'))
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS taps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                timestamp INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(telegram_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                reward_status TEXT DEFAULT 'pending',
                timestamp INTEGER,
                UNIQUE(referred_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                method TEXT,
                address TEXT,
                status TEXT DEFAULT 'pending',
                requested_at INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(telegram_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS upgrades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                power_level INTEGER,
                coins_spent INTEGER,
                timestamp INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(telegram_id)
            )
        ''')
        
        db.commit()

def validate_init_data(init_data):
    try:
        data_dict = {}
        for item in init_data.split('&'):
            key, value = item.split('=')
            data_dict[key] = value
        
        hash_str = data_dict.pop('hash')
        data_check_string = '\n'.join(f"{k}={v}" for k, v in sorted(data_dict.items()))
        
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        return computed_hash == hash_str
    except:
        return False

def get_user_data(telegram_id):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    if user:
        return dict(user)
    return None

def create_user(telegram_id, username, referrer_id=None):
    db = get_db()
    referral_code = hashlib.md5(f"{telegram_id}{time.time()}".encode()).hexdigest()[:8]
    
    user_data = {
        'telegram_id': telegram_id,
        'username': username,
        'referral_code': referral_code,
        'referrer_id': referrer_id
    }
    
    db.execute('''
        INSERT INTO users (telegram_id, username, referral_code, referrer_id) 
        VALUES (:telegram_id, :username, :referral_code, :referrer_id)
    ''', user_data)
    db.commit()
    
    # Apply referral bonus if applicable
    if referrer_id:
        db.execute('UPDATE users SET coins = coins + ? WHERE telegram_id = ?', (REFERRAL_BONUS, referrer_id))
        db.execute('''
            INSERT INTO referrals (referrer_id, referred_id, timestamp)
            VALUES (?, ?, ?)
        ''', (referrer_id, telegram_id, int(time.time())))
        db.commit()
    
    return user_data

@app.before_request
def before_request():
    if request.method == 'OPTIONS':
        return make_response(), 200
    
    # Skip auth for some endpoints
    if request.path in ['/api/leaderboard', '/']:
        return
    
    init_data = request.headers.get('X-Telegram-Init-Data')
    if not init_data or not validate_init_data(init_data):
        return jsonify({'error': 'Invalid initData'}), 401
    
    # Parse user data from initData
    user_data = {}
    for item in init_data.split('&'):
        if item.startswith('user='):
            user_data = json.loads(item[5:])
            break
    
    telegram_id = user_data.get('id')
    username = user_data.get('username', user_data.get('first_name', 'Player'))
    
    # Create user if not exists
    g.user = get_user_data(telegram_id)
    if not g.user:
        # Check for referral
        referrer_id = request.args.get('ref')
        g.user = create_user(telegram_id, username, referrer_id)
    else:
        g.user = dict(g.user)

@app.route('/api/tap', methods=['POST'])
def tap():
    user_id = g.user['telegram_id']
    db = get_db()
    
    # Anti-cheat: max 10 taps/second
    last_tap = db.execute('''
        SELECT timestamp FROM taps 
        WHERE user_id = ? 
        ORDER BY timestamp DESC LIMIT 1
    ''', (user_id,)).fetchone()
    
    if last_tap and (time.time() - last_tap['timestamp']) < 0.1:
        return jsonify({'error': 'Tap too fast'}), 429
    
    # Add tap record
    db.execute('INSERT INTO taps (user_id, timestamp) VALUES (?, ?)', (user_id, time.time()))
    
    # Update coins
    coins_earned = g.user['tap_power']
    db.execute('UPDATE users SET coins = coins + ? WHERE telegram_id = ?', (coins_earned, user_id))
    db.commit()
    
    return jsonify({
        'coins': g.user['coins'] + coins_earned,
        'earned': coins_earned
    })

@app.route('/api/user/<telegram_id>')
def get_user(telegram_id):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()
    if user:
        # Count referrals
        referrals = db.execute('''
            SELECT COUNT(*) as count FROM referrals 
            WHERE referrer_id = ?
        ''', (telegram_id,)).fetchone()['count']
        
        user_data = dict(user)
        user_data['referrals'] = referrals
        return jsonify(user_data)
    return jsonify({'error': 'User not found'}), 404

@app.route('/api/upgrade', methods=['POST'])
def upgrade():
    user_id = g.user['telegram_id']
    db = get_db()
    
    # Calculate upgrade cost
    upgrade_cost = BASE_UPGRADE_COST * (g.user['tap_power'] + 1)
    
    if g.user['coins'] < upgrade_cost:
        return jsonify({'error': 'Not enough coins'}), 400
    
    # Update user
    db.execute('''
        UPDATE users 
        SET coins = coins - ?, 
            tap_power = tap_power + 1 
        WHERE telegram_id = ?
    ''', (upgrade_cost, user_id))
    
    # Record upgrade
    db.execute('''
        INSERT INTO upgrades (user_id, power_level, coins_spent, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (user_id, g.user['tap_power'] + 1, upgrade_cost, time.time()))
    
    db.commit()
    
    return jsonify({
        'coins': g.user['coins'] - upgrade_cost,
        'tap_power': g.user['tap_power'] + 1
    })

@app.route('/api/leaderboard')
def leaderboard():
    db = get_db()
    top_users = db.execute('''
        SELECT telegram_id, username, coins, tap_power 
        FROM users 
        ORDER BY coins DESC 
        LIMIT 10
    ''').fetchall()
    
    return jsonify([dict(user) for user in top_users])

@app.route('/api/daily-reward', methods=['POST'])
def daily_reward():
    user_id = g.user['telegram_id']
    db = get_db()
    
    now = time.time()
    last_claim = g.user['last_daily_claim'] or 0
    
    # Check if 24 hours have passed
    if now - last_claim < 86400:
        return jsonify({'error': 'Reward already claimed'}), 400
    
    # Update user
    db.execute('''
        UPDATE users 
        SET coins = coins + ?, 
            last_daily_claim = ? 
        WHERE telegram_id = ?
    ''', (DAILY_REWARD, now, user_id))
    db.commit()
    
    return jsonify({
        'coins': g.user['coins'] + DAILY_REWARD,
        'reward': DAILY_REWARD
    })

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    user_id = g.user['telegram_id']
    data = request.json
    
    if g.user['coins'] < MIN_WITHDRAW:
        return jsonify({'error': f'Minimum withdrawal is {MIN_WITHDRAW} coins'}), 400
    
    valid_methods = ['paypal', 'usdt', 'telebirr', 'bank']
    if data['method'] not in valid_methods:
        return jsonify({'error': 'Invalid withdrawal method'}), 400
    
    db = get_db()
    
    # Record withdrawal request
    db.execute('''
        INSERT INTO withdrawals (user_id, method, address, status, requested_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, data['method'], data['address'], 'pending', time.time()))
    
    # Deduct coins
    db.execute('UPDATE users SET coins = coins - ? WHERE telegram_id = ?', (MIN_WITHDRAW, user_id))
    db.commit()
    
    return jsonify({
        'message': 'Withdrawal request submitted',
        'coins': g.user['coins'] - MIN_WITHDRAW
    })

@app.route('/api/referral', methods=['POST'])
def referral():
    user_id = g.user['telegram_id']
    return jsonify({
        'referral_code': g.user['referral_code'],
        'referral_link': f"{request.host_url}?ref={user_id}",
        'bonus': REFERRAL_BONUS
    })

@app.teardown_appcontext
def close_db(error):
    if hasattr(g, 'db'):
        g.db.close()

if __name__ == '__main__':
    os.makedirs(app.instance_path, exist_ok=True)
    init_db()
    app.run(host='0.0.0.0', port=5000)