/* Portal barcode camera scanner for /my/repairs/scan */
document.addEventListener('DOMContentLoaded', function () {
    var cameraBtn = document.getElementById('repair-scan-camera-btn');
    if (!cameraBtn) return;

    var barcodeInput = document.getElementById('repair_barcode_input');
    var scanForm = document.getElementById('repair_scan_form');

    var stream = null;
    var detector = null;
    var rafId = null;
    var active = false;

    // Build fullscreen overlay dynamically
    var overlay = document.createElement('div');
    overlay.style.cssText = [
        'display:none', 'position:fixed', 'top:0', 'left:0',
        'width:100%', 'height:100%', 'background:rgba(0,0,0,0.92)',
        'z-index:9999', 'flex-direction:column',
        'align-items:center', 'justify-content:center',
    ].join(';');

    var videoWrap = document.createElement('div');
    videoWrap.style.cssText = 'position:relative;width:92%;max-width:480px;';

    var video = document.createElement('video');
    video.setAttribute('autoplay', '');
    video.setAttribute('playsinline', '');   // required on iOS Safari
    video.setAttribute('muted', '');
    video.style.cssText = 'width:100%;border-radius:10px;display:block;';

    // Scan-guide rectangle overlay
    var guide = document.createElement('div');
    guide.style.cssText = [
        'position:absolute', 'top:50%', 'left:50%',
        'transform:translate(-50%,-50%)',
        'width:72%', 'height:32%',
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
    hint.textContent = 'Apunte la cámara al código de barras del equipo';

    videoWrap.appendChild(video);
    videoWrap.appendChild(guide);
    overlay.appendChild(videoWrap);
    overlay.appendChild(cancelBtn);
    overlay.appendChild(hint);
    document.body.appendChild(overlay);

    function stopCamera() {
        active = false;
        if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
        if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; }
        video.srcObject = null;
        overlay.style.display = 'none';
    }

    cancelBtn.addEventListener('click', stopCamera);

    // ZXing-based detector (fallback for older iOS Safari < 17)
    function buildZXingDetector(ZXing) {
        var hints = new Map([
            [ZXing.DecodeHintType.POSSIBLE_FORMATS, [
                ZXing.BarcodeFormat.CODE_128,
                ZXing.BarcodeFormat.CODE_39,
                ZXing.BarcodeFormat.EAN_13,
                ZXing.BarcodeFormat.EAN_8,
                ZXing.BarcodeFormat.QR_CODE,
                ZXing.BarcodeFormat.DATA_MATRIX,
                ZXing.BarcodeFormat.ITF,
            ]],
            [ZXing.DecodeHintType.TRY_HARDER, true],
        ]);
        var reader = new ZXing.MultiFormatReader();
        reader.setHints(hints);
        return {
            detect: function (videoEl) {
                if (videoEl.readyState < 2) return Promise.resolve([]);
                var canvas = document.createElement('canvas');
                canvas.width = videoEl.videoWidth;
                canvas.height = videoEl.videoHeight;
                canvas.getContext('2d').drawImage(videoEl, 0, 0);
                var luminance = new ZXing.HTMLCanvasElementLuminanceSource(canvas);
                var bitmap = new ZXing.BinaryBitmap(new ZXing.HybridBinarizer(luminance));
                try {
                    var result = reader.decodeWithState(bitmap);
                    return Promise.resolve([{ rawValue: result.getText() }]);
                } catch (e) {
                    return Promise.resolve([]);
                }
            },
        };
    }

    function getDetector() {
        if (detector) return Promise.resolve(detector);

        // Native BarcodeDetector (Chrome, Safari 17+ iOS)
        if ('BarcodeDetector' in window) {
            return BarcodeDetector.getSupportedFormats().then(function (formats) {
                detector = new BarcodeDetector({ formats: formats });
                return detector;
            });
        }

        // ZXing fallback — use Odoo's own bundled library
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

    function scanFrame(det) {
        if (!active) return;
        det.detect(video)
            .then(function (codes) {
                if (codes && codes.length > 0) {
                    var value = codes[0].rawValue;
                    if (window.navigator.vibrate) window.navigator.vibrate(100);
                    stopCamera();
                    barcodeInput.value = value;
                    scanForm.submit();
                } else {
                    rafId = requestAnimationFrame(function () { scanFrame(det); });
                }
            })
            .catch(function () {
                if (active) rafId = requestAnimationFrame(function () { scanFrame(det); });
            });
    }

    cameraBtn.addEventListener('click', function () {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            alert('La cámara no está disponible. Acceda al sitio usando HTTPS.');
            return;
        }

        overlay.style.display = 'flex';

        navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false })
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
    });
});
