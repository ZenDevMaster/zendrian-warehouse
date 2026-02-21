/**
 * Camera Barcode Scanner — BarcodeDetector API integration
 *
 * Pure enhancement: if BarcodeDetector is unavailable or camera fails,
 * the existing keyboard/bluetooth scanner continues working normally.
 *
 * Injects barcode values into #scan-input and triggers the same HTMX
 * submission flow — zero changes to server-side code.
 */

/* global htmx, playSound, refocusInput */

(function () {
    'use strict';

    // ── Constants ──────────────────────────────────────────────
    var SCAN_INTERVAL = 250;           // ~4 fps
    var DEDUP_WINDOW  = 2000;          // ignore same barcode within 2 s
    var RATE_LIMIT    = 700;           // match scanner.js MIN_SUBMIT_INTERVAL
    var FLASH_DURATION = 400;          // green flash ms
    var BARCODE_FORMATS = [
        'ean_13', 'ean_8', 'upc_a', 'upc_e',
        'code_128', 'code_39', 'code_93',
        'codabar', 'itf', 'qr_code', 'data_matrix'
    ];

    // ── State ──────────────────────────────────────────────────
    var stream          = null;
    var detector        = null;
    var scanning        = false;
    var scanTimer       = null;
    var lastBarcode     = '';
    var lastBarcodeTime = 0;
    var lastSubmitTime  = 0;
    var useFrontCamera  = false;
    var videoEl         = null;
    var canvasEl        = null;
    var canvasCtx       = null;
    var viewfinderEl    = null;
    var previewCard     = null;
    var toggleCheckbox  = null;
    var toggleLabel     = null;

    // ── Global flag: suppress focus overlay while camera is active ──
    window._cameraScannerActive = false;

    // ── Mobile camera repositioning ─────────────────────────────
    var MOBILE_BREAKPOINT = 768;

    function isMobileView() {
        return window.innerWidth <= MOBILE_BREAKPOINT;
    }

    function moveCameraToMobileMount() {
        var mount = document.getElementById('mobile-camera-mount');
        if (mount && previewCard && previewCard.parentNode !== mount) {
            mount.appendChild(previewCard);
        }
    }

    function moveCameraToSidebar() {
        var sidebarArea = document.getElementById('camera-preview-area');
        if (sidebarArea && previewCard && previewCard.parentNode !== sidebarArea) {
            sidebarArea.appendChild(previewCard);
        }
    }

    // ── Entry point (called from scan.html after script loads) ──
    window.initCameraScanner = function () {
        console.log('[camera-scanner] initCameraScanner() called');
        if (!('BarcodeDetector' in window)) {
            console.log('[camera-scanner] BarcodeDetector not in window, aborting');
            return;
        }

        // Filter to only supported formats
        console.log('[camera-scanner] Calling getSupportedFormats()...');
        BarcodeDetector.getSupportedFormats().then(function (supported) {
            console.log('[camera-scanner] Supported formats:', supported);
            var formats = BARCODE_FORMATS.filter(function (f) {
                return supported.indexOf(f) !== -1;
            });
            console.log('[camera-scanner] Filtered formats:', formats);
            if (formats.length === 0) {
                console.warn('[camera-scanner] No supported formats found, aborting');
                return;
            }

            detector = new BarcodeDetector({ formats: formats });
            console.log('[camera-scanner] BarcodeDetector created, building UI...');
            buildUI();
            console.log('[camera-scanner] UI built successfully');
        }).catch(function (err) {
            console.warn('[camera-scanner] getSupportedFormats() failed:', err);
            // getSupportedFormats not available — try all
            try {
                detector = new BarcodeDetector({ formats: BARCODE_FORMATS });
                console.log('[camera-scanner] Fallback BarcodeDetector created, building UI...');
                buildUI();
            } catch (e) {
                console.error('[camera-scanner] BarcodeDetector not usable:', e);
            }
        });
    };

    // ── Build UI elements ──────────────────────────────────────
    function buildUI() {
        // 1. Camera toggle checkbox (next to scan input)
        var toggleArea = document.getElementById('camera-toggle-area');
        if (toggleArea) {
            toggleLabel = document.createElement('label');
            toggleLabel.className = 'camera-toggle';

            toggleCheckbox = document.createElement('input');
            toggleCheckbox.type = 'checkbox';
            toggleCheckbox.id = 'camera-scanner-toggle';

            var labelText = document.createElement('span');
            labelText.textContent = '📷 Use Camera';

            toggleLabel.appendChild(toggleCheckbox);
            toggleLabel.appendChild(labelText);
            toggleArea.appendChild(toggleLabel);

            toggleCheckbox.addEventListener('change', function () {
                if (toggleCheckbox.checked) {
                    startCamera();
                } else {
                    stopCamera();
                }
            });
        }

        // 2. Camera preview card (in sidebar)
        var previewArea = document.getElementById('camera-preview-area');
        if (previewArea) {
            previewCard = document.createElement('div');
            previewCard.className = 'camera-preview-card';
            previewCard.style.display = 'none';

            // Header
            var header = document.createElement('div');
            header.className = 'camera-preview-header';

            var title = document.createElement('span');
            title.textContent = '📷 Camera Scanner';

            var switchBtn = document.createElement('button');
            switchBtn.type = 'button';
            switchBtn.textContent = '🔄 Switch';
            switchBtn.title = 'Switch camera';
            switchBtn.addEventListener('click', function () {
                useFrontCamera = !useFrontCamera;
                if (scanning) {
                    stopStream();
                    requestCamera();
                }
            });

            header.appendChild(title);
            header.appendChild(switchBtn);

            // Viewfinder
            viewfinderEl = document.createElement('div');
            viewfinderEl.className = 'camera-viewfinder';

            videoEl = document.createElement('video');
            videoEl.setAttribute('autoplay', '');
            videoEl.setAttribute('playsinline', '');
            videoEl.setAttribute('muted', '');
            videoEl.muted = true;

            canvasEl = document.createElement('canvas');

            // Overlay with centering guide
            var overlay = document.createElement('div');
            overlay.className = 'viewfinder-overlay';

            var guide = document.createElement('div');
            guide.className = 'viewfinder-guide';

            var guideBottom = document.createElement('div');
            guideBottom.className = 'viewfinder-guide-bottom';
            guide.appendChild(guideBottom);

            var scanline = document.createElement('div');
            scanline.className = 'viewfinder-scanline';

            overlay.appendChild(guide);
            overlay.appendChild(scanline);

            // Status message area (for errors)
            var statusEl = document.createElement('div');
            statusEl.className = 'camera-status';
            statusEl.id = 'camera-status';
            statusEl.style.display = 'none';

            viewfinderEl.appendChild(videoEl);
            viewfinderEl.appendChild(canvasEl);
            viewfinderEl.appendChild(overlay);
            viewfinderEl.appendChild(statusEl);

            previewCard.appendChild(header);
            previewCard.appendChild(viewfinderEl);
            previewArea.appendChild(previewCard);
        }

        // 3. Handle viewport resize — move camera between mount points
        window.addEventListener('resize', function () {
            if (!window._cameraScannerActive || !previewCard) return;
            if (isMobileView()) {
                moveCameraToMobileMount();
            } else {
                moveCameraToSidebar();
            }
        });

        // 4. Visibility API — pause/resume when tab hidden
        document.addEventListener('visibilitychange', function () {
            if (!scanning) return;
            if (document.hidden) {
                pauseScanning();
            } else {
                resumeScanning();
            }
        });
    }

    // ── Camera start / stop ────────────────────────────────────
    function startCamera() {
        if (previewCard) previewCard.style.display = '';
        if (toggleLabel) toggleLabel.classList.add('active');
        window._cameraScannerActive = true;

        // Suppress keyboard when camera is active
        if (window.setScanInputMode) {
            window.setScanInputMode('none');
        }

        // Move camera to mobile mount point if on mobile
        if (isMobileView()) {
            moveCameraToMobileMount();
        }

        // Suppress focus overlay
        var focusOverlay = document.getElementById('focus-overlay');
        if (focusOverlay) focusOverlay.style.display = 'none';

        requestCamera();
    }

    function stopCamera() {
        scanning = false;
        window._cameraScannerActive = false;
        if (toggleLabel) toggleLabel.classList.remove('active');
        stopStream();
        clearScanTimer();

        if (previewCard) previewCard.style.display = 'none';
        hideStatus();

        // Move camera back to sidebar
        moveCameraToSidebar();

        // Restore keyboard based on user's toggle preference
        var hideKbToggle = document.getElementById('hide-keyboard-toggle');
        if (window.setScanInputMode) {
            if (hideKbToggle && hideKbToggle.checked) {
                window.setScanInputMode('none');
            } else {
                window.setScanInputMode('text');
            }
        }

        // Re-focus scan input for keyboard scanner
        if (typeof refocusInput === 'function') refocusInput();
    }

    function requestCamera() {
        var constraints = {
            video: {
                facingMode: useFrontCamera ? 'user' : 'environment',
                width: { ideal: 1280 },
                height: { ideal: 720 }
            }
        };

        showStatus('📹', 'Starting camera…');

        navigator.mediaDevices.getUserMedia(constraints).then(function (mediaStream) {
            stream = mediaStream;
            videoEl.srcObject = stream;

            videoEl.onloadedmetadata = function () {
                videoEl.play();
                // Size canvas to match video
                canvasEl.width = videoEl.videoWidth;
                canvasEl.height = videoEl.videoHeight;
                canvasCtx = canvasEl.getContext('2d', { willReadFrequently: true });

                hideStatus();
                scanning = true;
                scheduleScan();
            };
        }).catch(function (err) {
            var msg = 'Camera access denied';
            if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
                msg = 'No camera found';
            } else if (err.name === 'NotReadableError') {
                msg = 'Camera is in use by another app';
            } else if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
                msg = 'Camera permission denied';
            } else if (err.name === 'OverconstrainedError') {
                msg = 'Camera constraints not satisfiable';
            }
            showStatus('🚫', msg);
            console.warn('[camera-scanner] getUserMedia error:', err);
        });
    }

    function stopStream() {
        if (stream) {
            stream.getTracks().forEach(function (t) { t.stop(); });
            stream = null;
        }
        if (videoEl) videoEl.srcObject = null;
    }

    // ── Scan loop ──────────────────────────────────────────────
    function scheduleScan() {
        if (!scanning) return;
        scanTimer = setTimeout(function () {
            requestAnimationFrame(scanFrame);
        }, SCAN_INTERVAL);
    }

    function scanFrame() {
        if (!scanning || !videoEl || videoEl.readyState < 2) {
            scheduleScan();
            return;
        }

        // Draw current video frame to canvas
        canvasCtx.drawImage(videoEl, 0, 0, canvasEl.width, canvasEl.height);

        detector.detect(canvasEl).then(function (barcodes) {
            if (barcodes.length > 0) {
                handleDetection(barcodes[0]);
            }
            scheduleScan();
        }).catch(function (err) {
            console.warn('[camera-scanner] detect error:', err);
            scheduleScan();
        });
    }

    function pauseScanning() {
        clearScanTimer();
    }

    function resumeScanning() {
        if (scanning) scheduleScan();
    }

    function clearScanTimer() {
        if (scanTimer) {
            clearTimeout(scanTimer);
            scanTimer = null;
        }
    }

    // ── Barcode detected ───────────────────────────────────────
    function handleDetection(barcode) {
        var value = barcode.rawValue;
        if (!value) return;

        var now = Date.now();

        // Dedup: same barcode within window
        if (value === lastBarcode && (now - lastBarcodeTime) < DEDUP_WINDOW) {
            return;
        }

        // Rate limit: match scanner.js interval
        if ((now - lastSubmitTime) < RATE_LIMIT) {
            return;
        }

        lastBarcode     = value;
        lastBarcodeTime = now;
        lastSubmitTime  = now;

        // Inject into scan input and trigger HTMX submission
        var input = document.getElementById('scan-input');
        var form  = document.getElementById('scan-form');
        if (input && form) {
            input.value = value;

            // Mark that camera scanner will handle the sound for this scan,
            // so the global htmx:afterRequest handler skips the duplicate beep.
            window._cameraScanSoundPlayed = true;

            htmx.trigger(form, 'submit');
        }

        // Haptic feedback
        if (navigator.vibrate) {
            navigator.vibrate(100);
        }

        // Audio feedback (instant — server response sound is suppressed)
        if (typeof playSound === 'function') {
            playSound('bleep');
        }

        // Visual flash on viewfinder
        flashViewfinder();

        // After detection, ensure camera stays visible on mobile
        if (isMobileView()) {
            setTimeout(function () {
                var mount = document.getElementById('mobile-camera-mount');
                if (mount && mount.children.length > 0) {
                    mount.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            }, 300);
        }
    }

    function flashViewfinder() {
        if (!viewfinderEl) return;
        viewfinderEl.classList.add('detected');
        setTimeout(function () {
            viewfinderEl.classList.remove('detected');
        }, FLASH_DURATION);
    }

    // ── Status messages ────────────────────────────────────────
    function showStatus(icon, message) {
        var el = document.getElementById('camera-status');
        if (!el) return;
        el.innerHTML = '<div class="camera-status-icon">' + icon + '</div>' +
                       '<div>' + message + '</div>';
        el.style.display = '';
        if (videoEl) videoEl.style.display = 'none';
    }

    function hideStatus() {
        var el = document.getElementById('camera-status');
        if (el) el.style.display = 'none';
        if (videoEl) videoEl.style.display = '';
    }

    // ── Cleanup on page unload ─────────────────────────────────
    window.addEventListener('beforeunload', function () {
        if (stream) {
            stream.getTracks().forEach(function (t) { t.stop(); });
        }
    });

    // ── Suppress focus overlay when camera is active ───────────
    // Monkey-patch: intercept focus overlay display
    var origOverlayObserver = new MutationObserver(function (mutations) {
        if (!window._cameraScannerActive) return;
        mutations.forEach(function (m) {
            if (m.type === 'attributes' && m.attributeName === 'style') {
                var overlay = m.target;
                if (overlay.style.display === 'flex') {
                    overlay.style.display = 'none';
                }
            }
        });
    });

    // Start observing once DOM is ready
    function observeFocusOverlay() {
        var overlay = document.getElementById('focus-overlay');
        if (overlay) {
            origOverlayObserver.observe(overlay, { attributes: true });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', observeFocusOverlay);
    } else {
        observeFocusOverlay();
    }

})();
