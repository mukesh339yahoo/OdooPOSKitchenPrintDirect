import base64
import re
import json
import os
import socket
import sqlite3
import threading
import queue
import time
from datetime import datetime
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, jsonify, request, render_template
from xml.etree import ElementTree as ET
from flask_cors import CORS
from subprocess import run, CalledProcessError
# Imports for ESC/POS (Requires 'python-escpos')
from escpos.printer import Network as EscposNetworkPrinter
from waitress import serve
# Imports for QZ TRAY (Requires 'websocket-client' if implemented)
# import websocket 
# import ssl 

app = Flask(__name__)

# --- Configuration ---
IMAGE_SAVE_PATH = 'print_images'
DB_PATH = 'jobs.db'
PRINTERS_FILE = os.path.join(os.path.dirname(__file__), "printers.json")

if not os.path.exists(IMAGE_SAVE_PATH):
    os.makedirs(IMAGE_SAVE_PATH)

if not os.path.exists(PRINTERS_FILE):
    with open(PRINTERS_FILE, "w") as f:
        json.dump({}, f)

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
                retries = job['retries']
                if retries < 5:
                    self._update_job_status(job_id, 'pending', message, increment_retry=True)
                    time.sleep(3) # Simple backoff before retrying
                    q.put(job_id) 
                else:
                    self._update_job_status(job_id, 'failed', message, increment_retry=True)
                    
            q.task_done()


# --- Dedicated Printing Functions ---
def print_to_system(file_name, system_printer_name):
    """Prints the image file using the OS print queue (lp command)."""
    try:
        # Use 'lp' (Linux/macOS standard) to send the file to the OS printer queue
        print_command = [
            'lp', '-d', system_printer_name, '-o', 'fit-to-page', file_name
        ]
        print(f"🖨️ Sending print job to OS printer: **{system_printer_name}**")
        run(print_command, check=True)
        return True, "Print job sent successfully to OS."
    except CalledProcessError as e:
        return False, f"OS printing failed (code: {e.returncode}): {e.stderr or e}"
    except FileNotFoundError:
        return False, "The 'lp' command was not found (Check if CUPS/printer service is installed)."


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


def print_to_qz_tray(receipt_data):
    return False, "QZ Tray communication not fully implemented in centralized proxy."


# --- API Routes ---
@app.route('/')
def index():
    return render_template('base.html', printers=load_printers())


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


@app.route('/hw_proxy/default_printer_action', methods=['POST'])
def handle_default_printer_action():
    try:
        data = request.json
        if data is None:
            return jsonify({"jsonrpc": "2.0", "id": 1, "error": {"code": 500, "message": "Empty body"}}), 500
            
        rpc_id = data.get('id', 1)
        printer_name = data.get('params', {}).get('data',{}).get('printer_name')
        
        if not printer_name:
            printer_name = "POS_Printer"
            
        receipt_data = data.get('params', {}).get('data', {}).get('receipt')
        
        printers_config = load_printers()
        if printer_name not in printers_config:
            return jsonify({
                "jsonrpc": "2.0", "id": rpc_id, 
                "error": {"code": 101, "message": f"Printer '{printer_name}' not configured."}
            }), 400
            
        if not receipt_data:
            return jsonify({
                "jsonrpc": "2.0", "id": rpc_id, 
                "error": {"code": 100, "message": "Receipt data not found."}
            }), 400
            
        try:
            image_bytes = base64.b64decode(receipt_data)
            img = Image.open(BytesIO(image_bytes))
            timestamp_ms = int(time.time() * 1000)
            job_id = f"receipt_{rpc_id}_{printer_name}_{timestamp_ms}"
            file_name = os.path.join(IMAGE_SAVE_PATH, f'{job_id}.png')
            img.save(file_name)
        except Exception as e:
            return jsonify({
                "jsonrpc": "2.0", "id": rpc_id, 
                "error": {"code": 200, "message": f"Image decoding error: {e}"}
            }), 500
            
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
            "error": {"code": 300, "message": f"Proxy server error: {e}"}
        }), 500


if __name__ == '__main__':
    # Initialize the queue manager when starting the server
    queue_manager = PrintQueueManager()
    
    # Run the Flask app with Waitress WSGI server
    print("🚀 Starting proxy with Waitress on port 9100...")
    serve(app, host='0.0.0.0', port=9100)
