import qrcode
import os
import socket

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()

mac_ip = get_local_ip()
PORT = "5001"
TABLES = 10
OUT_DIR = "static/qr"

os.makedirs(OUT_DIR, exist_ok=True)

for table_id in range(1, TABLES + 1):
    url = f"http://{mac_ip}:{PORT}/table/{table_id}"
    img = qrcode.make(url)
    path = f"{OUT_DIR}/table_{table_id}_qr.png"
    img.save(path)
    print(f"Table {table_id} → {url}")

print(f"\n🎉 Done! Your current IP is: {mac_ip}")
print(f"📱 Make sure your phone is on the same WiFi network!")