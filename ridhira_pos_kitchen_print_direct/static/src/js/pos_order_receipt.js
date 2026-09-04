/** @odoo-module **/

import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

patch(PosOrder.prototype, {
    export_for_printing() {
        const result = super.export_for_printing(...arguments);
        if (this.config) {
            result.customer_receipt_font_size = this.config.customer_receipt_font_size;
            result.customer_receipt_is_bold = this.config.customer_receipt_is_bold;
        }
        return result;
    }
});
