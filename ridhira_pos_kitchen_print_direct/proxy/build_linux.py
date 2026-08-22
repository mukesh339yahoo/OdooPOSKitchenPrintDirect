import os
import subprocess

def main():
    cmd = [
        'pyinstaller', '--onefile', '--clean',
        '--name', 'app_linux',
        '--add-data', 'templates:templates',
        '--add-data', 'fonts:fonts',
        '--add-data', 'escpos/capabilities/capabilities.json:escpos',
        '--exclude-module', 'win32print',
        '--exclude-module', 'win32ui',
        'app.py'
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)

if __name__ == '__main__':
    main()
