import os
import subprocess

def main():
    cmd = [
        'pyinstaller', '--onedir', '--noupx', '--clean',
        '--add-data', 'templates;templates',
        '--add-data', 'fonts;fonts',
        '--add-data', 'escpos/capabilities/capabilities.json;escpos/capabilities',
        'app.py'
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)

if __name__ == '__main__':
    main()
