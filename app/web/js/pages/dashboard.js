/** Dashboard page. */
const DashboardPage = (() => {
    let refreshTimer = null;
    let statCards = {};
    let recentTable = null;

    function render(container) {
        container.innerHTML = '';
        const page = document.createElement('div');
        page.className = 'animate-in';
        page.innerHTML = `
            <div class="page-header">
                <h1 class="page-title">Dashboard</h1>
                <p class="page-subtitle">Live surveillance overview and system health</p>
            </div>
            <div class="ticker-bar" id="dash-ticker">
                <span class="ticker-dot"></span>
                <span id="ticker-text">Loading...</span>
            </div>
            <div class="grid-6 mb-24" id="dash-stats"></div>
            <div class="grid-2 gap-20">
                <div class="card">
                    <div class="card-title">LATEST DETECTION</div>
                    <div class="snapshot-preview" id="dash-preview">No recent evidence</div>
                    <div id="dash-meta" style="margin-top:14px"></div>
                </div>
                <div class="card">
                    <div class="card-title">RECENT DETECTIONS</div>
                    <div id="dash-recent" style="max-height:450px;overflow-y:auto"></div>
                </div>
            </div>
        `;
        container.appendChild(page);

        const statsGrid = page.querySelector('#dash-stats');
        const metrics = [
            ['detections', 'DETECTIONS'], ['plates', 'UNIQUE PLATES'],
            ['rate_per_min', 'PLATES / MIN'], ['active_cameras', 'ACTIVE CAMERAS'],
            ['avg_confidence', 'AVG CONFIDENCE'], ['watchlist_hits', 'WATCHLIST HITS'],
        ];
        metrics.forEach(([key, label]) => {
            const card = createStatCard(label, '0', `stat-${key}`);
            statCards[key] = card;
            statsGrid.appendChild(card);
        });

        recentTable = createDataTable([
            { key: 'time', label: 'TIME', width: '80px' },
            { key: 'plate', label: 'PLATE', class: 'plate' },
            { key: 'source', label: 'CAM' },
            { key: 'state', label: 'STATE', html: row => row.watchlist_hit
                ? '<span class="badge badge-danger">WATCHLIST</span>'
                : '<span class="badge badge-success">CLEAR</span>' },
        ]);
        page.querySelector('#dash-recent').appendChild(recentTable.element);

        refresh();
        refreshTimer = setInterval(refresh, 3000);
    }

    async function refresh() {
        try {
            const stats = await API.get('/api/dashboard/stats');
            Object.entries(stats).forEach(([key, val]) => {
                if (statCards[key]) updateStatCard(statCards[key], val);
            });
            document.getElementById('ticker-text').textContent =
                `LIVE | Last detection ${stats.latest} | ${stats.active_cameras} cameras | Trend ${stats.trend_delta}`;

            const recent = await API.get('/api/dashboard/recent');
            const rows = (recent || []).map(r => ({
                ...r,
                time: (r.timestamp || '').split(' ').pop(),
                state: r.watchlist_hit ? 'WATCHLIST' : 'CLEAR',
                _class: r.watchlist_hit ? 'watchlist' : '',
            }));
            recentTable.setData(rows, (row) => {
                const preview = document.getElementById('dash-preview');
                const meta = document.getElementById('dash-meta');
                if (row.snapshot_id) {
                    preview.innerHTML = `<img src="/api/snapshots/${row.snapshot_id}" alt="snapshot">`;
                } else {
                    preview.textContent = 'Snapshot unavailable';
                }
                meta.innerHTML = `
                    <div class="flex-col gap-8" style="font-size:0.8rem">
                        <div><strong>PLATE:</strong> <span class="text-mono">${row.plate}</span></div>
                        <div><strong>CONFIDENCE:</strong> ${row.confidence != null ? (row.confidence * 100).toFixed(0) + '%' : '--'}</div>
                        <div><strong>TIME:</strong> ${row.timestamp}</div>
                        <div><strong>SOURCE:</strong> ${row.source}</div>
                    </div>
                `;
            });
            if (rows.length) recentTable.selectRow(0);
        } catch (e) { console.error('Dashboard refresh error', e); }
    }

    function teardown() {
        clearInterval(refreshTimer);
        statCards = {};
        recentTable = null;
    }

    return { render, teardown };
})();
