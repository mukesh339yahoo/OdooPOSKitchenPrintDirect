from flask import Flask, render_template_string

app = Flask(__name__)

@app.route('/')
def test():
    printers_json_str = "{}"
    message = ""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Ridhira Print Proxy Settings</title>
        <style>
            body { font-family: Arial, sans-serif; background-color: #f4f4f9; padding: 20px; max-width: 800px; margin: auto; }
            .header-container { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #ccc; padding-bottom: 10px; margin-bottom: 15px; }
            h2 { color: #333; margin: 0; }
            textarea { width: 100%; height: 400px; font-family: monospace; font-size: 14px; padding: 15px; border: 1px solid #ccc; border-radius: 5px; box-sizing: border-box; }
            .btn { background-color: #28a745; color: white; padding: 12px 25px; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; margin-top: 15px; font-weight: bold; }
            .btn:hover { background-color: #218838; }
            .msg { background-color: #d4edda; color: #155724; padding: 10px; border-radius: 4px; border: 1px solid #c3e6cb; margin-bottom: 15px; }
            .error { background-color: #f8d7da; color: #721c24; padding: 10px; border-radius: 4px; border: 1px solid #f5c6cb; margin-bottom: 15px; }
            .back-link { text-decoration: none; color: #28a745; font-weight: bold; padding: 8px 15px; border: 1px solid #28a745; border-radius: 4px; }
            .back-link:hover { background-color: #28a745; color: white; }
        </style>
    </head>
    <body>
        <div class="header-container">
            <h2>Printer Configuration</h2>
            <a href="/" class="back-link">Home Dashboard</a>
        </div>
        {% if message %}
            <div class="{% if 'Error' in message %}error{% else %}msg{% endif %}">{{ message }}</div>
        {% endif %}
        <p>Edit the JSON below to configure your printers. Be careful not to break the JSON format!</p>
        <form method="POST">
            <textarea name="printers_json">{{ printers_json }}</textarea>
            <br>
            <button class="btn" type="submit">Save Changes</button>
        </form>
    </body>
    </html>
    """
    return render_template_string(html, printers_json=printers_json_str, message=message)

with app.app_context():
    print(test())
