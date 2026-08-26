/** @odoo-module **/

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { ActionpadWidget } from "@point_of_sale/app/screens/product_screen/action_pad/action_pad";
import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";

patch(PosStore.prototype, {
    async assignDailyQueueNumber(order) {
        if (this.config.pos_queue_number_mode === 'global' || this.config.pos_queue_number_mode === 'local') {
            if (!order.daily_queue_number) {
                if (this.config.pos_queue_number_mode === 'global') {
                    try {
                        const nextNum = await this.env.services.orm.call(
                            'pos.order', 
                            'get_next_daily_queue_number', 
                            []
                        );
                        order.daily_queue_number = nextNum;
                    } catch (e) {
                        console.error("Failed to fetch global queue number, falling back to local tracking number", e);
                    }
                }
                
                // Fallback or Local Mode Generation
                if (!order.daily_queue_number) {
                    const todayStr = new Date().toLocaleDateString();
                    const cacheKeyDate = 'ridhira_queue_date_' + this.config.id;
                    const cacheKeyNum = 'ridhira_queue_num_' + this.config.id;
                    
                    const savedDate = localStorage.getItem(cacheKeyDate);
                    let currentNum = parseInt(localStorage.getItem(cacheKeyNum)) || 0;
                    
                    if (savedDate !== todayStr) {
                        currentNum = 0; // Reset for a new day
                        localStorage.setItem(cacheKeyDate, todayStr);
                    }
                    
                    currentNum += 1;
                    localStorage.setItem(cacheKeyNum, currentNum);
                    
                    order.daily_queue_number = currentNum.toString();
                }
            }
        }
    },

    async sendOrderInPreparation(order, opts = {}) {
        await this.assignDailyQueueNumber(order);
        return super.sendOrderInPreparation(...arguments);
    }
});

patch(PaymentScreen.prototype, {
    async validateOrder(isForceValidate) {
        await this.pos.assignDailyQueueNumber(this.currentOrder);
        return super.validateOrder(...arguments);
    }
});

patch(ActionpadWidget.prototype, {
    setup() {
        super.setup(...arguments);
        this.dialog = useService("dialog");
    },
    async assignTableTent() {
        const order = this.env.services.pos.get_order();
        const payload = await makeAwaitable(this.dialog, NumberPopup, {
            title: "Enter Table Tent / Seating Number",
            startingValue: order.table_tent_number || "",
        });
        if (payload) {
            order.table_tent_number = payload;
        }
    }
});
