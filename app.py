# import subprocess
# import time
# import webbrowser
# import os
#
#
# subprocess.Popen(["uvicorn", "main:app"], cwd="backend")
#
# time.sleep(2)
#
# path = os.path.abspath("frontend/index.html")
# webbrowser.open("file://" + path)

# import subprocess
# import webbrowser
# import time
# import os
# import sys
#
# # запуск backend
# proc = subprocess.Popen(
#     [sys.executable, "-m", "uvicorn", "main:app"],
#     cwd="backend"
# )
#
# time.sleep(2)
#
# # открываем HTML
# path = os.path.abspath("frontend/index.html")
# webbrowser.open("file://" + path)
#
# # 👇 ВАЖНО: следим за процессом
# try:
#     while True:
#         if proc.poll() is not None:
#             print("Закрываем app.py")
#             break
#         time.sleep(1)
# except KeyboardInterrupt:
#     print("Закрытие вручную...")
# finally:
#     proc.terminate()
#     try:
#         proc.wait(timeout=3)
#     except:
#         proc.kill()
#
#



import subprocess
import webbrowser
import time
import os
import sys
import requests

# proc = subprocess.Popen(
#     [sys.executable, "-m", "uvicorn", "main:app", "--reload"],
#     cwd="backend"
# )

proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "main:app"],
    cwd="backend"
)

def wait_for_server():
    for _ in range(20):
        try:
            requests.get("http://127.0.0.1:8000/ping")
            return True
        except:
            time.sleep(0.5)
    return False

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
finally:
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except:
        proc.kill()

