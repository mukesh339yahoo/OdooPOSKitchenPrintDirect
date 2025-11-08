# Ridhira POS Print Proxy

A lightweight hybrid printing solution for Odoo POS and Kitchen printers.

## Features
- Auto-detect local/network printers
- Web-based GUI for assigning printers to kitchens
- Test print button for each printer
- Compatible with Odoo POS frontend

## Setup
1. Install the Odoo add-on.
2. Run the Python proxy:
   ```bash
   cd proxy
   pip install flask requests
   python3 app.py
   ```
3. Set proxy URL in Odoo System Parameters:
   - Key: ridhira.proxy_url
   - Value: http://localhost:9100/print
