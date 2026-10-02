import odoo
from odoo.modules.registry import Registry

odoo.tools.config.parse_config(['-c', '/etc/odoo/odoo.conf', '--db_host=db', '--db_user=odoo', '--db_password=odoo', '-d', 'odoo20_test'])
registry = Registry('odoo20_test')
with registry.cursor() as cr:
    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
    module = env['ir.module.module'].search([('name', '=', 'ridhira_pos_kitchen_print_direct')])
    print(f"MODULE_STATE: {module.state}")
    print(f"MODULE_VERSION: {module.installed_version}")
    
    pos_config = env['pos.config']
    print(f"HAS_KITCHEN_ORDER_FONT_SIZE: {'kitchen_order_font_size' in pos_config._fields}")
    print(f"HAS_POS_QUEUE_NUMBER_MODE: {'pos_queue_number_mode' in pos_config._fields}")
    
    pos_printer = env['pos.printer']
    print(f"HAS_IS_LABEL_PRINTER: {'is_label_printer' in pos_printer._fields}")
    print(f"HAS_LABEL_WIDTH: {'label_width' in pos_printer._fields}")
    
    pos_order = env['pos.order']
    print(f"HAS_DAILY_QUEUE_NUMBER: {'daily_queue_number' in pos_order._fields}")
