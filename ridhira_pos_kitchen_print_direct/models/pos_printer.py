from odoo import api, fields, models

class PosPrinter(models.Model):
    _inherit = 'pos.printer'

    is_label_printer = fields.Boolean(
        string='Is a Cup Label Printer',
        default=False,
        help="Check this if this printer is a sticker/label printer (e.g. for Bubble Tea cups). It will split print payloads per cup instead of grouping them on a receipt."
    )
    
    label_width = fields.Integer(
        string="Label Canvas Width",
        default=400,
        help="Width of the thermal sticker canvas in pixels (e.g. 400)."
    )
    
    label_height = fields.Integer(
        string="Label Canvas Height",
        default=300,
        help="Height of the thermal sticker canvas in pixels (e.g. 300)."
    )

    @api.model
    def _load_pos_data_fields(self, config_id):
        result = super()._load_pos_data_fields(config_id)
        result.append('is_label_printer')
        result.append('label_width')
        result.append('label_height')
        return result

