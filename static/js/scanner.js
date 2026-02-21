/**
 * Barcode Scanner Input Management
 *
 * Bluetooth barcode scanners act as keyboard input devices.
 * This module:
 * 1. Keeps a hidden input always focused
 * 2. Buffers rapid keystrokes (scanner sends chars fast then Enter)
 * 3. Submits via HTMX on Enter
 * 4. Shows an overlay if focus is lost
 * 5. Re-focuses after each scan completes
 */

let scanInputId = null;
let overlayId = null;
let formId = null;
let lastSubmitTime = 0;
const MIN_SUBMIT_INTERVAL = 700; // ms — matches server-side rate limit

function initScanner(inputId, overlayElId, formElId) {
    scanInputId = inputId;
    overlayId = overlayElId;
    formId = formElId;

    const input = document.getElementById(scanInputId);
    const overlay = document.getElementById(overlayId);

    if (!input) return;

    // Focus management
    input.addEventListener('blur', function () {
        // Small delay to allow HTMX form submission to complete
        setTimeout(function () {
            if (document.activeElement !== input &&
                document.activeElement.tagName !== 'INPUT' &&
                document.activeElement.tagName !== 'SELECT') {
                if (overlay) overlay.style.display = 'flex';
            }
        }, 300);
    });

    // Submit on Enter, prevent default form submission (HTMX handles it)
    input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
            e.preventDefault();

            // Rate limit check
            const now = Date.now();
            if (now - lastSubmitTime < MIN_SUBMIT_INTERVAL) {
                // Too fast — play error sound and reject
                playSound('error');
                input.value = '';
                return;
            }
            lastSubmitTime = now;

            // Trigger HTMX submission
            htmx.trigger(document.getElementById(formId), 'submit');
        }
    });

    // After HTMX swap, clear input and re-focus (skip focus when camera active)
    document.addEventListener('htmx:afterSwap', function () {
        setTimeout(function () {
            const inp = document.getElementById(scanInputId);
            if (inp) {
                inp.value = '';
                // Skip focus when camera scanner is active to prevent
                // the browser from scrolling away from the viewfinder
                if (!window._cameraScannerActive) {
                    inp.focus();
                }
            }
            const ov = document.getElementById(overlayId);
            if (ov) ov.style.display = 'none';

            // Show floating toast when camera scanner is active
            if (window._cameraScannerActive && typeof window._showCameraScanToast === 'function') {
                window._showCameraScanToast();
            }
        }, 50);
    });

    // Initial focus
    input.focus();

    // Keyboard toggle initialization
    var hideKbToggle = document.getElementById('hide-keyboard-toggle');
    var hideKbLabel = document.getElementById('keyboard-toggle-area');

    if (hideKbToggle && hideKbLabel) {
        // Restore saved preference
        var savedPref = localStorage.getItem('zendrian_hide_keyboard');
        if (savedPref === 'true') {
            hideKbToggle.checked = true;
            hideKbLabel.classList.add('active');
            input.setAttribute('inputmode', 'none');
        }

        hideKbToggle.addEventListener('change', function() {
            var hide = hideKbToggle.checked;
            localStorage.setItem('zendrian_hide_keyboard', hide);
            hideKbLabel.classList.toggle('active', hide);

            if (hide) {
                input.setAttribute('inputmode', 'none');
                // Briefly blur to dismiss keyboard, then refocus
                input.blur();
                setTimeout(function() { input.focus(); }, 50);
            } else {
                // Only restore if camera scanner isn't active
                if (!window._cameraScannerActive) {
                    input.setAttribute('inputmode', 'text');
                    // Blur then re-focus so the mobile browser
                    // re-evaluates inputmode and shows the keyboard
                    input.blur();
                    setTimeout(function() { input.focus(); }, 50);
                }
            }
        });
    }
}

// Called by camera-scanner.js to suppress/restore keyboard
window.setScanInputMode = function(mode) {
    var input = document.getElementById('scan-input');
    if (!input) return;
    input.setAttribute('inputmode', mode);
    // Always blur then re-focus so the mobile browser
    // re-evaluates inputmode (shows or hides the keyboard)
    input.blur();
    setTimeout(function() { input.focus(); }, 50);
};

function refocusInput() {
    const input = document.getElementById(scanInputId);
    const overlay = document.getElementById(overlayId);
    if (input) {
        input.focus();
        input.value = '';
    }
    if (overlay) overlay.style.display = 'none';
}
