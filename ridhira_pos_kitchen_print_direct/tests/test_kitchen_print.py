from odoo.tests import HttpCase, tagged
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import time

class MockPrinterServer(BaseHTTPRequestHandler):
    jobs = []
    
    def log_message(self, format, *args):
        pass

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        MockPrinterServer.jobs.append(post_data)
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok", "success": True}).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()


@tagged('post_install', '-at_install', 'kitchen_print_test')
class TestPOSKitchenPrint(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Start mock server
        MockPrinterServer.jobs.clear()
        cls.server = HTTPServer(('0.0.0.0', 9100), MockPrinterServer)
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.daemon = True
        cls.thread.start()

        cls.env = cls.env
        
        # Create a dedicated POS config for testing
        cls.pos_config = cls.env['pos.config'].create({
            'name': 'Test Kitchen POS',
            'module_pos_restaurant': True,
            'is_order_printer': True,
            'self_ordering_mode': 'mobile',
        })
        
        # Create an ePos printer for the kitchen pointing to our mock server IP
        printer = cls.env['pos.printer'].create({
            'name': 'Mock Kitchen Printer',
            'printer_type': 'epson_epos',
            'epson_printer_ip': '127.0.0.1', # Hardcoded in pos_print_override to hit 9100 on the proxyIp
        })
        cls.pos_config.printer_ids = [(4, printer.id)]
        
        # Assign products to the printer by explicitly creating and assigning a pos category
        pos_categ = cls.env['pos.category'].create({'name': 'Test Kitchen Category'})
        product = cls.env['product.product'].search([('available_in_pos', '=', True)], limit=1)
        product.write({'pos_categ_ids': [(4, pos_categ.id)]})
        printer.write({'product_categories_ids': [(4, pos_categ.id)]})

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        MockPrinterServer.jobs.clear()
        # Open session
        if self.pos_config.current_session_id.state != 'opened':
            self.pos_config.open_ui()

    def wait_for_print_job(self, timeout=10):
        start = time.time()
        while time.time() - start < timeout:
            if len(MockPrinterServer.jobs) > 0:
                return True
            time.sleep(0.5)
        return False

    def test_01_customer_places_order(self):
        # We start the tour inside the POS UI!
        # The tour simulates self-ordering via our custom controller
        self.start_tour("/pos/ui?config_id=%d" % self.pos_config.id, "pos_kitchen_print_customer_order", login="admin")
        
        # The tour completes when the order simulation is done
        # Wait a few more seconds for the websocket message to be processed and print job sent
        self.assertTrue(self.wait_for_print_job(timeout=10), "Mock printer did not receive a print job after self order.")
        
        last_job = MockPrinterServer.jobs[-1]
        self.assertIn("print_receipt", last_job, "Print job payload does not contain print_receipt action.")
        
    def test_02_customer_cancels_order(self):
        self.start_tour("/pos/ui?config_id=%d" % self.pos_config.id, "pos_kitchen_print_customer_cancel", login="admin")
        
        # For this tour, it places an order, waits for print, then cancels it.
        # So we should expect 2 print jobs!
        self.assertTrue(self.wait_for_print_job(timeout=10))
        
        start = time.time()
        while time.time() - start < 10:
            if len(MockPrinterServer.jobs) >= 2:
                break
            time.sleep(0.5)
            
        self.assertGreaterEqual(len(MockPrinterServer.jobs), 2, "Mock printer did not receive the cancellation print job.")
        
        last_job = MockPrinterServer.jobs[-1]
        self.assertIn("print_receipt", last_job, "Cancellation print job payload does not contain print_receipt action.")
