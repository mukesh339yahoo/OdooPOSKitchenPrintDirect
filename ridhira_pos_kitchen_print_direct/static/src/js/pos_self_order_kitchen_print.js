/** @odoo-module **/

import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";

/**
 * QR mobile orders are placed from the customer's phone, which cannot reach the
 * kitchen print proxy. When a self-order is saved or cancelled on the server,
 * notify the open POS session and print kitchen tickets from the POS terminal
 * (same proxy path as cashier orders).
 */
patch(PosStore.prototype, {
    async initServerData() {
        const result = await super.initServerData(...arguments);
        const hasPrinters = (this.printers_category_ids_set?.size > 0) || (this.unwatched?.printers?.length > 0);
        const isSelfOrderEnabled = this.session._self_ordering || ["mobile", "kiosk", "consultation"].includes(this.config?.self_ordering_mode) || Boolean(this.config?.self_ordering_mode);

        if (isSelfOrderEnabled && hasPrinters) {
            this.data.connectWebSocket(
                "ORDER_STATE_CHANGED",
                this._ridhiraOnSelfOrderStateChanged.bind(this)
            );
        }
        return result;
    },

    async _ridhiraOnSelfOrderStateChanged() {
        const hasPrinters = (this.printers_category_ids_set?.size > 0) || (this.unwatched?.printers?.length > 0);
        if (!hasPrinters) {
            return;
        }

        const preparationBefore = new Map();
        const stateBefore = new Map();
        const tableBefore = new Map();
        const selfTableBefore = new Map();

        const isSelfOrder = (o) =>
            (o.pos_reference?.startsWith("Self-Order") ||
                o.pos_reference?.startsWith("Kiosk") ||
                (o.floating_order_name || "").startsWith("Self-Order") ||
                o.tracking_number ||
                (o.source && ["kiosk", "mobile"].includes(o.source))) &&
            typeof o.id === "number";

        for (const order of this.models["pos.order"].filter(isSelfOrder)) {
            preparationBefore.set(order.id, JSON.stringify(order.last_order_preparation_change));
            stateBefore.set(order.id, order.state);
            tableBefore.set(order.id, order.table_id);
            selfTableBefore.set(order.id, order.self_ordering_table_id);
        }

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
                    console.warn("[Ridhira POS] Could not parse session start date:", err);
                }
            }

            const domain = [
                ["config_id", "=", this.config.id],
                ["state", "in", ["draft", "cancel"]],
                "|", "|", "|", "|",
                ["source", "in", ["kiosk", "mobile"]],
                ["pos_reference", "ilike", "Kiosk"],
                ["pos_reference", "ilike", "Self-Order"],
                ["floating_order_name", "ilike", "Self-Order"],
                ["tracking_number", "!=", false]
            ];

            if (sessionStartDate) {
                domain.push(["write_date", ">=", sessionStartDate]);
            }

            // Include table QR orders (Odoo's getServerOrders excludes table_id for self-orders).
            await this.loadServerOrders(domain);
        } catch (e) {
            console.error("[Ridhira POS] Error fetching server orders:", e);
        }

        for (const order of this.models["pos.order"].filter(isSelfOrder)) {
            // Restore table link for mobile QR orders to prevent wiping on sync
            let bestTable = order.table_id || order.self_ordering_table_id || tableBefore.get(order.id) || selfTableBefore.get(order.id);
            if (bestTable && (!order.table_id || !order.self_ordering_table_id)) {
                const tableIdNum = bestTable.id || bestTable;
                if (typeof order.update === 'function') {
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
                console.log(`[Ridhira POS] Enforced table link for Order ${order.id} to Table ${tableIdNum}`);
            }

            const preparationAfter = JSON.stringify(order.last_order_preparation_change);
            const prepBefore = preparationBefore.get(order.id);
            const wasTrackedInPOS = stateBefore.has(order.id);
            const wasActiveInPOS = wasTrackedInPOS && stateBefore.get(order.id) !== "cancel";
            const isCancelled = order.state === "cancel";
            const justCancelled = wasActiveInPOS && isCancelled;
            const isDraft = order.state === "draft";
            // Check delta properly now that we preserve it
            const hasPrepChanges = prepBefore !== preparationAfter;
            const isNewServerOrder = !wasTrackedInPOS && isDraft;

            const shouldPrint = isNewServerOrder || (isDraft && hasPrepChanges) || justCancelled;

            if (shouldPrint) {
                try {
                    // Restore previous preparation state unconditionally so the kitchen prints correct diff
                    order.last_order_preparation_change = prepBefore ? JSON.parse(prepBefore) : { lines: {} };

                    await this.sendOrderInPreparation(order, { cancelled: isCancelled });
                } catch (e) {
                    console.error(`[Ridhira POS] Failed to print order ${order.id}:`, e);
                }
            }
        }
    },

    async printChanges(order, orderChange, reprint = false, printers = this.unwatched.printers) {
        console.log("[Ridhira POS] printChanges executing!", {
            orderId: order.id,
            orderChange,
            reprint,
            printers: printers?.length
        });
        const result = await super.printChanges(...arguments);
        console.log(`[Ridhira POS] printChanges completed with result: ${result}`);
        return result;
    }
});





