/** @odoo-module **/

import { HWPrinter } from "@point_of_sale/app/printer/hw_printer"; 
import { patch } from "@web/core/utils/patch";

// --- 1. PATCH: HWPrinter to suppress error ---
patch(HWPrinter.prototype, {
    
    /**
     * @override
     * The original method in Odoo 18 uses sendAction.
     * We override it to handle custom responses from our proxy.
     */
    async sendAction(data) {
        // Inject the printer name if it's available (either passed from Epson wrapper or native config)
        if (this.proxy_printer_name) {
            data.printer_name = this.proxy_printer_name;
        } else if (this.config && this.config.name) {
            data.printer_name = this.config.name;
        }
        
        try {
            const result = await super.sendAction(data);
            // If the proxy returns our custom success flag, normalize it
            if (result && result.success) {
                return true;
            }
            return result;
        } catch (error) {
            // Suppress connection errors or handle them gracefully
            console.warn("[Ridhira Proxy] Print action failed or returned error structure, returning true to suppress:", error);
            return true;
        }
    }
});

// --- 2. PATCH: EpsonPrinter to intercept and route to HWPrinter ---
// In Odoo Enterprise, IoT Box selection might be restricted. This allows
// users to configure an 'ePos Printer' with their Proxy IP, and we'll secretly
// route that print job to our Python Proxy via the HWPrinter logic!
import { EpsonPrinter } from "@pos_epson_printer/app/epson_printer";

patch(EpsonPrinter.prototype, {
    setup(params) {
        super.setup(...arguments);
        
        // Dynamically build the proxy URL using the IP configured in Odoo.
        // If they enter '192.168.1.100' as the Epson printer IP, it will target that IP on port 9100.
        const proxyIp = params.ip || "localhost";
        const proxyUrl = `http://${proxyIp}:9100`;

        // Create an internal HWPrinter instance pointing to our proxy
        this.ridhira_proxy_printer = new HWPrinter({ url: proxyUrl });
        console.log("[Ridhira Proxy] EpsonPrinter intercepted. Jobs will route to:", proxyUrl);
    },

    async printReceipt(receipt) {
        // Delegate the receipt rendering and RPC request to the HWPrinter
        if (this.ridhira_proxy_printer) {
            // Pass the Odoo printer name down to the HWPrinter so it can route it to the proxy
            this.ridhira_proxy_printer.proxy_printer_name = this.config?.name || "POS_Printer";
            return await this.ridhira_proxy_printer.printReceipt(receipt);
        }
        return super.printReceipt(...arguments);
    },

    async openCashbox() {
        if (this.ridhira_proxy_printer) {
            return await this.ridhira_proxy_printer.openCashbox();
        }
        return super.openCashbox(...arguments);
    }
});