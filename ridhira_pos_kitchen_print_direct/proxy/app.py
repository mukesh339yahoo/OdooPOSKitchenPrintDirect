import base64
import re
import json
import os
import socket
import sqlite3
import threading
import queue
import time
import platform
from datetime import datetime
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, jsonify, request, render_template, render_template_string
from xml.etree import ElementTree as ET
from flask_cors import CORS
from subprocess import run, CalledProcessError
import jwt
import requests
import dateutil.parser
import pytz
import textwrap

IS_WINDOWS = platform.system() == "Windows"
if IS_WINDOWS:
    try:
        import win32print
        import win32ui
        from PIL import ImageWin
    except ImportError:
        print("WARNING: pywin32 is not installed. System printing on Windows will fail.")
# Imports for ESC/POS (Requires 'python-escpos')
from escpos.printer import Network as EscposNetworkPrinter
from waitress import serve
# Imports for QZ TRAY (Requires 'websocket-client' if implemented)
# import websocket 
# import ssl 

import sys

# --- PyInstaller Path Resolution ---
if getattr(sys, 'frozen', False):
    BUNDLE_DIR = sys._MEIPASS
    APPLICATION_PATH = os.path.dirname(sys.executable)
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    APPLICATION_PATH = BUNDLE_DIR

app = Flask(__name__, template_folder=os.path.join(BUNDLE_DIR, 'templates'))

# --- Configuration ---
IMAGE_SAVE_PATH = os.path.join(APPLICATION_PATH, 'print_images')
DB_PATH = os.path.join(APPLICATION_PATH, 'jobs.db')
PRINTERS_FILE = os.path.join(APPLICATION_PATH, "printers.json")
SETTINGS_FILE = os.path.join(APPLICATION_PATH, "settings.json")
LICENSE_SERVER_URL = "https://ridhira-license-server.mukeshsharma339.workers.dev"
JWT_SECRET = "ridhira_kitchen_print_proxy_secret_key_2026" # IMPORTANT: Must match Cloudflare Worker secret

if not os.path.exists(IMAGE_SAVE_PATH):
    os.makedirs(IMAGE_SAVE_PATH)

if not os.path.exists(PRINTERS_FILE):
    with open(PRINTERS_FILE, "w") as f:
        json.dump({}, f)

if not os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, "w") as f:
        json.dump({"max_retries": 5, "retry_delay": 3}, f)

# Enable CORS for all routes
CORS(app, resources={r"/*": {"origins": "*"}})


# --- Utility Functions ---
def load_printers():
    """Loads the printer configuration from printers.json."""
    with open(PRINTERS_FILE) as f:
        return json.load(f)


def save_printers(data):
    """Saves the current printer configuration to printers.json."""
    with open(PRINTERS_FILE, "w") as f:
        json.dump(data, f, indent=4)

def load_settings():
    """Loads global settings from settings.json."""
    if not os.path.exists(SETTINGS_FILE):
        return {"max_retries": 5, "retry_delay": 3}
    with open(SETTINGS_FILE) as f:
        return json.load(f)

def save_settings(data):
    """Saves global settings to settings.json."""
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=4)


# --- Database & Queue Setup ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS print_jobs (
            id TEXT PRIMARY KEY,
            printer_name TEXT,
            status TEXT,
            retries INTEGER DEFAULT 0,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            file_path TEXT,
            error_message TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS license_cache (
            api_key TEXT PRIMARY KEY,
            token TEXT,
            expires_at DATETIME
        )
    ''')
    conn.commit()
    conn.close()

init_db()

class PrintQueueManager:
    def __init__(self):
        self.queues = {}
        self.threads = {}
        self.lock = threading.Lock()
        
        # Load pending jobs from DB on startup
        self._recover_jobs()
        
        # Start cleanup thread
        threading.Thread(target=self._cleanup_loop, daemon=True).start()

    def _recover_jobs(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id, printer_name, status, retries, file_path, error_message FROM print_jobs WHERE status IN ('pending', 'printing')")
        jobs = c.fetchall()
        
        for job in jobs:
            job_dict = {
                'id': job[0],
                'printer_name': job[1],
                'status': 'pending', # Reset 'printing' back to 'pending'
                'retries': job[3],
                'file_path': job[4],
                'error_message': job[5]
            }
            c.execute("UPDATE print_jobs SET status = 'pending' WHERE id = ?", (job[0],))
            self.enqueue_job(job_dict, save_to_db=False)
            
        conn.commit()
        conn.close()

    def _cleanup_loop(self):
        while True:
            time.sleep(3600) # Run cleanup every hour
            self._cleanup_old_jobs()
            
    def _cleanup_old_jobs(self):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            # Keep last 50 completed/failed/cancelled, delete older ones
            c.execute('''
                SELECT id, file_path FROM print_jobs 
                WHERE status IN ('completed', 'failed', 'cancelled') 
                ORDER BY timestamp DESC LIMIT -1 OFFSET 50
            ''')
            old_jobs = c.fetchall()
            
            for job_id, file_path in old_jobs:
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        print(f"Error removing file {file_path}: {e}")
                c.execute("DELETE FROM print_jobs WHERE id = ?", (job_id,))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Cleanup error: {e}")

    def enqueue_job(self, job, save_to_db=True):
        printer_name = job['printer_name']
        
        if save_to_db:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('''
                INSERT INTO print_jobs (id, printer_name, status, retries, file_path, error_message)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (job['id'], printer_name, job['status'], job['retries'], job['file_path'], job.get('error_message', '')))
            conn.commit()
            conn.close()
            
        with self.lock:
            if printer_name not in self.queues:
                self.queues[printer_name] = queue.Queue()
                t = threading.Thread(target=self._worker_loop, args=(printer_name,), daemon=True)
                self.threads[printer_name] = t
                t.start()
                
        self.queues[printer_name].put(job['id'])

    def _update_job_status(self, job_id, status, error_message='', increment_retry=False):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        if increment_retry:
            c.execute("UPDATE print_jobs SET status = ?, error_message = ?, retries = retries + 1 WHERE id = ?", (status, error_message, job_id))
        else:
            c.execute("UPDATE print_jobs SET status = ?, error_message = ? WHERE id = ?", (status, error_message, job_id))
        conn.commit()
        conn.close()

    def _get_job(self, job_id):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM print_jobs WHERE id = ?", (job_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    def _worker_loop(self, printer_name):
        q = self.queues[printer_name]
        while True:
            job_id = q.get()
            job = self._get_job(job_id)
            
            if not job or job['status'] == 'cancelled':
                q.task_done()
                continue
                
            self._update_job_status(job_id, 'printing')
            
            printers_config = load_printers()
            target_printer = printers_config.get(printer_name)
            
            if not target_printer:
                self._update_job_status(job_id, 'failed', f"Printer {printer_name} not found in config")
                q.task_done()
                continue
                
            file_path = job['file_path']
            print_type = target_printer['type']
            success = False
            message = ""
            
            try:
                if print_type == 'system':
                    success, message = print_to_system(file_path, target_printer.get("system_name"))
                elif print_type == 'escpos':
                    if os.path.exists(file_path):
                        with open(file_path, 'rb') as f:
                            image_bytes = f.read()
                        success, message = print_to_escpos(image_bytes, target_printer.get("ip"), target_printer.get("port"))
                    else:
                        success, message = False, f"Image file not found: {file_path}"
                elif print_type == 'tspl':
                    success, message = print_to_tspl(file_path, target_printer)
                elif print_type == 'qz':
                    success, message = print_to_qz_tray(file_path)
                else:
                    success, message = False, f"Unknown printer type: {print_type}"
            except Exception as e:
                success = False
                message = str(e)
                
            if success:
                self._update_job_status(job_id, 'completed', message)
            else:
                settings = load_settings()
                max_retries = int(settings.get('max_retries', 5))
                retry_delay = int(settings.get('retry_delay', 3))
                
                retries = job['retries']
                if retries < max_retries:
                    self._update_job_status(job_id, 'pending', message, increment_retry=True)
                    time.sleep(retry_delay) # Simple backoff before retrying
                    q.put(job_id) 
                else:
                    self._update_job_status(job_id, 'failed', message, increment_retry=True)
                    
            q.task_done()


# --- Dedicated Printing Functions ---
def print_to_system(file_name, system_printer_name):
    """Prints the image file using the OS print queue."""
    try:
        if IS_WINDOWS:
            import win32print
            import win32ui
            from PIL import ImageWin
            
            print(f"🖨️ Sending print job to Windows OS printer: **{system_printer_name}**")
            hprinter = win32print.OpenPrinter(system_printer_name)
            try:
                hdc = win32ui.CreateDC()
                hdc.CreatePrinterDC(system_printer_name)
                
                # PHYSICALWIDTH=110, PHYSICALHEIGHT=111
                printer_width = hdc.GetDeviceCaps(110)
                
                img = Image.open(file_name)
                
                hdc.StartDoc(file_name)
                hdc.StartPage()
                
                dib = ImageWin.Dib(img)
                # Scale image to fit width while maintaining aspect ratio
                ratio = printer_width / img.width
                scaled_height = int(img.height * ratio)
                
                dib.draw(hdc.GetHandleOutput(), (0, 0, printer_width, scaled_height))
                
                hdc.EndPage()
                hdc.EndDoc()
                hdc.DeleteDC()
                return True, "Print job sent successfully to Windows OS."
            finally:
                win32print.ClosePrinter(hprinter)
        else:
            # Use 'lp' (Linux/macOS standard) to send the file to the OS printer queue
            print_command = [
                'lp', '-d', system_printer_name, '-o', 'fit-to-page', file_name
            ]
            print(f"🖨️ Sending print job to macOS/Linux OS printer: **{system_printer_name}**")
            run(print_command, check=True)
            return True, "Print job sent successfully to OS."
    except Exception as e:
        return False, f"OS printing failed: {e}"


def print_to_escpos(image_bytes, ip, port):
    """Prints the image by connecting to an ESC/POS network printer."""
    try:
        p = EscposNetworkPrinter(ip, port)
        img = Image.open(BytesIO(image_bytes))
        p.image(img)
        p.cut()
        p.close()
        return True, f"Print job sent successfully to ESC/POS at {ip}:{port}."
    except socket.error as e:
        return False, f"ESC/POS connection error: {e}"
    except Exception as e:
        return False, f"ESC/POS printing failed: {e}"


def print_to_tspl(file_path, target_printer):
    """Prints a dynamic label using raw TSPL BITMAP commands from a raster image."""
    try:
        if not os.path.exists(file_path):
            return False, f"Image file not found: {file_path}"
            
        if not file_path.endswith('.png'):
            return False, "TSPL printers now expect a .png raster image."
            
        # 1. Convert PNG to TSPL bitmap data
        img = Image.open(file_path)
        img_binary = img.convert('1')
        width_px, height_px = img_binary.size
        width_bytes = (width_px + 7) // 8
        
        bitmap_data = bytearray()
        for y in range(height_px):
            for x_byte in range(width_bytes):
                byte_val = 0
                for bit in range(8):
                    x = x_byte * 8 + bit
                    if x < width_px:
                        # For TSPL: 1 is black (print), 0 is white (no print)
                        # PIL '1' mode: 0 is black, 255 is white
                        pixel = img_binary.getpixel((x, y))
                        if pixel == 0:
                            byte_val |= (1 << (7 - bit))
                bitmap_data.append(byte_val)
                
        # 2. Generate TSPL Command Sequence
        width_mm = width_px / 8.0
        height_mm = height_px / 8.0
        
        cmds = bytearray()
        cmds.extend(f"SIZE {width_mm:.1f} mm,{height_mm:.1f} mm\r\n".encode('utf-8'))
        cmds.extend(b"GAP 2 mm,0\r\n")
        cmds.extend(b"DIRECTION 1\r\n")
        cmds.extend(b"CLS\r\n")
        
        # BITMAP X,Y,width_in_bytes,height_in_dots,mode,bitmap_data
        cmds.extend(f"BITMAP 0,0,{width_bytes},{height_px},0,".encode('utf-8'))
        cmds.extend(bytes(bitmap_data))
        cmds.extend(b"\r\nPRINT 1,1\r\n")
        
        tspl_bytes = bytes(cmds)
        
        ip = target_printer.get("ip")
        
        if ip and ip != "127.0.0.1":
            port = target_printer.get("port", 9100)
            print(f"🖨️ Sending TSPL to network printer {ip}:{port}")
            with socket.create_connection((ip, port), timeout=5) as s:
                s.sendall(tspl_bytes)
            return True, f"Print job sent successfully to TSPL at {ip}:{port}."
        else:
            system_name = target_printer.get("system_name")
            print(f"🖨️ Sending TSPL to USB printer {system_name} via OS spooler")
            if IS_WINDOWS:
                import win32print
                hprinter = win32print.OpenPrinter(system_name)
                try:
                    win32print.StartDocPrinter(hprinter, 1, ("TSPL Print Job", None, "RAW"))
                    win32print.StartPagePrinter(hprinter)
                    win32print.WritePrinter(hprinter, tspl_bytes)
                    win32print.EndPagePrinter(hprinter)
                    win32print.EndDocPrinter(hprinter)
                finally:
                    win32print.ClosePrinter(hprinter)
                return True, "TSPL print job sent successfully to Windows USB spooler."
            else:
                print_command = ['lp', '-d', system_name, '-o', 'raw']
                run(print_command, input=tspl_bytes, check=True)
                return True, "TSPL print job sent successfully to macOS/Linux USB spooler."
                
    except socket.error as e:
        return False, f"TSPL network connection error: {e}"
    except Exception as e:
        return False, f"TSPL printing failed: {e}"


def print_to_qz_tray(receipt_data):
    return False, "QZ Tray communication not fully implemented in centralized proxy."


# --- API Routes ---
@app.route('/')
def index():
    return render_template('base.html', printers=load_printers())

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        try:
            new_printers = json.loads(request.form.get('printers_json', '{}'))
            save_printers(new_printers)
            
            new_settings = {
                "max_retries": int(request.form.get('max_retries', 5)),
                "retry_delay": int(request.form.get('retry_delay', 3))
            }
            save_settings(new_settings)
            
            message = "Settings and Printers updated successfully!"
        except Exception as e:
            message = f"Error saving JSON: {e}"
    else:
        message = ""

    current_printers = load_printers()
    printers_json_str = json.dumps(current_printers, indent=4)
    current_settings = load_settings()
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Ridhira Print Proxy Settings</title>
        <style>
            body { font-family: Arial, sans-serif; background-color: #f4f4f9; padding: 20px; max-width: 800px; margin: auto; }
            .header-container { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #ccc; padding-bottom: 10px; margin-bottom: 15px; }
            h2 { color: #333; margin: 0; }
            .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px; }
            textarea { width: 100%; height: 350px; font-family: monospace; font-size: 14px; padding: 15px; border: 1px solid #ccc; border-radius: 5px; box-sizing: border-box; }
            .btn { background-color: #28a745; color: white; padding: 12px 25px; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; margin-top: 15px; font-weight: bold; width: 100%; }
            .btn:hover { background-color: #218838; }
            .msg { background-color: #d4edda; color: #155724; padding: 10px; border-radius: 4px; border: 1px solid #c3e6cb; margin-bottom: 15px; }
            .error { background-color: #f8d7da; color: #721c24; padding: 10px; border-radius: 4px; border: 1px solid #f5c6cb; margin-bottom: 15px; }
            .back-link { text-decoration: none; color: #28a745; font-weight: bold; padding: 8px 15px; border: 1px solid #28a745; border-radius: 4px; }
            .back-link:hover { background-color: #28a745; color: white; }
            .form-group { margin-bottom: 15px; }
            label { font-weight: bold; display: block; margin-bottom: 5px; color: #555; }
            input[type="number"] { width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
        </style>
    </head>
    <body>
        <div class="header-container">
            <h2>Proxy Configuration</h2>
            <a href="{{ url_for('index') }}" class="back-link">Home Dashboard</a>
        </div>
        {% if message %}
            <div class="{% if 'Error' in message %}error{% else %}msg{% endif %}">{{ message }}</div>
        {% endif %}
        
        <form method="POST">
            <div class="card">
                <h3>Global Settings</h3>
                <div class="form-group">
                    <label>Max Retries (Print Queue)</label>
                    <input type="number" name="max_retries" value="{{ current_settings.get('max_retries', 5) }}" required>
                </div>
                <div class="form-group">
                    <label>Retry Delay (Seconds)</label>
                    <input type="number" name="retry_delay" value="{{ current_settings.get('retry_delay', 3) }}" required>
                </div>
            </div>

            <div class="card">
                <h3>Printer Configuration JSON</h3>
                <p style="margin-top:0; color:#666; font-size: 14px;">Edit the JSON below to configure your printers. Be careful not to break the JSON format!</p>
                <textarea name="printers_json">{{ printers_json }}</textarea>
            </div>
            
            <button class="btn" type="submit">Save Changes</button>
        </form>
    </body>
    </html>
    """
    return render_template_string(html, printers_json=printers_json_str, message=message)


@app.route('/detect', methods=['GET'])
def detect_printers():
    printers = load_printers()
    printers["POS_Printer"] = {
        "system_name": "POS_Printer_Default",
        "type": "system",
        "kitchen": False
    }
    printers["Kitchen_Printer"] = {
        "system_name": "Kitchen_Printer_Default",
        "type": "system",
        "kitchen": True
    }
    save_printers(printers)
    return jsonify(printers)


@app.route('/assign', methods=['POST'])
def assign_printer():
    data = request.json
    printers = load_printers()
    printers[data['name']] = {
        "kitchen": data.get("kitchen", False),
        "type": data.get("type", "system"), 
        "system_name": data.get("system_name", data['name']), 
        "ip": data.get("ip", "127.0.0.1"), 
        "port": data.get("port", 9100), 
    }
    save_printers(printers)
    return jsonify({"message": "Printer assigned successfully"})


@app.route('/api/jobs', methods=['GET'])
def api_get_jobs():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT id, printer_name, status, retries, timestamp, error_message FROM print_jobs ORDER BY timestamp DESC LIMIT 100")
    jobs = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(jobs)


@app.route('/api/jobs/retry/<job_id>', methods=['POST'])
def api_retry_job(job_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM print_jobs WHERE id = ?", (job_id,))
    row = c.fetchone()
    
    if row and row['status'] == 'failed':
        c.execute("UPDATE print_jobs SET status = 'pending', retries = 0, error_message = '' WHERE id = ?", (job_id,))
        conn.commit()
        
        job_dict = dict(row)
        job_dict['status'] = 'pending'
        job_dict['retries'] = 0
        queue_manager.enqueue_job(job_dict, save_to_db=False)
        conn.close()
        return jsonify({"success": True, "message": "Job queued for retry."})
    
    conn.close()
    return jsonify({"success": False, "message": "Job not found or not in failed state."}), 400


@app.route('/api/jobs/cancel/<job_id>', methods=['POST'])
def api_cancel_job(job_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM print_jobs WHERE id = ?", (job_id,))
    row = c.fetchone()
    if row:
        c.execute("UPDATE print_jobs SET status = 'cancelled' WHERE id = ?", (job_id,))
        conn.commit()
        
        file_path = row['file_path']
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        conn.close()
        return jsonify({"success": True})
        
    conn.close()
    return jsonify({"success": False}), 404


@app.route('/api/printers/status', methods=['GET'])
def api_printers_status():
    printers = load_printers()
    status_data = {}
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT printer_name, COUNT(*) FROM print_jobs WHERE status IN ('pending', 'printing') GROUP BY printer_name")
    queue_counts = dict(c.fetchall())
    conn.close()
    
    for name, config in printers.items():
        status_data[name] = {
            'type': config.get('type'),
            'kitchen': config.get('kitchen'),
            'queue_length': queue_counts.get(name, 0)
        }
    return jsonify(status_data)


def generate_test_image_bytes(printer_name):
    try:
        img_width = 384
        img_height = 400
        img = Image.new('L', (img_width, img_height), color=255)
        d = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 20) 
        except IOError:
            font = ImageFont.load_default()

        d.text((10, 20), "Ridhira POS Print Proxy", fill=0, font=font)
        d.text((10, 60), "--- TEST PRINT SUCCESS ---", fill=0, font=font)
        d.text((10, 100), f"Printer Name: {printer_name}", fill=0, font=font)
        d.text((10, 140), "Type: Confirmed Connection", fill=0, font=font)
        d.text((10, 180), f"Timestamp: {os.times()[4]}", fill=0, font=font)
        d.text((10, 220), "--------------------------", fill=0, font=font)
        
        buf = BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()
    except Exception as e:
        print(f"Error generating test image: {e}")
        return None

def generate_tspl_commands(cup_data):
    """
    Generates TSPL commands for Boba/Sticker printing based on dynamic label size.
    Converts pixel dimensions to millimeters assuming 203 DPI (8 dots/mm).
    """
    img_width_px = int(cup_data.get('label_width', 400))
    img_height_px = int(cup_data.get('label_height', 300))
    
    width_mm = img_width_px / 8.0
    height_mm = img_height_px / 8.0
    
    order_name = cup_data.get('order_name', '')
    seq = cup_data.get('sequence', '')
    is_takeout = cup_data.get('is_takeout', 'Takeout')
    table_no = cup_data.get('table_no', '')
    order_time = cup_data.get('order_time', '')
    change = cup_data.get('change', {})
    drink_name = change.get('name', 'Unknown Drink')
    is_cancelled = cup_data.get('is_cancelled', False)
    modifiers = cup_data.get('modifiers', '')
    price = cup_data.get('price', '')
    if isinstance(price, str):
        price = price.replace('\xa0', ' ').replace('\u00A0', ' ')
    
    if '(' in drink_name:
        drink_name = drink_name.split('(')[0].strip()
        
    cmds = []
    cmds.append(f"SIZE {width_mm:.1f} mm,{height_mm:.1f} mm")
    cmds.append("GAP 2 mm,0")
    cmds.append("DIRECTION 1")
    cmds.append("CLS")
    
    y = 20
    font = "2"
    font_small = "1"
    
    # 1. Header
    cmds.append(f'TEXT 20,{y},"{font}",0,1,1,"{is_takeout}"')
    order_header = f"{order_name} [{seq}]"
    cmds.append(f'TEXT {img_width_px - 200},{y},"{font}",0,1,1,"{order_header}"')
    y += 40
    
    if is_takeout != "Takeout" and table_no:
        cmds.append(f'TEXT 20,{y},"{font}",0,1,1,"{table_no}"')
        
    # Estimate width to prevent overlap in TSPL
    table_w_approx = 20 + len(str(table_no)) * 16 if (is_takeout != "Takeout" and table_no) else 0
    time_w_approx = len(str(order_time)) * 16
    time_x = max(img_width_px - time_w_approx - 20, img_width_px - 200)
    
    if table_w_approx + 10 > time_x:
        y += 40
        
    cmds.append(f'TEXT {time_x},{y},"{font}",0,1,1,"{order_time}"')
    y += 40
    
    # 2. Drink Name
    words = drink_name.split()
    current_line = ""
    for w in words:
        if len(current_line + w) > 20 and current_line:
            cmds.append(f'TEXT 20,{y},"{font}",0,1,1,"{current_line.strip()}"')
            y += 40
            current_line = w + " "
        else:
            current_line += w + " "
    if current_line:
        cmds.append(f'TEXT 20,{y},"{font}",0,1,1,"{current_line.strip()}"')
        y += 40
        
    # 3. Modifiers
    if modifiers:
        mod_words = modifiers.replace(" | ", ", ").split()
        mod_curr = ""
        for w in mod_words:
            if len(mod_curr + w) > 30 and mod_curr:
                cmds.append(f'TEXT 40,{y},"{font_small}",0,1,1,"{mod_curr.strip()}"')
                y += 30
                mod_curr = w + " "
            else:
                mod_curr += w + " "
        if mod_curr:
            cmds.append(f'TEXT 40,{y},"{font_small}",0,1,1,"{mod_curr.strip()}"')
            y += 30
            
    # 4. Price
    if price:
        cmds.append(f'TEXT 20,{y},"{font}",0,1,1,"{price}"')
        
    if is_cancelled:
        y += 40
        cmds.append(f'TEXT 20,{y},"{font}",0,1,1,"*** CANCELLED ***"')
        
    cmds.append("PRINT 1,1")
    return "\r\n".join(cmds) + "\r\n"

def render_boba_label(cup_data):
    """
    Renders a dynamic label for Boba/Sticker printing using the new layout standard.
    """
    # Extract configured dimensions or default to 400x300
    img_width = int(cup_data.get('label_width', 400))
    img_height = int(cup_data.get('label_height', 300))
    
    img = Image.new('L', (img_width, img_height), color=255)
    d = ImageDraw.Draw(img)
    
    try:
        font_dir = os.path.join(BUNDLE_DIR, 'fonts')
        
        # Load fonts at various sizes
        font_large = ImageFont.truetype(os.path.join(font_dir, 'Roboto-Bold.ttf'), 36)
        font_bold_medium = ImageFont.truetype(os.path.join(font_dir, 'Roboto-Bold.ttf'), 26)
        font_regular_medium = ImageFont.truetype(os.path.join(font_dir, 'Roboto-Regular.ttf'), 26)
        font_regular_small = ImageFont.truetype(os.path.join(font_dir, 'Roboto-Regular.ttf'), 22)
    except IOError:
        font_large = font_bold_medium = font_regular_medium = font_regular_small = ImageFont.load_default()

    # Data extraction
    order_name = cup_data.get('order_name', '')
    seq = cup_data.get('sequence', '')
    is_takeout = cup_data.get('is_takeout', 'Takeout')
    table_no = cup_data.get('table_no', '')
    order_time = cup_data.get('order_time', '')
    change = cup_data.get('change', {})
    drink_name = change.get('name', 'Unknown Drink')
    is_cancelled = cup_data.get('is_cancelled', False)
    
    # Strip any variant parenthesis from the base drink name since modifiers handles it
    if '(' in drink_name:
        drink_name = drink_name.split('(')[0].strip()
        
    modifiers = cup_data.get('modifiers', '')
    price = cup_data.get('price', '')
    if isinstance(price, str):
        price = price.replace('\xa0', ' ').replace('\u00A0', ' ')
    
    # Starting Y coordinate
    y = 10
    
    # 1. Header: Order number and sequence at top right
    # Left side: Takeout/Dine In (Point 2)
    d.text((10, y), f"{is_takeout}", font=font_bold_medium, fill=0)
    
    # Right side: Order # and Sequence
    order_header = f"{order_name}   [{seq}]"
    header_bbox = d.textbbox((0, 0), order_header, font=font_bold_medium)
    header_w = header_bbox[2] - header_bbox[0]
    d.text((img_width - header_w - 15, y), order_header, font=font_bold_medium, fill=0)
    
    y += 35
    
    # 3. Table and Time of Order
    table_w = 0
    if is_takeout != "Takeout" and table_no:
        d.text((10, y), f"{table_no}", font=font_regular_medium, fill=0)
        table_bbox = d.textbbox((0, 0), str(table_no), font=font_regular_medium)
        table_w = table_bbox[2] - table_bbox[0]
    
    time_bbox = d.textbbox((0, 0), order_time, font=font_regular_medium)
    time_w = time_bbox[2] - time_bbox[0]
    time_x = img_width - time_w - 15
    
    if (10 + table_w + 10) > time_x:
        y += 35
        
    d.text((time_x, y), order_time, font=font_regular_medium, fill=0)
    
    y += 40
    d.line([(10, y), (img_width - 15, y)], fill=0, width=2)
    y += 15
    
    # 4. Drink Name (Prominent/Bold)
    # Wrap drink name if it's too long
    words = drink_name.split()
    lines = []
    current_line = ""
    for w in words:
        test_line = current_line + w + " "
        bbox = d.textbbox((0,0), test_line, font=font_large)
        if bbox[2] - bbox[0] > (img_width - 20) and current_line:
            lines.append(current_line.strip())
            current_line = w + " "
        else:
            current_line = test_line
    if current_line:
        lines.append(current_line.strip())
        
    for line in lines:
        d.text((10, y), line, font=font_large, fill=0)
        y += 40
        
    y += 5
    
    # 5. Modifiers
    if modifiers:
        # Wrap modifiers to fit canvas width
        mod_words = modifiers.replace(" | ", ", ").split()
        mod_lines = []
        mod_curr = ""
        for w in mod_words:
            test_line = mod_curr + w + " "
            bbox = d.textbbox((0,0), test_line, font=font_regular_small)
            if bbox[2] - bbox[0] > (img_width - 20) and mod_curr:
                mod_lines.append(mod_curr.strip())
                mod_curr = w + " "
            else:
                mod_curr = test_line
        if mod_curr:
            mod_lines.append(mod_curr.strip())
            
        for line in mod_lines:
            d.text((20, y), f"{line}", font=font_regular_small, fill=0)
            y += 25
            
    y += 10
    
    # 6. Price
    if price:
        price_txt = f"{price}"
        d.text((10, y), price_txt, font=font_bold_medium, fill=0)
        
    # Cancelled stamp if needed
    if is_cancelled:
        y += 35
        d.text((10, y), "*** CANCELLED ***", font=font_large, fill=0)

    # Convert to pure black and white binary format for EscPos image printing
    img_binary = img.convert('1')
    return img_binary

@app.route('/test_print/<printer>', methods=['POST'])
def test_print(printer):
    try:
        printers_config = load_printers()
        if printer not in printers_config:
            return jsonify({"success": False, "message": f"Printer '{printer}' not found."}), 400

        image_bytes = generate_test_image_bytes(printer)
        if image_bytes is None:
            return jsonify({"success": False, "message": "Failed to generate test image."}), 500

        timestamp_ms = int(time.time() * 1000)
        job_id = f"test_{printer}_{timestamp_ms}"
        file_name = os.path.join(IMAGE_SAVE_PATH, f'{job_id}.png')
        
        Image.open(BytesIO(image_bytes)).save(file_name)
        
        job = {
            'id': job_id,
            'printer_name': printer,
            'status': 'pending',
            'retries': 0,
            'file_path': file_name
        }
        queue_manager.enqueue_job(job)

        return jsonify({"success": True, "message": f"Test print job queued for {printer}."}), 200

    except Exception as e:
        return jsonify({"success": False, "message": f"Test print error: {e}"}), 500

def execute_cashbox_kick(printer_name, rpc_id):
    printers_config = load_printers()
    if printer_name not in printers_config:
        return jsonify({
            "jsonrpc": "2.0", "id": rpc_id, 
            "error": {"code": 200, "message": "Odoo Server Error", "data": {"name": "ProxyError", "message": f"Printer '{printer_name}' not configured."}}
        }), 200
        
    target_printer = printers_config[printer_name]
    print_type = target_printer.get('type')
    
    print(f"🖨️ Kicking cash drawer for: **{printer_name}** (Type: {print_type})")
    
    success = False
    message = ""
    
    if print_type == 'escpos':
        ip = target_printer.get("ip")
        port = target_printer.get("port")
        try:
            p = EscposNetworkPrinter(ip, port)
            p.cashdraw(2)
            p.close()
            success = True
        except Exception as e:
            success = False
            message = f"ESC/POS cashbox error: {e}"
    elif print_type == 'system':
        system_name = target_printer.get("system_name")
        try:
            # Standard ESC/POS pulse command: ESC p m t1 t2
            kick_sequence = b'\x1B\x70\x00\x19\xFA'
            
            if IS_WINDOWS:
                import win32print
                hprinter = win32print.OpenPrinter(system_name)
                try:
                    win32print.StartDocPrinter(hprinter, 1, ("Cash Drawer Kick", None, "RAW"))
                    win32print.StartPagePrinter(hprinter)
                    win32print.WritePrinter(hprinter, kick_sequence)
                    win32print.EndPagePrinter(hprinter)
                    win32print.EndDocPrinter(hprinter)
                finally:
                    win32print.ClosePrinter(hprinter)
            else:
                print_command = ['lp', '-d', system_name, '-o', 'raw']
                run(print_command, input=kick_sequence, check=True)
                
            success = True
        except Exception as e:
            success = False
            message = f"System printer cashbox error: {e}"
    else:
        success = False
        message = f"Cashbox open not supported for printer type: {print_type}"

    if success:
        return jsonify({"jsonrpc": "2.0", "id": rpc_id, "result": True}), 200
    else:
        return jsonify({
            "jsonrpc": "2.0", "id": rpc_id, 
            "error": {"code": 200, "message": "Odoo Server Error", "data": {"name": "ProxyError", "message": message}}
        }), 200


import uuid
import subprocess

def get_machine_id():
    """Generates a permanent, physical machine ID based on the OS."""
    try:
        os_name = platform.system()
        if os_name == "Windows":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
                return winreg.QueryValueEx(key, "MachineGuid")[0]
                
        elif os_name == "Linux":
            with open("/etc/machine-id", "r") as f:
                return f.read().strip()
                
        elif os_name == "Darwin": # macOS
            output = subprocess.check_output(['ioreg', '-rd1', '-c', 'IOPlatformExpertDevice']).decode('utf-8')
            for line in output.split('\n'):
                if 'IOPlatformUUID' in line:
                    return line.split('=')[1].strip().strip('"')
    except Exception as e:
        print(f"[DEBUG] Error reading OS Machine ID: {e}")
        
    # Extreme Fallback: Generate a random UUID and save it to a local hidden file
    try:
        fallback_file = os.path.join(APPLICATION_PATH, '.device_id_fallback')
        if os.path.exists(fallback_file):
            with open(fallback_file, 'r') as f:
                return f.read().strip()
        new_uuid = uuid.uuid4().hex
        with open(fallback_file, 'w') as f:
            f.write(new_uuid)
        return new_uuid
    except:
        return "UNKNOWN-DEVICE-ID"


# --- License Verification ---
def verify_license(api_key):
    print(f"[DEBUG] verify_license called with api_key: {api_key}")
    if not api_key:
        print("[DEBUG] No API Key provided.")
        return False, "Missing API Key. Configure it in Odoo POS Settings."
        
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT token, expires_at FROM license_cache WHERE api_key = ?", (api_key,))
        row = c.fetchone()
        
        now = datetime.now(pytz.utc)
        
        # 1. Check Offline Cache
        if row:
            token = row[0]
            expires_at_str = row[1]
            try:
                expires_at = dateutil.parser.parse(expires_at_str)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=pytz.utc)
                
                if now < expires_at:
                    print("[DEBUG] Valid offline token found.")
                    # Mathematically verify the signature offline!
                    decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
                    if decoded.get('status') == 'active':
                        conn.close()
                        return True, "Valid"
                else:
                    print("[DEBUG] Offline token is expired.")
            except Exception as e:
                print(f"[DEBUG] Local token validation failed: {e}")
                # Fall through to internet check if local validation fails
        else:
            print("[DEBUG] No offline token found for this key.")
        
        # 2. Make Internet Request (Token missing or expired)
        print("[DEBUG] Checking SaaS License Server...")
        machine_id = get_machine_id()
        response = requests.post(LICENSE_SERVER_URL, json={"api_key": api_key, "device_id": machine_id}, timeout=5)
        print(f"[DEBUG] Cloudflare responded with HTTP {response.status_code}: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'active' and data.get('token'):
                # Save to cache
                c.execute("REPLACE INTO license_cache (api_key, token, expires_at) VALUES (?, ?, ?)", 
                          (api_key, data['token'], data['expires_at']))
                conn.commit()
                conn.close()
                return True, "Valid"
        
        conn.close()
        return False, "License Expired"
        
    except Exception as e:
        print(f"[DEBUG] License verification error: {e}")
        return False, f"License Verification Error: {e}"

@app.route('/hw_proxy/open_cashbox', methods=['POST'])
def handle_open_cashbox():
    try:
        data = request.json
        rpc_id = data.get('id', 1) if data else 1
        
        # Verify License
        api_key = data.get('params', {}).get('api_key')
        is_valid, msg = verify_license(api_key)
        if not is_valid:
             return jsonify({
                 "jsonrpc": "2.0", "id": rpc_id, 
                 "error": {"code": 200, "message": "License Expired", "data": {"name": "ProxyError", "message": msg}}
             }), 200
             
        printer_name = "POS_Printer"
        if data and data.get('params', {}).get('printer_name'):
             printer_name = data['params']['printer_name']
             
        return execute_cashbox_kick(printer_name, rpc_id)
    except Exception as e:
        rpc_id = request.json.get('id', 1) if request.is_json else 1
        return jsonify({
            "jsonrpc": "2.0", "id": rpc_id, 
            "error": {"code": 200, "message": "Odoo Server Error", "data": {"name": "ProxyError", "message": f"Proxy server error: {e}"}}
        }), 200


import hashlib

# --- Deduplication Cache ---
recent_prints_cache = {}
cache_lock = threading.Lock()

def is_duplicate_print(receipt_data):
    """
    Returns True if the exact same receipt_data was processed within the last 10 seconds.
    This safely drops duplicate retries from Odoo POS caused by network/license timeouts.
    """
    current_time = time.time()
    # Create MD5 hash of the payload
    payload_hash = hashlib.md5(receipt_data.encode('utf-8')).hexdigest()
    
    with cache_lock:
        # Cleanup old entries (older than 10 seconds)
        keys_to_delete = [k for k, v in recent_prints_cache.items() if current_time - v > 10]
        for k in keys_to_delete:
            del recent_prints_cache[k]
            
        if payload_hash in recent_prints_cache:
            return True
        else:
            recent_prints_cache[payload_hash] = current_time
            return False


@app.route('/hw_proxy/default_printer_action', methods=['POST'])
def handle_default_printer_action():
    try:
        data = request.json
        if data is None:
            return jsonify({"jsonrpc": "2.0", "id": 1, "error": {"code": 200, "message": "Odoo Server Error", "data": {"name": "ProxyError", "message": "Empty body"}}}), 200
            
        rpc_id = data.get('id', 1)
        data_obj = data.get('params', {}).get('data', {})
        api_key = data_obj.get('api_key')
        
        print(f"[DEBUG] Incoming default printer action. Received API key: {api_key}")
        
        # Verify License
        is_valid, msg = verify_license(api_key)
        if not is_valid:
             return jsonify({
                 "jsonrpc": "2.0", "id": rpc_id, 
                 "error": {"code": 200, "message": "License Expired", "data": {"name": "ProxyError", "message": msg}}
             }), 200

        printer_name = data_obj.get('printer_name')
        
        if not printer_name:
            printer_name = "POS_Printer"
            
        if data_obj.get('action') == 'cashbox':
            return execute_cashbox_kick(printer_name, rpc_id)
            
        receipt_data = data_obj.get('receipt')
        
        printers_config = load_printers()
        if printer_name not in printers_config:
            return jsonify({
                "jsonrpc": "2.0", "id": rpc_id, 
                "error": {"code": 200, "message": "Odoo Server Error", "data": {"name": "ProxyError", "message": f"Printer '{printer_name}' not configured."}}
            }), 200
            
        if not receipt_data:
            return jsonify({
                "jsonrpc": "2.0", "id": rpc_id, 
                "error": {"code": 200, "message": "Odoo Server Error", "data": {"name": "ProxyError", "message": "Receipt data not found."}}
            }), 200
            
        # Check for duplicate retries
        if is_duplicate_print(receipt_data):
            print(f"[DEBUG] Deduplication triggered: Ignoring duplicate print request from Odoo POS retry.")
            return jsonify({"jsonrpc": "2.0", "id": rpc_id, "result": True}), 200
            
        try:
            image_bytes = base64.b64decode(receipt_data)
            
            # Check for Boba JSON payload
            if image_bytes.startswith(b"BOBA_LABEL_JSON:"):
                print(f"[DEBUG] Boba Label JSON format detected! Decoding payload...")
                json_str = image_bytes.split(b":", 1)[1].decode('utf-8')
                print(f"[DEBUG] Boba Label JSON payload received: {json_str}")
                cup_data = json.loads(json_str)
                
                target_printer_type = printers_config.get(printer_name, {}).get("type", "system")
                timestamp_ms = int(time.time() * 1000)
                job_id = f"receipt_{rpc_id}_{printer_name}_{timestamp_ms}"
                
                # We now ALWAYS generate an image, even for TSPL printers
                img = render_boba_label(cup_data)
                print(f"[DEBUG] Successfully rendered Boba label image canvas for {cup_data.get('order_name', 'Unknown')}.")
                file_name = os.path.join(IMAGE_SAVE_PATH, f'{job_id}.png')
                img.save(file_name)
            else:
                img = Image.open(BytesIO(image_bytes))
                timestamp_ms = int(time.time() * 1000)
                job_id = f"receipt_{rpc_id}_{printer_name}_{timestamp_ms}"
                file_name = os.path.join(IMAGE_SAVE_PATH, f'{job_id}.png')
                img.save(file_name)
        except Exception as e:
            return jsonify({
                "jsonrpc": "2.0", "id": rpc_id, 
                "error": {"code": 200, "message": "Odoo Server Error", "data": {"name": "ProxyError", "message": f"Image decoding error: {e}"}}
            }), 200
            
        job = {
            'id': job_id,
            'printer_name': printer_name,
            'status': 'pending',
            'retries': 0,
            'file_path': file_name
        }
        
        queue_manager.enqueue_job(job)
        
        return jsonify({"jsonrpc": "2.0", "id": rpc_id, "result": True}), 200
        
    except Exception as e:
        rpc_id = request.json.get('id', 1) if request.is_json else 1
        return jsonify({
            "jsonrpc": "2.0", "id": rpc_id, 
            "error": {"code": 200, "message": "Odoo Server Error", "data": {"name": "ProxyError", "message": f"Proxy server error: {e}"}}
        }), 200


# Initialize the queue manager globally so it works in WSGI mode
queue_manager = PrintQueueManager()

if __name__ == '__main__':
    # Run the Flask app with Waitress WSGI server
    print("Starting proxy with Waitress on port 9100...")
    serve(app, host='0.0.0.0', port=9100)
