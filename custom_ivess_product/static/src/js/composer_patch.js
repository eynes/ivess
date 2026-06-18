/** @odoo-module **/

import { Composer } from "@mail/core/common/composer";
import { patch } from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";

    patch(Composer.prototype, {
    setup() {
        super.setup();

        onMounted(() => {
            const composer = this.props.composer;
            const model = composer?.thread?.model;
            if (model === "stock.request.order") {
                this.onClickFullComposer();
            }
        });
    },
});
