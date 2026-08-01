from odoo import fields, models, api

class PosConfig(models.Model):
    _inherit = 'pos.config'

    ridhira_kitchen_print_api_key = fields.Char(string='Proxy API Key', help="Enter your SaaS Proxy API Key to enable Kitchen Printing.")
    ridhira_explode_combos_in_kitchen = fields.Boolean(string="Split Combos to Respective Printers", default=False, help="If enabled, Combo items (like Burger + Coke) will be split to their respective Kitchen/Bar printers instead of all printing to the same printer.")

