/** @odoo-module **/

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
    filterChangeByCategories(categories, currentOrderChange) {
        // If the toggle is ENABLED (or if Odoo 19 does it natively and we want to keep native behavior)
        if (this.config.ridhira_explode_combos_in_kitchen) {
            return super.filterChangeByCategories(categories, currentOrderChange);
        }

        // If the toggle is DISABLED, we revert to Odoo 18 behavior:
        // Combo items are ALL sent to a single printer based on the PARENT combo's category.
        const matchesCategories = (change) => {
            const product = this.models["product.product"].get(change["product_id"]);
            const categoryIds = product.parentPosCategIds;
            for (const categoryId of categoryIds) {
                if (categories.includes(categoryId)) {
                    return true;
                }
            }
            return false;
        };

        const filterChanges = (changes) => {
            if (!changes || !Array.isArray(changes)) return [];
            // Find which Combo Parents match the printer's category
            const validParentUuids = new Set(
                changes
                    .filter((change) => change.isCombo && matchesCategories(change))
                    .map((change) => change.uuid)
            );

            return changes.filter(
                (change) => {
                    if (change.isCombo) {
                        // Parent matches the printer
                        return matchesCategories(change);
                    } else if (change.combo_parent_uuid) {
                        // Child follows the Parent!
                        return validParentUuids.has(change.combo_parent_uuid);
                    } else {
                        // Normal item
                        return matchesCategories(change);
                    }
                }
            );
        };

        if (Array.isArray(currentOrderChange)) {
            // Odoo 19 Array format
            return filterChanges(currentOrderChange);
        } else {
            // Odoo 17/18 Object format
            return {
                new: filterChanges(currentOrderChange["new"]),
                cancelled: filterChanges(currentOrderChange["cancelled"]),
                noteUpdate: filterChanges(currentOrderChange["noteUpdate"]),
            };
        }
    }
});
