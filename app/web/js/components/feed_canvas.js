/** Canvas-based video feed component for WebSocket JPEG stream. */
function createFeedCanvas(containerId) {
    const container = document.createElement('div');
    container.className = 'feed-container';
    container.id = containerId || 'feed-container';

    const canvas = document.createElement('canvas');
    canvas.className = 'feed-canvas';
    canvas.width = 640;
    canvas.height = 480;

    const placeholder = document.createElement('div');
    placeholder.className = 'feed-placeholder';
    placeholder.innerHTML = '<span style="font-size:2rem">📷</span><span>NO FEED</span><span style="font-size:0.75rem">Start cameras and detection in Settings</span>';

    const overlay = document.createElement('div');
    overlay.className = 'feed-overlay';
    overlay.innerHTML = '<span data-feed-status>Idle</span><span data-feed-fps></span>';

    container.appendChild(canvas);
    container.appendChild(placeholder);
    container.appendChild(overlay);

    const ctx = canvas.getContext('2d');
    let subscribedCamera = null;
    let frameCount = 0;

    function onFrame(data) {
        if (data.cameraId !== subscribedCamera) return;
        const url = URL.createObjectURL(data.blob);
        const img = new Image();
        img.onload = () => {
            canvas.width = img.width;
            canvas.height = img.height;
            ctx.drawImage(img, 0, 0);
            URL.revokeObjectURL(url);
            placeholder.classList.add('hidden');
            frameCount++;
        };
        img.src = url;
    }

    function subscribeCamera(cameraId) {
        if (subscribedCamera !== null) {
            WS.unsubscribe(subscribedCamera);
        }
        subscribedCamera = cameraId;
        WS.subscribe(cameraId);
        placeholder.classList.remove('hidden');
        frameCount = 0;
    }

    function unsubscribeAll() {
        if (subscribedCamera !== null) {
            WS.unsubscribe(subscribedCamera);
            subscribedCamera = null;
        }
    }

    function updateStatus(text) {
        overlay.querySelector('[data-feed-status]').textContent = text;
    }

    function updateFps(fps) {
        overlay.querySelector('[data-feed-fps]').textContent = fps ? `${fps.toFixed(1)} FPS` : '';
    }

    WS.on('frame', onFrame);

    return {
        element: container, canvas, subscribeCamera, unsubscribeAll,
        updateStatus, updateFps,
        teardown: () => {
            WS.off('frame', onFrame);
            unsubscribeAll();
        }
    };
}
