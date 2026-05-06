/** About page — system info. */
const AboutPage = (() => {
    function render(container) {
        container.innerHTML = `<div class="animate-in">
            <div class="page-header"><h1 class="page-title">About</h1>
            <p class="page-subtitle">System information and dependency status</p></div>
            <div class="card" id="about-info"><p class="text-muted">Loading...</p></div></div>`;
        load();
    }
    async function load() {
        try { const info = await API.get('/api/about');
            const el = document.getElementById('about-info');
            el.innerHTML = Object.entries(info).map(([k,v]) =>
                `<div class="flex-row" style="padding:8px 0;border-bottom:1px solid var(--border-subtle)">
                    <span class="text-muted" style="width:180px;font-size:0.78rem;text-transform:uppercase">${k.replace(/_/g,' ')}</span>
                    <span class="text-mono" style="font-size:0.82rem">${v}</span></div>`
            ).join('');
        } catch(e) { document.getElementById('about-info').innerHTML = '<p class="text-danger">Failed to load</p>'; }
    }
    function teardown(){}
    return { render, teardown };
})();
