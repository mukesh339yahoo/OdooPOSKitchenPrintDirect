from flask import Flask, request
app = Flask(__name__)
@app.errorhandler(404)
def handle_404(e): return '404 handled', 200
print(app.test_client().get('/foo').data)
