/** REST API client with JWT authentication. */
const API = (() => {
    function getBaseUrl() {
        return localStorage.getItem('anpr_backend_url') || 'http://192.168.1.43:8000';
    }

    function getToken() {
        return localStorage.getItem('anpr_token');
    }

    function setToken(token) {
        localStorage.setItem('anpr_token', token);
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
        getToken, setToken, clearToken, getBaseUrl
    };
})();
