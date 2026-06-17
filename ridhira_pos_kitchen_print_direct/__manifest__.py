{
    'name': 'Ridhira POS Kitchen Print Direct',
    'version': '1.0.0',
    'summary': 'Auto-detect and manage POS and Kitchen Printers with Test Print feature. Supports Self Orders',
    'description': "Integrates Odoo POS with local/network printers using a Python proxy. Supports Self Orders.",
    'author': 'Ridhira Technologies, Pune, India',
    'website': 'https://ridhira.desigoogly.com',
    'category': 'Point of Sale',
    'depends': ['point_of_sale'],
     'images': [
        'static/description/icon.png',
        'static/description/01_screenshot.png'
    ],
    'data': [],
    'assets': {
        'point_of_sale._assets_pos': [
            'ridhira_pos_kitchen_print_direct/static/src/js/pos_print_override.js',
            'ridhira_pos_kitchen_print_direct/static/src/js/pos_self_order_kitchen_print.js',
        ],
    },
    'license': 'OPL-1',
    'installable': True,
    'application': True,
}
