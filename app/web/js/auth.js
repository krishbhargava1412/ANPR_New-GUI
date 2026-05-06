/** Authentication module — login flow and token management. */
const Auth = (() => {
    let currentUser = null;

    function init() {
        document.getElementById('login-btn').addEventListener('click', handleLogin);
        document.getElementById('login-password').addEventListener('keydown', e => {
            if (e.key === 'Enter') handleLogin();
        });
        document.getElementById('login-username').addEventListener('keydown', e => {
            if (e.key === 'Enter') document.getElementById('login-password').focus();
        });
        document.getElementById('logout-btn').addEventListener('click', handleLogout);
    }

    async function handleLogin() {
        const username = document.getElementById('login-username').value.trim();
        const password = document.getElementById('login-password').value;
        const errorEl = document.getElementById('login-error');
        errorEl.textContent = '';

        if (!username || !password) {
            errorEl.textContent = 'Please enter username and password';
            return;
        }

        try {
            const result = await API.post('/api/auth/login', { username, password });
            API.setToken(result.access_token);
            currentUser = result.user;
            hideLogin();
            App.onAuthenticated(currentUser);
        } catch (e) {
            errorEl.textContent = e.message || 'Login failed';
        }
    }

    function handleLogout() {
        API.clearToken();
        WS.disconnect();
        currentUser = null;
        showLogin();
    }

    function showLogin() {
        document.getElementById('login-overlay').classList.remove('hidden');
        document.getElementById('app-shell').classList.add('hidden');
        document.getElementById('login-username').value = '';
        document.getElementById('login-password').value = '';
        document.getElementById('login-error').textContent = '';
        setTimeout(() => document.getElementById('login-username').focus(), 100);
    }

    function hideLogin() {
        document.getElementById('login-overlay').classList.add('hidden');
        document.getElementById('app-shell').classList.remove('hidden');
    }

    async function checkSession() {
        const token = API.getToken();
        if (!token) { showLogin(); return; }
        try {
            currentUser = await API.get('/api/auth/me');
            hideLogin();
            App.onAuthenticated(currentUser);
        } catch (e) {
            showLogin();
        }
    }

    function getUser() { return currentUser; }
    function isAdmin() { return currentUser?.role === 'admin'; }

    return { init, showLogin, hideLogin, checkSession, getUser, isAdmin, handleLogout };
})();
