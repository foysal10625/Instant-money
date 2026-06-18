import threading
import os
from flask import Flask

app = Flask(__name__)

@app.route("/")
def health():
    return "OK", 200

def run_bot():
    # run your bot script
    os.system("python bot.py")

if __name__ == "__main__":
    # bot run in background thread
    threading.Thread(target=run_bot).start()
    # flask server for Render health check
    app.run(host="0.0.0.0", port=10000)