from odoo import models, fields

class PosSession(models.Model):
    _inherit = 'pos.session'

    kitchen_order_font_size = fields.Selection(related='config_id.kitchen_order_font_size')
    kitchen_order_is_bold = fields.Boolean(related='config_id.kitchen_order_is_bold')
    kitchen_item_font_size = fields.Selection(related='config_id.kitchen_item_font_size')
    kitchen_item_is_bold = fields.Boolean(related='config_id.kitchen_item_is_bold')
    kitchen_extra_font_size = fields.Selection(related='config_id.kitchen_extra_font_size')
    kitchen_extra_is_bold = fields.Boolean(related='config_id.kitchen_extra_is_bold')
    
    pos_queue_number_mode = fields.Selection(related='config_id.pos_queue_number_mode')
    pos_enable_table_tent = fields.Boolean(related='config_id.pos_enable_table_tent')

    customer_receipt_font_size = fields.Selection(related='config_id.customer_receipt_font_size')
    customer_receipt_is_bold = fields.Boolean(related='config_id.customer_receipt_is_bold')

    def _loader_params_pos_printer(self):
        result = super()._loader_params_pos_printer()
        result['search_params']['fields'].append('is_label_printer')
        return result

    def _load_pos_data_fields(self, config):
        result = super()._load_pos_data_fields(config)
        result.extend(['kitchen_order_font_size', 'kitchen_order_is_bold', 'kitchen_item_font_size', 'kitchen_item_is_bold', 'kitchen_extra_font_size', 'kitchen_extra_is_bold', 'pos_queue_number_mode', 'pos_enable_table_tent', 'customer_receipt_font_size', 'customer_receipt_is_bold'])
        return result

    def _loader_params_pos_order(self):
        result = super()._loader_params_pos_order()
        if 'take_away' not in result['search_params']['fields']:
            result['search_params']['fields'].append('take_away')
        return result
