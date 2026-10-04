"""Launch the local security-awareness training lab.

This application records training events only; it never asks for or stores
passwords or other credentials.
"""
import os
import threading
import time
import webbrowser

from flask_server import app


HOST = "127.0.0.1"
# Port 5000 is reserved or blocked on some Windows systems.  Use 5050 by default.
PORT = int(os.environ.get("TRAINING_PORT", "5050"))


def open_training_page():
    """Open the browser only after Flask has had time to start."""
    time.sleep(1)
    webbrowser.open(f"http://{HOST}:{PORT}")


if __name__ == "__main__":
    print("Starting the security-awareness training lab...")
    print(f"Training page: http://{HOST}:{PORT}")
    print(f"Dashboard:     http://{HOST}:{PORT}/dashboard")
    print("This lab records training events only; it does not collect passwords.")

    threading.Thread(target=open_training_page, daemon=True).start()
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
