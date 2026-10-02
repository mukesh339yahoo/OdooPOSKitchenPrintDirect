/** @odoo-module **/

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
    filterChangeByCategories(categories, currentOrderChange) {
        if (this.config.ridhira_explode_combos_in_kitchen) {
            if (super.filterChangeByCategories) {
                return super.filterChangeByCategories(categories, currentOrderChange);
            }
            return currentOrderChange;
        }

        const matchesCategories = (change) => {
            const product = this.models["product.product"]?.get(change["product_id"]);
            if (!product) return false;
            const categoryIds = product.parentPosCategIds || [];
            for (const categoryId of categoryIds) {
                if (categories.includes(categoryId)) {
                    return true;
                }
            }
            return false;
        };

        const filterChanges = (changes) => {
            if (!changes || !Array.isArray(changes)) return [];
            const validParentUuids = new Set(
                changes
                    .filter((change) => change.isCombo && matchesCategories(change))
                    .map((change) => change.uuid)
            );

            return changes.filter(
                (change) => {
                    if (change.isCombo) {
                        return matchesCategories(change);
                    } else if (change.combo_parent_uuid) {
                        return validParentUuids.has(change.combo_parent_uuid);
                    } else {
                        return matchesCategories(change);
                    }
                }
            );
        };

        if (Array.isArray(currentOrderChange)) {
            return filterChanges(currentOrderChange);
        } else if (currentOrderChange && typeof currentOrderChange === 'object') {
            return {
                new: filterChanges(currentOrderChange["new"]),
                cancelled: filterChanges(currentOrderChange["cancelled"]),
                noteUpdate: filterChanges(currentOrderChange["noteUpdate"]),
                addedQuantity: filterChanges(currentOrderChange["addedQuantity"]),
                removedQuantity: filterChanges(currentOrderChange["removedQuantity"]),
            };
        }
        return currentOrderChange;
    }
});
