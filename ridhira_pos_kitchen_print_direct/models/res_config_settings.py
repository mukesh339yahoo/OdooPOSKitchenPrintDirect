from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ridhira_kitchen_print_api_key = fields.Char(related='pos_config_id.ridhira_kitchen_print_api_key', readonly=False)
    pos_ridhira_explode_combos_in_kitchen = fields.Boolean(related='pos_config_id.ridhira_explode_combos_in_kitchen', readonly=False)

    pos_kitchen_order_font_size = fields.Selection(related='pos_config_id.kitchen_order_font_size', readonly=False)
    pos_kitchen_order_is_bold = fields.Boolean(related='pos_config_id.kitchen_order_is_bold', readonly=False)

    pos_queue_number_mode = fields.Selection(related='pos_config_id.pos_queue_number_mode', readonly=False)
    pos_enable_table_tent = fields.Boolean(related='pos_config_id.pos_enable_table_tent', readonly=False)

