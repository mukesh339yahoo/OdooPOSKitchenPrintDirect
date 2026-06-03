import base64
import re
import json
import os
import socket
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, jsonify, request, render_template
from xml.etree import ElementTree as ET
from flask_cors import CORS
from subprocess import run, CalledProcessError
# Imports for ESC/POS (Requires 'python-escpos')
from escpos.printer import Network as EscposNetworkPrinter
# Imports for QZ TRAY (Requires 'websocket-client' if implemented)
# import websocket # Uncomment if you fully implement QZ Tray communication
# import ssl # Uncomment if you fully implement QZ Tray communication

app = Flask(__name__)

# --- Configuration ---
IMAGE_SAVE_PATH = 'print_images'

if not os.path.exists(IMAGE_SAVE_PATH):
    os.makedirs(IMAGE_SAVE_PATH)

# Enable CORS for all routes
CORS(app, resources={r"/*": {"origins": "*"}})

PRINTERS_FILE = os.path.join(os.path.dirname(__file__), "printers.json")

if not os.path.exists(PRINTERS_FILE):
    with open(PRINTERS_FILE, "w") as f:
        json.dump({}, f)


# --- Utility Functions ---
def load_printers():
    """Loads the printer configuration from printers.json."""
    with open(PRINTERS_FILE) as f:
        return json.load(f)


def save_printers(data):
    """Saves the current printer configuration to printers.json."""
    with open(PRINTERS_FILE, "w") as f:
        json.dump(data, f, indent=4)


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
        # Connect to the network printer
        p = EscposNetworkPrinter(ip, port)

        # Load the image from bytes
        img = Image.open(BytesIO(image_bytes))

        # Print the image (using the escpos library's native image conversion)
        p.image(img)
        p.cut()
        p.close()
        return True, f"Print job sent successfully to ESC/POS at {ip}:{port}."
    except socket.error as e:
        return False, f"ESC/POS connection error: Printer at {ip}:{port} is unreachable or offline. Error: {e}"
    except Exception as e:
        return False, f"ESC/POS printing failed: {e}"


def print_to_qz_tray(receipt_data):
    """
    Placeholder for QZ Tray communication. 
    Requires secure WebSocket connection (WSS) and conversion of print data 
    into QZ Tray's specific JSON command format.
    """
    print(
        f"⚠️ QZ Tray: Job received. QZ Tray communication is complex and requires a separate secure WebSocket implementation."
    )
    print(
        "If QZ Tray runs on the same machine as the proxy, implement WSS client logic here."
    )

    # Returning failure as this centralized proxy cannot securely talk to the client's local QZ Tray without more code.
    return False, "QZ Tray communication not fully implemented in centralized proxy."


# --- Routes ---


@app.route('/')
def index():
    return render_template('base.html', printers=load_printers())


@app.route('/detect', methods=['GET'])
def detect_printers():
    """Placeholder for printer detection, updating the config file."""
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
    """Assigns a target printer name to its configuration details."""
    data = request.json
    printers = load_printers()

    # Store type, IP, and Port based on configuration data received
    printers[data['name']] = {
        "kitchen": data.get("kitchen", False),
        "type": data.get("type", "system"),  # 'system', 'escpos', or 'qz'
        "system_name": data.get("system_name",
                                data['name']),  # Used for 'system' type
        "ip": data.get("ip", "127.0.0.1"),  # Used for 'escpos' type
        "port": data.get("port", 9100),  # Used for 'escpos' type
    }
    save_printers(printers)
    return jsonify({"message": "Printer assigned successfully"})

def generate_test_image_bytes(printer_name):
    """
    Creates a simple black-and-white test receipt image for printing.
    Returns: Tuple of (raw image bytes, base64 encoded bytes)
    """
    try:
        # Create a blank white image
        img_width = 384
        img_height = 400
        img = Image.new('L', (img_width, img_height), color=255) # 'L' mode for grayscale
        d = ImageDraw.Draw(img)

        # Use a simple font or load one if available
        try:
            # Try to load a known font (adjust path if necessary)
            font = ImageFont.truetype("arial.ttf", 20) 
        except IOError:
            # Fallback to the default PIL font
            font = ImageFont.load_default()

        # Add text lines
        d.text((10, 20), "Ridhira POS Print Proxy", fill=0, font=font)
        d.text((10, 60), "--- TEST PRINT SUCCESS ---", fill=0, font=font)
        d.text((10, 100), f"Printer Name: {printer_name}", fill=0, font=font)
        d.text((10, 140), "Type: Confirmed Connection", fill=0, font=font)
        d.text((10, 180), f"Timestamp: {os.times()[4]}", fill=0, font=font)
        d.text((10, 220), "--------------------------", fill=0, font=font)
        
        # Save image to bytes buffer
        buf = BytesIO()
        # Save as PNG which is standard for ESC/POS and system printing
        img.save(buf, format='PNG')
        image_bytes = buf.getvalue()
        
        return image_bytes

    except Exception as e:
        print(f"Error generating test image: {e}")
        return None

@app.route('/test_print/<printer>', methods=['POST'])
def test_print(printer):
    print(f"🖨️ Test print triggered for: {printer}")
    
    try:
        printers_config = load_printers()
        target_printer = printers_config.get(printer)

        if not target_printer:
            return jsonify({
                "success": False, 
                "message": f"Error: Printer '{printer}' not found in configuration."
            }), 400

        # Generate the test image data
        image_bytes = generate_test_image_bytes(printer)
        if image_bytes is None:
            return jsonify({"success": False, "message": "Failed to generate test image data."}), 500

        print_type = target_printer['type']
        print_success = False
        print_message = "Test job not executed."

        # --- Route and Execute Test Print ---
        if print_type == 'system':
            # For system printers, save the PNG file and use the OS command
            file_name = os.path.join(IMAGE_SAVE_PATH, f'test_receipt_{printer}.png')
            
            # Save the image from bytes to the file system
            Image.open(BytesIO(image_bytes)).save(file_name)
            
            system_name = target_printer.get("system_name")
            print_success, print_message = print_to_system(file_name, system_name)

        elif print_type == 'escpos':
            # For ESC/POS, send the raw bytes directly
            ip = target_printer.get("ip")
            port = target_printer.get("port")
            print_success, print_message = print_to_escpos(image_bytes, ip, port)
        
        else:
            print_message = f"Unsupported printer type for test: {print_type}"

        # --- Return Result ---
        if print_success:
            return jsonify({
                "success": True, 
                "message": f"Test print job successfully sent to {printer} ({print_type}). Details: {print_message}"
            }), 200
        else:
            print(f"❌ Test Print Failed for {printer}: {print_message}")
            return jsonify({
                "success": False, 
                "message": f"Test print failed for {printer}. Check proxy logs. Error: {print_message}"
            }), 500

    except Exception as e:
        print(f"❌ General Error during test print for {printer}: {e}")
        return jsonify({
            "success": False, 
            "message": f"Proxy encountered an internal error during test print: {e}"
        }), 500

@app.route('/hw_proxy/default_printer_action', methods=['POST'])
def handle_default_printer_action():
    """
    Handles the standard Odoo RPC payload, routes the job, and prints based on printer type.
    """
    try:

        data = request.json
        
        if data is None:
            # Handle the case where the request body was empty or malformed
            return jsonify({
                "jsonrpc": "2.0", 
                "id": 1, 
                "error": {"code": 500, "message": "Received empty or invalid JSON body."}
            }), 500
        print("before image saved1")
        rpc_id = data.get('id', 1)
        printer_name = data.get('params', {}).get('data',{}).get('printer_name')

        if printer_name is None:
            # We assume 'POS_Printer' is the default for generic/unnamed jobs.
            # IMPORTANT: This must be a name that exists as a key in your printers.json!
        	printer_name = "POS_Printer"
        	print("⚠️ ALERT: Incoming print job was missing a name. Falling back to 'POS_Printer'.")
                                                              
        receipt_data = data.get('params', {}).get('data', {}).get('receipt')
        print("before image saved2")	        
        printers_config = load_printers()
        target_printer = printers_config.get(printer_name)
        
        if not target_printer:
            return jsonify({
                "jsonrpc": "2.0", "id": rpc_id, 
                "error": {"code": 101, "message": f"Printer '{printer_name}' not configured in proxy."}
            }), 400

		
        # --- Decode Base64 Data (Needed for System and ESC/POS) ---
        if target_printer['type'] in ['system', 'escpos']:

            try:
                print("before image saved")
                # The receipt_data contains base64 encoded image data
                image_bytes = base64.b64decode(receipt_data)
                # Decode, Save, and Print to OS Queue
                img = Image.open(BytesIO(image_bytes))
                file_name = os.path.join(
                    IMAGE_SAVE_PATH, f'receipt_{rpc_id}_{printer_name}.png')
                img.save(file_name)
                print("image saved")

            except Exception as e:
                # This handles corrupted or invalid base64
                return jsonify({
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {
                        "code": 200,
                        "message": f"Image decoding error: {e}"
                    }
                }), 500

        # 1. Check Configuration
        if not target_printer:
            return jsonify({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {
                    "code": 101,
                    "message":
                    f"Printer '{printer_name}' not configured in proxy."
                }
            }), 400

        # 2. Check Data
        if not receipt_data:
            return jsonify({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {
                    "code": 100,
                    "message": "Receipt data not found in payload."
                }
            }), 400

        print_success = False
        print_message = "No print action taken."

        # --- Decode Base64 Data (Needed for System and ESC/POS) ---
        if target_printer['type'] in ['system', 'escpos']:
            try:
                # The receipt_data contains base64 encoded image data
                image_bytes = base64.b64decode(receipt_data)
            except Exception as e:
                # This handles corrupted or invalid base64
                return jsonify({
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {
                        "code": 200,
                        "message": f"Image decoding error: {e}"
                    }
                }), 500

        # --- 3. ROUTING AND PRINTING ---
        if target_printer['type'] == 'system':
            # Decode, Save, and Print to OS Queue
            img = Image.open(BytesIO(image_bytes))
            file_name = os.path.join(IMAGE_SAVE_PATH,
                                     f'receipt_{rpc_id}_{printer_name}.png')
            img.save(file_name)
            print_success, print_message = print_to_system(
                file_name, target_printer.get("system_name"))

        elif target_printer['type'] == 'escpos':
            # Decode and Print directly over Network Socket
            print_success, print_message = print_to_escpos(
                image_bytes, target_printer.get("ip"),
                target_printer.get("port"))

        elif target_printer['type'] == 'qz':
            # Pass raw receipt data to the QZ Tray handler (Placeholder)
            print_success, print_message = print_to_qz_tray(receipt_data)

        # --- 4. FINAL RESPONSE ---
        if print_success:
            # Successful JSON-RPC response stops the Odoo POS UI error
            return jsonify({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": True
            }), 200
        else:
            print(f"❌ Printing failed: {print_message}")
            # Failed JSON-RPC response displays a clean error message
            return jsonify({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {
                    "code": 301,
                    "message": print_message
                }
            }), 500

    except Exception as e:
        # --- GENERAL ERROR RESPONSE ---
        print(f"❌ General Proxy Error: {e}")
        try:
            rpc_id = request.json.get('id', 1)
        except:
            rpc_id = 1

        return jsonify({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {
                "code": 300,
                "message": f"Proxy server error: {e}"
            }
        }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9100, debug=True)
