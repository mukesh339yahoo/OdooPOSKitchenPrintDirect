{
    'name': 'Ridhira POS Print Proxy',
    'version': '1.0.0',
    'summary': 'Auto-detect and manage POS and Kitchen Printers with Test Print feature',
    'description': "Integrates Odoo POS with local/network printers using a Python proxy.",
    'author': 'Ridhira Technologies, Pune, India',
    'website': 'https://ridhira.desigoogly.com',
    'category': 'Point of Sale',
    'depends': ['point_of_sale', 'pos_epson_printer'],
    'data': [],
    'assets': {
        'point_of_sale._assets_pos': [
            'ridhira_pos_print_proxy/static/src/js/pos_print_override.js',
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'application': True,
}