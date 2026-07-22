/** @odoo-module **/

import { HWPrinter } from "@point_of_sale/app/printer/hw_printer"; 
import { patch } from "@web/core/utils/patch";

// The base URL for your Python proxy (Keep this to ensure connection)
const PROXY_URL = "http://localhost:9100"; 

// --- 1. PATCH: HWPrinter to set URL and suppress error ---
patch(HWPrinter.prototype, {
    
    // Override setup to replace the default IoT URL with your custom proxy URL base
    setup(params) {
        // Call the original setup to initialize properties
        super.setup(...arguments);
        
        // **Override the URL** that HWPrinter uses for RPC calls
        this.url = PROXY_URL;
        
        console.log("[Ridhira Proxy] HWPrinter URL redirected to:", this.url);
    },
    
    /**
     * @override
     * The original method in Odoo 18 uses sendAction.
     * We override it to handle custom responses from our proxy.
     */
    async sendAction(data) {
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
// users to configure an 'ePos Printer' with a dummy IP, and we'll secretly
// route that print job to our Python Proxy via the HWPrinter logic!
import { EpsonPrinter } from "@pos_epson_printer/app/epson_printer";

patch(EpsonPrinter.prototype, {
    setup(params) {
        super.setup(...arguments);
        // Create an internal HWPrinter instance pointing to our proxy
        this.ridhira_proxy_printer = new HWPrinter({ url: PROXY_URL });
        console.log("[Ridhira Proxy] EpsonPrinter intercepted. Jobs will route to:", PROXY_URL);
    },

    async printReceipt(receipt) {
        // Delegate the receipt rendering and RPC request to the HWPrinter
        if (this.ridhira_proxy_printer) {
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