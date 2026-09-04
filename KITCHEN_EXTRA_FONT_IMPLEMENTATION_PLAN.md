# Implement Font Settings for Kitchen Food Extras & Sides

This plan details the steps to add configuration options for users to independently select larger and bold fonts for kitchen food extras, sides, modifiers, and notes on the printed kitchen receipts.

## Implementation Details

### Backend Configuration (Python & XML)
---
#### [pos_config.py](ridhira_pos_kitchen_print_direct/models/pos_config.py)
Add the new fields to the `pos.config` model to store the database values:
- `kitchen_extra_font_size`: Selection field (`Normal`, `Large`).
- `kitchen_extra_is_bold`: Boolean field.

#### [res_config_settings.py](ridhira_pos_kitchen_print_direct/models/res_config_settings.py)
Add related fields pointing to `pos_config_id` to make them available in the settings view:
- `pos_kitchen_extra_font_size`
- `pos_kitchen_extra_is_bold`

#### [res_config_settings_views.xml](ridhira_pos_kitchen_print_direct/views/res_config_settings_views.xml)
Add the new fields to the settings UI under the "Kitchen Printers" block, right below the "Kitchen Item Style" settings. This gives users granular control over modifiers.

#### [pos_session.py](ridhira_pos_kitchen_print_direct/models/pos_session.py)
Ensure the new configuration fields are loaded into the POS session by adding `kitchen_extra_font_size` and `kitchen_extra_is_bold` to the `result` array in `_loader_params_pos_config`.

### Frontend Assets (JS & XML)
---
#### [pos_self_order_kitchen_print.js](ridhira_pos_kitchen_print_direct/static/src/js/pos_self_order_kitchen_print.js)
Extract the new configuration variables (`kitchen_extra_font_size`, `kitchen_extra_is_bold`) from `this.config` and append them to the data context passed to the receipt template.

#### [pos_print_override.xml](ridhira_pos_kitchen_print_direct/static/src/xml/pos_print_override.xml)
Append new CSS rules inside our existing `<style>` injection block within `point_of_sale.OrderChangeReceipt`. 

We will specifically target the classes Odoo uses for modifiers, variants, and customer notes, such as:
- `.pos-receipt-variant`
- `.pos-receipt-order-data-variants`
- `.pos-receipt-note`
- `.ps-3`
- `.text-muted`

```xml
<t t-if="data.kitchen_extra_font_size == 'Large'">
    .pos-receipt-variant, .pos-receipt-note, .pos-receipt-order-data-variants, .ps-3, .text-muted {
        font-size: 1.3em !important; 
        line-height: 1.2 !important;
    }
</t>
<t t-if="data.kitchen_extra_is_bold">
    .pos-receipt-variant, .pos-receipt-note, .pos-receipt-order-data-variants, .ps-3, .text-muted {
        font-weight: bold !important;
        color: black !important; /* Overrides the default grey/muted text for better visibility */
    }
</t>
```

## Verification Plan
### Manual Verification
1. Open Odoo Settings > Point of Sale.
2. Toggle the new "Kitchen Extra Font Size" to "Large" and check "Bold Kitchen Extra Text".
3. Place an order in the POS containing a main item WITH modifiers/sides and a customer note.
4. Print the kitchen receipt.
5. Verify the modifiers and notes on the receipt correctly adopt the larger, bolder font without affecting the main item size (unless the main item size is also configured).
