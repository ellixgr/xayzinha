from flask import Flask

app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "SanizinhaBot está online! 🟢"
