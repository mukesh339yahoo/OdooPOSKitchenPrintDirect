# Implement Font Settings for Kitchen Food Items

This plan details the steps to add configuration options for users to select larger and bold fonts for kitchen food items on the printed kitchen receipts.

## Implementation Details

### Backend Configuration (Python & XML)
---
#### [pos_config.py](ridhira_pos_kitchen_print_direct/models/pos_config.py)
Add the new fields to the `pos.config` model to store the database values:
- `kitchen_item_font_size`: Selection field (`Normal`, `Large`).
- `kitchen_item_is_bold`: Boolean field.

#### [res_config_settings.py](ridhira_pos_kitchen_print_direct/models/res_config_settings.py)
Add related fields pointing to `pos_config_id` to make them available in the settings view:
- `pos_kitchen_item_font_size`
- `pos_kitchen_item_is_bold`

#### [res_config_settings_views.xml](ridhira_pos_kitchen_print_direct/views/res_config_settings_views.xml)
Add the new fields to the settings UI under the "Kitchen Printers" block so the user can configure them.

#### [pos_session.py](ridhira_pos_kitchen_print_direct/models/pos_session.py)
Ensure the new configuration fields are loaded into the POS session by adding `kitchen_item_font_size` and `kitchen_item_is_bold` to the `result` array in `_loader_params_pos_config`.

### Frontend Assets (JS & XML)
---
#### [pos_self_order_kitchen_print.js](ridhira_pos_kitchen_print_direct/static/src/js/pos_self_order_kitchen_print.js)
Extract the new configuration variables (`kitchen_item_font_size`, `kitchen_item_is_bold`) from `this.config` and append them to the data context passed to the receipt template, similar to how it's done for the header.

#### [pos_print_override.xml](ridhira_pos_kitchen_print_direct/static/src/xml/pos_print_override.xml)
Add a new `<xpath>` block to target the item lines in `point_of_sale.OrderChangeReceipt`. We will wrap or modify the product name `<div class="product-name">` or `<span>` line item with logic that applies `font-weight: bold;` and/or the `pos-receipt-title` class based on the configuration.

## Verification Plan
### Manual Verification
1. Open Odoo Settings > Point of Sale.
2. Toggle the "Kitchen Item Font Size" to "Large" and check "Bold Kitchen Item Text".
3. Place an order in the POS and print the kitchen receipt.
4. Verify the food item names on the receipt appear larger and bold.
