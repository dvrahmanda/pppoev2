# 🔧 Troubleshooting Sistem Ping ONT

## 🚨 **Masalah: Semua ONT Status OFF**

### **Penyebab Utama:**

1. **❌ Command Ping Tidak Kompatibel Windows**
   - Script lama menggunakan `ping -c 1 -W 1` (Linux)
   - Windows menggunakan `ping -n 1 -w 1000`

2. **🌐 IP Address Tidak Valid**
   - IP kosong atau format salah
   - IP berada di subnet yang berbeda
   - IP tidak dapat diakses dari jaringan lokal

3. **🔥 Firewall/Network Issues**
   - Windows Firewall memblokir ping
   - Router memblokir ICMP packets
   - Network policy membatasi ping

4. **📡 Jaringan Tidak Terhubung**
   - Tidak ada koneksi internet
   - Subnet mask tidak sesuai
   - Gateway tidak dikonfigurasi

## 🛠️ **Solusi Lengkap**

### **Langkah 1: Reset Status ONT**
```bash
# Reset semua status ke ON untuk testing
python reset_ont_status.py
```

### **Langkah 2: Test Ping Manual**
```bash
# Test ping ke beberapa IP
python test_ping_simple.py
```

### **Langkah 3: Jalankan Sistem Ping yang Diperbaiki**
```bash
# Sistem ping yang sudah kompatibel Windows
python ping_check.py
```

## 🔍 **Diagnosis Masalah**

### **A. Test Ping Lokal**
```bash
# Test ping ke localhost
ping 127.0.0.1

# Test ping ke router
ping 192.168.1.1

# Test ping ke internet
ping 8.8.8.8
```

### **B. Test IP ONT**
```bash
# Test IP dari data ONT
ping 10.239.1.53
ping 10.239.0.161
```

### **C. Cek Network Configuration**
```bash
# Cek IP lokal
ipconfig

# Cek routing table
route print

# Cek firewall status
netsh advfirewall show allprofiles
```

## 📋 **Script yang Sudah Diperbaiki**

### **1. `ping_check.py` (Updated)**
- ✅ Kompatibel Windows & Linux
- ✅ Error handling yang lebih baik
- ✅ Debugging output
- ✅ Platform detection

### **2. `test_ping_simple.py` (New)**
- ✅ Test ping manual
- ✅ Test jaringan lokal
- ✅ Test IP ONT
- ✅ Detailed output

### **3. `reset_ont_status.py` (New)**
- ✅ Reset status ke ON
- ✅ Tampilkan statistik
- ✅ Backup otomatis

## 🎯 **Langkah Testing Lengkap**

### **Step 1: Reset Status**
```bash
python reset_ont_status.py
# Pilih 'y' untuk reset
```

### **Step 2: Test Ping Dasar**
```bash
python test_ping_simple.py
# Verifikasi ping lokal berfungsi
```

### **Step 3: Jalankan Sistem Ping**
```bash
python ping_check.py
# Monitor output untuk error
```

### **Step 4: Cek di Browser**
- Buka: `http://localhost:5000`
- Lihat apakah status berubah
- Monitor notifikasi real-time

## 🚨 **Error yang Sering Muncul**

### **Error 1: "File onts.json tidak ditemukan"**
```bash
# Solusi: Pastikan file ada
dir onts.json
# Jika tidak ada, copy dari csvjson.json
copy csvjson.json onts.json
```

### **Error 2: "Permission denied"**
```bash
# Solusi: Jalankan sebagai Administrator
# Atau cek file permissions
```

### **Error 3: "Network unreachable"**
```bash
# Solusi: Cek koneksi jaringan
ipconfig
ping 8.8.8.8
```

## 🔧 **Konfigurasi Windows**

### **A. Enable ICMP Ping**
```bash
# Buka Windows Defender Firewall
# Advanced Settings → Inbound Rules
# Enable "File and Printer Sharing (Echo Request - ICMPv4-In)"
```

### **B. Cek Network Profile**
```bash
# Pastikan network profile "Private" bukan "Public"
# Control Panel → Network and Internet → Network and Sharing Center
```

### **C. Disable Antivirus Temporarily**
- Nonaktifkan antivirus sementara untuk testing
- Test ping dengan antivirus off
- Jika berhasil, tambahkan exception

## 📊 **Monitoring & Debugging**

### **A. Log Output**
```bash
# Jalankan dengan output detail
python ping_check.py > ping_log.txt 2>&1

# Monitor log real-time
Get-Content ping_log.txt -Wait
```

### **B. Browser Console**
- F12 → Console
- Lihat error JavaScript
- Monitor network requests

### **C. Flask Debug Mode**
```python
# Di app.py, pastikan debug mode on
app.run(debug=True, host='0.0.0.0', port=5000)
```

## 🎉 **Indikator Berhasil**

### **✅ Ping Berfungsi:**
- Status ONT berubah dari OFF ke ON
- Notifikasi real-time muncul
- Icon di peta berubah warna
- RTO count reset ke 0

### **✅ Sistem Monitoring:**
- Dashboard menampilkan statistik benar
- Peta update setiap 5 detik
- Notifikasi tersimpan di histori
- Backup otomatis berfungsi

## 🚀 **Command Cepat**

```bash
# Reset dan test lengkap
python reset_ont_status.py && python test_ping_simple.py && python ping_check.py

# Monitor log
Get-Content ping_log.txt -Wait

# Test API manual
curl -X POST http://localhost:5000/api/ont-status/1 -H "Content-Type: application/json" -d "{\"status\": \"ON\", \"rto_count\": 0}"
```

## 📞 **Support**

Jika masih ada masalah:
1. ✅ Jalankan semua script testing
2. ✅ Cek output error detail
3. ✅ Verifikasi koneksi jaringan
4. ✅ Test ping manual di command prompt
5. ✅ Cek firewall dan antivirus

**Sistem ping yang sudah diperbaiki seharusnya berfungsi dengan baik di Windows!** 🎯
