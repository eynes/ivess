/* Sincroniza los inputs de rango de fecha de la barra de filtros: al cambiar
 * "Desde" actualiza el mínimo permitido en "Hasta" y viceversa, para que la
 * validación nativa del navegador bloquee un rango invertido antes de
 * enviarlo. Mejora progresiva: el servidor (_maint_parse_filters en
 * controllers/portal.py) valida esto igual e informa con un alert-danger
 * aunque este script no corra. */
(function init() {
    function bind(fromId, toId) {
        var fromInput = document.getElementById(fromId);
        var toInput = document.getElementById(toId);
        if (!fromInput || !toInput) {
            return;
        }
        fromInput.addEventListener('change', function () {
            toInput.min = fromInput.value || '';
        });
        toInput.addEventListener('change', function () {
            fromInput.max = toInput.value || '';
        });
    }
    bind('o_maint_f_date_from', 'o_maint_f_date_to');
})();
