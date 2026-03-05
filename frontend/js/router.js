/**
 * router.js — Client-Side Panel Router
 * ======================================
 * Manages panel visibility and sidebar active state.
 */

const Router = {
    _panels: ['chat', 'voice', 'vision', 'settings'],
    _titleMap: {
        chat: 'Chat',
        voice: 'Voice I/O',
        vision: 'Vision',
        settings: 'Settings',
    },

    /**
     * Initialise the router — attach click handlers to nav buttons.
     */
    init() {
        document.querySelectorAll('.nav-btn[data-panel]').forEach(btn => {
            btn.addEventListener('click', () => {
                this.navigate(btn.dataset.panel);
            });
        });

        // Listen for programmatic navigation
        EventBus.on('navigate', (panel) => this.navigate(panel));
    },

    /**
     * Switch to a specific panel.
     * @param {string} panelId - One of: chat, voice, vision, settings.
     */
    navigate(panelId) {
        if (!this._panels.includes(panelId)) return;

        AppState.activePanel = panelId;

        // Update sidebar buttons
        document.querySelectorAll('.nav-btn[data-panel]').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.panel === panelId);
        });

        // Update panels
        document.querySelectorAll('.panel').forEach(panel => {
            panel.classList.toggle('active', panel.id === `panel-${panelId}`);
        });

        // Update header
        document.getElementById('header-title').textContent = this._titleMap[panelId] || panelId;

        EventBus.emit('panel:changed', panelId);
    },
};
