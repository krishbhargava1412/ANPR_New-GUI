/** WebSocket client with auto-reconnect and message routing. */
const WS = (() => {
    let socket = null;
    let reconnectTimer = null;
    const listeners = {};
    const decoder = new TextDecoder();

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

        try {
            if (socket) socket.close();
        } catch (e) {}

        socket = new WebSocket(urlObj.toString());
        socket.binaryType = 'arraybuffer';

        socket.onopen = () => {
            emit('connected');
            clearTimeout(reconnectTimer);
        };

        socket.onclose = () => {
            emit('disconnected');
            scheduleReconnect();
        };

        socket.onerror = (e) => {
            console.error('[WS] Error', e);
        };

        socket.onmessage = (event) => {
            if (event.data instanceof ArrayBuffer) {
                const buf = event.data;
                if (buf.byteLength < 2) return;
                const view = new DataView(buf);
                const eventLen = view.getUint16(0, false);
                if (buf.byteLength < 2 + eventLen) return;
                const socketEvent = decoder.decode(buf.slice(2, 2 + eventLen));
                const jpegBlob = new Blob([buf.slice(2 + eventLen)], { type: 'image/jpeg' });
                emit('shared_frame', { socketEvent, blob: jpegBlob });
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
        if (socket) {
            socket.close();
            socket = null;
        }
    }

    function send(data) {
        if (socket?.readyState === WebSocket.OPEN) {
            console.log('[WS][SEND][JSON]', data.type || 'message', data);
            socket.send(JSON.stringify(data));
        } else {
            console.warn('[WS][SEND][JSON][SKIP] Socket not open', data.type || 'message', data);
        }
    }

    function sendBinary(data) {
        if (socket?.readyState === WebSocket.OPEN) {
            console.log('[WS][SEND][BINARY] bytes=', data.byteLength);
            socket.send(data);
        } else {
            console.warn('[WS][SEND][BINARY][SKIP] Socket not open');
        }
    }

    function subscribe(cameraId) {
        send({ type: 'subscribe_camera', camera_id: cameraId });
    }

    function unsubscribe(cameraId) {
        send({ type: 'unsubscribe_camera', camera_id: cameraId });
    }

    function subscribeShare(socketEvent) {
        send({ type: 'subscribe_share', socket_event: socketEvent });
    }

    function unsubscribeShare(socketEvent) {
        send({ type: 'unsubscribe_share', socket_event: socketEvent });
    }

    function on(event, callback) {
        if (!listeners[event]) listeners[event] = [];
        listeners[event].push(callback);
    }

    function off(event, callback) {
        if (!listeners[event]) return;
        listeners[event] = listeners[event].filter((cb) => cb !== callback);
    }

    function emit(event, data) {
        (listeners[event] || []).forEach((cb) => {
            try {
                cb(data);
            } catch (e) {
                console.error('[WS] Listener error', e);
            }
        });
    }

    return {
        connect,
        disconnect,
        send,
        sendBinary,
        subscribe,
        unsubscribe,
        subscribeShare,
        unsubscribeShare,
        on,
        off,
    };
})();
