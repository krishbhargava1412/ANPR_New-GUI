/** Alert banner component. */
const AlertBanner = (() => {
    let dismissTimer = null;

    function init() {
        document.getElementById('alert-dismiss').addEventListener('click', hide);
        WS.on('alert', show);
    }

    function show(data) {
        const banner = document.getElementById('alert-banner');
        const text = document.getElementById('alert-text');
        text.textContent = `WATCHLIST ALERT: ${data.plate} detected on ${data.source || 'Camera ' + data.camera_id}`;
        banner.classList.remove('hidden');
        clearTimeout(dismissTimer);
        dismissTimer = setTimeout(hide, 15000);
    }

    function hide() {
        document.getElementById('alert-banner').classList.add('hidden');
        clearTimeout(dismissTimer);
    }

    return { init, show, hide };
})();
