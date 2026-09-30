import os
import sys
import subprocess

def main():
    pyinstaller_bin = os.path.join(os.path.dirname(sys.executable), 'pyinstaller')
    if not os.path.exists(pyinstaller_bin) and not os.path.exists(pyinstaller_bin + '.exe'):
        pyinstaller_bin = 'pyinstaller'

    cmd = [
        pyinstaller_bin, '-y', '--onefile', '--clean',
        '--name', 'app',
        '--add-data', 'templates;templates',
        '--add-data', 'static;static',
        '--add-data', 'fonts;fonts',
        '--add-data', 'escpos/capabilities/capabilities.json;escpos',
        '--add-data', 'escpos/capabilities/capabilities.json;escpos/capabilities',
        '--hidden-import', 'PIL',
        '--hidden-import', 'PIL.Image',
        '--hidden-import', 'PIL.ImageDraw',
        '--hidden-import', 'PIL.ImageFont',
        '--hidden-import', 'PIL.ImageWin',
        '--hidden-import', 'win32print',
        '--hidden-import', 'win32ui',
        '--hidden-import', 'waitress',
        '--hidden-import', 'escpos',
        '--hidden-import', 'jwt',
        '--hidden-import', 'pytz',
        '--hidden-import', 'dateutil',
        'app.py'
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)

if __name__ == '__main__':
    main()
