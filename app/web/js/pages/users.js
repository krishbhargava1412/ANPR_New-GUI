/** User management page (admin only). */
const UsersPage = (() => {
    let table = null;
    function render(container) {
        container.innerHTML = `<div class="animate-in">
            <div class="page-header"><h1 class="page-title">User Management</h1>
            <p class="page-subtitle">Admin — create and manage operator accounts</p></div>
            <div class="card mb-16"><div class="card-title">CREATE USER</div>
                <div class="form-row">
                    <div class="form-group flex-1"><input type="text" id="usr-name" placeholder="Username"></div>
                    <div class="form-group flex-1"><input type="text" id="usr-full" placeholder="Full Name"></div>
                    <div class="form-group flex-1"><input type="password" id="usr-pass" placeholder="Password"></div>
                    <div class="form-group"><select id="usr-role">
                        <option>gate keeper</option><option>manager</option><option>operator</option><option>viewer</option><option>admin</option>
                    </select></div>
                    <button class="btn btn-primary btn-sm" id="usr-create" style="margin-top:auto">CREATE</button>
                </div>
            </div>
            <div class="card" id="usr-table"></div></div>`;
        table = createDataTable([
            { key: 'username', label: 'USERNAME' },
            { key: 'full_name', label: 'NAME' },
            { key: 'role', label: 'ROLE', html: r => `<span class="badge badge-info">${r.role}</span>` },
            { key: 'created_at', label: 'CREATED' },
            { key: 'action', label: '', width: '80px', html: r =>
                `<button class="btn btn-danger btn-xs" data-del="${r.id}">DELETE</button>` },
        ]);
        document.getElementById('usr-table').appendChild(table.element);
        document.getElementById('usr-create').onclick = create;
        document.getElementById('usr-table').addEventListener('click', async e => {
            const id = e.target.dataset.del;
            if (id && confirm('Delete this user?')) { await API.del(`/api/users/${id}`); refresh(); }
        });
        refresh();
    }
    async function create() {
        const u = document.getElementById('usr-name').value.trim();
        const f = document.getElementById('usr-full').value.trim();
        const p = document.getElementById('usr-pass').value;
        const r = document.getElementById('usr-role').value;
        if (!u || !p) return alert('Username and password required');
        try { await API.post('/api/users', { username:u, full_name:f, password:p, role:r });
            document.getElementById('usr-name').value = '';
            document.getElementById('usr-full').value = '';
            document.getElementById('usr-pass').value = '';
            refresh();
        } catch(e) { alert(e.message); }
    }
    async function refresh() {
        try { const res = await API.get('/api/users'); table.setData(res.users || []); } catch(e){}
    }
    function teardown() { table = null; }
    return { render, teardown };
})();
