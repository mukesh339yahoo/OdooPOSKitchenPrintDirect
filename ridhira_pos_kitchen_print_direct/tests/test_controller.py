from odoo import http
from odoo.http import request
import uuid
import json

class RidhiraTestController(http.Controller):

    @http.route('/ridhira_test/simulate_self_order', type='json', auth='user')
    def simulate_self_order(self, config_id, action='order', order_id=None):
        pos_config = request.env['pos.config'].browse(config_id)
        
        # We need a product available in POS
        product = request.env['product.product'].search([('available_in_pos', '=', True)], limit=1)
        
        if action == 'order':
            order_uuid = str(uuid.uuid4())
            line_uuid = str(uuid.uuid4())
            
            order = request.env['pos.order'].create({
                'session_id': pos_config.current_session_id.id,
                'company_id': pos_config.company_id.id,
                'state': 'draft',
                'source': 'mobile', # Important for proxy filter
                'uuid': order_uuid,
                'tracking_number': 'S-TEST1',
                'amount_tax': 0.0,
                'amount_total': product.lst_price,
                'amount_paid': 0.0,
                'amount_return': 0.0,
                'lines': [(0, 0, {
                    'product_id': product.id,
                    'qty': 1,
                    'price_unit': product.lst_price,
                    'price_subtotal': product.lst_price,
                    'price_subtotal_incl': product.lst_price,
                    'uuid': line_uuid,
                })],
            })
            
            # Create a fake preparation state delta for the printer
            order.last_order_preparation_change = json.dumps({
                "lines": {
                    line_uuid: {
                        "uuid": line_uuid,
                        "product_id": product.id,
                        "qty": 1,
                        "name": product.name,
                    }
                }
            })
            
            pos_config._notify('ORDER_STATE_CHANGED', {})
            return {'status': 'ok', 'order_id': order.id}
            
        elif action == 'cancel' and order_id:
            order = request.env['pos.order'].browse(order_id)
            if order.exists():
                order.write({'state': 'cancel'})
                # In Odoo, cancellation often empties the preparation lines
                order.last_order_preparation_change = json.dumps({"lines": {}})
                pos_config._notify('ORDER_STATE_CHANGED', {})
                return {'status': 'ok'}
        
        return {'status': 'error'}
