from odoo import fields, models, api

class PosConfig(models.Model):
    _inherit = 'pos.config'

    ridhira_kitchen_print_api_key = fields.Char(string='Proxy API Key', help="Enter your SaaS Proxy API Key to enable Kitchen Printing.")
    ridhira_explode_combos_in_kitchen = fields.Boolean(string="Split Combos to Respective Printers", default=False, help="If enabled, Combo items (like Burger + Coke) will be split to their respective Kitchen/Bar printers instead of all printing to the same printer.")

    kitchen_order_font_size = fields.Selection([
        ('Normal', 'Normal'),
        ('Large', 'Large')
    ], string='Kitchen Order Font Size', default='Normal', help="Font size for the Order Number on kitchen prints.")
    
    kitchen_order_is_bold = fields.Boolean(
        string='Kitchen Order Font Bold',
        default=False,
        help="Whether the Order Number should be bold on kitchen prints."
    )

