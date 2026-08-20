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

    // Opt-in trace for diagnosing keyboard-wedge scanners on mobile devices.
    const inputLog = [];
    let inputLogEnabled = false;
    let inputLogPanel = null;
    let pendingAndroidComposition = null;
    let sawAndroidCompositionKey = false;

    function recordInputEvent(name, detail) {
        if (!inputLogEnabled) return;
        inputLog.push({
            time: new Date().toISOString().slice(11, 23),
            name: name,
            detail: detail,
            value: input.value,
        });
        if (inputLog.length > 100) inputLog.shift();
        inputLogPanel.value = inputLog.map(function (entry) {
            return entry.time + ' ' + entry.name + ' ' + entry.detail + ' value="' + entry.value + '"';
        }).join('\n');
        inputLogPanel.scrollTop = inputLogPanel.scrollHeight;
    }

    function createInputLog() {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = 'Input Log';
        button.style.cssText = 'padding:6px 10px;border:1px solid #64748b;border-radius:6px;background:#fff;color:#334155;font-size:.85rem;white-space:nowrap;';

        inputLogPanel = document.createElement('textarea');
        inputLogPanel.readOnly = true;
        inputLogPanel.style.cssText = 'display:none;position:fixed;z-index:2000;left:12px;right:12px;bottom:12px;height:220px;padding:10px;background:#0f172a;color:#e2e8f0;border:1px solid #64748b;border-radius:8px;font:12px monospace;';
        inputLogPanel.setAttribute('aria-label', 'Scanner input log');
        document.body.appendChild(inputLogPanel);

        button.addEventListener('click', function () {
            inputLogEnabled = !inputLogEnabled;
            inputLog.length = 0;
            inputLogPanel.value = '';
            inputLogPanel.style.display = inputLogEnabled ? 'block' : 'none';
            button.textContent = inputLogEnabled ? 'Stop Log' : 'Input Log';
            button.style.background = inputLogEnabled ? '#dbeafe' : '#fff';
            if (inputLogEnabled) {
                recordInputEvent('log', 'started inputmode=' + input.getAttribute('inputmode'));
            }
        });

        input.parentElement.parentElement.appendChild(button);
    }

    createInputLog();

    input.addEventListener('beforeinput', function (e) {
        recordInputEvent('beforeinput', 'type=' + e.inputType + ' data=' + JSON.stringify(e.data));
        if (sawAndroidCompositionKey &&
            e.inputType === 'insertCompositionText' &&
            /^\d$/.test(e.data || '')) {
            pendingAndroidComposition = {
                digit: e.data,
                value: input.value,
                time: Date.now(),
            };
            setTimeout(function () { pendingAndroidComposition = null; }, 100);
        }
        sawAndroidCompositionKey = false;
    });

    input.addEventListener('input', function (e) {
        recordInputEvent('input', 'type=' + e.inputType + ' data=' + JSON.stringify(e.data));
    });

    input.addEventListener('keyup', function (e) {
        recordInputEvent('keyup', 'key=' + JSON.stringify(e.key) + ' code=' + e.code + ' keyCode=' + e.keyCode);
    });

    // Focus management
    input.addEventListener('blur', function () {
        recordInputEvent('blur', '');
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
        if (pendingAndroidComposition &&
            (Date.now() - pendingAndroidComposition.time) < 100 &&
            e.key === pendingAndroidComposition.digit &&
            e.code === 'Digit' + pendingAndroidComposition.digit) {
            // Do not remove without testing Android keyboard-wedge scanners.
            // Chrome on the warehouse tablet emits keyCode 229 followed by an
            // insertCompositionText digit, then the scanner's real DigitN key.
            // Removing the composition digit here preserves normal text input
            // while preventing the duplicated leading digit in SKU scans.
            input.value = pendingAndroidComposition.value;
            recordInputEvent('composition', 'removed duplicate Android IME digit');
            pendingAndroidComposition = null;
        }
        sawAndroidCompositionKey = e.keyCode === 229;
        recordInputEvent('keydown', 'key=' + JSON.stringify(e.key) + ' code=' + e.code + ' keyCode=' + e.keyCode);
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
            recordInputEvent('submit', '');
            htmx.trigger(document.getElementById(formId), 'submit');
        }
    });

    // After HTMX swap, clear input and re-focus (skip focus when camera active)
    document.addEventListener('htmx:afterSwap', function () {
        setTimeout(function () {
            const inp = document.getElementById(scanInputId);
            if (inp) {
                recordInputEvent('afterSwap', 'before clear');
                inp.value = '';
                recordInputEvent('afterSwap', 'after clear');
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
