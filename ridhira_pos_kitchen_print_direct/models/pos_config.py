from odoo import fields, models, api

class PosConfig(models.Model):
    _inherit = 'pos.config'

    ridhira_kitchen_print_api_key = fields.Char(string='Proxy API Key', help="Enter your SaaS Proxy API Key to enable Kitchen Printing.")
    ridhira_explode_combos_in_kitchen = fields.Boolean(string="Split Combos to Respective Printers", default=False, help="If enabled, Combo items (like Burger + Coke) will be split to their respective Kitchen/Bar printers instead of all printing to the same printer.")

    kitchen_order_font_size = fields.Selection([
        ('Normal', 'Normal'),
        ('Large', 'Large')
    ], string='Kitchen Order Font Size', default='Normal', help="Font size for the Order Number on kitchen prints.")
    
    kitchen_item_font_size = fields.Selection([
        ('Normal', 'Normal'),
        ('Large', 'Large')
    ], string='Kitchen Item Font Size', default='Normal', help="Font size for the Food Items on kitchen prints.")
    
    pos_queue_number_mode = fields.Selection([
        ('disabled', 'Disabled (Default Odoo)'),
        ('local', 'Single Terminal (Local)'),
        ('global', 'Multi Terminal (Global)')
    ], string="Queue Numbering Mode", default='disabled', help="Select the queue numbering behavior.")
    
    pos_enable_table_tent = fields.Boolean(
        string="Table Tent Enabled", 
        default=False, 
        help="Enable the 'Assign Table Tent' seating tracker feature."
    )
    
    kitchen_order_is_bold = fields.Boolean(
        string='Kitchen Order Font Bold',
        default=False,
        help="Whether the Order Number should be bold on kitchen prints."
    )

    kitchen_item_is_bold = fields.Boolean(
        string='Kitchen Item Font Bold',
        default=False,
        help="Whether the Food Items should be bold on kitchen prints."
    )

    kitchen_extra_font_size = fields.Selection([
        ('Normal', 'Normal'),
        ('Large', 'Large')
    ], string='Kitchen Extra Font Size', default='Normal', help="Font size for the Food Extras/Sides on kitchen prints.")
    
    kitchen_extra_is_bold = fields.Boolean(
        string='Kitchen Extra Font Bold',
        default=False,
        help="Whether the Food Extras/Sides should be bold on kitchen prints."
    )

    customer_receipt_font_size = fields.Selection([
        ('Normal', 'Normal'),
        ('Large', 'Large')
    ], string='Customer Receipt Font Size', default='Normal', help="Font size for the Customer Receipt.")
    
    customer_receipt_is_bold = fields.Boolean(
        string='Customer Receipt Font Bold',
        default=False,
        help="Whether the Customer Receipt should be bold."
    )
