/**
 * state.js — Centralised Application State
 * ==========================================
 * Reactive global state store. Components read from and write to this
 * object, and the event bus is used to notify listeners of mutations.
 */

const AppState = {
    // ---- Session Management ----
    sessions: {},           // { sessionId: { id, name, messages:[], createdAt } }
    activeSessionId: null,  // currently selected session

    // ---- UI ----
    activePanel: 'chat',    // chat | voice | vision | settings
    isStreaming: false,      // true while SSE is active
    isSending: false,        // true while waiting for response

    // ---- Health ----
    backendOnline: false,
    healthData: null,        // last health check response

    // ---- Voice ----
    isRecording: false,
    audioBlob: null,         // last recorded audio
    lastTranscript: '',

    // ---- Vision ----
    selectedImage: null,     // File object or null
    selectedImageUrl: '',    // data URL or remote URL
    cameraStreaming: false,
    lastSnapshot: null,      // Blob

    // ---- Helpers ----

    /**
     * Get the active session object.
     * @returns {object|null}
     */
    getActiveSession() {
        return this.sessions[this.activeSessionId] || null;
    },

    /**
     * Generate a new unique session ID.
     * @returns {string}
     */
    generateSessionId() {
        return 'session_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
    },

    /**
     * Create a new session and set it as active.
     * @param {string} [name] - Optional session name.
     * @returns {string} The new session ID.
     */
    createSession(name) {
        const id = this.generateSessionId();
        this.sessions[id] = {
            id,
            name: name || `Chat ${Object.keys(this.sessions).length + 1}`,
            messages: [],
            createdAt: new Date().toISOString(),
        };
        this.activeSessionId = id;
        this.persistSessions();
        EventBus.emit('session:created', id);
        EventBus.emit('session:changed', id);
        return id;
    },

    /**
     * Switch to an existing session.
     * @param {string} sessionId
     */
    switchSession(sessionId) {
        if (this.sessions[sessionId]) {
            this.activeSessionId = sessionId;
            localStorage.setItem(CONFIG.ACTIVE_SESSION_KEY, sessionId);
            EventBus.emit('session:changed', sessionId);
        }
    },

    /**
     * Add a message to the active session.
     * @param {object} msg - { role, content, toolCalls?, toolResults? }
     */
    addMessage(msg) {
        const session = this.getActiveSession();
        if (session) {
            session.messages.push(msg);
            this.persistSessions();
            EventBus.emit('message:added', msg);
        }
    },

    /**
     * Save sessions to localStorage.
     */
    persistSessions() {
        try {
            localStorage.setItem(CONFIG.SESSION_STORAGE_KEY, JSON.stringify(this.sessions));
            localStorage.setItem(CONFIG.ACTIVE_SESSION_KEY, this.activeSessionId);
        } catch (e) {
            console.warn('Failed to persist sessions:', e);
        }
    },

    /**
     * Load sessions from localStorage.
     */
    loadSessions() {
        try {
            const raw = localStorage.getItem(CONFIG.SESSION_STORAGE_KEY);
            if (raw) {
                this.sessions = JSON.parse(raw);
            }
            const activeId = localStorage.getItem(CONFIG.ACTIVE_SESSION_KEY);
            if (activeId && this.sessions[activeId]) {
                this.activeSessionId = activeId;
            }
        } catch (e) {
            console.warn('Failed to load sessions:', e);
        }
    },
};
