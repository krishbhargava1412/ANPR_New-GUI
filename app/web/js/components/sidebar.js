/** Sidebar component. */
const Sidebar = (() => {
    const NAV_ITEMS = [
        { icon: '📊', label: 'Dashboard', route: 'dashboard' },
        { icon: '🎯', label: 'Detection', route: 'detection' },
        { icon: '📋', label: 'History', route: 'history' },
        { icon: '🔍', label: 'Watchlist', route: 'watchlist' },
        { icon: '⚙', label: 'Settings', route: 'settings' },
        { icon: 'ℹ', label: 'About', route: 'about' },
    ];

    const ADMIN_ITEMS = [
        { icon: '👥', label: 'Users', route: 'users' },
    ];

    function render(user) {
        const nav = document.getElementById('sidebar-nav');
        nav.innerHTML = '';
        const items = Auth.isAdmin() ? [...NAV_ITEMS, ...ADMIN_ITEMS] : NAV_ITEMS;
        items.forEach(item => {
            const btn = document.createElement('button');
            btn.className = 'nav-item';
            btn.dataset.route = item.route;
            btn.innerHTML = `<span class="nav-icon">${item.icon}</span><span class="nav-label">${item.label}</span>`;
            btn.addEventListener('click', () => Router.navigate(item.route));
            nav.appendChild(btn);
        });

        const userInfo = document.getElementById('user-info');
        if (user) {
            userInfo.innerHTML = `
                <span class="username">${user.full_name || user.username}</span>
                <span class="role">${user.role}</span>
            `;
        }
    }

    return { render };
})();
