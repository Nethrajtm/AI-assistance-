/**
 * app.js — Application Entry Point
 * ==================================
 * Bootstraps all modules, loads persisted state,
 * and kicks off the UI.
 */

(function App() {
    'use strict';

    // ----------------------------------------------------------------
    //  Boot Sequence
    // ----------------------------------------------------------------

    function boot() {
        console.log('%c🤖 AI Assistant v1.0.0', 'color:#6c63ff;font-size:16px;font-weight:bold;');
        console.log('%cBooting modules…', 'color:#9d9db8;');

        // 1. Load persisted sessions
        AppState.loadSessions();

        // 2. Ensure at least one session exists
        if (Object.keys(AppState.sessions).length === 0) {
            AppState.createSession('New Chat');
        } else if (!AppState.activeSessionId) {
            // Pick the most recent session
            const ids = Object.keys(AppState.sessions);
            AppState.activeSessionId = ids[ids.length - 1];
        }

        // 3. Initialise components in dependency order
        Toast.init();
        Router.init();
        ChatComponent.init();
        VoiceComponent.init();
        VisionComponent.init();
        SettingsComponent.init();

        console.log('%c✓ All modules initialised', 'color:#2dd4a0;');
    }

    // ----------------------------------------------------------------
    //  Start when DOM is ready
    // ----------------------------------------------------------------

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
