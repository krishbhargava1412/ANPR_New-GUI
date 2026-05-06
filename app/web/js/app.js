/** Main application boot — wires everything together. */
const App = (() => {
    function init() {
        Auth.init();
        Router.init();
        AlertBanner.init();

        // Register routes
        Router.register('dashboard', DashboardPage);
        Router.register('detection', DetectionPage);
        Router.register('history', HistoryPage);
        Router.register('watchlist', WatchlistPage);
        Router.register('settings', SettingsPage);
        Router.register('about', AboutPage);
        Router.register('users', UsersPage);

        // Check session on load
        Auth.checkSession();
    }

    function onAuthenticated(user) {
        Sidebar.render(user);
        WS.connect();
        Router.start();
    }

    // Boot
    document.addEventListener('DOMContentLoaded', init);

    return { init, onAuthenticated };
})();
