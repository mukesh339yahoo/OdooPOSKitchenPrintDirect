/** @odoo-module **/

import { HWPrinter } from "@point_of_sale/app/printer/hw_printer";
import { patch } from "@web/core/utils/patch";

// Base URL of the Flask print proxy (same machine as printers or reachable from the browser).
export const PROXY_URL = "http://localhost:9100";

patch(HWPrinter.prototype, {
    setup(params) {
        super.setup(...arguments);
        this.url = PROXY_URL;
    },

    sendPrintingJob(img) {
        const data = { action: "print_receipt", receipt: img };
        if (this.config?.name) {
            data.printer_name = this.config.name;
        }
        return this.sendAction(data);
    },
});
