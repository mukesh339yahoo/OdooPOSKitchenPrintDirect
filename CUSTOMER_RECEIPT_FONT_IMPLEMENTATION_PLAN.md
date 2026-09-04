# Implement Font Settings for Customer Receipts

This plan outlines the approach for allowing users to dynamically select a larger font size and bold text exclusively for the Customer Receipt in the POS. It ensures we avoid the CSS leakage issue that occurred previously by strictly scoping our CSS injections.

## Goal
Provide a configuration interface in the POS Settings for users to configure the font size and boldness of the items and prices on the Customer Receipt, without impacting the Kitchen Receipt or other areas of the POS.

## Proposed Implementation

### 1. Backend Configuration (Python & XML)
We will introduce two new fields for customer receipt styling, following the exact same pattern used for kitchen printers.

- **`pos_config.py`**
  Add database fields to the `pos.config` model:
  - `customer_receipt_font_size`: Selection field (`Normal`, `Large`).
  - `customer_receipt_is_bold`: Boolean field.

- **`res_config_settings.py`**
  Add the related fields to make them accessible in settings:
  - `pos_customer_receipt_font_size`
  - `pos_customer_receipt_is_bold`

- **`res_config_settings_views.xml`**
  Add a new configuration block in the POS Settings UI under the standard "Receipts" section for these two fields.

- **`pos_session.py`**
  Update `_loader_params_pos_config` to ensure `customer_receipt_font_size` and `customer_receipt_is_bold` are loaded into the POS session environment upon startup.

### 2. Frontend Data Payload (JavaScript)
To get these new configuration fields into the Customer Receipt rendering engine, we will patch Odoo's native receipt data builder.

- **`pos_self_order_kitchen_print.js`** (or a new JS file)
  We will patch `PosOrder.prototype.export_for_printing` (or `getOrderData`, depending on exact Odoo 19 schema) to append our new configuration fields into the receipt payload object.
  ```javascript
  // Pseudocode
  patch(PosOrder.prototype, {
      export_for_printing() {
          const receipt = super.export_for_printing(...arguments);
          receipt.customer_receipt_font_size = this.pos.config.customer_receipt_font_size;
          receipt.customer_receipt_is_bold = this.pos.config.customer_receipt_is_bold;
          return receipt;
      }
  });
  ```

### 3. XML Templates & Scoped CSS
We will inject targeted CSS into the Customer Receipt, ensuring we scope it using a unique class wrapper so it cannot leak to the kitchen receipt. Furthermore, we will explicitly target `.pos-receipt-right-align` to ensure the **price** scales up alongside the product name.

- **`pos_receipt_override.xml`**
  Target `point_of_sale.OrderReceipt`.
  
  ```xml
  <t t-name="ridhira_pos_kitchen_print_direct.OrderReceipt" t-inherit="point_of_sale.OrderReceipt" t-inherit-mode="extension">
      <!-- 1. Inject a unique scoping class into the root div -->
      <xpath expr="//div[hasclass('pos-receipt')]" position="attributes">
          <attribute name="class" add="customer-receipt-styled" separator=" "/>
      </xpath>
      
      <!-- 2. Inject scoped CSS rules -->
      <xpath expr="//div[hasclass('pos-receipt')]" position="inside">
          <style>
              <t t-if="receipt.customer_receipt_font_size == 'Large'">
                  .customer-receipt-styled .pos-receipt-order-data, 
                  .customer-receipt-styled .pos-receipt-left-padding, 
                  .customer-receipt-styled .product-name, 
                  .customer-receipt-styled .pos-receipt-right-align,
                  .customer-receipt-styled .pos-receipt-vat {
                      font-size: 1.5em !important;
                      line-height: 1.2 !important;
                  }
              </t>
              <t t-if="receipt.customer_receipt_is_bold">
                  .customer-receipt-styled .pos-receipt-order-data, 
                  .customer-receipt-styled .pos-receipt-left-padding, 
                  .customer-receipt-styled .product-name, 
                  .customer-receipt-styled .pos-receipt-right-align,
                  .customer-receipt-styled .pos-receipt-vat {
                      font-weight: bold !important;
                      color: black !important;
                  }
              </t>
          </style>
      </xpath>
  </t>
  ```

## User Review Required
> [!IMPORTANT]
> The above plan will securely add font configuration to the Customer Receipt while ensuring both the **item name** and **price** correctly scale up together. 
> Please review this plan, and let me know if you approve to proceed with the implementation!
