/** Watchlist management page. */
const WatchlistPage = (() => {
    let table = null;

    function render(container) {
        container.innerHTML = '';
        const page = document.createElement('div');
        page.className = 'animate-in';
        page.innerHTML = `
            <div class="page-header">
                <h1 class="page-title">Watchlist</h1>
                <p class="page-subtitle">Manage plates of interest for real-time alerting</p>
            </div>
            <div class="card mb-16">
                <div class="form-row">
                    <div class="form-group flex-1">
                        <input type="text" id="wl-plate" placeholder="Enter plate number (e.g. MH01AB1234)">
                    </div>
                    <div class="form-group flex-1">
                        <input type="text" id="wl-notes" placeholder="Notes (optional)">
                    </div>
                    <button class="btn btn-primary btn-sm" id="wl-add" style="margin-top:auto">ADD TO WATCHLIST</button>
                </div>
            </div>
            <div class="card" id="wl-table-wrap"></div>
        `;
        container.appendChild(page);

        table = createDataTable([
            { key: 'plate', label: 'PLATE NUMBER', class: 'plate' },
            { key: 'action', label: 'ACTION', width: '120px', html: (row) =>
                `<button class="btn btn-danger btn-xs" data-remove="${row.plate}">REMOVE</button>` },
        ]);
        page.querySelector('#wl-table-wrap').appendChild(table.element);

        page.querySelector('#wl-add').addEventListener('click', addPlate);
        page.querySelector('#wl-plate').addEventListener('keydown', e => { if (e.key === 'Enter') addPlate(); });
        page.querySelector('#wl-table-wrap').addEventListener('click', async e => {
            const plate = e.target.dataset.remove;
            if (plate) {
                await API.del(`/api/watchlist/${encodeURIComponent(plate)}`);
                refresh();
            }
        });

        refresh();
    }

    async function addPlate() {
        const plateEl = document.getElementById('wl-plate');
        const notesEl = document.getElementById('wl-notes');
        const plate = plateEl.value.trim().toUpperCase();
        if (!plate) return;
        await API.post('/api/watchlist', { plate, notes: notesEl.value });
        plateEl.value = '';
        notesEl.value = '';
        refresh();
    }

    async function refresh() {
        try {
            const res = await API.get('/api/watchlist');
            const plates = (res.plates || []).map(p => ({ plate: p }));
            table.setData(plates);
        } catch (e) { console.error('Watchlist refresh error', e); }
    }

    function teardown() { table = null; }
    return { render, teardown };
})();
