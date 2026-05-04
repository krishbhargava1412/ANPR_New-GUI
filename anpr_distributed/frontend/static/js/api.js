/**
 * ANPR Command Center — API Client
 *
 * Handles all HTTP communication with the FastAPI backend.
 * Manages JWT tokens in localStorage, auto-refreshes on 401.
 */
const API = (() => {
    const BASE = window.location.origin;

    function getToken() { return localStorage.getItem('anpr_access_token'); }
    function getRefreshToken() { return localStorage.getItem('anpr_refresh_token'); }
    function setTokens(access, refresh) {
        localStorage.setItem('anpr_access_token', access);
        localStorage.setItem('anpr_refresh_token', refresh);
    }
    function clearTokens() {
        localStorage.removeItem('anpr_access_token');
        localStorage.removeItem('anpr_refresh_token');
        localStorage.removeItem('anpr_user');
    }
    function getUser() {
        try { return JSON.parse(localStorage.getItem('anpr_user')); }
        catch { return null; }
    }
    function setUser(u) { localStorage.setItem('anpr_user', JSON.stringify(u)); }

    async function request(path, opts = {}) {
        const url = `${BASE}/api${path}`;
        const headers = { 'Content-Type': 'application/json', ...opts.headers };
        const token = getToken();
        if (token) headers['Authorization'] = `Bearer ${token}`;

        let res = await fetch(url, { ...opts, headers });

        // Auto-refresh on 401
        if (res.status === 401 && getRefreshToken()) {
            const refreshed = await refreshAccessToken();
            if (refreshed) {
                headers['Authorization'] = `Bearer ${getToken()}`;
                res = await fetch(url, { ...opts, headers });
            }
        }
        return res;
    }

    async function refreshAccessToken() {
        try {
            const res = await fetch(`${BASE}/api/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: getRefreshToken() }),
            });
            if (res.ok) {
                const data = await res.json();
                setTokens(data.access_token, data.refresh_token);
                return true;
            }
        } catch {}
        clearTokens();
        return false;
    }

    async function login(username, password) {
        const res = await fetch(`${BASE}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Login failed');
        }
        const data = await res.json();
        setTokens(data.access_token, data.refresh_token);
        setUser({ id: data.user_id, username: data.username, full_name: data.full_name, role: data.role });
        return data;
    }

    function logout() { clearTokens(); }
    function isLoggedIn() { return !!getToken(); }

    // ── Generic CRUD helpers ─────────────────────────────────────────────
    async function get(path) {
        const res = await request(path);
        if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
        return res.json();
    }
    async function post(path, body) {
        const res = await request(path, { method: 'POST', body: JSON.stringify(body) });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `POST ${path} failed`);
        }
        return res.json();
    }
    async function patch(path, body) {
        const res = await request(path, { method: 'PATCH', body: JSON.stringify(body) });
        if (!res.ok) throw new Error(`PATCH ${path} failed`);
        return res.json();
    }
    async function del(path) {
        const res = await request(path, { method: 'DELETE' });
        if (!res.ok && res.status !== 204) throw new Error(`DELETE ${path} failed`);
        return true;
    }

    // ── Specific endpoints ───────────────────────────────────────────────
    const dashboard = () => get('/dashboard/stats');
    const detections = (params = '') => get(`/detections${params ? '?' + params : ''}`);
    const cameras = () => get('/cameras');
    const addCamera = (body) => post('/cameras', body);
    const deleteCamera = (id) => del(`/cameras/${id}`);
    const watchlist = () => get('/watchlist');
    const addWatchlist = (body) => post('/watchlist', body);
    const removeWatchlist = (plate) => del(`/watchlist/${encodeURIComponent(plate)}`);
    const users = () => get('/users');
    const addUser = (body) => post('/users', body);
    const updateUser = (id, body) => patch(`/users/${id}`, body);
    const deleteUser = (id) => del(`/users/${id}`);
    const changePassword = (body) => post('/auth/change-password', body);
    const healthCheck = async () => {
        try { const r = await fetch(`${BASE}/api/health`); return r.ok; }
        catch { return false; }
    };
    const exportCSV = (params = '') => {
        const token = getToken();
        const url = `${BASE}/api/detections/export${params ? '?' + params : ''}`;
        // Create a temporary link with auth
        return request(`/detections/export${params ? '?' + params : ''}`).then(res => res.blob());
    };

    return {
        login, logout, isLoggedIn, getUser, setUser,
        dashboard, detections, cameras, addCamera, deleteCamera,
        watchlist, addWatchlist, removeWatchlist,
        users, addUser, updateUser, deleteUser,
        changePassword, healthCheck, exportCSV, get, post,
    };
})();
