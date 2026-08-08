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

            //if (bestTable && (!order.table_id || !order.self_ordering_table_id)) {
            if (bestTable && !order.self_ordering_table_id) {
                const tableIdNum = bestTable.id || bestTable; // Fallback in case it's already a number

                if (typeof order.update === 'function') {
                    // Update both to be safe, using the numeric ID
                    order.update({
                        //table_id: tableIdNum,
                        self_ordering_table_id: tableIdNum
                    });
                } //else if (typeof order.set_table === 'function') {
                //order.set_table(bestTable);
                //}
                else {
                    //order.table_id = bestTable;
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
        console.log("Ridhira: printChanges executing!", { orderId: order.id, orderChange, reprint, printers: printers?.length });
        
        let result = true;
        const normalPrinters = [];
        const labelPrinters = [];
        
        for (const p of (printers || [])) {
            const isLabel = (p.config && p.config.is_label_printer) || p.is_label_printer || (p.config && p.config.name && p.config.name.includes("KITCHEN_PRINTERESCPOS"));
            console.log(`[Ridhira POS] Evaluating printer: ${p.config?.name || p.name || 'Unknown'}. isLabel Evaluated to: ${isLabel}`, p);
            if (isLabel) {
                console.log(`[Ridhira POS] Routing to Label Printers array: ${p.config?.name || 'Unknown'}`);
                labelPrinters.push(p);
            } else {
                console.log(`[Ridhira POS] Routing to Normal Printers array: ${p.config?.name || 'Unknown'}`);
                normalPrinters.push(p);
            }
        }
        
        // 1. Process Normal Printers via Odoo's native QWeb rendering
        if (normalPrinters.length > 0) {
            const normalResult = await super.printChanges(order, orderChange, reprint, normalPrinters);
            result = result && normalResult;
        }
        
        // 2. Process Label Printers by splitting quantities into individual cups
        if (labelPrinters.length > 0) {
            for (const printer of labelPrinters) {
                // We only care about new and cancelled items for labels (noteUpdates usually apply to existing items, but for labels it's hard to update a physical sticker)
                const processChanges = async (changesList, isCancelled) => {
                    for (const change of (changesList || [])) {
                        const qty = Math.abs(change.qty || change.quantity || 1); // Extract absolute quantity
                        for (let i = 1; i <= qty; i++) {
                            // Odoo 19 property fallback for Table ID and Order Name
                            let tableNameStr = "";
                            
                            // 1. Try Odoo 19 native getTable()
                            if (typeof order.getTable === 'function') {
                                const tableObj = order.getTable();
                                if (tableObj) {
                                    if (tableObj.floor_id && tableObj.floor_id.name) tableNameStr = `${tableObj.floor_id.name} - `;
                                    else if (tableObj.floor && tableObj.floor.name) tableNameStr = `${tableObj.floor.name} - `;
                                    
                                    if (typeof tableObj.getName === 'function') tableNameStr += tableObj.getName();
                                    else tableNameStr += tableObj.name || tableObj.id;
                                }
                            }
                            
                            // 2. Fallback for primitive ID parsing
                            if (!tableNameStr) {
                                const tObj = order.table || order.table_id || order.self_ordering_table_id || order.tableId;
                                if (tObj) {
                                    if (typeof tObj === 'object') {
                                        tableNameStr = tObj.name || tObj.table_name || tObj[1] || (tObj.id ? String(tObj.id) : "");
                                    } else {
                                        let foundTable = null;
                                        try {
                                            // Try to lookup the table by ID in Odoo 19 POS models
                                            if (this.models && this.models['restaurant.table']) {
                                                const tableModel = this.models['restaurant.table'];
                                                if (typeof tableModel.get === 'function') foundTable = tableModel.get(tObj);
                                                else if (typeof tableModel.getAll === 'function') {
                                                    const tables = tableModel.getAll();
                                                    foundTable = tables.find(t => t.id == tObj);
                                                }
                                            }
                                        } catch(e) {}
                                        
                                        if (foundTable && foundTable.name) {
                                            tableNameStr = foundTable.name;
                                        } else {
                                            const tMap = window.posmodel && window.posmodel.tables_by_id;
                                            if (tMap && tMap[tObj]) tableNameStr = tMap[tObj].name;
                                            else tableNameStr = String(tObj);
                                        }
                                    }
                                }
                            }
                            if (tableNameStr === "[object Object]") tableNameStr = "Unknown Table";
                            
                            // Extract Modifiers and Price from matched OrderLine or Change
                            let priceStr = "";
                            let modifiers = [];
                            
                            try {
                                let orderLines = [];
                                if (typeof order.getOrderlines === 'function') orderLines = order.getOrderlines();
                                else if (typeof order.get_orderlines === 'function') orderLines = order.get_orderlines();
                                else orderLines = order.lines || order.orderlines || [];
                                
                                let matchedLine = null;
                                if (change.uuid) {
                                    matchedLine = orderLines.find(l => l.uuid === change.uuid);
                                } else if (change.line_uuid) {
                                    matchedLine = orderLines.find(l => l.uuid === change.line_uuid);
                                }
                                
                                if (matchedLine) {
                                    let rawPrice = null;
                                    if (typeof matchedLine.get_price_with_tax === 'function') {
                                        rawPrice = matchedLine.get_price_with_tax();
                                    } else if (matchedLine.displayPrice !== undefined) {
                                        rawPrice = matchedLine.displayPrice;
                                    } else if (matchedLine.priceIncl !== undefined) {
                                        rawPrice = matchedLine.priceIncl;
                                    } else if (matchedLine.price_unit !== undefined) {
                                        rawPrice = matchedLine.price_unit;
                                    } else if (typeof matchedLine.getDisplayPrice === 'function') {
                                        rawPrice = matchedLine.getDisplayPrice();
                                    }
                                    
                                    if (rawPrice !== null) {
                                        const formattedPrice = window.posmodel && window.posmodel.env && window.posmodel.env.utils && window.posmodel.env.utils.formatCurrency 
                                            ? window.posmodel.env.utils.formatCurrency(rawPrice) 
                                            : "$" + parseFloat(rawPrice).toFixed(2);
                                        priceStr = formattedPrice;
                                    }
                                }
                            } catch (e) {}
                            
                            // Respect the print_price_on_label toggle
                            const shouldPrintPrice = printer.print_price_on_label !== false && printer.config?.print_price_on_label !== false;
                            if (!shouldPrintPrice) {
                                priceStr = "";
                            }
                            
                            // Use Odoo 19 native attribute value names
                            if (Array.isArray(change.attribute_value_names) && change.attribute_value_names.length > 0) {
                                modifiers.push(...change.attribute_value_names);
                            }
                            // Fallbacks for older versions
                            if (modifiers.length === 0 && Array.isArray(change.name_wrap) && change.name_wrap.length > 1) {
                                modifiers.push(change.name_wrap.slice(1).join(" "));
                            }
                            
                            if (change.customer_note) {
                                modifiers.push(`Note: ${change.customer_note}`);
                            } else if (change.note) {
                                modifiers.push(`Note: ${change.note}`);
                            }
                            
                            const modifiersStr = modifiers.join(" | ");
                            
                            const oName = (order.name && order.name !== '/') ? order.name : (order.tracking_number || order.trackingNumber || order.uid || "Order");
                            const isTakeout = order.takeaway ? "Takeout" : (tableNameStr && tableNameStr !== "Takeout" && tableNameStr !== "Unknown Table" ? "Dine In" : "Takeout");
                            
                            const cupData = {
                                order_name: oName,
                                table_no: tableNameStr,
                                is_takeout: isTakeout,
                                order_time: new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}),
                                sequence: `${i}/${qty}`,
                                is_cancelled: isCancelled,
                                change: change,
                                modifiers: modifiersStr,
                                price: priceStr,
                                label_width: printer.config?.label_width || printer.label_width || 400,
                                label_height: printer.config?.label_height || printer.label_height || 300
                            };
                            
                            try {
                                console.log(`[Ridhira POS] Sending Cup ${i} of ${qty} for ${cupData.order_name} to label printer...`, cupData);
                                const payloadStr = "BOBA_LABEL_JSON:" + JSON.stringify(cupData);
                                const base64Payload = btoa(unescape(encodeURIComponent(payloadStr)));
                                
                                const hwPrinter = printer.ridhira_proxy_printer || printer;
                                
                                // Crucial: Since we bypassed EpsonPrinter.printReceipt, we must inject the printer name manually!
                                const targetPrinterName = (printer.config && printer.config.name) || printer.name || "POS_Printer";
                                hwPrinter.proxy_printer_name = targetPrinterName;
                                
                                if (typeof hwPrinter.sendAction === 'function') {
                                    // Odoo 19 bypass: send directly to Proxy without htmlToCanvas rendering
                                    await hwPrinter.sendAction({
                                        action: "print_receipt",
                                        receipt: base64Payload,
                                        printer_name: targetPrinterName
                                    });
                                } else {
                                    // Fallback
                                    await printer.printReceipt(base64Payload);
                                }
                                console.log(`[Ridhira POS] Successfully dispatched label payload for Cup ${i}`);
                            } catch (e) {
                                console.error("[Ridhira Proxy] Failed to send Boba label to printer:", e);
                                result = false;
                            }
                        }
                    }
                };
                
                // Safely flatten changes from Odoo 17/18/19 formats FIRST
                let allNew = [];
                let allCancelled = [];
                
                if (Array.isArray(orderChange)) {
                    for (const oc of orderChange) {
                        if (oc.new || oc.cancelled) {
                            if (oc.new) allNew = allNew.concat(oc.new);
                            if (oc.cancelled) allCancelled = allCancelled.concat(oc.cancelled);
                        } else {
                            if (oc.qty > 0) allNew.push(oc);
                            else if (oc.qty < 0) allCancelled.push(oc);
                        }
                    }
                } else if (orderChange) {
                    if (orderChange.new) allNew = allNew.concat(orderChange.new);
                    if (orderChange.cancelled) allCancelled = allCancelled.concat(orderChange.cancelled);
                }

                // MANUALLY FILTER BY CATEGORY TO PREVENT ODOO 19 CRASHES
                const categories = (printer.config && printer.config.product_categories_ids) || printer.product_categories_ids || [];
                if (categories.length > 0) {
                    const matchesCategories = (change) => {
                        let product;
                        try {
                            if (this.models && this.models['product.product']) {
                                product = this.models['product.product'].get(change.product_id);
                            } else if (window.posmodel && window.posmodel.db) {
                                product = window.posmodel.db.get_product_by_id(change.product_id);
                            }
                        } catch(e) {}
                        
                        if (!product) return true;
                        
                        let categIds = [];
                        if (product.parentPosCategIds) categIds = product.parentPosCategIds;
                        else if (product.pos_categ_ids) categIds = product.pos_categ_ids;
                        else if (product.pos_categ_id) {
                            categIds = Array.isArray(product.pos_categ_id) ? [product.pos_categ_id[0]] : [product.pos_categ_id];
                        }
                        
                        for (const cid of categIds) {
                            if (categories.includes(cid)) return true;
                        }
                        return false;
                    };
                    
                    const validParentUuids = new Set(
                        [...allNew, ...allCancelled]
                            .filter(change => change.isCombo && matchesCategories(change))
                            .map(change => change.uuid)
                    );
                    
                    const safeFilter = (change) => {
                        if (change.isCombo) return matchesCategories(change);
                        if (change.combo_parent_uuid) return validParentUuids.has(change.combo_parent_uuid);
                        return matchesCategories(change);
                    };

                    allNew = allNew.filter(safeFilter);
                    allCancelled = allCancelled.filter(safeFilter);
                }
                
                await processChanges(allNew, false);
                await processChanges(allCancelled, true);
            }
        }
        
        console.log(`Ridhira: printChanges completed with result: ${result}`);
        return result;
    }
});