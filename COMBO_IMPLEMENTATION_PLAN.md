# Implementation Plan: Combo Kitchen Printing Fix (Odoo 19)

This plan outlines the steps to patch Odoo 19's native kitchen printing logic to "explode" combos, routing individual combo choices (sub-items) to their respective printers while prepending the Parent Combo name for context.

## User Review Required
> [!IMPORTANT]
> **Odoo Core Assumption:**
> This plan assumes you are using the standard `pos_restaurant` kitchen printing flow where `computeChanges` is used to build the `OrderChangeReceipt`. 
> 
> *Please confirm if your clients are using the native Odoo `pos_restaurant` preparation printers, or if they are using a custom module for kitchen routing.*

## Proposed Changes

We will create a new JavaScript patch that hooks into the Odoo POS data models.

### `ridhira_pos_kitchen_print_direct`

#### [MODIFY] `models/pos_config.py` & `models/res_config_settings.py`
- We will add a new boolean field `ridhira_explode_combos_in_kitchen` to the POS configuration.

#### [MODIFY] `views/res_config_settings_views.xml`
- We will expose this boolean field in the Odoo POS Settings page under the Kitchen Print section with the label: "Split Combos to Respective Printers".

#### [NEW] `static/src/js/pos_order_combo_patch.js`
- **Patch `pos.order` model (`PosOrder.prototype`):**
    - We will override the `computeChanges(categories)` method.
    - **Logic to inject:**
        1. When the method runs, it first checks `this.pos.config.ridhira_explode_combos_in_kitchen`.
        2. If `false`, it immediately falls back to Odoo's native `super.computeChanges(categories)` flow.
        3. If `true`, it proceeds to the custom explosion logic: bypass routing the parent line to a single printer, iterate over its sub-items (`combo_lines`), calculate specific POS Categories for each, and generate virtual `OrderChange` dictionaries formatting the display name as `{parent_product_name}\n  • {sub_item_name}`.

#### [MODIFY] `__manifest__.py`
- We will add the new `pos_order_combo_patch.js` file to the `point_of_sale._assets_pos` bundle array in the `assets` section of the manifest so Odoo loads the script.

## Verification Plan

### Manual Verification
1. **Setup:** In Odoo, create a "Burger Combo". Set the Burger to the "Kitchen" POS category, and the Coke to the "Bar" POS category.
2. **Order Placement:** Add the Burger Combo to the cart in the POS UI.
3. **Print Execution:** Click "Order" to send the tickets to the proxy.
4. **Validation:** 
    - Verify that the Kitchen Printer receives a ticket showing:
      `Burger Combo`
      `  • Burger`
    - Verify that the Bar Printer receives a separate ticket showing:
      `Burger Combo`
      `  • Coke`
    - Verify that a standard non-combo item still prints normally.
