/** WebSocket client with auto-reconnect and message routing. */
const WS = (() => {
    let socket = null;
    let reconnectTimer = null;
    const listeners = {};

    let frameCounters = {};
    setInterval(() => {
        Object.keys(frameCounters).forEach(camId => {
            if (frameCounters[camId] > 0) {
                console.log(`[WS] Camera ${camId} is sending frames to frontend (${frameCounters[camId]} fps)`);
                frameCounters[camId] = 0;
            }
        });
    }, 1000);

    function connect() {
        const token = API.getToken();
        if (!token) return;

        let urlObj;
        try {
            urlObj = new URL(API.getBaseUrl());
            urlObj.protocol = urlObj.protocol === 'https:' ? 'wss:' : 'ws:';
            urlObj.pathname = '/ws/feed';
            urlObj.searchParams.set('token', token);
        } catch (e) {
            console.error('Invalid backend URL', e);
            return;
        }
        
        const url = urlObj.toString();

        try { if (socket) socket.close(); } catch (e) {}
        socket = new WebSocket(url);
        socket.binaryType = 'arraybuffer';

        socket.onopen = () => {
            console.log('[WS] Connected');
            emit('connected');
            clearTimeout(reconnectTimer);
        };

        socket.onclose = () => {
            console.log('[WS] Disconnected');
            emit('disconnected');
            scheduleReconnect();
        };

        socket.onerror = (e) => {
            console.error('[WS] Error', e);
        };

        socket.onmessage = (event) => {
            if (event.data instanceof ArrayBuffer) {
                const buf = event.data;
                const view = new DataView(buf);
                const cameraId = view.getUint32(0);
                const jpegBlob = new Blob([buf.slice(4)], { type: 'image/jpeg' });
                
                if (frameCounters[cameraId] === undefined || frameCounters[cameraId] === 0) {
                    console.log(`[WS] First binary frame received for Cam ${cameraId}, size: ${jpegBlob.size} bytes`);
                }
                
                frameCounters[cameraId] = (frameCounters[cameraId] || 0) + 1;
                
                emit('frame', { cameraId, blob: jpegBlob });
                return;
            }
            try {
                const data = JSON.parse(event.data);
                emit(data.type || 'message', data);
            } catch (e) {
                console.warn('[WS] Parse error', e);
            }
        };
    }

    function scheduleReconnect() {
        clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(() => connect(), 3000);
    }

    function disconnect() {
        clearTimeout(reconnectTimer);
        if (socket) { socket.close(); socket = null; }
    }

    function send(data) {
        if (socket?.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify(data));
        }
    }

    function sendBinary(data) {
        if (socket?.readyState === WebSocket.OPEN) {
            socket.send(data);
        }
    }

    function subscribe(cameraId) { send({ type: 'subscribe_camera', camera_id: cameraId }); }
    function unsubscribe(cameraId) { send({ type: 'unsubscribe_camera', camera_id: cameraId }); }

    function on(event, callback) {
        if (!listeners[event]) listeners[event] = [];
        listeners[event].push(callback);
    }

    function off(event, callback) {
        if (!listeners[event]) return;
        listeners[event] = listeners[event].filter(cb => cb !== callback);
    }

    function emit(event, data) {
        (listeners[event] || []).forEach(cb => {
            try { cb(data); } catch (e) { console.error('[WS] Listener error', e); }
        });
    }

    return { connect, disconnect, send, sendBinary, subscribe, unsubscribe, on, off };
})();
