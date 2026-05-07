/** REST API client with JWT authentication. */
const API = (() => {
    const DEFAULT_BACKEND_URL = 'http://192.168.1.43:8000';

    function normalizeBaseUrl(value) {
        if (!value) return DEFAULT_BACKEND_URL;
        try {
            const url = new URL(value);
            return url.origin;
        } catch (_) {
            return DEFAULT_BACKEND_URL;
        }
    }

    function getBaseUrl() {
        const saved = localStorage.getItem('anpr_backend_url');
        if (saved) return normalizeBaseUrl(saved);

        if (window.location.protocol === 'file:') {
            return DEFAULT_BACKEND_URL;
        }

        if (window.location.port && window.location.port !== '8000') {
            return DEFAULT_BACKEND_URL;
        }

        return normalizeBaseUrl(window.location.origin);
    }

    function getToken() {
        return localStorage.getItem('anpr_token');
    }

    function setToken(token) {
        localStorage.setItem('anpr_token', token);
    }

    function setBaseUrl(url) {
        localStorage.setItem('anpr_backend_url', normalizeBaseUrl(url));
    }

    function clearToken() {
        localStorage.removeItem('anpr_token');
    }

    async function request(method, path, body = null) {
        const headers = { 'Content-Type': 'application/json' };
        const token = getToken();
        if (token) headers['Authorization'] = `Bearer ${token}`;

        const opts = { method, headers };
        if (body !== null) opts.body = JSON.stringify(body);

        const res = await fetch(`${getBaseUrl()}${path}`, opts);
        if (res.status === 401) {
            clearToken();
            Auth.showLogin();
            throw new Error('Unauthorized');
        }
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || 'Request failed');
        }
        if (res.headers.get('content-type')?.includes('application/json')) {
            return res.json();
        }
        return res;
    }

    return {
        get: (path) => request('GET', path),
        post: (path, body) => request('POST', path, body),
        put: (path, body) => request('PUT', path, body),
        del: (path) => request('DELETE', path),
        getToken, setToken, clearToken, getBaseUrl, setBaseUrl
    };
})();
