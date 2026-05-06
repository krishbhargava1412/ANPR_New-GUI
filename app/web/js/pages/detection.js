/** Detection page — JS-driven camera capture + live detection via WebSocket. */
const DetectionPage = (() => {
    let logEntries = [];
    let detectionListener = null;
    let telemetryListener = null;
    let statusListener = null;
    let frameListener = null;

    // Camera capture state
    let localStream = null;
    let captureCanvas = null;
    let captureCtx = null;
    let captureInterval = null;
    let currentCameraId = 0;
    let isDetecting = false;
    let isPaused = false;

    // FPS config — send every N ms
    const FRAME_INTERVAL_MS = 100; // ~10 fps to backend

    function render(container) {
        container.innerHTML = '';
        const page = document.createElement('div');
        page.className = 'animate-in';
        page.innerHTML = `
            <div class="page-header">
                <h1 class="page-title">Live Detection</h1>
                <p class="page-subtitle">Browser camera feed — frames are processed on the GPU backend</p>
            </div>
            <div class="flex-row mb-16" style="flex-wrap:wrap;gap:12px;align-items:center">
                <div id="local-cam-controls" style="display:none;align-items:center;gap:8px">
                    <select id="det-camera-select" style="width:180px"></select>
                    <label style="font-size:0.75rem;cursor:pointer;display:flex;align-items:center;gap:4px">
                        <input type="checkbox" id="det-share-toggle" checked> Share Feed
                    </label>
                    <button id="det-start" class="btn btn-success btn-sm">▶ START EMITTING</button>
                    <button id="det-stop"  class="btn btn-danger btn-sm" disabled>■ STOP</button>
                </div>
                
                <button id="det-activate-local" class="btn btn-secondary btn-sm">📷 ACTIVATE MY CAMERA</button>

                <div style="height:20px;width:1px;background:#444;margin:0 10px"></div>

                <div style="display:flex;align-items:center;gap:8px">
                    <input type="number" id="det-join-id" value="0" style="width:50px;padding:4px;border-radius:4px;background:#222;color:#fff;border:1px solid #444" title="Camera ID">
                    <button id="det-join"  class="btn btn-ghost btn-sm" style="border:1px solid #444">👁 JOIN FEED</button>
                    <button id="det-leave" class="btn btn-ghost btn-sm" style="border:1px solid #444;display:none">🚪 LEAVE</button>
                </div>

                <button id="det-pause" class="btn btn-secondary btn-sm" disabled>⏸ PAUSE AI</button>
                <span id="det-status" class="text-muted" style="font-size:0.78rem;margin-left:auto"></span>
            </div>

            <div class="grid-2 gap-20">
                <!-- Live feed -->
                <div style="position:relative">
                    <video id="det-video" autoplay muted playsinline
                           style="width:100%;border-radius:8px;background:#000;display:none"></video>
                    <!-- Using <img> for the feed is much more reliable on mobile/Android -->
                    <img id="det-preview-img" 
                         style="width:100%;border-radius:8px;background:#111;display:block;min-height:240px">
                    <div id="det-overlay" style="
                        position:absolute;top:8px;left:8px;
                        background:rgba(0,0,0,.55);color:#0f9;
                        font-size:0.72rem;padding:4px 8px;border-radius:4px;
                        font-family:monospace;pointer-events:none">
                        <span id="det-feed-status">No feed</span>
                        &nbsp;|&nbsp;<span id="det-feed-fps"></span>
                    </div>
                    <!-- Bounding-box overlay canvas (transparent) -->
                    <canvas id="det-bbox-canvas" style="
                        position:absolute;top:0;left:0;width:100%;height:100%;
                        border-radius:8px;pointer-events:none"></canvas>
                </div>

                <!-- Detection log -->
                <div class="log-panel">
                    <div class="log-header">
                        <span class="log-header-title">LIVE DETECTION STREAM</span>
                        <span class="log-count" id="det-log-count">0</span>
                        <span style="flex:1"></span>
                        <button class="btn btn-ghost btn-xs" id="det-clear-log">CLEAR</button>
                    </div>
                    <div class="log-list" id="det-log-list"></div>
                </div>
            </div>
        `;
        container.appendChild(page);

        // ── Elements ──────────────────────────────────────────────────────
        const video        = page.querySelector('#det-video');
        const previewImg   = page.querySelector('#det-preview-img');
        const bboxCanvas   = page.querySelector('#det-bbox-canvas');
        const bboxCtx      = bboxCanvas.getContext('2d');

        captureCanvas = document.createElement('canvas');
        captureCanvas.width  = 640;
        captureCanvas.height = 480;
        captureCtx = captureCanvas.getContext('2d');

        // ── Controls ──────────────────────────────────────────────────────
        page.querySelector('#det-activate-local').addEventListener('click', async () => {
            await enumerateCameras();
            document.getElementById('local-cam-controls').style.display = 'flex';
            document.getElementById('det-activate-local').style.display = 'none';
        });

        page.querySelector('#det-start').addEventListener('click', async () => {
            if (isDetecting) return;
            const select = document.getElementById('det-camera-select');
            const deviceId = select.value;
            if (!deviceId) { setStatus('Select a camera first'); return; }

            currentCameraId = parseInt(select.selectedIndex) || 0;
            const label = select.options[select.selectedIndex]?.text || `CAM ${currentCameraId}`;
            const share = document.getElementById('det-share-toggle').checked;

            try {
                await startCapture(deviceId, video, previewImg, bboxCanvas, bboxCtx, label, share);
            } catch (e) {
                setStatus(`Camera error: ${e.message}`);
            }
        });

        page.querySelector('#det-stop').addEventListener('click', () => {
            stopCapture();
        });

        page.querySelector('#det-pause').addEventListener('click', () => {
            if (!isDetecting) return;
            isPaused = !isPaused;
            WS.send({ type: 'pause_detection', camera_id: currentCameraId });
            page.querySelector('#det-pause').textContent = isPaused ? '▶ RESUME' : '⏸ PAUSE';
            setStatus(isPaused ? 'Paused' : 'Running');
        });

        page.querySelector('#det-clear-log').addEventListener('click', () => {
            logEntries = [];
            page.querySelector('#det-log-list').innerHTML = '';
            page.querySelector('#det-log-count').textContent = '0';
        });

        // ── WebSocket listeners ───────────────────────────────────────────
        detectionListener = (data) => {
            addLogEntry(data);
            // Draw bbox on overlay
            if (data.bbox) drawBbox(bboxCtx, bboxCanvas, data.bbox, data.plate, data.confidence);
        };
        telemetryListener = (data) => {
            const fps = data.fps || (data.latency_ms ? (1000 / data.latency_ms).toFixed(1) : '');
            document.getElementById('det-feed-fps').textContent = fps ? `${fps} FPS` : '';
            setStatus(`${data.box_count || 0} plate(s) | ${(data.latency_ms || 0).toFixed(0)} ms`);
        };
        statusListener = (data) => {
            setStatus(data.message || '');
        };

        // Listener for incoming shared frames from OTHER users
        frameListener = ({ cameraId, blob }) => {
            if (cameraId !== currentCameraId) return;
            
            // If we are NOT the source (emitting), draw the incoming shared frame
            if (!isDetecting) {
                const url = URL.createObjectURL(blob);
                const oldUrl = previewImg.src;
                
                previewImg.onload = () => {
                    if (oldUrl && oldUrl.startsWith('blob:')) URL.revokeObjectURL(oldUrl);
                    document.getElementById('det-feed-status').textContent = 'Viewing Shared Feed';
                    
                    // Sync bbox canvas size
                    if (bboxCanvas.width !== previewImg.naturalWidth) {
                        bboxCanvas.width = previewImg.naturalWidth;
                        bboxCanvas.height = previewImg.naturalHeight;
                    }
                };
                previewImg.src = url;
            }
        };

        WS.on('detection', detectionListener);
        WS.on('telemetry',  telemetryListener);
        WS.on('status',     statusListener);
        WS.on('frame',      frameListener);
        
        // Join/Leave logic
        page.querySelector('#det-join').addEventListener('click', () => {
            const idInput = document.getElementById('det-join-id');
            currentCameraId = parseInt(idInput.value) || 0;
            console.log(`[Detection] Joining Feed for Camera ID: ${currentCameraId}`);
            WS.send({ type: 'subscribe_camera', camera_id: currentCameraId });
            page.querySelector('#det-join').style.display = 'none';
            page.querySelector('#det-leave').style.display = 'inline-block';
            setStatus(`Joined Camera ${currentCameraId}`);
        });

        page.querySelector('#det-leave').addEventListener('click', () => {
            WS.send({ type: 'unsubscribe_camera', camera_id: currentCameraId });
            page.querySelector('#det-join').style.display = 'inline-block';
            page.querySelector('#det-leave').style.display = 'none';
            previewImg.src = '';
            bboxCtx.clearRect(0, 0, bboxCanvas.width, bboxCanvas.height);
            document.getElementById('det-feed-status').textContent = 'No feed';
            setStatus('Left feed');
        });
    }

    // ── Camera enumeration ─────────────────────────────────────────────────
    async function enumerateCameras() {
        const select = document.getElementById('det-camera-select');
        try {
            // Request brief permission so labels are available
            const tmp = await navigator.mediaDevices.getUserMedia({ video: true });
            tmp.getTracks().forEach(t => t.stop());

            const devices = await navigator.mediaDevices.enumerateDevices();
            const cams = devices.filter(d => d.kind === 'videoinput');
            select.innerHTML = '<option value="">Select Camera</option>';
            cams.forEach((cam, i) => {
                const opt = document.createElement('option');
                opt.value = cam.deviceId;
                opt.textContent = cam.label || `Camera ${i}`;
                select.appendChild(opt);
            });
            if (cams.length) select.value = cams[0].deviceId;
        } catch (e) {
            select.innerHTML = '<option value="">Camera permission denied</option>';
            console.warn('Camera enumeration failed:', e);
        }
    }

    // ── Capture + streaming ────────────────────────────────────────────────
    async function startCapture(deviceId, video, previewImg, bboxCanvas, bboxCtx, label, share) {
        localStream = await navigator.mediaDevices.getUserMedia({
            video: { deviceId: { exact: deviceId }, width: 640, height: 480 }
        });
        video.srcObject = localStream;
        video.style.display = 'block'; // Show local video
        previewImg.style.display = 'none'; // Hide the img preview for local source
        await video.play();

        isDetecting = true;
        isPaused = false;

        document.getElementById('det-start').disabled = true;
        document.getElementById('det-stop').disabled  = false;
        document.getElementById('det-pause').disabled = false;
        document.getElementById('det-feed-status').textContent = 'Live';

        // Tell backend to start pipeline
        WS.send({ type: 'start_detection', camera_id: currentCameraId, label, share });

        let framesSent = 0;
        let lastFpsTime = performance.now();

        captureInterval = setInterval(() => {
            if (!isDetecting || isPaused) return;
            if (video.readyState < 2) return;

            // Draw to hidden capture canvas
            captureCanvas.width  = video.videoWidth  || 640;
            captureCanvas.height = video.videoHeight || 480;
            captureCtx.drawImage(video, 0, 0);

            // Sync bbox canvas size to local video
            if (bboxCanvas.width !== video.videoWidth) {
                bboxCanvas.width = video.videoWidth;
                bboxCanvas.height = video.videoHeight;
            }

            // Encode to JPEG blob and send via WebSocket
            captureCanvas.toBlob(blob => {
                if (!blob) return;
                blob.arrayBuffer().then(buf => {
                    // Prepend 4-byte big-endian camera_id header
                    const header = new ArrayBuffer(4);
                    new DataView(header).setUint32(0, currentCameraId, false);
                    const combined = new Uint8Array(header.byteLength + buf.byteLength);
                    combined.set(new Uint8Array(header), 0);
                    combined.set(new Uint8Array(buf), 4);
                    
                    WS.sendBinary(combined.buffer);
                    console.log(`[Camera] Frame emitted: CamID=${currentCameraId}, Size=${(combined.byteLength / 1024).toFixed(1)} KB`);
                });
            }, 'image/jpeg', 0.75);

            // Local FPS counter
            framesSent++;
            const now = performance.now();
            if (now - lastFpsTime >= 1000) {
                console.log(`[Camera] Sending ${framesSent} fps to backend`);
                framesSent = 0;
                lastFpsTime = now;
            }
        }, FRAME_INTERVAL_MS);
    }

    function stopCapture() {
        clearInterval(captureInterval);
        captureInterval = null;

        if (localStream) {
            localStream.getTracks().forEach(t => t.stop());
            localStream = null;
        }

        WS.send({ type: 'stop_detection', camera_id: currentCameraId });

        isDetecting = false;
        isPaused = false;

        document.getElementById('det-start').disabled  = false;
        document.getElementById('det-stop').disabled   = true;
        document.getElementById('det-pause').disabled  = true;
        
        const video = document.getElementById('det-video');
        const img = document.getElementById('det-preview-img');
        if (video) video.style.display = 'none';
        if (img) img.style.display = 'block';

        document.getElementById('det-feed-status').textContent = 'Stopped';
        document.getElementById('det-feed-fps').textContent    = '';
        setStatus('Detection stopped');
    }

    // ── Bounding box overlay ───────────────────────────────────────────────
    let bboxClearTimer = null;
    function drawBbox(ctx, canvas, bbox, plate, conf) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        clearTimeout(bboxClearTimer);

        const [x1, y1, x2, y2] = bbox;
        const scaleX = canvas.offsetWidth  / (captureCanvas.width  || 640);
        const scaleY = canvas.offsetHeight / (captureCanvas.height || 480);

        ctx.save();
        ctx.strokeStyle = '#0f9';
        ctx.lineWidth   = 2;
        ctx.strokeRect(x1 * scaleX, y1 * scaleY, (x2 - x1) * scaleX, (y2 - y1) * scaleY);

        ctx.fillStyle = 'rgba(0,255,153,0.15)';
        ctx.fillRect(x1 * scaleX, y1 * scaleY, (x2 - x1) * scaleX, (y2 - y1) * scaleY);

        const label = `${plate}  ${conf ? (conf * 100).toFixed(0) + '%' : ''}`;
        ctx.font = 'bold 13px monospace';
        ctx.fillStyle = '#0f9';
        ctx.fillText(label, x1 * scaleX + 4, y1 * scaleY - 6);
        ctx.restore();

        bboxClearTimer = setTimeout(() => ctx.clearRect(0, 0, canvas.width, canvas.height), 1500);
    }

    // ── Helpers ────────────────────────────────────────────────────────────
    function setStatus(msg) {
        const el = document.getElementById('det-status');
        if (el) el.textContent = msg;
    }

    function addLogEntry(data) {
        logEntries.unshift(data);
        if (logEntries.length > 200) logEntries.pop();

        const list = document.getElementById('det-log-list');
        if (!list) return;
        const entry = document.createElement('div');
        entry.className = `log-entry ${data.watchlist_hit ? 'alert' : ''}`;
        const time = new Date(data.timestamp * 1000).toLocaleTimeString();
        entry.innerHTML = `
            <span class="log-time">${time}</span>
            <span class="log-cam">${data.source || 'CAM ' + data.camera_id}</span>
            <span class="log-plate">${data.plate}</span>
            <span class="log-conf">${data.confidence ? (data.confidence * 100).toFixed(0) + '%' : '--'}</span>
        `;
        list.prepend(entry);
        document.getElementById('det-log-count').textContent = logEntries.length;
    }

    function teardown() {
        stopCapture();
        if (detectionListener) WS.off('detection', detectionListener);
        if (telemetryListener) WS.off('telemetry',  telemetryListener);
        if (statusListener)    WS.off('status',      statusListener);
        if (frameListener)     WS.off('frame',       frameListener);
        logEntries = [];
    }

    return { render, teardown };
})();
