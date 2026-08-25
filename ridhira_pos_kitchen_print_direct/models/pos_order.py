from odoo import models, fields, api

class PosOrder(models.Model):
    _inherit = 'pos.order'

    # 1. Ensure the field exists and is loaded into POS
    take_away = fields.Boolean(
        string="Take Away", 
        compute="_compute_take_away", 
        inverse="_inverse_take_away",
        store=False
    )

    @api.depends('preset_id')
    def _compute_take_away(self):
        for order in self:
            is_takeaway = False
            if hasattr(order, 'preset_id') and order.preset_id:
                if hasattr(order.preset_id, 'service_at') and order.preset_id.service_at != 'table':
                    is_takeaway = True
            order.take_away = is_takeaway

    def _inverse_take_away(self):
        pass # Allow the POS to write to it without throwing an error

