/** Settings page. */
const SettingsPage = (() => {
    function render(container) {
        container.innerHTML = `<div class="animate-in">
            <div class="page-header"><h1 class="page-title">Settings</h1>
            <p class="page-subtitle">Detection, camera, and interface configuration</p></div>
            <div class="grid-2 gap-20">
                <div class="card"><div class="card-title">DETECTION</div><div class="flex-col">
                    <div class="form-group"><label class="form-label">Confidence Threshold</label>
                    <input type="number" id="set-conf" min="0" max="1" step="0.05" value="0.5"></div>
                    <div class="form-group"><label class="form-label">Frame Skip</label>
                    <input type="number" id="set-skip" min="1" max="30" value="5"></div>
                    <div class="form-group"><label class="form-label">Model</label><select id="set-model"></select></div>
                    <label class="flex-row gap-8" style="font-size:0.85rem"><input type="checkbox" id="set-snap" checked> Save Snapshots</label>
                    <label class="flex-row gap-8" style="font-size:0.85rem"><input type="checkbox" id="set-proxy" checked> Proxy Resolution</label>
                </div></div>
                <div class="card"><div class="card-title">CAMERAS</div><div class="flex-col">
                    <div class="form-group"><label class="form-label">Local Indices</label>
                    <input type="text" id="set-cam" placeholder="0, 1, 2"></div>
                    <div class="form-group"><label class="form-label">IP/RTSP URLs</label>
                    <textarea id="set-ip" rows="4" placeholder="rtsp://..."></textarea></div>
                    <button class="btn btn-secondary btn-sm" id="set-scan">SCAN</button>
                    <span id="set-scan-r" class="text-muted" style="font-size:0.78rem"></span>
                </div></div>
            </div>
            <div class="flex-row mt-8" style="justify-content:flex-end">
            <button class="btn btn-primary" id="set-save">SAVE SETTINGS</button></div></div>`;
        document.getElementById('set-save').onclick = save;
        document.getElementById('set-scan').onclick = scan;
        load(); loadModels();
    }
    async function load() {
        try { const s = await API.get('/api/settings');
            document.getElementById('set-conf').value = s.confidence_threshold ?? 0.5;
            document.getElementById('set-skip').value = s.frame_skip ?? 5;
            document.getElementById('set-cam').value = s.camera_indices ?? '';
            document.getElementById('set-ip').value = s.ip_camera_urls ?? '';
            document.getElementById('set-snap').checked = s.save_snapshots !== false;
            document.getElementById('set-proxy').checked = s.proxy_resolution_enabled !== false;
        } catch(e){}
    }
    async function loadModels() {
        try { const r = await API.get('/api/settings/models'); const s = document.getElementById('set-model');
            (r.models||[]).forEach(m => { const o = document.createElement('option'); o.value=m; o.textContent=m; s.appendChild(o); });
        } catch(e){}
    }
    async function save() {
        try { await API.put('/api/settings', {
            confidence_threshold: parseFloat(document.getElementById('set-conf').value),
            frame_skip: parseInt(document.getElementById('set-skip').value),
            camera_indices: document.getElementById('set-cam').value,
            ip_camera_urls: document.getElementById('set-ip').value,
            save_snapshots: document.getElementById('set-snap').checked,
            proxy_resolution_enabled: document.getElementById('set-proxy').checked,
            model_name: document.getElementById('set-model').value,
        }); alert('Settings saved'); } catch(e) { alert('Failed: '+e.message); }
    }
    async function scan() { const r = document.getElementById('set-scan-r'); r.textContent='Scanning...';
        try { const res = await API.post('/api/cameras/scan');
            r.textContent = res.available.length ? 'Found: '+res.available.join(', ') : 'None found';
        } catch(e) { r.textContent='Failed'; }
    }
    function teardown(){}
    return { render, teardown };
})();
