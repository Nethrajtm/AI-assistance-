/**
 * toast.js — Toast Notification Component
 * =========================================
 * Provides success / error / info toasts with auto-dismiss.
 */

const Toast = {
    _container: null,

    init() {
        this._container = document.getElementById('toast-container');
    },

    /**
     * Show a toast notification.
     * @param {string} message
     * @param {'success'|'error'|'info'} type
     * @param {number} [durationMs=4000]
     */
    show(message, type = 'info', durationMs = 4000) {
        if (!this._container) this.init();

        const icons = { success: '✓', error: '✕', info: 'ℹ' };
        const el = document.createElement('div');
        el.className = `toast ${type}`;
        el.innerHTML = `<span>${icons[type] || ''}</span> ${this._escapeHtml(message)}`;
        this._container.appendChild(el);

        // Auto-remove
        setTimeout(() => {
            el.style.opacity = '0';
            el.style.transform = 'translateY(8px) scale(0.95)';
            setTimeout(() => el.remove(), 300);
        }, durationMs);
    },

    success(msg) { this.show(msg, 'success'); },
    error(msg) { this.show(msg, 'error', 6000); },
    info(msg) { this.show(msg, 'info'); },

    _escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    },
};
