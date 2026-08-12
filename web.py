import os
from flask import Flask

app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "SanizinhaBot está online! 🟢 Funcionando perfeitamente!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)
