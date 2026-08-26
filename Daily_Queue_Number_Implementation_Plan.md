# Daily Queue Number Implementation Plan (Odoo 19)

This document outlines the proposed solution to implement a prominent Daily Queue Number across the Customer Receipt, Kitchen Printer Ticket, and Kitchen Display System (KDS), specifically designed for **Odoo 19 architecture**.

## Background and Requirements
*   **Context**: Fast-food / takeaway mode relies on a short, easy-to-read sequential Order/Queue Number (e.g., 001, 002) for calling out orders, instead of the long Odoo POS Order Reference (e.g., Order 00001-001-0004).
*   **Requirement**: Prominently display this short queue number on the Customer Receipt (matching the provided McDonald's layout), Kitchen Printer Ticket, and KDS order cards.
*   **Generation Target**: Add support for both Single Terminal (local generation) and Multi Terminal (global generation).
*   **Optional Feature**: Table Tent (Seating Tracker) for dine-in orders.
*   **Version Target**: **Odoo 19 Community/Enterprise** (Utilizing OWL components and `@web/core/utils/patch`).

## Impact & Backward Compatibility

To support default Odoo users and provide optimal performance for single-terminal shops, we will introduce a **Queue Number Generation Mode** setting.

### [NEW] `ridhira_pos_kitchen_print_direct/models/res_config_settings.py`
*   Add a Selection field: `pos_queue_number_mode` (Label: "Queue Numbering Mode").
*   Add a Boolean field: `pos_enable_table_tent` (Label: "Table Tent Enabled").
*   **Option 1: Disabled (Default)**
    *   Customer Receipts print exactly as standard Odoo 19.
    *   Kitchen Printers/KDS use standard tracking/order references.
*   **Option 2: Single Terminal (Local)**
    *   *Best for 1 cash register.*
    *   Reuses Odoo's native session-based `tracking_number`.
    *   **Pros**: Zero delay. Works 100% offline.
    *   **Cons**: Sequence resets per-session (not strictly at midnight globally), and if you open a second terminal, both will issue `#1`.
*   **Option 3: Multi Terminal (Global)**
    *   *Required for multiple concurrent cashiers/kiosks.*
    *   Uses a centralized backend sequence that resets at midnight globally.
    *   **Pros**: Guaranteed no duplicate numbers across all terminals.
    *   **Cons**: Requires a network RPC call to fetch the number (adding a millisecond delay) and requires constant server connectivity.

## Proposed Changes

### 1. Backend Global Sequence (For Multi-Terminal Mode)
#### [NEW] `ridhira_pos_kitchen_print_direct/data/ir_sequence_data.xml`
*   Create a new standard Odoo sequence (`ir.sequence`) named `pos.daily.queue.number`.
*   Set it to reset daily.

#### [MODIFY] `ridhira_pos_kitchen_print_direct/models/pos_order.py`
*   Add a new field `daily_queue_number = fields.Char(string="Daily Queue Number")`.
*   When processing a new POS order, if the config is set to `Multi Terminal (Global)`, assign the next value from the global sequence to this field.

### 2. Frontend Logic (Odoo 19 OWL / Store Patch)
#### [NEW] `ridhira_pos_kitchen_print_direct/static/src/js/pos_order_patch.js`
*   Utilize Odoo 19's `@web/core/utils/patch` to patch the POS Store (`PosStore.prototype`) or the relevant Order classes.
*   Check the configured `pos_queue_number_mode`.
*   If **Multi Terminal (Global)**: Make an RPC call (`this.env.services.orm.call` or `this.data.call`) to retrieve the next `daily_queue_number` when validating the order.
*   If **Single Terminal (Local)**: Do nothing (the native `tracking_number` is already generated locally).

### 3. Optional: Table Tent (Seating) Tracker
To match the "Seating : 214" behavior seen on McDonald's receipts for dine-in customers, we will implement a lightweight table tent tracker. This feature will only activate if the **"Table Tent Enabled"** toggle is turned on in the POS settings.

#### [NEW] Cashier UI & Order Model Patch
*   Add a new OWL Component button to the POS Actionpad/ControlButtons: **"Assign Table Tent"**.
    *   **Visibility**: This button will only be visible if `pos.config.pos_enable_table_tent` is `True`.
*   When clicked, show a standard Odoo 19 `NumberPopup` to enter the physical plastic tent number.
*   Save this number to the order object.
*   *(Note: For kiosks using native Odoo 19 Self-Ordering, we will simply map Odoo's native `tracker_number` variable).*

### 4. Customer Receipt UI Override
Modify the Customer Receipt to match the provided McDonald's reference layout exactly, incorporating both the optional table tent and the queue number.

#### [NEW] `ridhira_pos_kitchen_print_direct/static/src/xml/pos_receipt_override.xml`
*   Extend the Odoo 19 OWL template `point_of_sale.OrderReceipt` (using `t-inherit` and `t-inherit-mode="extension"`).
*   Example XML structure for the Odoo 19 rendering engine:
    ```xml
    <t t-if="props.data.config.pos_queue_number_mode !== 'disabled'">
        <div class="pos-receipt-center-align" style="margin-bottom: 15px;">
            <!-- Optional Table Tent Output -->
            <t t-if="props.data.config.pos_enable_table_tent and props.data.table_tent_number">
                <div style="font-size: 1.2em; font-weight: bold; margin-bottom: 5px;">
                    Seating : <t t-esc="props.data.table_tent_number"/>
                </div>
            </t>
            
            <div>------------------------</div>
            <div style="font-size: 1.2em;">Your order number is</div>
            <div style="font-size: 3em; font-weight: bold;">
                <!-- Dynamically pick the number based on the mode -->
                <t t-if="props.data.config.pos_queue_number_mode === 'global'">
                    <t t-esc="props.data.daily_queue_number"/>
                </t>
                <t t-else="">
                    <t t-esc="props.data.tracking_number"/>
                </t>
            </div>
            <div>------------------------</div>
        </div>
    </t>
    ```

### 5. Kitchen Printer Ticket UI Override
Update the existing Kitchen Printer ticket to emphasize the Queue Number and Table Tent.

#### [MODIFY] `ridhira_pos_kitchen_print_direct/static/src/xml/pos_print_override.xml`
*   Apply the same Odoo 19 `t-if` logic as the customer receipt to decide between `daily_queue_number` and `tracking_number`.
*   Display `Seating : [Number]` prominently if `pos_enable_table_tent` is true and a tent was assigned.

### 6. Enterprise KDS (`pos_preparation_display`) UI Override
Ensure the native Odoo 19 Enterprise KDS order cards display the queue number and table tent prominently.

#### [NEW] `ridhira_pos_kitchen_print_direct/static/src/xml/pos_kds_override.xml`
*   Extend the Odoo 19 Enterprise KDS order card OWL template.
*   Apply the same conditional logic to inject the massive queue number and seating information into the KDS card header.

## Technical Considerations / Caveats

> [!WARNING]
> **Offline Mode Limitation (Global Mode Peak)**: If you select the `Multi Terminal (Global)` mode, the terminal requires a constant connection to the server to fetch the next number. If the internet goes down, it will temporarily fall back to the local `tracking_number` (Single Terminal logic) to ensure the restaurant can continue operating.

> [!TIP]
> **Enabling KDS on Enterprise Instances**: The KDS XML override (`pos_kds_override.xml`) extends the `pos_preparation_display` Enterprise module. Because this module is not present in Community Edition, it will cause a crash if enabled there. To enable the KDS customizations when installing on a true Enterprise instance:
> 1. Ensure the `pos_preparation_display` module is installed.
> 2. Open `__manifest__.py`.
> 3. Add `'pos_preparation_display'` to the `depends` list.
> 4. Add `'ridhira_pos_kitchen_print_direct/static/src/xml/pos_kds_override.xml'` to the `point_of_sale._assets_pos` list.
> 5. Restart Odoo and upgrade the module.

## Verification Plan

### Manual Verification
1.  **Toggle Check**: Ensure the POS Settings "Queue Numbering Mode" and "Table Tent Enabled" work in Odoo 19.
2.  **Table Tent Check**: With the feature enabled, verify the OWL "Assign Table Tent" button appears in the POS interface. Enter `214`.
3.  **Customer Receipt**: Verify it prints `Seating : 214` at the very top. Turn the setting off and verify the seating line disappears.
4.  **Multi/Single Terminal Check**: Test both Local and Global modes to ensure the proper queue number logic applies seamlessly in the Odoo 19 POS environment.
