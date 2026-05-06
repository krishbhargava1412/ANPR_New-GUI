/** History page — search, grouped results, detail panel. */
const HistoryPage = (() => {
    let groupTable = null;

    function render(container) {
        container.innerHTML = '';
        const page = document.createElement('div');
        page.className = 'animate-in';
        page.innerHTML = `
            <div class="page-header">
                <h1 class="page-title">History</h1>
                <p class="page-subtitle">Investigation workflow grouped by plate</p>
            </div>
            <div class="card mb-16">
                <div class="form-row">
                    <div class="form-group flex-1">
                        <label class="form-label">Plate</label>
                        <input type="text" id="hist-plate" placeholder="Plate text">
                    </div>
                    <div class="form-group flex-1">
                        <label class="form-label">Source</label>
                        <input type="text" id="hist-source" placeholder="Camera / source">
                    </div>
                    <div class="form-group">
                        <label class="form-label">Time Range</label>
                        <select id="hist-time">
                            <option value="">All Time</option>
                            <option value="1h">Last 1 Hour</option>
                            <option value="24h">Last 24 Hours</option>
                            <option value="7d">Last 7 Days</option>
                        </select>
                    </div>
                    <button class="btn btn-primary btn-sm" id="hist-search" style="margin-top:auto">SEARCH</button>
                    <button class="btn btn-secondary btn-sm" id="hist-export" style="margin-top:auto">EXPORT CSV</button>
                </div>
            </div>
            <div class="grid-2 gap-20">
                <div class="card" style="overflow:auto;max-height:600px" id="hist-table-wrap"></div>
                <div class="card">
                    <div class="card-title">DETAIL</div>
                    <div class="snapshot-preview" id="hist-preview">Select a plate</div>
                    <div id="hist-detail" style="margin-top:14px;font-size:0.8rem"></div>
                    <div id="hist-actions" style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap"></div>
                </div>
            </div>
        `;
        container.appendChild(page);

        groupTable = createDataTable([
            { key: 'plate', label: 'PLATE', class: 'plate' },
            { key: 'count', label: 'SEEN' },
            { key: 'first_seen', label: 'FIRST', render: r => (r.first_seen || '').split(' ').pop() },
            { key: 'last_seen', label: 'LAST', render: r => (r.last_seen || '').split(' ').pop() },
            { key: 'avg_confidence', label: 'CONF', render: r => r.avg_confidence != null ? (r.avg_confidence * 100).toFixed(0) + '%' : '--' },
            { key: 'flagged', label: 'FLAG', html: r => r.flagged ? '<span class="badge badge-warning">FLAGGED</span>' : '<span class="badge badge-info">OPEN</span>' },
        ]);
        page.querySelector('#hist-table-wrap').appendChild(groupTable.element);

        page.querySelector('#hist-search').addEventListener('click', refresh);
        page.querySelector('#hist-plate').addEventListener('keydown', e => { if (e.key === 'Enter') refresh(); });
        page.querySelector('#hist-export').addEventListener('click', exportCSV);

        refresh();
    }

    function getTimeRange() {
        const val = document.getElementById('hist-time')?.value;
        const now = new Date();
        if (val === '1h') return { from_date: fmt(new Date(now - 3600000)), to_date: fmt(now) };
        if (val === '24h') return { from_date: fmt(new Date(now - 86400000)), to_date: fmt(now) };
        if (val === '7d') return { from_date: fmt(new Date(now - 604800000)), to_date: fmt(now) };
        return {};
    }

    function fmt(d) { return d.toISOString().split('T')[0]; }

    async function refresh() {
        try {
            const plate = document.getElementById('hist-plate')?.value || '';
            const source = document.getElementById('hist-source')?.value || '';
            const time = getTimeRange();
            const params = new URLSearchParams({ plate, source, ...time });
            const res = await API.get(`/api/history?${params}`);
            const groups = res.groups || [];
            groupTable.setData(groups.map(g => ({ ...g, _class: g.watchlist_hit ? 'watchlist' : '' })), (row) => showDetail(row));
            if (groups.length) groupTable.selectRow(0);
        } catch (e) { console.error('History refresh error', e); }
    }

    function showDetail(group) {
        const preview = document.getElementById('hist-preview');
        const detail = document.getElementById('hist-detail');
        const actions = document.getElementById('hist-actions');
        const lastMatch = group.matches?.[group.matches.length - 1];
        if (lastMatch?.snapshot_id) {
            preview.innerHTML = `<img src="/api/snapshots/${lastMatch.snapshot_id}" alt="snapshot">`;
        } else {
            preview.textContent = 'Snapshot unavailable';
        }
        detail.innerHTML = `
            <div><strong>Plate:</strong> <span class="text-mono">${group.plate}</span></div>
            <div><strong>Sightings:</strong> ${group.count}</div>
            <div><strong>First seen:</strong> ${group.first_seen}</div>
            <div><strong>Last seen:</strong> ${group.last_seen}</div>
            <div><strong>Avg confidence:</strong> ${group.avg_confidence != null ? (group.avg_confidence * 100).toFixed(0) + '%' : '--'}</div>
            <div><strong>Sources:</strong> ${(group.sources || []).join(', ')}</div>
            <div><strong>Watchlist:</strong> ${group.watchlist_hit ? 'Yes' : 'No'}</div>
        `;
        actions.innerHTML = '';
        const flagBtn = document.createElement('button');
        flagBtn.className = 'btn btn-secondary btn-sm';
        flagBtn.textContent = group.flagged ? 'UNFLAG' : 'FLAG PLATE';
        flagBtn.addEventListener('click', async () => {
            await API.post('/api/history/flag', { plate: group.plate, flagged: !group.flagged, note: '' });
            refresh();
        });
        actions.appendChild(flagBtn);
    }

    async function exportCSV() {
        try {
            const res = await API.post('/api/history/export');
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url; a.download = 'history_export.csv'; a.click();
            URL.revokeObjectURL(url);
        } catch (e) { console.error('Export error', e); }
    }

    function teardown() { groupTable = null; }
    return { render, teardown };
})();
