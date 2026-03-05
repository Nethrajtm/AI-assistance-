/**
 * events.js — Event Bus (Pub/Sub)
 * ================================
 * Decoupled communication between modules.
 * Components emit and listen to named events without direct coupling.
 */

const EventBus = {
    /** @type {Object<string, Function[]>} */
    _listeners: {},

    /**
     * Subscribe to an event.
     * @param {string} event - Event name (e.g. 'session:changed').
     * @param {Function} callback
     * @returns {Function} Unsubscribe function.
     */
    on(event, callback) {
        if (!this._listeners[event]) {
            this._listeners[event] = [];
        }
        this._listeners[event].push(callback);

        // Return an unsubscribe function
        return () => {
            this._listeners[event] = this._listeners[event].filter(cb => cb !== callback);
        };
    },

    /**
     * Emit an event to all subscribers.
     * @param {string} event
     * @param  {...any} args
     */
    emit(event, ...args) {
        const callbacks = this._listeners[event];
        if (callbacks) {
            callbacks.forEach(cb => {
                try {
                    cb(...args);
                } catch (err) {
                    console.error(`EventBus error in "${event}" handler:`, err);
                }
            });
        }
    },

    /**
     * Subscribe to an event, auto-unsubscribe after first fire.
     * @param {string} event
     * @param {Function} callback
     */
    once(event, callback) {
        const unsub = this.on(event, (...args) => {
            unsub();
            callback(...args);
        });
    },
};
