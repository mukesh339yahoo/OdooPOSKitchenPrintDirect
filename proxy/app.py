import base64, re, json, os
from io import BytesIO
from PIL import Image
from flask import Flask, jsonify, request, render_template
from xml.etree import ElementTree as ET
from flask_cors import CORS  # ✅ Import CORS

app = Flask(__name__)

# --- Configuration ---
IMAGE_SAVE_PATH = 'print_images'

if not os.path.exists(IMAGE_SAVE_PATH):
    os.makedirs(IMAGE_SAVE_PATH)

# ✅ Enable CORS for all routes
CORS(app, resources={r"/*": {"origins": "*"}})

PRINTERS_FILE = os.path.join(os.path.dirname(__file__), "printers.json")

if not os.path.exists(PRINTERS_FILE):
    with open(PRINTERS_FILE, "w") as f:
        json.dump({}, f)

# --- Utility Functions ---
def load_printers():
    with open(PRINTERS_FILE) as f:
        return json.load(f)

def save_printers(data):
    with open(PRINTERS_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- Routes ---

@app.route('/')
def index():
    return render_template('base.html', printers=load_printers())

@app.route('/detect', methods=['GET'])
def detect_printers():
    printers = {
        "POS_Printer": {"status": "connected"},
        "Kitchen_Printer": {"status": "connected"},
    }
    save_printers(printers)
    return jsonify(printers)

@app.route('/assign', methods=['POST'])
def assign_printer():
    data = request.json
    printers = load_printers()
    printers[data['name']] = {"kitchen": data.get("kitchen", "Unknown")}
    save_printers(printers)
    return jsonify({"message": "Printer assigned successfully"})

@app.route('/test_print/<printer>', methods=['POST'])
def test_print(printer):
    print(f"🖨️ Test print triggered for: {printer}")
    return jsonify({"message": f"Test print sent to {printer}!"})

@app.route('/hw_proxy/default_printer_action', methods=['POST'])
def handle_default_printer_action():
    """
    Handles the standard Odoo RPC payload containing the base64 image data.
    Payload structure: {"id":..., "jsonrpc":"2.0", "method":"call", "params":{"data":{...}}}
    """
    try:
        # Get the JSON data from the request body
        data = request.json
        rpc_id = data.get('id', 1)  # Default to 1 if not present
        
        # Navigate the JSON structure to find the base64 receipt string
        receipt_data = data.get('params', {}).get('data', {}).get('receipt')
        
        # --- Handle Missing Data ---
        if not receipt_data:
            # Return JSON-RPC error format
            return jsonify({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": 100, "message": "Receipt data (base64 string) not found in payload."}
            }), 400

        # --- 1. Decode the Base64 Image ---
        try:
            # Decode the base64 string
            image_bytes = base64.b64decode(receipt_data)
            
            # Use BytesIO to load the bytes into PIL's Image module
            img = Image.open(BytesIO(image_bytes))
            
        except Exception as e:
            # --- FALLBACK: Handle faulty ePOS data ---
            print(f"⚠️ Could not decode Base64 data into a standard image (e.g., PNG/JPEG). "
                  f"This might be raw ePOS XML/Text data. Error: {e}")
            
            # Save Raw Content for inspection.
            file_name = os.path.join(IMAGE_SAVE_PATH, 'raw_receipt_data.txt')
            with open(file_name, 'wb') as f:
                f.write(receipt_data.encode('utf-8'))
            print(f"Raw content saved to {file_name} for debugging.")
            
            # Return JSON-RPC error format
            return jsonify({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": 200, "message": f"Unreadable print format. Saved raw data. Error: {e}"}
            }), 500

        
        # --- 2. Save Image to Local Folder ---
        file_name = os.path.join(IMAGE_SAVE_PATH, f'receipt_{data.get("id", "unknown")}.png')
        img.save(file_name)
        print(f"✅ Image saved successfully to {file_name}")

        # --- 3. Print the Image (Placeholder/System Printing) ---
        # Add your actual printing command here if needed.
        print("🖨️ Print command execution placeholder.")
        
        # --- SUCCESS RESPONSE: JSON-RPC 2.0 Format ---
        # This response is crucial for stopping the Odoo "Failed in printing" error.
        return jsonify({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": True  # A simple 'True' indicates success to the Odoo client
        }), 200

    except Exception as e:
        # --- GENERAL ERROR RESPONSE ---
        print(f"❌ Error in print action: {e}")
        
        # Try to get rpc_id again in case the error happened before it was defined
        try:
            rpc_id = request.json.get('id', 1)
        except:
            rpc_id = 1
            
        # Return JSON-RPC error format for general server errors
        return jsonify({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": 300, "message": f"Proxy server error during processing: {e}"}
        }), 500

if __name__ == '__main__':
    # Running on 9100 as per your proxy configuration
    app.run(host='0.0.0.0', port=9100, debug=True)