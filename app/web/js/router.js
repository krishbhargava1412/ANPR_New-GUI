/** Hash-based SPA router with page lifecycle. */
const Router = (() => {
    const routes = {};
    let currentPage = null;
    let currentRoute = '';

    function register(hash, pageModule) {
        routes[hash] = pageModule;
    }

    function navigate(hash) {
        location.hash = hash;
    }

    function handleRoute() {
        const hash = location.hash.slice(1) || 'dashboard';
        if (hash === currentRoute) return;

        // Teardown previous page
        if (currentPage && currentPage.teardown) {
            try { currentPage.teardown(); } catch (e) { console.error('Teardown error', e); }
        }

        const container = document.getElementById('page-container');
        container.innerHTML = '';

        const page = routes[hash];
        if (page) {
            currentPage = page;
            currentRoute = hash;
            try {
                page.render(container);
            } catch (e) {
                console.error('Render error', e);
                container.innerHTML = `<div class="card"><p class="text-danger">Page error: ${e.message}</p></div>`;
            }
        } else {
            container.innerHTML = '<div class="card"><p class="text-muted">Page not found</p></div>';
        }

        // Update sidebar active state
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.toggle('active', item.dataset.route === hash);
        });
    }

    function init() {
        window.addEventListener('hashchange', handleRoute);
    }

    function start() {
        handleRoute();
    }

    return { register, navigate, init, start };
})();
