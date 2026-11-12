import json
import time
from datetime import datetime
from pathlib import Path

# Definisikan path file sesuai dengan struktur folder kamu
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'

# Jika file pppoes.json atau user_active.json berada di folder data, gunakan path ini:
# Kalau ternyata filenya di folder utama (sejajar script), hapus bagian "DATA_DIR /"
PPPOES_FILE = DATA_DIR / 'pppoes.json'
USER_ACTIVE_FILE = DATA_DIR / 'user_active.json'

INTERVAL_MENIT = 1  # Cek otomatis setiap 1 menit

def check_and_update_status():
    # 1. Pastikan kedua file yang dibutuhkan ada
    if not PPPOES_FILE.exists():
        print(f"[ERROR] File master {PPPOES_FILE.name} tidak ditemukan!")
        return
    if not USER_ACTIVE_FILE.exists():
        print(f"[ERROR] File realtime {USER_ACTIVE_FILE.name} tidak ditemukan!")
        return

    try:
        # 2. Baca data user aktif saat ini
        with open(USER_ACTIVE_FILE, 'r', encoding='utf-8') as f:
            active_data = json.load(f)
            # Ambil list pppoe sesuai struktur file user_active.json kamu
            active_list = active_data.get('pppoe', [])
        
        # Kumpulkan nama user yang online ke dalam Set (biar pencarian cepat & case-insensitive)
        active_names = set()
        active_details = {} # Untuk menyimpan ip dan uptime terbaru
        for u in active_list:
            if isinstance(u, dict):
                # Di user_active.json milikmu key utamanya adalah 'user'
                user_name = u.get('user') or u.get('name')
                if user_name:
                    clean_name = str(user_name).strip().lower()
                    active_names.add(clean_name)
                    active_details[clean_name] = {
                        "ip": u.get("ip", "-"),
                        "uptime": u.get("uptime", "-")
                    }

        # 3. Baca data pppoes.json (yang sudah ada koordinat latitude & longitude)
        with open(PPPOES_FILE, 'r', encoding='utf-8') as f:
            pppoes_data = json.load(f)

        # 4. Bandingkan data dan update statusnya
        updated_data = []
        online_count = 0
        has_changes = False

        for item in pppoes_data:
            new_item = dict(item)
            # Menggunakan key 'user' sesuai format pppoes.json milikmu
            user_name = item.get('user') or item.get('name')
            clean_user_name = str(user_name).strip().lower() if user_name else ""
            
            old_status = item.get('status', 'OFFLINE')
            
            # Cek keaktifan
            if clean_user_name in active_names:
                new_status = "ONLINE"
                online_count += 1
                # Update IP dan Uptime realtime dari MikroTik jika tersedia
                new_item['ip'] = active_details[clean_user_name]['ip']
                new_item['uptime'] = active_details[clean_user_name]['uptime']
            else:
                new_status = "OFFLINE"
                # Kamu bisa mengosongkan IP/uptime jika offline, atau biarkan strip
                new_item['uptime'] = "-"

            new_item['status'] = new_status
            
            # Tandai jika ada perubahan status dari file sebelumnya
            if old_status != new_status or item.get('uptime') != new_item['uptime']:
                has_changes = True
                
            updated_data.append(new_item)

        # 5. Tulis kembali ke pppoes.json HANYA jika ada perubahan data/status
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if has_changes:
            with open(PPPOES_FILE, 'w', encoding='utf-8') as f:
                json.dump(updated_data, f, indent=4)
            print(f"[{current_time}] [SUCCESS] pppoes.json diperbarui! Online: {online_count} | Offline: {len(updated_data) - online_count}")
        else:
            print(f"[{current_time}] [INFO] Tidak ada perubahan status user. File tetap aman.")

    except Exception as e:
        print(f"[ERROR] Terjadi kesalahan saat sinkronisasi: {e}")

def main():
    print(f"[*] Script Sinkronisasi Realtime Status PPPoE berjalan...")
    print(f"[-] Memeriksa kecocokan data setiap {INTERVAL_MENIT} menit. Tekan Ctrl+C untuk keluar.\n")
    
    while True:
        check_and_update_status()
        time.sleep(INTERVAL_MENIT * 60)

if __name__ == '__main__':
    main()