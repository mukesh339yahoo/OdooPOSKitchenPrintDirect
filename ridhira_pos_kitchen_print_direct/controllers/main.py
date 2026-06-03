from odoo import http
from odoo.http import request
import requests

class POSPrinterController(http.Controller):
    @http.route('/ridhira_pos_print_proxy/print', type='json', auth='public')
    def send_print(self, data):
        proxy_url = request.env['ir.config_parameter'].sudo().get_param('ridhira.proxy_url', 'http://localhost:9100/print')
        res = requests.post(proxy_url, json=data)
        return res.json()
