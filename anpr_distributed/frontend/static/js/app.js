/**
 * ANPR Command Center — Application Logic
 *
 * SPA router, page rendering, modal management, toast notifications.
 * Connects the UI (index.html) to the API client (api.js).
 */
document.addEventListener('DOMContentLoaded', () => {

    // ═══════════ ELEMENTS ═══════════════════════════════════════════════════
    const $login       = document.getElementById('login-screen');
    const $app         = document.getElementById('app-shell');
    const $loginForm   = document.getElementById('login-form');
    const $loginError  = document.getElementById('login-error');
    const $loginBtn    = document.getElementById('login-btn');
    const $logout      = document.getElementById('btn-logout');
    const $pageTitle   = document.getElementById('page-title');
    const $pageContainer = document.getElementById('page-container');
    const $sidebarToggle = document.getElementById('sidebar-toggle');
    const $sidebar     = document.getElementById('sidebar');
    const $navUsers    = document.getElementById('nav-users');
    const $topbarTime  = document.getElementById('topbar-time');
    const $serverStatus = document.getElementById('server-status');

    let currentPage = 'dashboard';
    let refreshInterval = null;

    // ═══════════ AUTH ════════════════════════════════════════════════════════
    function showApp() {
        const user = API.getUser();
        if (!user) return showLogin();
        $login.style.display = 'none';
        $app.style.display = 'flex';
        document.getElementById('user-display-name').textContent = user.full_name || user.username;
        document.getElementById('user-display-role').textContent = user.role;
        document.getElementById('user-avatar').textContent = (user.full_name || user.username).charAt(0).toUpperCase();
        // Show admin nav if admin
        $navUsers.style.display = user.role === 'admin' ? 'flex' : 'none';
        navigateTo('dashboard');
        startAutoRefresh();
    }

    function showLogin() {
        $login.style.display = 'flex';
        $app.style.display = 'none';
        stopAutoRefresh();
    }

    $loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('login-username').value.trim();
        const password = document.getElementById('login-password').value;
        $loginError.style.display = 'none';
        $loginBtn.querySelector('.btn-text').textContent = 'Signing in...';
        $loginBtn.disabled = true;
        try {
            await API.login(username, password);
            showApp();
        } catch (err) {
            $loginError.textContent = err.message;
            $loginError.style.display = 'block';
        } finally {
            $loginBtn.querySelector('.btn-text').textContent = 'Sign In';
            $loginBtn.disabled = false;
        }
    });

    $logout.addEventListener('click', () => {
        API.logout();
        showLogin();
    });

    // ═══════════ NAVIGATION ═════════════════════════════════════════════════
    const pageTitles = {
        dashboard: 'Dashboard', detections: 'Detection History',
        watchlist: 'Alert Watchlist', cameras: 'Camera Management',
        users: 'User Management',
    };

    function navigateTo(page) {
        currentPage = page;
        $pageTitle.textContent = pageTitles[page] || page;
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
        const target = document.getElementById(`page-${page}`);
        if (target) target.classList.add('active');
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        const navItem = document.querySelector(`.nav-item[data-page="${page}"]`);
        if (navItem) navItem.classList.add('active');
        // Load page data
        switch (page) {
            case 'dashboard': loadDashboard(); break;
            case 'detections': loadDetections(); break;
            case 'watchlist': loadWatchlist(); break;
            case 'cameras': loadCameras(); break;
            case 'users': loadUsers(); break;
        }
    }

    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            navigateTo(item.dataset.page);
            $sidebar.classList.remove('open');
        });
    });

    $sidebarToggle.addEventListener('click', () => $sidebar.classList.toggle('open'));
    document.getElementById('btn-view-all-detections')?.addEventListener('click', () => navigateTo('detections'));

    // ═══════════ DASHBOARD ══════════════════════════════════════════════════
    async function loadDashboard() {
        try {
            const stats = await API.dashboard();
            document.getElementById('stat-total').textContent = formatNumber(stats.total_detections);
            document.getElementById('stat-plates').textContent = formatNumber(stats.unique_plates);
            document.getElementById('stat-watchlist').textContent = formatNumber(stats.watchlist_hits);
            document.getElementById('stat-cameras').textContent = stats.active_cameras;
            document.getElementById('stat-rate').textContent = stats.recent_rate_per_min ?? '--';
            document.getElementById('stat-confidence').textContent =
                stats.avg_confidence != null ? `${(stats.avg_confidence * 100).toFixed(0)}%` : '--';
        } catch { /* server offline — stats stay as -- */ }

        // Load recent detections
        try {
            const dets = await API.detections('limit=10');
            renderRecentDetections(dets);
        } catch {}
    }

    function renderRecentDetections(dets) {
        const body = document.getElementById('recent-detections-body');
        if (!dets.length) {
            body.innerHTML = '<tr><td colspan="5" class="empty-state">No detections yet</td></tr>';
            return;
        }
        body.innerHTML = dets.map(d => `
            <tr>
                <td>${formatTime(d.detected_at)}</td>
                <td><span class="plate-number">${escHtml(d.plate_number)}</span></td>
                <td>Camera ${d.camera_id}</td>
                <td>${d.confidence != null ? `${(d.confidence * 100).toFixed(1)}%` : '--'}</td>
                <td>${d.watchlist_hit
                    ? '<span class="badge badge-danger">⚠ ALERT</span>'
                    : '<span class="badge badge-success">Clear</span>'}</td>
            </tr>`).join('');
    }

    // ═══════════ DETECTIONS ═════════════════════════════════════════════════
    let detectionsPage = 0;

    async function loadDetections() {
        const params = new URLSearchParams();
        const plate = document.getElementById('filter-plate').value.trim();
        const cam = document.getElementById('filter-camera').value;
        const wl = document.getElementById('filter-watchlist-only').checked;
        const from = document.getElementById('filter-from').value;
        const to = document.getElementById('filter-to').value;
        if (plate) params.set('plate', plate);
        if (cam) params.set('camera_id', cam);
        if (wl) params.set('watchlist_only', 'true');
        if (from) params.set('from_date', from);
        if (to) params.set('to_date', to);
        params.set('limit', '50');
        params.set('offset', String(detectionsPage * 50));

        try {
            const dets = await API.detections(params.toString());
            const body = document.getElementById('detections-body');
            if (!dets.length) {
                body.innerHTML = '<tr><td colspan="7" class="empty-state">No detections found</td></tr>';
                return;
            }
            body.innerHTML = dets.map(d => `
                <tr>
                    <td>${d.id}</td>
                    <td>${formatTime(d.detected_at)}</td>
                    <td><span class="plate-number">${escHtml(d.plate_number)}</span></td>
                    <td>Camera ${d.camera_id}</td>
                    <td>${d.confidence != null ? `${(d.confidence * 100).toFixed(1)}%` : '--'}</td>
                    <td>${d.ocr_score != null ? `${(d.ocr_score * 100).toFixed(1)}%` : '--'}</td>
                    <td>${d.watchlist_hit
                        ? '<span class="badge badge-danger">⚠ ALERT</span>'
                        : '<span class="badge badge-success">Clear</span>'}</td>
                </tr>`).join('');
        } catch (err) {
            toast('Failed to load detections', 'error');
        }
    }

    document.getElementById('btn-search-detections').addEventListener('click', () => {
        detectionsPage = 0;
        loadDetections();
    });

    document.getElementById('btn-export-csv').addEventListener('click', async () => {
        try {
            const blob = await API.exportCSV();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url; a.download = 'detections_export.csv';
            document.body.appendChild(a); a.click(); a.remove();
            URL.revokeObjectURL(url);
            toast('CSV exported successfully', 'success');
        } catch { toast('Export failed', 'error'); }
    });

    // ═══════════ WATCHLIST ═══════════════════════════════════════════════════
    async function loadWatchlist() {
        try {
            const items = await API.watchlist();
            const body = document.getElementById('watchlist-body');
            if (!items.length) {
                body.innerHTML = '<tr><td colspan="5" class="empty-state">Watchlist is empty</td></tr>';
                return;
            }
            body.innerHTML = items.map(w => `
                <tr>
                    <td><span class="plate-number">${escHtml(w.plate_number)}</span></td>
                    <td><span class="badge badge-${w.threat_level}">${w.threat_level}</span></td>
                    <td>${escHtml(w.notes || '--')}</td>
                    <td>${formatTime(w.added_at)}</td>
                    <td>
                        <button class="btn-sm btn-danger" onclick="App.removeWatchlistPlate('${escHtml(w.plate_number)}')">Remove</button>
                    </td>
                </tr>`).join('');
        } catch { toast('Failed to load watchlist', 'error'); }
    }

    document.getElementById('btn-add-watchlist').addEventListener('click', () => {
        showModal('Add to Watchlist', `
            <div class="form-group">
                <label>Plate Number</label>
                <input type="text" id="modal-wl-plate" placeholder="e.g. DL01AB1234" required>
            </div>
            <div class="form-group">
                <label>Threat Level</label>
                <select id="modal-wl-threat">
                    <option value="low">Low</option>
                    <option value="medium" selected>Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                </select>
            </div>
            <div class="form-group">
                <label>Notes</label>
                <textarea id="modal-wl-notes" placeholder="Optional notes..."></textarea>
            </div>
        `, async () => {
            const plate = document.getElementById('modal-wl-plate').value.trim();
            const threat = document.getElementById('modal-wl-threat').value;
            const notes = document.getElementById('modal-wl-notes').value.trim();
            if (!plate) return toast('Plate number is required', 'error');
            try {
                await API.addWatchlist({ plate_number: plate, threat_level: threat, notes: notes || null });
                closeModal();
                toast(`${plate} added to watchlist`, 'success');
                loadWatchlist();
            } catch (err) { toast(err.message, 'error'); }
        });
    });

    // ═══════════ CAMERAS ════════════════════════════════════════════════════
    async function loadCameras() {
        try {
            const cams = await API.cameras();
            const grid = document.getElementById('cameras-grid');
            if (!cams.length) {
                grid.innerHTML = '<div class="empty-state-large">No cameras configured. Click "Add Camera" to begin.</div>';
                return;
            }
            grid.innerHTML = cams.map(c => `
                <div class="camera-card">
                    <div class="camera-card-header">
                        <h4>${escHtml(c.name)}</h4>
                        <span class="badge ${c.is_active ? 'badge-success' : 'badge-danger'}">${c.is_active ? 'Active' : 'Inactive'}</span>
                    </div>
                    <div class="camera-card-details">
                        <p><strong>Type:</strong> ${c.source_type.toUpperCase()}</p>
                        <p><strong>URL:</strong> <span style="word-break:break-all;font-family:var(--font-mono);font-size:0.75rem;">${escHtml(c.source_url)}</span></p>
                        ${c.location ? `<p><strong>Location:</strong> ${escHtml(c.location)}</p>` : ''}
                    </div>
                    <div class="camera-card-footer">
                        <button class="btn-sm btn-danger" onclick="App.deleteCamera(${c.id}, '${escHtml(c.name)}')">Delete</button>
                    </div>
                </div>`).join('');
            // Populate camera filter dropdown
            const sel = document.getElementById('filter-camera');
            sel.innerHTML = '<option value="">All Cameras</option>' +
                cams.map(c => `<option value="${c.id}">${escHtml(c.name)}</option>`).join('');
        } catch { toast('Failed to load cameras', 'error'); }
    }

    document.getElementById('btn-add-camera').addEventListener('click', () => {
        showModal('Add Camera', `
            <div class="form-group">
                <label>Camera Name</label>
                <input type="text" id="modal-cam-name" placeholder="e.g. Gate 1 Entry">
            </div>
            <div class="form-group">
                <label>Source URL / Device Index</label>
                <input type="text" id="modal-cam-url" placeholder="rtsp://admin:pass@192.168.1.10:554/stream1">
            </div>
            <div class="form-group">
                <label>Type</label>
                <select id="modal-cam-type">
                    <option value="rtsp" selected>RTSP</option>
                    <option value="onvif">ONVIF</option>
                    <option value="usb">USB</option>
                    <option value="file">File</option>
                </select>
            </div>
            <div class="form-group">
                <label>Location</label>
                <input type="text" id="modal-cam-location" placeholder="e.g. Main Gate, Building A">
            </div>
        `, async () => {
            const name = document.getElementById('modal-cam-name').value.trim();
            const url = document.getElementById('modal-cam-url').value.trim();
            const type = document.getElementById('modal-cam-type').value;
            const loc = document.getElementById('modal-cam-location').value.trim();
            if (!name || !url) return toast('Name and URL are required', 'error');
            try {
                await API.addCamera({ name, source_url: url, source_type: type, location: loc || null });
                closeModal();
                toast(`Camera "${name}" added`, 'success');
                loadCameras();
            } catch (err) { toast(err.message, 'error'); }
        });
    });

    // ═══════════ USERS ══════════════════════════════════════════════════════
    async function loadUsers() {
        try {
            const list = await API.users();
            const body = document.getElementById('users-body');
            body.innerHTML = list.map(u => `
                <tr>
                    <td><strong>${escHtml(u.username)}</strong></td>
                    <td>${escHtml(u.full_name)}</td>
                    <td><span class="badge badge-info">${u.role}</span></td>
                    <td>${u.is_active
                        ? '<span class="badge badge-success">Active</span>'
                        : '<span class="badge badge-danger">Inactive</span>'}</td>
                    <td>${u.last_login ? formatTime(u.last_login) : 'Never'}</td>
                    <td>
                        ${u.username !== 'admin' ? `
                            <button class="btn-sm btn-outline" onclick="App.toggleUser(${u.id}, ${!u.is_active})">${u.is_active ? 'Deactivate' : 'Activate'}</button>
                            <button class="btn-sm btn-danger" onclick="App.deleteUser(${u.id}, '${escHtml(u.username)}')">Delete</button>
                        ` : '<span style="color:var(--text-muted);font-size:0.8rem;">Protected</span>'}
                    </td>
                </tr>`).join('');
        } catch { toast('Failed to load users', 'error'); }
    }

    document.getElementById('btn-add-user').addEventListener('click', () => {
        showModal('Create User', `
            <div class="form-group">
                <label>Username</label>
                <input type="text" id="modal-user-name" placeholder="username" required>
            </div>
            <div class="form-group">
                <label>Full Name</label>
                <input type="text" id="modal-user-fullname" placeholder="Full Name">
            </div>
            <div class="form-group">
                <label>Password</label>
                <input type="password" id="modal-user-pass" placeholder="Min 6 characters" required>
            </div>
            <div class="form-group">
                <label>Role</label>
                <select id="modal-user-role">
                    <option value="viewer">Viewer</option>
                    <option value="gate_keeper">Gate Keeper</option>
                    <option value="operator" selected>Operator</option>
                    <option value="manager">Manager</option>
                    <option value="admin">Admin</option>
                </select>
            </div>
        `, async () => {
            const username = document.getElementById('modal-user-name').value.trim();
            const full_name = document.getElementById('modal-user-fullname').value.trim();
            const password = document.getElementById('modal-user-pass').value;
            const role = document.getElementById('modal-user-role').value;
            if (!username || password.length < 6) return toast('Username and 6+ char password required', 'error');
            try {
                await API.addUser({ username, full_name, password, role });
                closeModal();
                toast(`User "${username}" created`, 'success');
                loadUsers();
            } catch (err) { toast(err.message, 'error'); }
        });
    });

    // ═══════════ MODAL ══════════════════════════════════════════════════════
    const $modalOverlay = document.getElementById('modal-overlay');
    const $modalTitle   = document.getElementById('modal-title');
    const $modalBody    = document.getElementById('modal-body');
    const $modalFooter  = document.getElementById('modal-footer');

    function showModal(title, bodyHtml, onConfirm) {
        $modalTitle.textContent = title;
        $modalBody.innerHTML = bodyHtml;
        $modalFooter.innerHTML = `
            <button class="btn-sm btn-outline" id="modal-cancel-btn">Cancel</button>
            <button class="btn-sm btn-primary" id="modal-confirm-btn">Confirm</button>
        `;
        $modalOverlay.style.display = 'flex';
        document.getElementById('modal-cancel-btn').addEventListener('click', closeModal);
        document.getElementById('modal-confirm-btn').addEventListener('click', onConfirm);
    }

    function closeModal() { $modalOverlay.style.display = 'none'; }
    document.getElementById('modal-close').addEventListener('click', closeModal);
    $modalOverlay.addEventListener('click', (e) => { if (e.target === $modalOverlay) closeModal(); });

    // ═══════════ TOAST ══════════════════════════════════════════════════════
    function toast(msg, type = 'info') {
        const el = document.createElement('div');
        el.className = `toast toast-${type}`;
        el.textContent = msg;
        document.getElementById('toast-container').appendChild(el);
        setTimeout(() => el.remove(), 4200);
    }

    // ═══════════ UTILITIES ══════════════════════════════════════════════════
    function formatNumber(n) {
        if (n == null) return '--';
        return n.toLocaleString();
    }

    function formatTime(iso) {
        if (!iso) return '--';
        try {
            const d = new Date(iso);
            return d.toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' });
        } catch { return iso; }
    }

    function escHtml(s) {
        if (s == null) return '';
        const d = document.createElement('div');
        d.textContent = String(s);
        return d.innerHTML;
    }

    // ═══════════ AUTO-REFRESH ════════════════════════════════════════════════
    function startAutoRefresh() {
        stopAutoRefresh();
        refreshInterval = setInterval(() => {
            if (currentPage === 'dashboard') loadDashboard();
        }, 15000); // Refresh dashboard every 15s
    }
    function stopAutoRefresh() { if (refreshInterval) clearInterval(refreshInterval); }

    // ═══════════ CLOCK ══════════════════════════════════════════════════════
    function updateClock() {
        const now = new Date();
        $topbarTime.textContent = now.toLocaleString('en-IN', {
            day: '2-digit', month: 'short', year: 'numeric',
            hour: '2-digit', minute: '2-digit', second: '2-digit',
        });
    }
    setInterval(updateClock, 1000);
    updateClock();

    // ═══════════ SERVER HEALTH ═══════════════════════════════════════════════
    async function checkHealth() {
        const online = await API.healthCheck();
        const dot = $serverStatus.querySelector('.status-dot');
        const label = $serverStatus.querySelector('span:last-child');
        dot.className = `status-dot ${online ? 'online' : 'offline'}`;
        label.textContent = online ? 'Server Online' : 'Server Offline';
    }
    setInterval(checkHealth, 30000);

    // ═══════════ GLOBAL ACTIONS (called from inline onclick) ═════════════════
    window.App = {
        removeWatchlistPlate: async (plate) => {
            if (!confirm(`Remove "${plate}" from watchlist?`)) return;
            try { await API.removeWatchlist(plate); toast(`${plate} removed`, 'success'); loadWatchlist(); }
            catch { toast('Failed to remove', 'error'); }
        },
        deleteCamera: async (id, name) => {
            if (!confirm(`Delete camera "${name}"?`)) return;
            try { await API.deleteCamera(id); toast(`Camera deleted`, 'success'); loadCameras(); }
            catch { toast('Failed to delete camera', 'error'); }
        },
        deleteUser: async (id, name) => {
            if (!confirm(`Delete user "${name}"? This cannot be undone.`)) return;
            try { await API.deleteUser(id); toast(`User deleted`, 'success'); loadUsers(); }
            catch { toast('Failed to delete user', 'error'); }
        },
        toggleUser: async (id, activate) => {
            try { await API.updateUser(id, { is_active: activate }); toast('User updated', 'success'); loadUsers(); }
            catch { toast('Failed to update user', 'error'); }
        },
    };

    // ═══════════ INIT ═══════════════════════════════════════════════════════
    if (API.isLoggedIn()) { showApp(); } else { showLogin(); }
    checkHealth();
});
