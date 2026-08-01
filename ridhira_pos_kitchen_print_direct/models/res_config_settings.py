from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ridhira_kitchen_print_api_key = fields.Char(related='pos_config_id.ridhira_kitchen_print_api_key', readonly=False)
