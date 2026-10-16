/** @odoo-module **/

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { ScaleScreen } from "@point_of_sale/app/screens/scale_screen/scale_screen";
import { patch } from "@web/core/utils/patch";
import { onMounted, onWillUnmount } from "@odoo/owl";
import { RidhiraProxyScaleInterface } from "./scale_proxy_interface";

// 1. Patch ScaleScreen for live periodic weight polling and optional auto-confirm
patch(ScaleScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.scalePollTimer = null;

        onMounted(() => {
            // Read immediately on mount
            this.scale?.readWeight();

            const interval = this.pos.config.scale_polling_interval || 250;
            this.scalePollTimer = setInterval(async () => {
                if (this.scale && !this.scale.loading) {
                    await this.scale.readWeight();
                    if (
                        this.pos.config.scale_auto_confirm &&
                        this.scale.isWeightValid &&
                        this.scale.is_stable &&
                        this.scale.netWeight > 0
                    ) {
                        this.confirm();
                    }
                }
            }, interval);
        });

        onWillUnmount(() => {
            if (this.scalePollTimer) {
                clearInterval(this.scalePollTimer);
                this.scalePollTimer = null;
            }
        });
    },

    close() {
        if (this.scalePollTimer) {
            clearInterval(this.scalePollTimer);
            this.scalePollTimer = null;
        }
        super.close(...arguments);
    }
});

// 2. Patch PosStore for instant one-touch weighing if fruit is already placed on the scale
patch(PosStore.prototype, {
    async handleWeighableProduct(values, order, configure) {
        if (
            values.product_tmpl_id.to_weight && 
            this.scale && 
            configure && 
            this.config.scale_enabled && 
            this.config.scale_auto_confirm &&
            this.scale instanceof RidhiraProxyScaleInterface
        ) {
            try {
                await this.scale.readWeight();
                const decimalAccuracy = this.models["decimal.precision"].find(
                    (dp) => dp.name === "Product Unit"
                ).digits;
                const overridedValues = {};
                if (order.pricelist_id) {
                    overridedValues.pricelist = order.pricelist_id;
                }
                if (order.fiscal_position_id) {
                    overridedValues.fiscalPosition = order.fiscal_position_id;
                }
                this.scale.setProduct(
                    values.product_id,
                    decimalAccuracy,
                    values.product_id.getTaxDetails({ overridedValues }).total_included
                );

                if (this.scale.isWeightValid && this.scale.is_stable && this.scale.netWeight > 0) {
                    const weight = this.scale.confirmWeight();
                    if (weight) {
                        values.qty = weight;
                        return true;
                    }
                }
            } catch (e) {
                console.warn("⚖️ [Ridhira Scale] Direct weight read failed, falling back to dialog:", e);
            }
        }

        // Standard flow (opens ScaleScreen dialog with live readout)
        return super.handleWeighableProduct(...arguments);
    }
});
