/** @odoo-module **/

import { EpsonPrinter } from "@point_of_sale/app/utils/printer/epson_printer";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";

// --- 1. PATCH: EpsonPrinter to intercept and route to Ridhira Python Proxy ---
// In Odoo, users configure a network printer with 'epson_epos' and enter the
// Proxy IP (e.g. localhost or 192.168.x.x). We route jobs to the Ridhira Python Proxy.

patch(EpsonPrinter.prototype, {
    setup(params) {
        super.setup(...arguments);
        const printer = params?.printer || {};
        this.printer = printer;
        this.proxyIp = printer.printer_ip || params?.ip || "localhost";
        this.proxyUrl = `http://${this.proxyIp}:9100`;
        this.proxy_printer_name = printer.name || "POS_Printer";
        this.ridhira_proxy_printer = this;
        console.log(`[Ridhira Proxy] EpsonPrinter intercepted for ${this.proxy_printer_name}. Jobs will route to: ${this.proxyUrl}`);
    },

    /**
     * @override
     * In Odoo 20, BasePrinter/EpsonPrinter sendPrintingJob receives the HTMLCanvasElement or string.
     * We convert it to base64 and send it directly to our Python proxy.
     */
    async sendPrintingJob(img) {
        let base64Data = "";
        if (img instanceof HTMLCanvasElement) {
            const dataUrl = img.toDataURL("image/png");
            base64Data = dataUrl.split(",")[1];
        } else if (typeof img === "string") {
            base64Data = img;
        } else if (img && typeof img.toDataURL === "function") {
            base64Data = img.toDataURL("image/png").split(",")[1];
        }

        const printerName = this.proxy_printer_name || this.printer?.name || this.name || "POS_Printer";
        const apiKey = window.ridhira_api_key || (this.pos?.config?.ridhira_kitchen_print_api_key) || "";

        const payload = {
            jsonrpc: "2.0",
            method: "call",
            params: {
                data: {
                    printer_name: printerName,
                    receipt: base64Data,
                    api_key: apiKey,
                    action: "print_receipt",
                },
            },
            id: Math.floor(Math.random() * 1000000),
        };

        try {
            const res = await fetch(`${this.proxyUrl}/hw_proxy/default_printer_action`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
                signal: AbortSignal.timeout(this.timeout || 15000),
            });

            const data = await res.json();

            if (data && data.result) {
                document.body.dataset.ridhiraLastPrint = Date.now();
                return {
                    result: true,
                    canRetry: false,
                };
            }

            if (data && data.error) {
                const errMsg = data.error.message || data.error.data?.message;
                if (errMsg === "License Expired") {
                    console.error("[Ridhira Proxy] SaaS License Expired.");
                    alert("Kitchen Print Failed: Your Proxy Subscription has expired. Please visit https://ridhira.desigoogly.com/ to renew.");
                    return {
                        result: false,
                        canRetry: false,
                        errorCode: "LICENSE_EXPIRED",
                    };
                }
            }

            return {
                result: false,
                canRetry: true,
                errorCode: data?.error?.message || "PRINT_FAILED",
            };
        } catch (err) {
            console.warn("[Ridhira Proxy] Direct print connection failed:", err);
            return {
                result: false,
                canRetry: true,
                errorCode: "PRINTER_NOT_REACHABLE",
            };
        }
    },

    async printReceipt(receipt) {
        return this.sendPrintingJob(receipt);
    },

    async sendAction(data) {
        const printerName = data.printer_name || this.proxy_printer_name || "POS_Printer";
        const apiKey = window.ridhira_api_key || data.api_key || "";
        const payload = {
            jsonrpc: "2.0",
            method: "call",
            params: {
                data: {
                    printer_name: printerName,
                    receipt: data.receipt || "",
                    api_key: apiKey,
                    action: data.action || "print_receipt",
                },
            },
            id: Math.floor(Math.random() * 1000000),
        };

        try {
            const res = await fetch(`${this.proxyUrl}/hw_proxy/default_printer_action`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            const resp = await res.json();
            return Boolean(resp && resp.result);
        } catch (e) {
            console.warn("[Ridhira Proxy] sendAction failed:", e);
            return false;
        }
    },

    async openCashbox() {
        const printerName = this.proxy_printer_name || "POS_Printer";
        const apiKey = window.ridhira_api_key || "";
        const payload = {
            jsonrpc: "2.0",
            method: "call",
            params: {
                printer_name: printerName,
                api_key: apiKey,
            },
            id: Math.floor(Math.random() * 1000000),
        };

        try {
            const res = await fetch(`${this.proxyUrl}/hw_proxy/open_cashbox`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
                signal: AbortSignal.timeout(5000),
            });
            const data = await res.json();
            return Boolean(data && data.result);
        } catch (err) {
            console.warn("[Ridhira Proxy] Cashbox open failed:", err);
            return false;
        }
    },
});

// --- 2. PATCH: PosStore to expose API Key globally ---
patch(PosStore.prototype, {
    async processServerData() {
        await super.processServerData(...arguments);
        if (this.config && this.config.ridhira_kitchen_print_api_key) {
            window.ridhira_api_key = this.config.ridhira_kitchen_print_api_key;
        }
    },
});