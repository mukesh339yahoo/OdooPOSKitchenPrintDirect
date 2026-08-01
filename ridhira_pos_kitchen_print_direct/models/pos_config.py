from odoo import fields, models, api

class PosConfig(models.Model):
    _inherit = 'pos.config'

    ridhira_kitchen_print_api_key = fields.Char(string='Proxy API Key', help="Enter your SaaS Proxy API Key to enable Kitchen Printing.")

