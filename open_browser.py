import time,urllib.request,webbrowser
for _ in range(60):
 try:
  urllib.request.urlopen('http://127.0.0.1:8000/api/ai/status',timeout=1)
  webbrowser.open('http://127.0.0.1:8000');break
 except Exception:time.sleep(1)
