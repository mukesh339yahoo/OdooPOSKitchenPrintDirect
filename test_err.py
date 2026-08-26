from flask import Flask
import traceback
app = Flask(__name__)
@app.errorhandler(Exception)
def handle_exception(e): return traceback.format_exc(), 200, {'Content-Type': 'text/plain'}
@app.route('/')
def i(): return 1/0
print(app.test_client().get('/').data)
