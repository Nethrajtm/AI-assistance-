/**
 * vision.js — Vision Panel Component
 * ====================================
 * Image upload, URL input, drag-and-drop, vision analysis,
 * live camera MJPEG stream, and snapshot capture.
 */

const VisionComponent = {
    _els: {},

    // ----------------------------------------------------------------
    //  Init
    // ----------------------------------------------------------------

    init() {
        this._els = {
            uploadZone: document.getElementById('upload-zone'),
            fileInput: document.getElementById('vision-file-input'),
            previewContainer: document.getElementById('image-preview-container'),
            previewImg: document.getElementById('image-preview'),
            removeBtn: document.getElementById('image-preview-remove'),
            urlInput: document.getElementById('vision-url-input'),
            promptInput: document.getElementById('vision-prompt'),
            analyzeBtn: document.getElementById('btn-analyze'),
            response: document.getElementById('vision-response'),
            responseText: document.getElementById('vision-response-text'),
            cameraStream: document.getElementById('camera-stream'),
            noCameraMsg: document.getElementById('no-camera-msg'),
            startCameraBtn: document.getElementById('btn-start-camera'),
            snapshotBtn: document.getElementById('btn-snapshot'),
            useSnapshotBtn: document.getElementById('btn-use-snapshot'),
        };

        this._bindEvents();
    },

    // ----------------------------------------------------------------
    //  Event Bindings
    // ----------------------------------------------------------------

    _bindEvents() {
        // Upload zone click
        this._els.uploadZone.addEventListener('click', () => {
            this._els.fileInput.click();
        });

        // File selected
        this._els.fileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) this._setImage(file);
        });

        // Drag and drop
        this._els.uploadZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            this._els.uploadZone.classList.add('drag-over');
        });

        this._els.uploadZone.addEventListener('dragleave', () => {
            this._els.uploadZone.classList.remove('drag-over');
        });

        this._els.uploadZone.addEventListener('drop', (e) => {
            e.preventDefault();
            this._els.uploadZone.classList.remove('drag-over');
            const file = e.dataTransfer.files[0];
            if (file && file.type.startsWith('image/')) {
                this._setImage(file);
            } else {
                Toast.error('Please drop a valid image file');
            }
        });

        // Remove image
        this._els.removeBtn.addEventListener('click', () => {
            this._clearImage();
        });

        // Analyze
        this._els.analyzeBtn.addEventListener('click', () => this._analyze());

        // Camera controls
        this._els.startCameraBtn.addEventListener('click', () => this._toggleCamera());
        this._els.snapshotBtn.addEventListener('click', () => this._captureSnapshot());
        this._els.useSnapshotBtn.addEventListener('click', () => this._analyzeSnapshot());
    },

    // ----------------------------------------------------------------
    //  Image Management
    // ----------------------------------------------------------------

    _setImage(file) {
        AppState.selectedImage = file;
        const reader = new FileReader();
        reader.onload = (e) => {
            AppState.selectedImageUrl = e.target.result;
            this._els.previewImg.src = e.target.result;
            this._els.previewContainer.style.display = 'block';
            this._els.uploadZone.style.display = 'none';
        };
        reader.readAsDataURL(file);
    },

    _clearImage() {
        AppState.selectedImage = null;
        AppState.selectedImageUrl = '';
        this._els.previewImg.src = '';
        this._els.previewContainer.style.display = 'none';
        this._els.uploadZone.style.display = 'block';
        this._els.fileInput.value = '';
    },

    // ----------------------------------------------------------------
    //  Vision Analysis
    // ----------------------------------------------------------------

    async _analyze() {
        const prompt = this._els.promptInput.value.trim();
        if (!prompt) {
            Toast.error('Please enter a prompt');
            return;
        }

        const imageUrl = this._els.urlInput.value.trim();
        const hasFile = AppState.selectedImage != null;
        const hasUrl = imageUrl.length > 0;

        if (!hasFile && !hasUrl) {
            Toast.error('Please provide an image (upload or URL)');
            return;
        }

        this._els.analyzeBtn.disabled = true;
        this._els.analyzeBtn.textContent = '⏳ Analyzing…';
        this._els.response.style.display = 'none';

        try {
            const result = await API.vision({
                prompt,
                image: hasFile ? AppState.selectedImage : undefined,
                imageUrl: hasUrl ? imageUrl : undefined,
                sessionId: AppState.activeSessionId,
            });

            this._els.responseText.textContent = result.description;
            this._els.response.style.display = 'block';
            Toast.success('Image analyzed successfully');
        } catch (err) {
            Toast.error(`Vision error: ${err.message}`);
        } finally {
            this._els.analyzeBtn.disabled = false;
            this._els.analyzeBtn.textContent = '🔍 Analyze Image';
        }
    },

    // ----------------------------------------------------------------
    //  Camera
    // ----------------------------------------------------------------

    _toggleCamera() {
        if (AppState.cameraStreaming) {
            // Stop
            this._els.cameraStream.src = '';
            this._els.cameraStream.style.display = 'none';
            this._els.noCameraMsg.style.display = 'block';
            this._els.startCameraBtn.textContent = '▶️ Start Feed';
            this._els.startCameraBtn.classList.remove('active');
            AppState.cameraStreaming = false;
        } else {
            // Start MJPEG stream
            this._els.cameraStream.src = API.videoStreamUrl();
            this._els.cameraStream.style.display = 'block';
            this._els.noCameraMsg.style.display = 'none';
            this._els.startCameraBtn.textContent = '⏹️ Stop Feed';
            this._els.startCameraBtn.classList.add('active');
            AppState.cameraStreaming = true;

            // Handle stream errors
            this._els.cameraStream.onerror = () => {
                Toast.error('Camera stream failed — is the backend camera enabled?');
                this._toggleCamera();
            };
        }
    },

    async _captureSnapshot() {
        try {
            const blob = await API.snapshot();
            AppState.lastSnapshot = blob;

            // Show snapshot in preview
            const url = URL.createObjectURL(blob);
            this._els.previewImg.src = url;
            this._els.previewContainer.style.display = 'block';
            this._els.uploadZone.style.display = 'none';

            // Convert to file for vision API
            AppState.selectedImage = new File([blob], 'snapshot.jpg', { type: 'image/jpeg' });
            Toast.success('Snapshot captured');
        } catch (err) {
            Toast.error(`Snapshot failed: ${err.message}`);
        }
    },

    async _analyzeSnapshot() {
        if (!AppState.lastSnapshot && !AppState.selectedImage) {
            Toast.error('Capture a snapshot first');
            return;
        }
        this._analyze();
    },
};
