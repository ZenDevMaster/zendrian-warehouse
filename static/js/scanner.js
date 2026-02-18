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

    // After HTMX swap, clear input and re-focus
    document.addEventListener('htmx:afterSwap', function () {
        setTimeout(function () {
            const inp = document.getElementById(scanInputId);
            if (inp) {
                inp.value = '';
                inp.focus();
            }
            const ov = document.getElementById(overlayId);
            if (ov) ov.style.display = 'none';
        }, 50);
    });

    // Initial focus
    input.focus();
}

function refocusInput() {
    const input = document.getElementById(scanInputId);
    const overlay = document.getElementById(overlayId);
    if (input) {
        input.focus();
        input.value = '';
    }
    if (overlay) overlay.style.display = 'none';
}
