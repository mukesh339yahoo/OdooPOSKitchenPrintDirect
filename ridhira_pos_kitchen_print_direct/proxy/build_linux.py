import os
import sys
import subprocess

def main():
    cmd = [
        'pyinstaller', '-y', '--onefile', '--clean',
        '--name', 'app_linux',
        '--add-data', 'templates:templates',
        '--add-data', 'static:static',
        '--add-data', 'fonts:fonts',
        '--add-data', 'escpos/capabilities/capabilities.json:escpos',
        '--add-data', 'escpos/capabilities/capabilities.json:escpos/capabilities',
        '--hidden-import', 'PIL',
        '--hidden-import', 'PIL.Image',
        '--hidden-import', 'PIL.ImageDraw',
        '--hidden-import', 'PIL.ImageFont',
        '--hidden-import', 'waitress',
        '--hidden-import', 'escpos',
        '--hidden-import', 'jwt',
        '--hidden-import', 'pytz',
        '--hidden-import', 'dateutil',
        '--hidden-import', 'flask_cors',
        '--hidden-import', 'serial',
        '--hidden-import', 'serial.tools.list_ports',
        '--exclude-module', 'win32print',
        '--exclude-module', 'win32ui',
        'app.py'
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)

if __name__ == '__main__':
    main()
