/** Detection page with auto-started local camera, explicit detection toggle, and live share sessions. */
const DetectionPage = (() => {
    let logEntries = [];
    let detectionListener = null;
    let telemetryListener = null;
    let statusListener = null;
    let shareStartedListener = null;
    let shareStoppedListener = null;
    let sharedFrameListener = null;

    let localStream = null;
    let captureCanvas = null;
    let captureCtx = null;
    let previewCanvas = null;
    let previewCtx = null;
    let bboxCanvas = null;
    let bboxCtx = null;
    let localVideo = null;

    let emitInterval = null;
    let previewAnimationId = null;
    let sessionPollTimer = null;
    let remoteImageUrl = null;

    let currentCameraId = Math.floor(Date.now() % 2147483647);
    let currentLabel = 'Local Camera';
    let isDetecting = false;
    let isPaused = false;
    let isSharing = false;
    let activeShareSession = null;
    let joinedShareEvent = null;
    let emittedFramesCount = 0;
    let lastEmitLogTs = 0;

    const FRAME_INTERVAL_MS = 100;

    function render(container) {
        container.innerHTML = '';
        const page = document.createElement('div');
        page.className = 'animate-in';
        page.innerHTML = `
            <div class="page-header">
                <h1 class="page-title">Live Detection</h1>
                <p class="page-subtitle">Camera starts automatically. Detection and live sharing are controlled separately.</p>
            </div>

            <div class="flex-row mb-16" style="flex-wrap:wrap;gap:12px;align-items:center">
                <select id="det-camera-select" style="width:240px"></select>
                <button id="det-detect-toggle" class="btn btn-success btn-sm">START DETECTION</button>
                <button id="det-share-toggle" class="btn btn-secondary btn-sm">SHARE LIVE FEED</button>
                <button id="det-pause" class="btn btn-secondary btn-sm" disabled>PAUSE AI</button>
                <span id="det-status" class="text-muted" style="font-size:0.78rem;margin-left:auto"></span>
            </div>

            <div class="grid-2 gap-20">
                <div style="position:relative">
                    <canvas id="det-feed-canvas" style="width:100%;border-radius:8px;background:#000;display:block;min-height:240px"></canvas>
                    <canvas id="det-bbox-canvas" style="position:absolute;top:0;left:0;width:100%;height:100%;border-radius:8px;pointer-events:none"></canvas>
                    <div id="det-overlay" style="position:absolute;top:8px;left:8px;background:rgba(0,0,0,.55);color:#0f9;font-size:0.72rem;padding:4px 8px;border-radius:4px;font-family:monospace;pointer-events:none">
                        <span id="det-feed-status">Starting camera...</span>
                        &nbsp;|&nbsp;<span id="det-feed-fps"></span>
                    </div>
                    <video id="det-video" autoplay muted playsinline style="display:none"></video>
                </div>

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

            <div class="card mt-20">
                <div class="flex-row" style="justify-content:space-between;align-items:center;margin-bottom:12px">
                    <div>
                        <div class="section-title">Active Sharing Sessions</div>
                        <div class="text-muted" style="font-size:0.8rem">Join a live shared feed by socket event.</div>
                    </div>
                    <button id="det-refresh-sessions" class="btn btn-ghost btn-sm">REFRESH</button>
                </div>
                <div id="det-session-list" class="table-wrap"></div>
            </div>
        `;
        container.appendChild(page);

        localVideo = page.querySelector('#det-video');
        previewCanvas = page.querySelector('#det-feed-canvas');
        previewCtx = previewCanvas.getContext('2d');
        bboxCanvas = page.querySelector('#det-bbox-canvas');
        bboxCtx = bboxCanvas.getContext('2d');

        captureCanvas = document.createElement('canvas');
        captureCanvas.width = 640;
        captureCanvas.height = 480;
        captureCtx = captureCanvas.getContext('2d');

        page.querySelector('#det-camera-select').addEventListener('change', onCameraChange);
        page.querySelector('#det-detect-toggle').addEventListener('click', toggleDetection);
        page.querySelector('#det-share-toggle').addEventListener('click', toggleShare);
        page.querySelector('#det-pause').addEventListener('click', togglePause);
        page.querySelector('#det-clear-log').addEventListener('click', clearLog);
        page.querySelector('#det-refresh-sessions').addEventListener('click', refreshShareSessions);

        bindWebSocketListeners();
        initializeCamera();
        refreshShareSessions();
        sessionPollTimer = setInterval(refreshShareSessions, 5000);
    }

    async function initializeCamera() {
        await populateCameraList();
        const select = document.getElementById('det-camera-select');
        if (!select?.value) {
            setStatus('No camera available');
            document.getElementById('det-feed-status').textContent = 'No local camera';
            return;
        }
        select.dataset.lastValue = select.value;
        await startLocalPreview(select.value, getSelectedCameraLabel());
    }

    async function populateCameraList() {
        const select = document.getElementById('det-camera-select');
        if (!select) return;
        try {
            const warmup = await navigator.mediaDevices.getUserMedia({ video: true });
            warmup.getTracks().forEach((track) => track.stop());
            const devices = await navigator.mediaDevices.enumerateDevices();
            const cameras = devices.filter((device) => device.kind === 'videoinput');
            select.innerHTML = '';
            cameras.forEach((camera, index) => {
                const opt = document.createElement('option');
                opt.value = camera.deviceId;
                opt.textContent = camera.label || `Camera ${index + 1}`;
                select.appendChild(opt);
            });
        } catch (e) {
            select.innerHTML = '<option value="">Camera permission denied</option>';
        }
    }

    async function startLocalPreview(deviceId, label) {
        stopLocalStream();
        currentLabel = label;
        const select = document.getElementById('det-camera-select');
        if (select) {
            select.value = deviceId;
            select.dataset.lastValue = deviceId;
        }
        localStream = await navigator.mediaDevices.getUserMedia({
            video: { deviceId: { exact: deviceId }, width: 640, height: 480 },
        });
        localVideo.srcObject = localStream;
        await localVideo.play();
        document.getElementById('det-feed-status').textContent = 'Local Camera Live';
        setStatus(`Camera ready: ${label}`);
        drawLocalPreview();
        updateButtons();
    }

    function drawLocalPreview() {
        cancelAnimationFrame(previewAnimationId);
        const loop = () => {
            if (joinedShareEvent) {
                previewAnimationId = requestAnimationFrame(loop);
                return;
            }
            if (!localVideo || localVideo.readyState < 2) {
                previewAnimationId = requestAnimationFrame(loop);
                return;
            }
            const width = localVideo.videoWidth || 640;
            const height = localVideo.videoHeight || 480;
            syncCanvasSize(width, height);
            previewCtx.drawImage(localVideo, 0, 0, width, height);
            previewAnimationId = requestAnimationFrame(loop);
        };
        previewAnimationId = requestAnimationFrame(loop);
    }

    async function onCameraChange(event) {
        const deviceId = event.target.value;
        if (!deviceId) return;
        if (isDetecting || isSharing) {
            setStatus('Stop detection and sharing before switching camera');
            event.target.value = event.target.dataset.lastValue || event.target.value;
            return;
        }
        event.target.dataset.lastValue = deviceId;
        await startLocalPreview(deviceId, getSelectedCameraLabel());
    }

    function toggleDetection() {
        if (!localStream) {
            setStatus('Local camera is not ready');
            return;
        }
        if (!isDetecting) {
            isDetecting = true;
            isPaused = false;
            console.log('[Detection][CONTROL] start_detection', {
                cameraId: currentCameraId,
                label: currentLabel,
            });
            WS.send({ type: 'start_detection', camera_id: currentCameraId, label: currentLabel });
            ensureEmitLoop();
            document.getElementById('det-feed-status').textContent = isSharing ? 'Live + Shared + Detecting' : 'Detecting';
            setStatus('Detection started');
        } else {
            console.log('[Detection][CONTROL] stop_detection', {
                cameraId: currentCameraId,
            });
            WS.send({ type: 'stop_detection', camera_id: currentCameraId });
            isDetecting = false;
            isPaused = false;
            clearOverlay();
            maybeStopEmitLoop();
            document.getElementById('det-feed-status').textContent = isSharing ? 'Local Camera Shared' : 'Local Camera Live';
            setStatus('Detection stopped');
        }
        updateButtons();
    }

    function togglePause() {
        if (!isDetecting) return;
        isPaused = !isPaused;
        console.log('[Detection][CONTROL] pause_detection', {
            cameraId: currentCameraId,
            paused: isPaused,
        });
        WS.send({ type: 'pause_detection', camera_id: currentCameraId });
        setStatus(isPaused ? 'Detection paused' : 'Detection resumed');
        updateButtons();
    }

    function toggleShare() {
        if (!localStream) {
            setStatus('Local camera is not ready');
            return;
        }
        if (!isSharing) {
            console.log('[Detection][CONTROL] start_share', {
                cameraId: currentCameraId,
                label: currentLabel,
            });
            WS.send({ type: 'start_share', camera_id: currentCameraId, label: currentLabel });
        } else {
            console.log('[Detection][CONTROL] stop_share', {
                cameraId: currentCameraId,
                socketEvent: activeShareSession?.socket_event || '',
            });
            WS.send({
                type: 'stop_share',
                camera_id: currentCameraId,
                socket_event: activeShareSession?.socket_event || '',
            });
        }
    }

    function ensureEmitLoop() {
        if (emitInterval) return;
        console.log('[Detection][EMIT] loop started', {
            cameraId: currentCameraId,
            detect: isDetecting,
            share: isSharing,
        });
        emitInterval = setInterval(() => {
            if (!localVideo || localVideo.readyState < 2) return;
            if (!isDetecting && !isSharing) return;
            if (isDetecting && isPaused) return;

            const width = localVideo.videoWidth || 640;
            const height = localVideo.videoHeight || 480;
            captureCanvas.width = width;
            captureCanvas.height = height;
            captureCtx.drawImage(localVideo, 0, 0, width, height);

            captureCanvas.toBlob((blob) => {
                if (!blob) return;
                blob.arrayBuffer().then((buf) => {
                    const header = new ArrayBuffer(4);
                    new DataView(header).setUint32(0, currentCameraId, false);
                    const combined = new Uint8Array(header.byteLength + buf.byteLength);
                    combined.set(new Uint8Array(header), 0);
                    combined.set(new Uint8Array(buf), 4);
                    emittedFramesCount += 1;
                    const emitMode = isDetecting && isSharing
                        ? `detection+share:${activeShareSession?.socket_event || 'pending'}`
                        : isDetecting
                            ? 'detection'
                            : `share:${activeShareSession?.socket_event || 'pending'}`;
                    const now = Date.now();
                    if (emittedFramesCount <= 5 || now - lastEmitLogTs >= 1000) {
                        console.log('[Detection][EMIT][FRAME]', {
                            frame: emittedFramesCount,
                            cameraId: currentCameraId,
                            bytes: combined.byteLength,
                            mode: emitMode,
                            paused: isPaused,
                        });
                        lastEmitLogTs = now;
                    }
                    WS.sendBinary(combined.buffer);
                });
            }, 'image/jpeg', 0.75);
        }, FRAME_INTERVAL_MS);
    }

    function maybeStopEmitLoop() {
        if (isDetecting || isSharing) return;
        console.log('[Detection][EMIT] loop stopped', {
            cameraId: currentCameraId,
            framesSent: emittedFramesCount,
        });
        clearInterval(emitInterval);
        emitInterval = null;
        emittedFramesCount = 0;
        lastEmitLogTs = 0;
    }

    function bindWebSocketListeners() {
        detectionListener = (data) => {
            if (data.camera_id !== currentCameraId) return;
            addLogEntry(data);
            if (data.bbox) drawBbox(data.bbox, data.plate, data.confidence);
        };
        telemetryListener = (data) => {
            if (data.camera_id !== currentCameraId) return;
            const fps = data.fps || (data.latency_ms ? (1000 / data.latency_ms).toFixed(1) : '');
            document.getElementById('det-feed-fps').textContent = fps ? `${fps} FPS` : '';
            setStatus(`${data.box_count || 0} plate(s) | ${(data.latency_ms || 0).toFixed(0)} ms`);
        };
        statusListener = (data) => {
            if (data.camera_id !== currentCameraId) return;
            setStatus(data.message || '');
        };
        shareStartedListener = (data) => {
            activeShareSession = data.session;
            isSharing = true;
            ensureEmitLoop();
            document.getElementById('det-feed-status').textContent = isDetecting ? 'Live + Shared + Detecting' : 'Local Camera Shared';
            setStatus(`Sharing on ${data.session.socket_event}`);
            updateButtons();
            refreshShareSessions();
        };
        shareStoppedListener = (data) => {
            if (data.camera_id !== currentCameraId) return;
            isSharing = false;
            activeShareSession = null;
            maybeStopEmitLoop();
            document.getElementById('det-feed-status').textContent = isDetecting ? 'Detecting' : 'Local Camera Live';
            setStatus('Live feed sharing stopped');
            updateButtons();
            refreshShareSessions();
        };
        sharedFrameListener = ({ socketEvent, blob }) => {
            if (socketEvent !== joinedShareEvent) return;
            if (remoteImageUrl) URL.revokeObjectURL(remoteImageUrl);
            remoteImageUrl = URL.createObjectURL(blob);
            const image = new Image();
            image.onload = () => {
                syncCanvasSize(image.width, image.height);
                previewCtx.drawImage(image, 0, 0, previewCanvas.width, previewCanvas.height);
                document.getElementById('det-feed-status').textContent = `Viewing Shared Feed: ${socketEvent}`;
                URL.revokeObjectURL(remoteImageUrl);
                remoteImageUrl = null;
            };
            image.src = remoteImageUrl;
        };

        WS.on('detection', detectionListener);
        WS.on('telemetry', telemetryListener);
        WS.on('status', statusListener);
        WS.on('share_started', shareStartedListener);
        WS.on('share_stopped', shareStoppedListener);
        WS.on('shared_frame', sharedFrameListener);
    }

    async function refreshShareSessions() {
        const list = document.getElementById('det-session-list');
        if (!list) return;
        try {
            const res = await API.get('/api/detection/share-sessions');
            const sessions = res.sessions || [];
            if (!sessions.length) {
                list.innerHTML = '<div class="text-muted" style="padding:12px 0">No active sharing sessions.</div>';
                return;
            }
            list.innerHTML = sessions.map((session) => `
                <div class="flex-row" style="justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.06)">
                    <div>
                        <div style="font-weight:600">${escapeHtml(session.label)}</div>
                        <div class="text-muted" style="font-size:0.78rem">${escapeHtml(session.owner_username)} | ${escapeHtml(session.socket_event)}</div>
                    </div>
                    <button class="btn btn-ghost btn-sm det-join-session" data-socket-event="${escapeHtml(session.socket_event)}">
                        ${joinedShareEvent === session.socket_event ? 'LEAVE' : 'JOIN'}
                    </button>
                </div>
            `).join('');
            list.querySelectorAll('.det-join-session').forEach((button) => {
                button.addEventListener('click', () => {
                    const socketEvent = button.dataset.socketEvent;
                    if (joinedShareEvent === socketEvent) {
                        leaveSharedFeed();
                    } else {
                        joinSharedFeed(socketEvent);
                    }
                });
            });
        } catch (e) {
            list.innerHTML = `<div class="text-muted" style="padding:12px 0">${escapeHtml(e.message)}</div>`;
        }
    }

    function joinSharedFeed(socketEvent) {
        if (joinedShareEvent && joinedShareEvent !== socketEvent) {
            WS.unsubscribeShare(joinedShareEvent);
        }
        joinedShareEvent = socketEvent;
        clearOverlay();
        console.log('[Detection][CONTROL] subscribe_share', { socketEvent });
        WS.subscribeShare(socketEvent);
        setStatus(`Joined shared feed ${socketEvent}`);
        refreshShareSessions();
    }

    function leaveSharedFeed() {
        if (!joinedShareEvent) return;
        console.log('[Detection][CONTROL] unsubscribe_share', { socketEvent: joinedShareEvent });
        WS.unsubscribeShare(joinedShareEvent);
        joinedShareEvent = null;
        clearOverlay();
        setStatus('Left shared feed');
        document.getElementById('det-feed-status').textContent = isDetecting
            ? (isSharing ? 'Live + Shared + Detecting' : 'Detecting')
            : (isSharing ? 'Local Camera Shared' : 'Local Camera Live');
        refreshShareSessions();
    }

    function drawBbox(bbox, plate, confidence) {
        clearOverlay();
        const [x1, y1, x2, y2] = bbox;
        const scaleX = bboxCanvas.width / (captureCanvas.width || bboxCanvas.width || 1);
        const scaleY = bboxCanvas.height / (captureCanvas.height || bboxCanvas.height || 1);

        bboxCtx.save();
        bboxCtx.strokeStyle = '#0f9';
        bboxCtx.lineWidth = 2;
        bboxCtx.strokeRect(x1 * scaleX, y1 * scaleY, (x2 - x1) * scaleX, (y2 - y1) * scaleY);
        bboxCtx.fillStyle = 'rgba(0,255,153,0.15)';
        bboxCtx.fillRect(x1 * scaleX, y1 * scaleY, (x2 - x1) * scaleX, (y2 - y1) * scaleY);
        bboxCtx.font = 'bold 13px monospace';
        bboxCtx.fillStyle = '#0f9';
        bboxCtx.fillText(`${plate} ${confidence ? `${(confidence * 100).toFixed(0)}%` : ''}`, x1 * scaleX + 4, Math.max(14, y1 * scaleY - 6));
        bboxCtx.restore();
        window.clearTimeout(drawBbox.clearTimer);
        drawBbox.clearTimer = window.setTimeout(clearOverlay, 1500);
    }

    function clearOverlay() {
        if (bboxCtx && bboxCanvas) {
            bboxCtx.clearRect(0, 0, bboxCanvas.width, bboxCanvas.height);
        }
    }

    function syncCanvasSize(width, height) {
        if (previewCanvas.width !== width || previewCanvas.height !== height) {
            previewCanvas.width = width;
            previewCanvas.height = height;
        }
        if (bboxCanvas.width !== width || bboxCanvas.height !== height) {
            bboxCanvas.width = width;
            bboxCanvas.height = height;
        }
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
            <span class="log-cam">${escapeHtml(data.source || `CAM ${data.camera_id}`)}</span>
            <span class="log-plate">${escapeHtml(data.plate || '--')}</span>
            <span class="log-conf">${data.confidence ? `${(data.confidence * 100).toFixed(0)}%` : '--'}</span>
        `;
        list.prepend(entry);
        document.getElementById('det-log-count').textContent = String(logEntries.length);
    }

    function clearLog() {
        logEntries = [];
        const list = document.getElementById('det-log-list');
        if (list) list.innerHTML = '';
        document.getElementById('det-log-count').textContent = '0';
    }

    function updateButtons() {
        const detectBtn = document.getElementById('det-detect-toggle');
        const shareBtn = document.getElementById('det-share-toggle');
        const pauseBtn = document.getElementById('det-pause');
        if (detectBtn) detectBtn.textContent = isDetecting ? 'STOP DETECTION' : 'START DETECTION';
        if (shareBtn) shareBtn.textContent = isSharing ? 'STOP SHARING' : 'SHARE LIVE FEED';
        if (pauseBtn) {
            pauseBtn.disabled = !isDetecting;
            pauseBtn.textContent = isPaused ? 'RESUME AI' : 'PAUSE AI';
        }
    }

    function getSelectedCameraLabel() {
        const select = document.getElementById('det-camera-select');
        return select?.options?.[select.selectedIndex]?.textContent || 'Local Camera';
    }

    function setStatus(message) {
        const node = document.getElementById('det-status');
        if (node) node.textContent = message;
    }

    function stopLocalStream() {
        if (!localStream) return;
        localStream.getTracks().forEach((track) => track.stop());
        localStream = null;
    }

    function escapeHtml(value) {
        return String(value || '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    }

    function teardown() {
        if (isDetecting) {
            WS.send({ type: 'stop_detection', camera_id: currentCameraId });
        }
        if (isSharing) {
            WS.send({
                type: 'stop_share',
                camera_id: currentCameraId,
                socket_event: activeShareSession?.socket_event || '',
            });
        }
        if (joinedShareEvent) {
            WS.unsubscribeShare(joinedShareEvent);
            joinedShareEvent = null;
        }
        clearInterval(emitInterval);
        emitInterval = null;
        clearInterval(sessionPollTimer);
        sessionPollTimer = null;
        cancelAnimationFrame(previewAnimationId);
        previewAnimationId = null;
        stopLocalStream();
        clearOverlay();

        if (detectionListener) WS.off('detection', detectionListener);
        if (telemetryListener) WS.off('telemetry', telemetryListener);
        if (statusListener) WS.off('status', statusListener);
        if (shareStartedListener) WS.off('share_started', shareStartedListener);
        if (shareStoppedListener) WS.off('share_stopped', shareStoppedListener);
        if (sharedFrameListener) WS.off('shared_frame', sharedFrameListener);

        logEntries = [];
        isDetecting = false;
        isPaused = false;
        isSharing = false;
        activeShareSession = null;
    }

    return { render, teardown };
})();
