from flask import Flask, jsonify, request, render_template
from flask_cors import CORS   # ✅ Import CORS
import json, os

app = Flask(__name__)

# ✅ Enable CORS for all routes
CORS(app, resources={r"/*": {"origins": "*"}})

PRINTERS_FILE = os.path.join(os.path.dirname(__file__), "printers.json")

if not os.path.exists(PRINTERS_FILE):
    with open(PRINTERS_FILE, "w") as f:
        json.dump({}, f)

def load_printers():
    with open(PRINTERS_FILE) as f:
        return json.load(f)

def save_printers(data):
    with open(PRINTERS_FILE, "w") as f:
        json.dump(data, f, indent=4)

@app.route('/')
def index():
    return render_template('base.html', printers=load_printers())

@app.route('/detect', methods=['GET'])
def detect_printers():
    printers = {"POS_Printer": {"status": "connected"}, "Kitchen_Printer": {"status": "connected"}}
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
    print(f"Test print triggered for: {printer}")
    return jsonify({"message": f"Test print sent to {printer}!"})

@app.route('/print', methods=['POST', 'OPTIONS'])
def print_from_odoo():
    if request.method == 'OPTIONS':
        # ✅ Handle preflight request manually (for older browsers)
        response = jsonify({'status': 'OK'})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST, OPTIONS")
        return response

    payload = request.json
    print("Received Print Job:", payload)
    response = jsonify({"status": "success", "details": payload})
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9100)
