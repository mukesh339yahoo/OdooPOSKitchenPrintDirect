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
    
    daily_queue_number = fields.Char(string="Daily Queue Number", readonly=True, copy=False)
    table_tent_number = fields.Char(string="Table Tent Number", readonly=True, copy=False)

    @api.model
    def _order_fields(self, ui_order):
        fields = super(PosOrder, self)._order_fields(ui_order)
        if 'daily_queue_number' in ui_order:
            fields['daily_queue_number'] = ui_order.get('daily_queue_number')
        if 'table_tent_number' in ui_order:
            fields['table_tent_number'] = ui_order.get('table_tent_number')
        return fields
        
    @api.model
    def get_next_daily_queue_number(self):
        """Called via RPC from POS frontend to get the next global queue number"""
        return self.env['ir.sequence'].next_by_code('pos.daily.queue.number') or ''

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

