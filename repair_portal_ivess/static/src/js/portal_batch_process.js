/* Portal batch processing (/my/repairs/batch): pick N serial numbers, verify they
 * share the same stage, then start/finish the stage for the whole batch at once.
 *
 * Accumulation happens client-side: each scan/typed serial is resolved+validated
 * against the server (/my/repairs/batch/resolve) and, if eligible and homogeneous
 * with the current batch, added to the on-screen list. The server re-validates
 * everything authoritatively when "Comenzar"/"Fin de Etapa" are pressed — this
 * client-side list is UX only, never trusted for the actual state change.
 */
(function init() {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', run);
    } else {
        run();
    }

    function run() {
        var table = document.getElementById('batch-table');
        if (!table) return; // not the batch page

        var tbody = document.getElementById('batch-table-body');
        var emptyRow = document.getElementById('batch-table-empty-row');
        var alertBox = document.getElementById('batch-alert');
        var stageIndicator = document.getElementById('batch-stage-indicator');
        var input = document.getElementById('batch_barcode_input');
        var addBtn = document.getElementById('batch_barcode_add_btn');
        var cameraBtn = document.getElementById('batch-scan-camera-btn');
        var startBtn = document.getElementById('batch-btn-start');
        var finishBtn = document.getElementById('batch-btn-finish');

        var STAGE_BADGE = window.REPAIR_STAGE_BADGE || {};

        var items = [];       // {id, name, serial, stage, stage_label, stage_started, status, statusMessage}
        var batchStage = null;

        // ── JSON-RPC helper ──────────────────────────────────────────────────────
        function jsonRpc(url, params) {
            return fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ jsonrpc: '2.0', method: 'call', id: 1, params: params || {} }),
            })
                .then(function (r) { return r.json(); })
                .then(function (d) { return d.result; });
        }

        // ── Alerts ───────────────────────────────────────────────────────────────
        function showAlert(message, level) {
            alertBox.innerHTML =
                '<div class="alert alert-' + (level || 'danger') + ' alert-dismissible fade show" role="alert">' +
                escapeHtml(message) +
                '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>' +
                '</div>';
        }

        function clearAlert() {
            alertBox.innerHTML = '';
        }

        function escapeHtml(text) {
            var div = document.createElement('div');
            div.textContent = text == null ? '' : String(text);
            return div.innerHTML;
        }

        // ── Rendering ────────────────────────────────────────────────────────────
        function statusBadge(item) {
            switch (item.status) {
                case 'ok':
                    return '<span class="badge text-bg-success" title="Etapa iniciada">Iniciado</span>';
                case 'done':
                    return '<span class="badge text-bg-success" title="Etapa finalizada">Finalizado</span>';
                case 'error':
                    return '<span class="badge text-bg-danger" title="' + escapeHtml(item.statusMessage || '') + '">Error</span>';
                default:
                    return '<span class="badge text-bg-secondary">Pendiente</span>';
            }
        }

        function render() {
            tbody.innerHTML = '';
            if (!items.length) {
                tbody.appendChild(emptyRow);
                stageIndicator.textContent = 'Sin definir';
                stageIndicator.className = 'badge text-bg-secondary';
                startBtn.disabled = true;
                finishBtn.disabled = true;
                return;
            }

            items.forEach(function (item) {
                var tr = document.createElement('tr');
                if (item.status === 'error') tr.classList.add('table-danger');
                else if (item.status === 'ok' || item.status === 'done') tr.classList.add('table-success');

                var removeCell =
                    '<button type="button" class="btn btn-sm btn-outline-secondary batch-remove-btn" data-id="' +
                    item.id + '" title="Quitar del lote"><i class="fa fa-times"></i></button>';

                tr.innerHTML =
                    '<td>' + escapeHtml(item.serial) + '</td>' +
                    '<td>' + escapeHtml(item.name) + '</td>' +
                    '<td><span class="badge text-bg-' + (STAGE_BADGE[item.stage] || 'secondary') + '">' +
                    escapeHtml(item.stage_label) + '</span></td>' +
                    '<td>' + statusBadge(item) + '</td>' +
                    '<td class="text-end">' + removeCell + '</td>';
                tbody.appendChild(tr);
            });

            tbody.querySelectorAll('.batch-remove-btn').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    removeItem(parseInt(btn.getAttribute('data-id'), 10));
                });
            });

            if (batchStage) {
                stageIndicator.textContent = window.REPAIR_STAGE_LABELS && window.REPAIR_STAGE_LABELS[batchStage]
                    ? window.REPAIR_STAGE_LABELS[batchStage] : batchStage;
                stageIndicator.className = 'badge text-bg-' + (STAGE_BADGE[batchStage] || 'secondary');
            }
            startBtn.disabled = false;
            finishBtn.disabled = false;
        }

        function removeItem(id) {
            items = items.filter(function (i) { return i.id !== id; });
            if (!items.length) batchStage = null;
            render();
        }

        // ── Adding equipment to the batch ────────────────────────────────────────
        function addBarcode(rawValue) {
            var barcode = (rawValue || '').trim();
            if (!barcode) return;

            jsonRpc('/my/repairs/batch/resolve', { barcode: barcode })
                .then(function (res) {
                    if (!res || !res.ok) {
                        showAlert((res && res.message) || 'No se pudo resolver el número de serie.');
                        return;
                    }
                    var repair = res.repair;

                    if (items.some(function (i) { return i.id === repair.id; })) {
                        showAlert('El equipo "' + repair.name + '" ya está en el lote.', 'warning');
                        return;
                    }

                    if (batchStage && repair.stage !== batchStage) {
                        var batchLabel = window.REPAIR_STAGE_LABELS && window.REPAIR_STAGE_LABELS[batchStage]
                            ? window.REPAIR_STAGE_LABELS[batchStage] : batchStage;
                        showAlert(
                            'El equipo "' + repair.name + '" está en etapa "' + repair.stage_label +
                            '", distinta a la del lote ("' + batchLabel + '"). No se puede agregar.'
                        );
                        return;
                    }

                    batchStage = repair.stage;
                    items.push({
                        id: repair.id,
                        name: repair.name,
                        serial: repair.serial,
                        stage: repair.stage,
                        stage_label: repair.stage_label,
                        stage_started: repair.stage_started,
                        status: 'pending',
                        statusMessage: '',
                    });
                    clearAlert();
                    render();
                    if (window.navigator.vibrate) window.navigator.vibrate(60);
                })
                .catch(function () {
                    showAlert('Error de comunicación con el servidor. Intente nuevamente.');
                });
        }

        // ── Apply per-record results returned by start/finish ────────────────────
        function applyResults(results) {
            (results || []).forEach(function (r) {
                var item = items.find(function (i) { return i.id === r.id; });
                if (!item) return;
                if (r.ok) {
                    item.status = r.new_stage ? 'done' : 'ok';
                    item.statusMessage = '';
                    if (r.new_stage) {
                        item.stage = r.new_stage;
                        item.stage_label = (window.REPAIR_STAGE_LABELS && window.REPAIR_STAGE_LABELS[r.new_stage])
                            || r.new_stage;
                    }
                } else {
                    item.status = 'error';
                    item.statusMessage = r.error || 'Error desconocido.';
                }
            });
            render();
        }

        // ── Comenzar / Fin de Etapa ──────────────────────────────────────────────
        function startBatch() {
            if (!items.length) return;
            clearAlert();
            startBtn.disabled = true;
            var ids = items.map(function (i) { return i.id; });
            jsonRpc('/my/repairs/batch/start', { repair_ids: ids })
                .then(function (res) {
                    if (!res) {
                        showAlert('Error de comunicación con el servidor.');
                        return;
                    }
                    if (res.results) applyResults(res.results);
                    if (!res.ok) {
                        showAlert(res.message || 'No se pudo iniciar el lote.');
                    } else {
                        showAlert('Lote iniciado correctamente.', 'success');
                    }
                })
                .catch(function () {
                    showAlert('Error de comunicación con el servidor.');
                })
                .finally(function () {
                    startBtn.disabled = items.length === 0;
                });
        }

        function finishBatch() {
            if (!items.length) return;
            clearAlert();
            finishBtn.disabled = true;
            var ids = items.map(function (i) { return i.id; });
            jsonRpc('/my/repairs/batch/finish', { repair_ids: ids })
                .then(function (res) {
                    if (!res) {
                        showAlert('Error de comunicación con el servidor.');
                        return;
                    }
                    if (res.results) applyResults(res.results);
                    if (!res.ok) {
                        showAlert(res.message || 'No se pudo finalizar la etapa del lote.');
                        return;
                    }
                    showAlert('Etapa finalizada correctamente para el lote.', 'success');
                    // Quitar del lote los equipos procesados con éxito; los que fallaron
                    // quedan visibles para que el operario decida qué hacer.
                    items = items.filter(function (i) { return i.status !== 'done'; });
                    if (!items.length) batchStage = null;
                    render();
                })
                .catch(function () {
                    showAlert('Error de comunicación con el servidor.');
                })
                .finally(function () {
                    finishBtn.disabled = items.length === 0;
                });
        }

        // ── Input handlers ───────────────────────────────────────────────────────
        input.focus();
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                addBarcode(input.value);
                input.value = '';
                input.focus();
            }
        });
        addBtn.addEventListener('click', function () {
            addBarcode(input.value);
            input.value = '';
            input.focus();
        });
        if (cameraBtn) {
            cameraBtn.addEventListener('click', function () {
                if (!window.RepairScanner) return;
                window.RepairScanner.open(addBarcode);
            });
        }
        startBtn.addEventListener('click', startBatch);
        finishBtn.addEventListener('click', finishBatch);

        render();
    }
}());
