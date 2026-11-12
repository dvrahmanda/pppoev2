# Web Push VAPID

Fitur ini mengirim push ke browser teknisi ketika perubahan status PPPoE sudah terkonfirmasi. Notifikasi push hanya berisi ringkasan jumlah akun online/offline; detail akun tetap ada di dashboard.

## Alur

1. Browser meminta izin notifikasi dan membuat subscription melalui service worker.
2. Halaman mengirim subscription ke Flask bersama token pendaftaran teknisi.
3. Server menyimpan endpoint dan subscription di `data/push_subscriptions.json`; token pemilik perangkat disimpan sebagai hash.
4. `/api/update-pppoe` membandingkan status dari snapshot router dengan status sebelumnya. Secara default perubahan harus terlihat pada dua snapshot berturut-turut.
5. Setelah perubahan terkonfirmasi, aplikasi menambah histori notifikasi dan mengirim push dengan VAPID. Klik notifikasi membuka halaman admin.

Untuk menyimpulkan akun yang tidak dikirim sebagai OFFLINE, payload router harus berupa snapshot lengkap dan menyertakan `"snapshot_complete": true`. Jangan gunakan flag ini jika kiriman berisi sebagian akun. Jika router mengirim semua akun beserta field statusnya, flag tersebut tidak diperlukan.

Jika laporan dari sebuah MikroTik berhenti masuk selama 3 menit, server membuat satu notifikasi **Gangguan MikroTik** untuk teknisi. Notifikasi akan aktif kembali setelah router mengirim laporan lagi. Ubah `MIKROTIK_HEARTBEAT_TIMEOUT_SECONDS` di `.env` jika interval laporan dari script MikroTik berbeda. Server Flask harus tetap berjalan agar batas waktu ini dapat diperiksa.

## Persiapan server

Web Push memerlukan secure context: HTTPS untuk alamat server, atau `localhost` untuk pengembangan. Akses melalui IP LAN dengan HTTP tidak cukup. Pastikan HTTPS memakai sertifikat yang dipercaya browser.

Di PowerShell dari folder proyek:

```powershell
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
python .\scripts\generate_vapid_keys.py
```

Generator menyimpan private key ke `runtime/secrets/vapid_private.pem`, lalu menampilkan public key, token pendaftaran 5–8 karakter, dan VAPID subject. Default token adalah 8 karakter. Salin nilai tersebut ke `.env`, ganti alamat email, dan atur `PUBLIC_BASE_URL` ke origin HTTPS yang dipakai teknisi. Jangan bagikan private key atau file `.env`.

Untuk mengganti token tanpa mengganti pasangan VAPID, jalankan `python .\scripts\generate_vapid_keys.py --token-only`. Opsi `--token-length 5` sampai `--token-length 8` dapat dipakai untuk memilih panjang token. Server membatasi percobaan token yang salah hingga 10 kali per alamat klien dalam 5 menit.

`PPPOE_STATUS_CONFIRMATIONS=2` mengurangi notifikasi palsu akibat satu snapshot yang terlambat. Nilai `1` mengirim setelah satu snapshot.

Untuk mencegah snapshot palsu memicu notifikasi, isi `MIKROTIK_API_TOKEN` dan ubah pengirim router agar menyertakan header `X-API-Token` yang sama. Jika nilainya kosong, endpoint update tetap kompatibel dengan pengirim lama dan tidak terlindungi token.

Jalankan aplikasi dengan `python .\app.py` agar pemeriksa timeout MikroTik ikut berjalan.

## Aktifkan pada perangkat teknisi

1. Restart aplikasi setelah mengisi `.env`.
2. Buka halaman `/notifications` melalui HTTPS.
3. Masukkan `PUSH_ENROLLMENT_TOKEN`, beri nama perangkat bila perlu, lalu tekan **Aktifkan push**.
4. Izinkan notifikasi browser dan gunakan **Kirim uji** untuk memastikan perangkat menerima push.
5. Ulangi untuk tiap browser/perangkat. Bagikan token hanya kepada teknisi yang boleh menerima notifikasi.

Token pendaftaran mengatur subscription push; autentikasi untuk halaman admin/API monitoring yang sudah ada tetap perlu ditangani terpisah. Di iPhone/iPad, tambahkan situs ke Home Screen dan aktifkan push dari web app tersebut.

## Data dan rotasi key

Private key dan daftar subscription diabaikan oleh Git. Simpan backup keduanya secara terbatas. Jangan membuat key baru setiap restart. Jika private key dirotasi dengan `--force`, tekan **Matikan** lalu **Aktifkan push** pada tiap perangkat agar subscription dibuat ulang dengan public key baru.
