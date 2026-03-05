/**
 * chat.js — Chat Panel Component
 * ================================
 * Handles message rendering, SSE streaming, session sidebar,
 * auto-resize textarea, markdown-like formatting, and tool-call display.
 */

const ChatComponent = {
    // DOM references
    _els: {},
    _streamController: null, // AbortController for active stream

    // ----------------------------------------------------------------
    //  Initialisation
    // ----------------------------------------------------------------

    init() {
        this._els = {
            input: document.getElementById('chat-input'),
            sendBtn: document.getElementById('send-btn'),
            messagesBox: document.getElementById('messages-container'),
            welcomeScreen: document.getElementById('welcome-screen'),
            sessionsList: document.getElementById('sessions-list'),
            newSessionBtn: document.getElementById('new-session-btn'),
            headerSubtitle: document.getElementById('header-subtitle'),
            attachImageBtn: document.getElementById('btn-attach-image'),
            chatImageInput: document.getElementById('chat-image-input'),
        };

        this._bindEvents();
        this._bindBusEvents();
        this._renderSessionsList();
        this._renderActiveSession();
    },

    // ----------------------------------------------------------------
    //  Event Bindings
    // ----------------------------------------------------------------

    _bindEvents() {
        // Send on button click
        this._els.sendBtn.addEventListener('click', () => this._send());

        // Send on Enter (Shift+Enter for newline)
        this._els.input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this._send();
            }
        });

        // Auto-resize textarea
        this._els.input.addEventListener('input', () => this._autoResize());

        // New session
        this._els.newSessionBtn.addEventListener('click', () => {
            AppState.createSession();
        });

        // Attach image
        this._els.attachImageBtn.addEventListener('click', () => {
            this._els.chatImageInput.click();
        });

        this._els.chatImageInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) {
                Toast.info(`Image attached: ${file.name}`);
                AppState._chatAttachedImage = file;
            }
        });
    },

    _bindBusEvents() {
        EventBus.on('session:created', () => this._renderSessionsList());
        EventBus.on('session:changed', () => this._renderActiveSession());
        EventBus.on('message:added', () => this._scrollToBottom());
    },

    // ----------------------------------------------------------------
    //  Auto-resize textarea
    // ----------------------------------------------------------------

    _autoResize() {
        const el = this._els.input;
        el.style.height = 'auto';
        el.style.height = Math.min(el.scrollHeight, 120) + 'px';
    },

    // ----------------------------------------------------------------
    //  Sessions Sidebar
    // ----------------------------------------------------------------

    _renderSessionsList() {
        const container = this._els.sessionsList;
        container.innerHTML = '';

        const ids = Object.keys(AppState.sessions).sort((a, b) => {
            return (AppState.sessions[b].createdAt || '').localeCompare(AppState.sessions[a].createdAt || '');
        });

        this._els.headerSubtitle.textContent =
            `Sessions: ${ids.length}`;

        // Update settings panel counters
        const totalEl = document.getElementById('settings-total-sessions');
        if (totalEl) totalEl.textContent = ids.length;

        ids.forEach(id => {
            const session = AppState.sessions[id];
            const el = document.createElement('div');
            el.className = `session-item${id === AppState.activeSessionId ? ' active' : ''}`;
            el.innerHTML = `<span class="session-icon">💬</span> ${this._esc(session.name)}`;
            el.addEventListener('click', () => AppState.switchSession(id));
            container.appendChild(el);
        });
    },

    // ----------------------------------------------------------------
    //  Render Active Session Messages
    // ----------------------------------------------------------------

    _renderActiveSession() {
        const session = AppState.getActiveSession();
        this._renderSessionsList();

        if (!session || session.messages.length === 0) {
            this._els.welcomeScreen.style.display = 'flex';
            this._els.messagesBox.style.display = 'none';
            this._updateSessionInfo(session);
            return;
        }

        this._els.welcomeScreen.style.display = 'none';
        this._els.messagesBox.style.display = 'flex';
        this._els.messagesBox.innerHTML = '';

        session.messages.forEach(msg => this._appendMessageEl(msg));
        this._scrollToBottom();
        this._updateSessionInfo(session);
    },

    _updateSessionInfo(session) {
        const idEl = document.getElementById('settings-session-id');
        const countEl = document.getElementById('settings-msg-count');
        if (session) {
            if (idEl) idEl.textContent = session.id.slice(0, 20) + '…';
            if (countEl) countEl.textContent = session.messages.length;
            document.getElementById('header-subtitle').textContent =
                `Session: ${session.name}`;
        } else {
            if (idEl) idEl.textContent = '—';
            if (countEl) countEl.textContent = '0';
        }
    },

    // ----------------------------------------------------------------
    //  Message Rendering
    // ----------------------------------------------------------------

    _appendMessageEl(msg) {
        const container = this._els.messagesBox;

        const wrapper = document.createElement('div');
        wrapper.className = `message ${msg.role}`;

        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.textContent = msg.role === 'user' ? '👤' : '🤖';

        const content = document.createElement('div');
        content.className = 'message-content';
        content.innerHTML = this._formatContent(msg.content || '');

        // Tool calls
        if (msg.toolCalls && msg.toolCalls.length > 0) {
            msg.toolCalls.forEach(tc => {
                const card = document.createElement('div');
                card.className = 'tool-call-card';
                card.innerHTML = `
          <div class="tool-call-header">🔧 Tool: ${this._esc(tc.name)}</div>
          <div class="tool-call-body">${this._esc(JSON.stringify(tc.arguments, null, 2))}</div>
        `;
                content.appendChild(card);
            });
        }

        // Tool results
        if (msg.toolResults && msg.toolResults.length > 0) {
            msg.toolResults.forEach(tr => {
                const card = document.createElement('div');
                card.className = 'tool-call-card';
                card.innerHTML = `
          <div class="tool-call-header">📋 Result: ${this._esc(tr.name)}</div>
          <div class="tool-call-body">${this._esc(typeof tr.result === 'string' ? tr.result : JSON.stringify(tr.result, null, 2))}</div>
        `;
                content.appendChild(card);
            });
        }

        wrapper.appendChild(avatar);
        wrapper.appendChild(content);
        container.appendChild(wrapper);
    },

    /**
     * Creates a streaming assistant message element and returns a handle.
     * @returns {{ element: HTMLElement, contentEl: HTMLElement, append(text: string): void, finish(): void }}
     */
    _createStreamingMessage() {
        this._els.welcomeScreen.style.display = 'none';
        this._els.messagesBox.style.display = 'flex';

        const wrapper = document.createElement('div');
        wrapper.className = 'message assistant';

        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.textContent = '🤖';

        const content = document.createElement('div');
        content.className = 'message-content';

        // Typing indicator (shown until first token)
        const typing = document.createElement('div');
        typing.className = 'typing-indicator';
        typing.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
        content.appendChild(typing);

        wrapper.appendChild(avatar);
        wrapper.appendChild(content);
        this._els.messagesBox.appendChild(wrapper);
        this._scrollToBottom();

        let rawText = '';
        let typingRemoved = false;

        return {
            element: wrapper,
            contentEl: content,
            append(text) {
                if (!typingRemoved) {
                    typing.remove();
                    typingRemoved = true;
                }
                rawText += text;
                content.innerHTML = ChatComponent._formatContent(rawText);
                ChatComponent._scrollToBottom();
            },
            finish() {
                if (!typingRemoved) typing.remove();
                content.innerHTML = ChatComponent._formatContent(rawText);
                return rawText;
            },
        };
    },

    // ----------------------------------------------------------------
    //  Send Message
    // ----------------------------------------------------------------

    async _send() {
        const text = this._els.input.value.trim();
        if (!text || AppState.isSending) return;

        // Ensure a session exists
        if (!AppState.activeSessionId) {
            AppState.createSession();
        }

        const session = AppState.getActiveSession();

        // Add user message
        const userMsg = { role: 'user', content: text };
        AppState.addMessage(userMsg);
        this._appendMessageEl(userMsg);

        // Clear input
        this._els.input.value = '';
        this._autoResize();

        // Build API payload
        const apiMessages = session.messages.map(m => ({
            role: m.role,
            content: m.content,
        }));

        const payload = {
            session_id: session.id,
            messages: apiMessages,
            temperature: CONFIG.DEFAULT_TEMPERATURE,
        };

        // ---- Stream mode ----
        AppState.isSending = true;
        AppState.isStreaming = true;
        this._els.sendBtn.disabled = true;

        const streamHandle = this._createStreamingMessage();

        this._streamController = API.chatStream(payload, {
            onToken: (token) => {
                streamHandle.append(token);
            },
            onToolCall: (tc) => {
                Toast.info(`Tool called: ${tc.name}`);
            },
            onDone: (fullText) => {
                const finalText = streamHandle.finish();
                const assistantMsg = { role: 'assistant', content: finalText || fullText };
                AppState.addMessage(assistantMsg);
                this._finishSend();
            },
            onError: (err) => {
                streamHandle.finish();
                Toast.error(`Chat error: ${err}`);
                this._finishSend();
            },
        });
    },

    _finishSend() {
        AppState.isSending = false;
        AppState.isStreaming = false;
        this._els.sendBtn.disabled = false;
        this._els.input.focus();
    },

    // ----------------------------------------------------------------
    //  Helpers
    // ----------------------------------------------------------------

    _scrollToBottom() {
        const el = this._els.messagesBox;
        requestAnimationFrame(() => {
            el.scrollTop = el.scrollHeight;
        });
    },

    /**
     * Basic markdown-like formatting:
     * - **bold**  → <strong>
     * - *italic*  → <em>
     * - `code`    → <code>
     * - ```block``` → <pre><code>
     * - newlines  → <br>
     */
    _formatContent(text) {
        if (!text) return '';
        let html = this._esc(text);

        // Code blocks
        html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
            return `<pre><code>${code}</code></pre>`;
        });

        // Inline code
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

        // Bold
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

        // Italic
        html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

        // Line breaks (but not inside <pre>)
        html = html.replace(/\n/g, '<br>');

        return html;
    },

    _esc(str) {
        const div = document.createElement('div');
        div.textContent = str || '';
        return div.innerHTML;
    },
};
