{
    'name': 'Ridhira POS Kitchen Print Direct',
    'version': '2.0.0',
    'summary': 'No IOT Box required. Manage POS and Kitchen Printers. Advanced Label/Sticker Printing. Print Job live dashboard and built-in KDS (Queue Display) included.',
    'description': "Integrates Odoo POS with local/network printers using a Python proxy. Supports advanced Thermal Label/Sticker printing. Now includes a local, proxy-hosted Queue Display System (KDS) for customer order tracking.",
    'author': 'Ridhira Technologies, Pune, India',
    'support': 'ridhiratech@gmail.com',
    'website': 'https://ridhira.desigoogly.com',
    'category': 'Point of Sale',
    'depends': ['point_of_sale'],
    'live_test_url': 'https://ridhira.desigoogly.com/printproxydemo/',
    'images': [
        'static/description/icon.png',
        'static/description/01_screenshot.png'
    ],
    'data': [
        'views/res_config_settings_views.xml',
        'views/pos_printer_views.xml',
        'data/ir_sequence_data.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'ridhira_pos_kitchen_print_direct/static/src/xml/pos_print_override.xml',
            'ridhira_pos_kitchen_print_direct/static/src/js/pos_print_override.js',
            'ridhira_pos_kitchen_print_direct/static/src/js/pos_order_combo_patch.js',
            'ridhira_pos_kitchen_print_direct/static/src/js/pos_self_order_kitchen_print.js',
            'ridhira_pos_kitchen_print_direct/static/src/js/pos_order_patch.js',
            'ridhira_pos_kitchen_print_direct/static/src/js/pos_order_receipt.js',
            'ridhira_pos_kitchen_print_direct/static/src/xml/pos_receipt_override.xml',
        ],
        'web.assets_tests': [
            'ridhira_pos_kitchen_print_direct/static/tests/tours/kitchen_print_tour.js',
        ],
    },
    'license': 'OPL-1',
    'installable': True,
    'application': True,
}
