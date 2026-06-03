/** @odoo-module **/

import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";

/**
 * QR mobile orders are placed from the customer's phone, which cannot reach the
 * kitchen print proxy. When a self-order is saved on the server, notify the open
 * POS session and print kitchen tickets from the POS terminal (same proxy path as
 * cashier orders).
 */
patch(PosStore.prototype, {
    async initServerData() {
        const result = await super.initServerData(...arguments);
        if (this.session._self_ordering && this.printers_category_ids_set?.size) {
            this.data.connectWebSocket(
                "ORDER_STATE_CHANGED",
                this._ridhiraOnSelfOrderStateChanged.bind(this)
            );
        }
        return result;
    },

    async _ridhiraOnSelfOrderStateChanged() {
        if (!this.printers_category_ids_set?.size) {
            return;
        }

        const preparationBefore = new Map();
        for (const order of this.models["pos.order"].filter(
            (o) =>
                !o.finalized &&
                o.pos_reference?.startsWith("Self-Order") &&
                typeof o.id === "number"
        )) {
            preparationBefore.set(
                order.id,
                JSON.stringify(order.last_order_preparation_change)
            );
        }

        // Include table QR orders (Odoo's getServerOrders excludes table_id for self-orders).
        await this.loadServerOrders([
            ["config_id", "=", this.config.id],
            ["state", "=", "draft"],
            "|",
            ["pos_reference", "ilike", "Kiosk"],
            ["pos_reference", "ilike", "Self-Order"],
        ]);

        for (const order of this.models["pos.order"].filter(
            (o) =>
                !o.finalized &&
                o.pos_reference?.startsWith("Self-Order") &&
                typeof o.id === "number"
        )) {
            const preparationAfter = JSON.stringify(order.last_order_preparation_change);
            if (preparationBefore.get(order.id) !== preparationAfter) {
                await this.sendOrderInPreparation(order);
            }
        }
    },
});
