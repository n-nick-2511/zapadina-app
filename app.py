import subprocess
import webbrowser
import time
import os
import sys
import requests


proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"],
    cwd="backend"
)

def wait_for_server():
    for _ in range(30):
        try:
            requests.get("http://127.0.0.1:8000/ping", timeout=1)
            return True
        except requests.RequestException:
            time.sleep(1)
    return False

# def wait_for_server():
#     for _ in range(20):
#         try:
#             # requests.get("http://127.0.0.1:8000/ping")
#             requests.get("http://85.239.49.27:8000/ping")
#             return True
#         except:
#             time.sleep(0.5)
#     return False

if wait_for_server():
    print("✅ Сервер запущен")
    path = os.path.abspath("frontend/index.html")
    webbrowser.open("file://" + path)
else:
    print("❌ Сервер не поднялся")

try:
    while True:
        if proc.poll() is not None:
            print("Закрываем app.py")
            break
        time.sleep(1)
except KeyboardInterrupt:
    print("Закрытие вручную...")
# finally:
#     proc.terminate()
#     try:
#         proc.wait(timeout=3)
#     except:
        # proc.kill()

