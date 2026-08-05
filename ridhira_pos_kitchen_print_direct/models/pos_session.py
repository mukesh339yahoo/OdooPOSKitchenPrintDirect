from odoo import models

class PosSession(models.Model):
    _inherit = 'pos.session'

    def _loader_params_pos_printer(self):
        result = super()._loader_params_pos_printer()
        result['search_params']['fields'].append('is_label_printer')
        return result
