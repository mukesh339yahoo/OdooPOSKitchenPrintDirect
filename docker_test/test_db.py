import odoo
odoo.tools.config.parse_config(['-c', '/etc/odoo/odoo.conf'])
env = odoo.api.Environment(odoo.sql_db.db_connect('default').cursor(), 1, {})
config = env['pos.config'].search([], limit=1)
print(f"Font size: {config.kitchen_order_font_size}")
print(f"Bold: {config.kitchen_order_is_bold}")
