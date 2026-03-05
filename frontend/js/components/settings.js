/**
 * settings.js — Settings Panel Component
 * ========================================
 * Health monitoring, session info display, periodic health polling.
 */

const SettingsComponent = {
    _els: {},
    _healthInterval: null,

    // ----------------------------------------------------------------
    //  Init
    // ----------------------------------------------------------------

    init() {
        this._els = {
            healthStatus: document.getElementById('health-status'),
            healthProvider: document.getElementById('health-provider'),
            healthVersion: document.getElementById('health-version'),
            healthUptime: document.getElementById('health-uptime'),
            healthDot: document.getElementById('health-dot'),
            providerBadge: document.getElementById('provider-badge'),
            backendUrl: document.getElementById('settings-backend-url'),
        };

        // Show backend URL
        this._els.backendUrl.textContent = CONFIG.API_BASE;

        // Initial health check
        this._checkHealth();

        // Poll health
        this._healthInterval = setInterval(
            () => this._checkHealth(),
            CONFIG.HEALTH_POLL_INTERVAL
        );
    },

    // ----------------------------------------------------------------
    //  Health Check
    // ----------------------------------------------------------------

    async _checkHealth() {
        const start = performance.now();
        try {
            const data = await API.health();
            const latency = Math.round(performance.now() - start);

            AppState.backendOnline = true;
            AppState.healthData = data;

            this._els.healthStatus.textContent = '● Online';
            this._els.healthStatus.style.color = 'var(--accent-success)';
            this._els.healthProvider.textContent = data.provider || '—';
            this._els.healthVersion.textContent = data.version || '—';
            this._els.healthUptime.textContent = latency + 'ms';
            this._els.healthDot.className = 'status-dot online';
            this._els.providerBadge.textContent = data.provider || 'LLM';

        } catch (err) {
            AppState.backendOnline = false;

            this._els.healthStatus.textContent = '● Offline';
            this._els.healthStatus.style.color = 'var(--accent-danger)';
            this._els.healthProvider.textContent = '—';
            this._els.healthVersion.textContent = '—';
            this._els.healthUptime.textContent = '—';
            this._els.healthDot.className = 'status-dot offline';
            this._els.providerBadge.textContent = 'Offline';
        }
    },

    // ----------------------------------------------------------------
    //  Cleanup
    // ----------------------------------------------------------------

    destroy() {
        if (this._healthInterval) clearInterval(this._healthInterval);
    },
};
