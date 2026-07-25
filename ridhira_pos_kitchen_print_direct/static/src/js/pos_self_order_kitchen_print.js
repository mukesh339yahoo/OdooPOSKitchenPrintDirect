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
        const stateBefore = new Map();
        const tableBefore = new Map(); // 1. Added for table caching
        const selfTableBefore = new Map(); // Backs up self_ordering_table_id

        for (const order of this.models["pos.order"].filter(
            (o) =>
                (['kiosk', 'mobile'].includes(o.source) || (o.floating_order_name || "").startsWith("Self-Order") || (o.floating_order_name || "").startsWith("Table tracker") || o.tracking_number) &&
                typeof o.id === "number"
        )) {
            preparationBefore.set(order.id, JSON.stringify(order.last_order_preparation_change));
            stateBefore.set(order.id, order.state);
            tableBefore.set(order.id, order.table_id); // 2. Added for table caching
            selfTableBefore.set(order.id, order.self_ordering_table_id);
        }

        console.log("Ridhira: Preparation state before sync:", Object.fromEntries(preparationBefore));

        // Restrict fetch domain to current POS session window and mobile/self orders
        console.log("Ridhira: Fetching new orders from server...");
        try {
            const rawStartDate = this.pos_session?.start_at || this.session?.start_at || this.session?.opened_at;
            let sessionStartDate = null;
            if (rawStartDate) {
                try {
                    if (typeof rawStartDate === 'object' && rawStartDate.toFormat) {
                        sessionStartDate = rawStartDate.toUTC().toFormat('yyyy-MM-dd HH:mm:ss');
                    } else {
                        const d = new Date(rawStartDate);
                        if (!isNaN(d.getTime())) {
                            sessionStartDate = d.toISOString().replace('T', ' ').split('.')[0];
                        }
                    }
                } catch (err) {
                    console.warn("Ridhira: Could not parse session start date:", err);
                }
            }

            const domain = [
                ["config_id", "=", this.config.id],
                ["state", "in", ["draft", "cancel"]],
                "|", "|",
                ["source", "in", ["kiosk", "mobile"]],
                ["tracking_number", "!=", false],
                ["floating_order_name", "ilike", "Self-Order"]
            ];
            if (sessionStartDate) {
                domain.push(["write_date", ">=", sessionStartDate]);
            }
            await this.data.loadServerOrders(domain);
        } catch (e) {
            console.error("Ridhira: Error fetching server orders:", e);
        }

        let sentToPrinter = false;

        for (const order of this.models["pos.order"].filter(
            (o) =>
                (['kiosk', 'mobile'].includes(o.source) || (o.floating_order_name || "").startsWith("Self-Order") || (o.floating_order_name || "").startsWith("Table tracker") || o.tracking_number) &&
                typeof o.id === "number"
        )) {
            // 3. Prevent Table Wiping Bug
            // If the server synced a self_ordering_table_id but NOT a table_id, we MUST copy it over.
            // Otherwise, when the POS pushes changes back to the server (e.g. during printing), it sends table_id=False,
            // which triggers an Odoo python override that wipes self_ordering_table_id on the server!
            let bestTable = order.table_id || order.self_ordering_table_id || tableBefore.get(order.id) || selfTableBefore.get(order.id);

            if (bestTable && (!order.table_id || !order.self_ordering_table_id)) {
                const tableIdNum = bestTable.id || bestTable; // Fallback in case it's already a number

                if (typeof order.update === 'function') {
                    // Update both to be safe, using the numeric ID
                    order.update({
                        table_id: tableIdNum,
                        self_ordering_table_id: tableIdNum
                    });
                } else if (typeof order.set_table === 'function') {
                    order.set_table(bestTable);
                } else {
                    order.table_id = bestTable;
                    order.self_ordering_table_id = bestTable;
                }
                console.log(`Ridhira: Enforced table link for Order ${order.id} to Table ${tableIdNum}`);
            }

            const preparationAfter = JSON.stringify(order.last_order_preparation_change);
            const prepBefore = preparationBefore.get(order.id);
            const wasTrackedInPOS = stateBefore.has(order.id);
            const wasActiveInPOS = wasTrackedInPOS && stateBefore.get(order.id) !== "cancel";
            const isCancelled = order.state === "cancel";
            const justCancelled = wasActiveInPOS && isCancelled;
            const isDraft = order.state === "draft";
            const hasPrepChanges = prepBefore !== preparationAfter;

            const shouldPrint = (isDraft && hasPrepChanges) || justCancelled;

            console.log(`Ridhira: Order ${order.id} | Source: ${order.source} | Tracking: ${order.tracking_number}`);
            console.log(`Ridhira: Before: ${prepBefore} | After: ${preparationAfter} | wasActiveInPOS: ${wasActiveInPOS} | isCancelled: ${isCancelled} | shouldPrint: ${shouldPrint}`);

            if (shouldPrint) {
                console.log(`Ridhira: Printing required for Order ${order.id}! (hasPrepChanges: ${hasPrepChanges}, justCancelled: ${justCancelled})`);
                try {
                    // Restore previous preparation state before server sync overwritten it
                    order.last_order_preparation_change = prepBefore ? JSON.parse(prepBefore) : { lines: {} };

                    await this.sendOrderInPreparation(order, { cancelled: isCancelled });
                    sentToPrinter = true;
                    console.log(`Ridhira: sendOrderInPreparation finished for order ${order.id}.`);
                } catch (e) {
                    console.error(`Ridhira: Failed to print order ${order.id}:`, e);
                }
            } else {
                console.log(`Ridhira: No printing required for Order ${order.id}.`);
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