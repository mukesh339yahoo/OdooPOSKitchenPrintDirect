/** @odoo-module **/

import { PosStore } from "@point_of_sale/app/services/pos_store";
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
        if (this.session._self_ordering || ['mobile', 'kiosk'].includes(this.config.self_ordering_mode)) {
            console.log("Ridhira: Connecting to ORDER_STATE_CHANGED websocket...");
            this.data.connectWebSocket(
                "ORDER_STATE_CHANGED",
                this._ridhiraOnSelfOrderStateChanged.bind(this)
            );
        }
        return result;
    },

    async _ridhiraOnSelfOrderStateChanged() {
        console.log("Ridhira: Received ORDER_STATE_CHANGED event!");
        if (!this.unwatched?.printers?.length) {
            console.warn("Ridhira: No unwatched printers configured for Kitchen Printing. Aborting.");
            return;
        }

        const preparationBefore = new Map();
        for (const order of this.models["pos.order"].filter(
            (o) =>
                !o.finalized &&
                (['kiosk', 'mobile'].includes(o.source) || (o.floating_order_name || "").startsWith("Self-Order") || (o.floating_order_name || "").startsWith("Table tracker") || o.tracking_number) &&
                typeof o.id === "number"
        )) {
            preparationBefore.set(
                order.id,
                JSON.stringify(order.last_order_preparation_change)
            );
        }
        
        console.log("Ridhira: Preparation state before sync:", Object.fromEntries(preparationBefore));

        // Include table QR orders (Odoo's getServerOrders excludes table_id for self-orders).
        console.log("Ridhira: Fetching new orders from server...");
        try {
            await this.data.loadServerOrders([
                ["config_id", "=", this.config.id],
                ["state", "in", ["draft", "cancel"]],
                "|", "|",
                ["source", "in", ["kiosk", "mobile"]],
                ["tracking_number", "!=", false],
                ["floating_order_name", "ilike", "Self-Order"]
            ]);
        } catch (e) {
            console.error("Ridhira: Error fetching server orders:", e);
        }

        let sentToPrinter = false;
        
        for (const order of this.models["pos.order"].filter(
            (o) =>
                !o.finalized &&
                (['kiosk', 'mobile'].includes(o.source) || (o.floating_order_name || "").startsWith("Self-Order") || (o.floating_order_name || "").startsWith("Table tracker") || o.tracking_number) &&
                typeof o.id === "number"
        )) {
            const preparationAfter = JSON.stringify(order.last_order_preparation_change);
            const prepBefore = preparationBefore.get(order.id);
            
            console.log(`Ridhira: Order ${order.id} | Source: ${order.source} | Tracking: ${order.tracking_number}`);
            console.log(`Ridhira: Before: ${prepBefore} | After: ${preparationAfter}`);
            
            const isCancelled = order.state === "cancel";
            
            if (prepBefore !== preparationAfter || isCancelled) {
                console.log(`Ridhira: Changes detected for Order ${order.id}! Sending to printer...`);
                try {
                    // Restore the PREVIOUS preparation state before the server sync overwritten it.
                    // This allows Odoo's internal `changesToOrder` to compute the correct delta!
                    order.last_order_preparation_change = prepBefore ? JSON.parse(prepBefore) : { lines: {} };
                    
                    await this.sendOrderInPreparation(order, { cancelled: isCancelled });
                    sentToPrinter = true;
                    console.log(`Ridhira: sendOrderInPreparation finished for order ${order.id}.`);
                } catch (e) {
                    console.error(`Ridhira: Failed to print order ${order.id}:`, e);
                }
            } else {
                console.log(`Ridhira: No preparation changes for Order ${order.id}.`);
            }
        }
        
        if (!sentToPrinter) {
            console.log("Ridhira: Done processing event, but no new changes were sent to the printer.");
        }
    },

    async printChanges(order, orderChange, reprint = false, printers = this.unwatched.printers) {
        console.log("Ridhira: printChanges executing!", {
            orderId: order.id,
            orderChange,
            reprint,
            printers: printers?.length
        });
        const result = await super.printChanges(...arguments);
        console.log(`Ridhira: printChanges completed with result: ${result}`);
        return result;
    }
});
