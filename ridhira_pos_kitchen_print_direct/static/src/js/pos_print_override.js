/** @odoo-module **/

import { HWPrinter } from "@point_of_sale/app/utils/printer/hw_printer"; 
import { EpsonPrinter } from "@point_of_sale/app/utils/printer/epson_printer";
import { PosStore } from "@point_of_sale/app/services/pos_store";
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
        
        // Inject SaaS API Key if available
        if (window.ridhira_api_key) {
            data.api_key = window.ridhira_api_key;
        } else if (this.pos && this.pos.config && this.pos.config.ridhira_kitchen_print_api_key) {
            data.api_key = this.pos.config.ridhira_kitchen_print_api_key;
        }
        
        try {
            const result = await super.sendAction(data);
            
            // If the proxy returns our custom success flag, normalize it
            if (result && result.success) {
                return true;
            }
            // Handle Proxy SaaS License Expiration
            if (result && result.error && result.error.message === "License Expired") {
                console.error("[Ridhira Proxy] SaaS License Expired.");
                if (window.posmodel && window.posmodel.popup) {
                     window.posmodel.popup.add("ErrorPopup", {
                        title: "Kitchen Print Failed: License Expired",
                        body: "Your Proxy Subscription has expired. Please visit billing.yourdomain.com to renew.",
                    });
                } else if (this.pos && this.pos.env && this.pos.env.services && this.pos.env.services.popup) {
                    this.pos.env.services.popup.add("ErrorPopup", {
                        title: "Kitchen Print Failed: License Expired",
                        body: "Your Proxy Subscription has expired. Please visit billing.yourdomain.com to renew.",
                    });
                } else if (this.pos && this.pos.popup) {
                     this.pos.popup.add("ErrorPopup", {
                        title: "Kitchen Print Failed: License Expired",
                        body: "Your Proxy Subscription has expired. Please visit billing.yourdomain.com to renew.",
                    });
                } else {
                    alert("Kitchen Print Failed: Your Proxy Subscription has expired. Please visit billing.yourdomain.com to renew.");
                }
                return false;
            }
            
            return result || true;
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

patch(EpsonPrinter.prototype, {
    setup(params) {
        super.setup(...arguments);
        
        // Dynamically build the proxy URL using the IP configured in Odoo.
        // If they enter '192.168.1.100' as the Epson printer IP, it will target that IP on port 9100.
        const proxyIp = params.ip || "localhost";
        const proxyUrl = `http://${proxyIp}:9100`;

        // Create an internal HWPrinter instance pointing to our proxy
        this.ridhira_proxy_printer = new HWPrinter({ url: proxyUrl });
        // Inject POS instance so HWPrinter can access the API Key
        this.ridhira_proxy_printer.pos = this.pos || params.pos;
        console.log("[Ridhira Proxy] EpsonPrinter intercepted. Jobs will route to:", proxyUrl);
    },

    async printReceipt(receipt) {
        console.log("[Ridhira Proxy] EpsonPrinter.printReceipt called!");
        // Delegate the receipt rendering and RPC request to the HWPrinter
        if (this.ridhira_proxy_printer) {
            console.log("[Ridhira Proxy] Routing receipt to HWPrinter...");
            // Pass the Odoo printer name down to the HWPrinter so it can route it to the proxy
            this.ridhira_proxy_printer.proxy_printer_name = this.config?.name || "POS_Printer";
            const result = await this.ridhira_proxy_printer.printReceipt(receipt);
            console.log("[Ridhira Proxy] HWPrinter.printReceipt returned:", result);
            document.body.dataset.ridhiraLastPrint = Date.now();
            return result;
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

// --- 3. PATCH: PosStore to expose API Key globally ---
patch(PosStore.prototype, {
    async processServerData() {
        await super.processServerData(...arguments);
        console.log("[Ridhira Proxy] Config loaded:", this.config);
        console.log("[Ridhira Proxy] API Key from config:", this.config ? this.config.ridhira_kitchen_print_api_key : "config is null");
        if (this.config && this.config.ridhira_kitchen_print_api_key) {
            window.ridhira_api_key = this.config.ridhira_kitchen_print_api_key;
        }
    }
});