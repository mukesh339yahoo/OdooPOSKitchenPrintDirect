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
   pip3 install Flask Pillow Flask-CORS python-escpos
   python3 app.py
   ```
3. proxy URL http://localhost:9100
