/** @odoo-module **/

import { ScaleInterface } from "@point_of_sale/app/utils/scale/scale_interface";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

export class RidhiraProxyScaleInterface extends ScaleInterface {
    setup(pos) {
        this.proxyUrl = this.pos.config.scale_proxy_url || "http://localhost:9100";
        this.status = {
            SCALE_IN_MOTION: false,
            OVER_CAPACITY: false,
            UNDER_ZERO: false,
        };
        this.is_stable = false;
        this.pollingInterval = this.pos.config.scale_polling_interval || 250;
    }

    async connectToScale() {
        if (!this.pos.config.scale_enabled) {
            return false;
        }

        this.proxyUrl = (this.pos.config.scale_proxy_url || "http://localhost:9100").replace(/\/$/, "");
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 2000);
            const res = await fetch(`${this.proxyUrl}/scale/status`, { signal: controller.signal });
            clearTimeout(timeoutId);

            if (!res.ok) {
                return false;
            }

            const data = await res.json();
            console.log("⚖️ [Ridhira Scale] Connected to scale proxy at", this.proxyUrl, data);
            return true;
        } catch (err) {
            console.warn("⚖️ [Ridhira Scale] Unable to connect to scale proxy at", this.proxyUrl, err);
            return false;
        }
    }

    async _readWeight() {
        try {
            const proxyUrl = (this.pos.config.scale_proxy_url || "http://localhost:9100").replace(/\/$/, "");
            const res = await fetch(`${proxyUrl}/scale/weight`);
            if (!res.ok) {
                return this.weight;
            }
            const data = await res.json();
            
            this.status = {
                SCALE_IN_MOTION: !data.is_stable,
                OVER_CAPACITY: Boolean(data.is_over_capacity),
                UNDER_ZERO: Boolean(data.is_under_zero),
            };
            this.is_stable = Boolean(data.is_stable);

            if (data.is_over_capacity) {
                this.onError(_t("Scale is over capacity"), false);
            } else if (data.is_under_zero) {
                this.onError(_t("Scale is under zero"), false);
            }

            return typeof data.weight === "number" ? data.weight : this.weight;
        } catch (error) {
            console.error("⚖️ [Ridhira Scale] Error reading weight:", error);
            return this.weight;
        }
    }

    async requestTare() {
        try {
            const proxyUrl = (this.pos.config.scale_proxy_url || "http://localhost:9100").replace(/\/$/, "");
            await fetch(`${proxyUrl}/scale/tare`, { method: "POST" });
        } catch (e) {
            console.warn("⚖️ [Ridhira Scale] Error sending tare command:", e);
        }
        await super.requestTare();
    }

    get isWeightValid() {
        return (
            super.isWeightValid && 
            !this.status.SCALE_IN_MOTION && 
            !this.status.OVER_CAPACITY && 
            !this.status.UNDER_ZERO
        );
    }
}

// Add with sequence 10 so it precedes standard WebSerial (seq 100)
registry.category("electronic_scales").add("ridhira_proxy_scale", RidhiraProxyScaleInterface, { sequence: 10 });
