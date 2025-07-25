document.addEventListener('DOMContentLoaded', () => {
    const tg = window.Telegram.WebApp;
    tg.expand();

    const API_URL = 'https://coin-tap-game.onrender.com/api'; // Your Render backend URL
    const MIN_WITHDRAWAL_BALANCE = 50000;
    
    // DOM Elements
    const coinCounter = document.getElementById('coin-counter');
    const tapButton = document.getElementById('tap-button');
    const upgradeBtn = document.getElementById('upgrade-btn');
    const powerLevelSpan = document.getElementById('power-level');
    const upgradeCostSpan = document.getElementById('upgrade-cost');
    const dailyRewardBtn = document.getElementById('daily-reward-btn');
    const usernameSpan = document.getElementById('username');
    const navBtns = document.querySelectorAll('.nav-btn');
    const views = document.querySelectorAll('.view');
    const leaderboardList = document.getElementById('leaderboard-list');
    const referralLinkInput = document.getElementById('referral-link');
    const shareReferralBtn = document.getElementById('share-referral-btn');
    const withdrawNavBtn = document.getElementById('withdraw-nav-btn');
    const withdrawForm = document.getElementById('withdraw-form');

    let userData = {};
    let telegramId;

    function init() {
        if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
            telegramId = tg.initDataUnsafe.user.id;
            usernameSpan.textContent = tg.initDataUnsafe.user.username || 'User';
            fetchUserData();
        } else {
            // For local development
            telegramId = '12345'; // Mock ID
            usernameSpan.textContent = 'dev_user';
            fetchUserData();
        }
    }
    
    async function fetchUserData() {
        try {
            const response = await fetch(`${API_URL}/user/${telegramId}?username=${usernameSpan.textContent}`);
            userData = await response.json();
            updateUI();
        } catch (error) {
            console.error('Error fetching user data:', error);
        }
    }

    function updateUI() {
        coinCounter.textContent = userData.coins || 0;
        powerLevelSpan.textContent = userData.tap_power || 1;
        upgradeCostSpan.textContent = (userData.tap_power || 1) * 50;
        referralLinkInput.value = `https://t.me/YOUR_BOT_USERNAME?start=${telegramId}`; // Replace with your bot's username
        
        if (userData.coins >= MIN_WITHDRAWAL_BALANCE) {
            withdrawNavBtn.style.display = 'block';
        } else {
            withdrawNavBtn.style.display = 'none';
        }
    }
    
    // --- Event Listeners ---
    
    tapButton.addEventListener('click', async () => {
        // Tap animation
        tapButton.style.transform = 'scale(0.95)';
        setTimeout(() => tapButton.style.transform = 'scale(1)', 100);

        try {
            await fetch(`${API_URL}/tap`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ telegram_id: telegramId })
            });
            userData.coins += userData.tap_power;
            updateUI();
        } catch (error) {
            console.error('Error on tap:', error);
        }
    });

    upgradeBtn.addEventListener('click', async () => {
        try {
            const response = await fetch(`${API_URL}/upgrade`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ telegram_id: telegramId })
            });
            const result = await response.json();
            if (response.ok) {
                await fetchUserData();
            } else {
                alert(result.message);
            }
        } catch (error) {
            console.error('Error upgrading:', error);
        }
    });

    dailyRewardBtn.addEventListener('click', async () => {
        try {
            const response = await fetch(`${API_URL}/daily-reward`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ telegram_id: telegramId })
            });
            const result = await response.json();
            alert(result.message);
            if (response.ok) {
                await fetchUserData();
            }
        } catch (error) {
            console.error('Error claiming daily reward:', error);
        }
    });

    shareReferralBtn.addEventListener('click', () => {
        const text = `Join this awesome tap-to-earn game and get a bonus! ${referralLinkInput.value}`;
        tg.openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(referralLinkInput.value)}&text=${encodeURIComponent(text)}`);
    });

    withdrawForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const method = document.getElementById('withdraw-method').value;
        const address = document.getElementById('withdraw-address').value;
        const amount = parseInt(document.getElementById('withdraw-amount').value);

        if (amount > userData.coins) {
            alert("You cannot withdraw more coins than you have.");
            return;
        }

        try {
            const response = await fetch(`${API_URL}/withdraw`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ telegram_id: telegramId, method, address, amount })
            });
            const result = await response.json();
            alert(result.message);
            if (response.ok) {
                await fetchUserData();
            }
        } catch (error) {
            console.error('Error submitting withdrawal:', error);
        }
    });

    // --- Navigation ---
    navBtns.forEach(btn => {
        btn.addEventListener('click', async () => {
            const viewName = btn.getAttribute('data-view');
            
            document.querySelector('.view[style*="display: block"]')?.style.setProperty('display', 'none', 'important');
            document.querySelector('main').style.display = 'none';

            if (viewName === 'game') {
                document.querySelector('main').style.display = 'block';
            } else {
                const view = document.getElementById(`${viewName}-view`);
                if (view) {
                    view.style.display = 'block';
                    if (viewName === 'leaderboard') {
                        await loadLeaderboard();
                    }
                }
            }
        });
    });

    async function loadLeaderboard() {
        try {
            const response = await fetch(`${API_URL}/leaderboard`);
            const leaders = await response.json();
            leaderboardList.innerHTML = '';
            leaders.forEach(leader => {
                const li = document.createElement('li');
                li.innerHTML = `<span>${leader.username}</span><span>${leader.coins}</span>`;
                leaderboardList.appendChild(li);
            });
        } catch (error) {
            console.error('Error loading leaderboard:', error);
        }
    }

    init();
});
