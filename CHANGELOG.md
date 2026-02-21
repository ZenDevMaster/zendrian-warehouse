
1.1.1 Fix: Double beep on camera barcode scan

- Fixed duplicate audio feedback when scanning barcodes via the camera scanner
- Root cause: `playSound('bleep')` was called immediately in `camera-scanner.js` on detection, then called again when the HTMX server response returned with the `X-Play-Sound` header
- Fix: Camera scanner now sets `window._cameraScanSoundPlayed = true` before triggering the HTMX submission; the global `htmx:afterRequest` handler in `base.html` checks this flag and skips the duplicate sound
- The instant client-side beep is preserved for responsive feedback; only the redundant server-response beep is suppressed

Files changed:
- `static/js/camera-scanner.js` (modified — added `_cameraScanSoundPlayed` flag in `handleDetection()`)
- `templates/base.html` (modified — added flag check in `htmx:afterRequest` sound handler)

1.1.0 Camera-Based Barcode Scanning (BarcodeDetector API)

- Added camera-based barcode scanning as a progressive enhancement for Chrome on Android devices
- When the browser-native `BarcodeDetector` API is detected, a "📷 Use Camera" checkbox appears next to the scan input bar
- Checking the box activates the device camera with a live viewfinder in the sidebar, complete with barcode centering guide overlay and animated scan line
- Supports all major barcode formats: EAN-13, EAN-8, UPC-A, UPC-E, Code 128, Code 39, Code 93, Codabar, ITF, QR Code, Data Matrix
- Detected barcodes are automatically submitted through the existing HTMX scan pipeline — same audio feedback, visual feedback, and server processing as physical scanners
- Haptic feedback (vibration) on successful barcode detection via `navigator.vibrate()`
- Camera switching button (front/back) for flexible scanning positions
- Smart deduplication (2-second window) prevents re-scanning the same barcode still in frame
- Rate limiting (700ms) matches the physical scanner rate limit
- Battery-conscious: scan loop pauses when browser tab is hidden (Visibility API)
- Zero-overhead on unsupported browsers: `camera-scanner.js` is only loaded when `BarcodeDetector` is available
- No server-side changes required — pure client-side progressive enhancement

Files added/changed:
- `static/js/camera-scanner.js` (new)
- `templates/scan.html` (modified — added placeholder containers and conditional script loader)
- `static/css/style.css` (modified — added ~210 lines of camera scanner styles)
- `plans/CAMERA_BARCODE_SCANNER.md` (new — architecture design document)

1.0.0 initial release
