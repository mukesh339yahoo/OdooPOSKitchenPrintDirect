from flask import Flask, render_template_string
app = Flask(__name__)
@app.route('/')
def i(): return 'hi'
@app.route('/test')
def t(): return render_template_string('{{ url_for(\'i\') }}')
print(app.test_client().get('/test').data)
