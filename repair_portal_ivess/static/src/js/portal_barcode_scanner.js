/* Portal camera barcode scanner.
 *
 * Exposes a reusable `window.RepairScanner.open(onDetect)` API (ZXing-based,
 * DataMatrix/QR/Aztec/Code128/EAN) used by both /my/repairs/scan (single
 * equipment) and /my/repairs/batch (batch processing).
 */
(function init() {
    var stream = null;
    var detector = null;
    var rafId = null;
    var active = false;
    var currentOnDetect = null;

    var overlay = null;
    var video = null;
    var guide = null;

    // ── Overlay (built lazily, once, on first open()) ───────────────────────────
    function ensureOverlay() {
        if (overlay) return;

        overlay = document.createElement('div');
        overlay.style.cssText = [
            'display:none', 'position:fixed', 'top:0', 'left:0',
            'width:100%', 'height:100%', 'background:rgba(0,0,0,0.92)',
            'z-index:9999', 'flex-direction:column',
            'align-items:center', 'justify-content:center',
        ].join(';');

        var videoWrap = document.createElement('div');
        videoWrap.style.cssText = 'position:relative;width:92%;max-width:480px;';

        video = document.createElement('video');
        video.setAttribute('autoplay', '');
        video.setAttribute('playsinline', '');
        video.setAttribute('muted', '');
        video.style.cssText = 'width:100%;border-radius:10px;display:block;';

        // Guide square — sized in JS once the video is playing
        guide = document.createElement('div');
        guide.style.cssText = [
            'position:absolute', 'top:50%', 'left:50%',
            'transform:translate(-50%,-50%)',
            'width:70%', 'height:70%',   // overridden in JS after video plays
            'border:2.5px solid #875a7b', 'border-radius:8px',
            'pointer-events:none',
            'box-shadow:0 0 0 9999px rgba(0,0,0,0.45)',
        ].join(';');

        var cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'btn btn-light mt-3 px-4';
        cancelBtn.innerHTML = '<i class="fa fa-times me-1"></i>Cancelar';

        var hint = document.createElement('p');
        hint.className = 'text-white mt-2 small text-center px-3';
        hint.textContent = 'Centre el código en el cuadro y acérquese';

        videoWrap.appendChild(video);
        videoWrap.appendChild(guide);
        overlay.appendChild(videoWrap);
        overlay.appendChild(cancelBtn);
        overlay.appendChild(hint);
        document.body.appendChild(overlay);

        cancelBtn.addEventListener('click', stopCamera);
    }

    // ── Stop ──────────────────────────────────────────────────────────────────
    function stopCamera() {
        active = false;
        if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
        if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; }
        if (video) video.srcObject = null;
        if (overlay) overlay.style.display = 'none';
        currentOnDetect = null;
    }

    // ── ZXing detector ────────────────────────────────────────────────────────
    function buildZXingDetector(ZXing) {
        var hints = new Map([
            [ZXing.DecodeHintType.POSSIBLE_FORMATS, [
                ZXing.BarcodeFormat.DATA_MATRIX,
                ZXing.BarcodeFormat.QR_CODE,
                ZXing.BarcodeFormat.AZTEC,
                ZXing.BarcodeFormat.CODE_128,
                ZXing.BarcodeFormat.EAN_13,
                ZXing.BarcodeFormat.EAN_8,
            ]],
            [ZXing.DecodeHintType.TRY_HARDER, true],
        ]);
        var reader = new ZXing.MultiFormatReader();
        reader.setHints(hints);

        return {
            detect: function (videoEl) {
                if (videoEl.readyState < 2) return Promise.resolve([]);
                var vw = videoEl.videoWidth;
                var vh = videoEl.videoHeight;
                var dw = videoEl.clientWidth;
                var dh = videoEl.clientHeight;
                if (!vw || !vh || !dw || !dh) return Promise.resolve([]);

                // Guide is a square = 88% of the shorter display dimension, centered.
                // Must match the sizing in the 'playing' handler below.
                var guideDisplaySize = Math.min(dw, dh) * 0.88;
                var guideDx = (dw - guideDisplaySize) / 2;
                var guideDy = (dh - guideDisplaySize) / 2;

                // Map display coords → video frame coords
                var sx = vw / dw;
                var sy = vh / dh;
                var cropX = Math.max(0, Math.round(guideDx * sx));
                var cropY = Math.max(0, Math.round(guideDy * sy));
                var cropW = Math.min(Math.round(guideDisplaySize * sx), vw - cropX);
                var cropH = Math.min(Math.round(guideDisplaySize * sy), vh - cropY);

                var canvas = document.createElement('canvas');
                canvas.width = cropW;
                canvas.height = cropH;
                canvas.getContext('2d').drawImage(
                    videoEl,
                    cropX, cropY, cropW, cropH,
                    0, 0, cropW, cropH
                );

                var lum = new ZXing.HTMLCanvasElementLuminanceSource(canvas);
                var bmp = new ZXing.BinaryBitmap(new ZXing.HybridBinarizer(lum));
                try {
                    var result = reader.decodeWithState(bmp);
                    return Promise.resolve([{ rawValue: result.getText() }]);
                } catch (e) {
                    return Promise.resolve([]);
                }
            },
        };
    }

    function getDetector() {
        if (detector) return Promise.resolve(detector);
        return new Promise(function (resolve, reject) {
            if (window.ZXing) {
                detector = buildZXingDetector(window.ZXing);
                return resolve(detector);
            }
            var script = document.createElement('script');
            script.src = '/web/static/lib/zxing-library/zxing-library.js';
            script.onload = function () {
                detector = buildZXingDetector(window.ZXing);
                resolve(detector);
            };
            script.onerror = function () {
                reject(new Error('No se pudo cargar el lector de códigos de barras.'));
            };
            document.head.appendChild(script);
        });
    }

    // ── Scan loop ─────────────────────────────────────────────────────────────
    function scanFrame(det) {
        if (!active) return;
        det.detect(video)
            .then(function (codes) {
                if (codes && codes.length > 0) {
                    var value = codes[0].rawValue;
                    // Ignore spurious 1–2 char reads (e.g. Code39 false positives
                    // like "G" misread from the Data Matrix finder pattern).
                    if (!value || value.length < 3) {
                        rafId = requestAnimationFrame(function () { scanFrame(det); });
                        return;
                    }
                    // Odoo ZPL uses GS1 AI "21" (serial number) prefix: "21" + lot_name.
                    // Strip it so the search matches stock.lot.name directly.
                    if (/^21\d/.test(value) && value.length > 2) {
                        value = value.slice(2);
                    }
                    if (window.navigator.vibrate) window.navigator.vibrate(100);
                    var onDetect = currentOnDetect;
                    stopCamera();
                    if (onDetect) onDetect(value);
                } else {
                    rafId = requestAnimationFrame(function () { scanFrame(det); });
                }
            })
            .catch(function () {
                if (active) rafId = requestAnimationFrame(function () { scanFrame(det); });
            });
    }

    // ── Public API ────────────────────────────────────────────────────────────
    // window.RepairScanner.open(onDetect): opens the camera overlay; onDetect(value)
    // is called once with the decoded (GS1-stripped) value, after the camera stops.
    function openScanner(onDetect) {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            alert('La cámara no está disponible. Acceda al sitio usando HTTPS.');
            return;
        }

        ensureOverlay();
        currentOnDetect = onDetect;
        overlay.style.display = 'flex';

        // Once the video is playing, size the guide to a square that fits the frame.
        // This MUST match the crop calculation in detect() above. Re-registered on
        // every open() so the guide stays correct across repeated scans/orientations.
        video.addEventListener('playing', function () {
            var dw = video.clientWidth;
            var dh = video.clientHeight;
            var gsz = Math.round(Math.min(dw, dh) * 0.88);
            guide.style.width = gsz + 'px';
            guide.style.height = gsz + 'px';
        }, { once: true });

        navigator.mediaDevices.getUserMedia({
            video: {
                facingMode: { ideal: 'environment' },
                width: { ideal: 1280 },
                height: { ideal: 720 },
            },
            audio: false,
        })
            .then(function (s) {
                stream = s;
                video.srcObject = s;
                return video.play();
            })
            .then(function () { return getDetector(); })
            .then(function (det) {
                active = true;
                scanFrame(det);
            })
            .catch(function (err) {
                stopCamera();
                var msg = 'No se pudo acceder a la cámara.';
                if (err.name === 'NotAllowedError') {
                    msg = 'Permiso de cámara denegado. Habilítelo en Ajustes → Safari → ' + location.hostname + ' → Cámara.';
                } else if (err.name === 'NotFoundError') {
                    msg = 'No se encontró ninguna cámara en el dispositivo.';
                } else if (err.message) {
                    msg = err.message;
                }
                alert(msg);
            });
    }

    window.RepairScanner = { open: openScanner };

    // ── Adapter for /my/repairs/scan (single-equipment scan page) ──────────────
    function bindScanPage() {
        var cameraBtn = document.getElementById('repair-scan-camera-btn');
        if (!cameraBtn) return;

        var barcodeInput = document.getElementById('repair_barcode_input');
        var scanForm = document.getElementById('repair_scan_form');

        cameraBtn.addEventListener('click', function () {
            window.RepairScanner.open(function (value) {
                barcodeInput.value = value;
                scanForm.submit();
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindScanPage);
    } else {
        bindScanPage();
    }
}());
