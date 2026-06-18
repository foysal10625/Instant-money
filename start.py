import threading
import os
from flask import Flask
import bot  # your bot.py import

app = Flask(__name__)

@app.route("/")
def health():
    return "OK", 200

def run_bot():
    os.system("python bot.py")

if __name__ == "__main__":
    # Run bot in separate thread
    threading.Thread(target=run_bot).start()
    app.run(host="0.0.0.0", port=10000)