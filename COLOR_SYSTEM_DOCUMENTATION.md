# 🎨 Sistem Warna Dashboard Monitoring ONT

## 📋 **Ringkasan Sistem Warna**

Sistem monitoring ONT menggunakan **sistem warna yang berbeda** untuk membedakan jenis perangkat dan statusnya berdasarkan field `Icon` dalam data.

## 🎯 **Kategori Perangkat Berdasarkan Icon**

### **1. 🟢 CSR (Customer Service Representative)**
- **Icon:** `155`
- **Status Online:** 🟢 **Hijau** (`#27ae60`)
- **Status Offline:** 🟠 **Oranye** (`#ff6b35`)
- **Deskripsi:** Perangkat yang melayani customer secara langsung

### **2. 🔵 APBD (Anggaran Pendapatan dan Belanja Daerah)**
- **Icon:** `119`
- **Status Online:** 🔵 **Biru** (`#3498db`)
- **Status Offline:** 🔴 **Merah** (`#e74c3c`)
- **Deskripsi:** Perangkat yang terkait dengan sistem anggaran daerah

### **3. 🟡 Default/Umum**
- **Icon:** Lainnya (bukan 119 atau 155)
- **Status Online:** 🟢 **Hijau** (`#27ae60`)
- **Status Offline:** 🔴 **Merah** (`#e74c3c`)
- **Deskripsi:** Perangkat umum atau kategori lainnya

## 🗺️ **Implementasi di Peta (Map)**

### **A. Icon Marker SVG**
```javascript
// Tentukan warna berdasarkan Icon dan status
let onColor, offColor;

if (ont.Icon === 119) {
  // Icon 119: Biru ketika hidup, Merah ketika mati
  onColor = "#3498db";  // Biru (APBD Online)
  offColor = "#e74c3c"; // Merah (APBD Offline)
} else if (ont.Icon === 155) {
  // Icon 155: Hijau ketika hidup, Oranye ketika mati
  onColor = "#27ae60";  // Hijau (CSR Online)
  offColor = "#ff6b35"; // Oranye (CSR Offline)
} else {
  // Default: Hijau ketika hidup, Merah ketika mati
  onColor = "#27ae60";  // Hijau (Umum Online)
  offColor = "#e74c3c"; // Merah (Umum Offline)
}
```

### **B. Status Display**
- **ON:** Menggunakan `onColor` sesuai kategori
- **OFF:** Menggunakan `offColor` sesuai kategori
- **OFF(Waiting Connection):** Menggunakan `offColor` dengan RTO count
- **OFF(RTO):** Menggunakan `offColor` dengan RTO count

## 📊 **Dashboard Statistics**

### **A. Statistik Berdasarkan Kategori**
```javascript
// Load ONT statistics
fetch('/api/onts')
  .then(response => response.json())
  .then(data => {
    const totalOnts = data.length;
    const onlineOnts = data.filter(ont => ont.status === 'ON').length;
    const offlineOnts = totalOnts - onlineOnts;
    
    // Kategori CSR (Icon 155)
    const csrOnts = data.filter(ont => ont.Icon === 155);
    const csrOnline = csrOnts.filter(ont => ont.status === 'ON').length;
    const csrOffline = csrOnts.length - csrOnline;
    
    // Kategori APBD (Icon 119)
    const apbdOnts = data.filter(ont => ont.Icon === 119);
    const apbdOnline = apbdOnts.filter(ont => ont.status === 'ON').length;
    const apbdOffline = apbdOnts.length - apbdOnline;
    
    // Update dashboard
    document.getElementById('total-onts').textContent = totalOnts;
    document.getElementById('online-onts').textContent = onlineOnts;
    document.getElementById('offline-onts').textContent = offlineOnts;
    document.getElementById('csr-online').textContent = csrOnline;
    document.getElementById('csr-offline').textContent = csrOffline;
    document.getElementById('apbd-online').textContent = apbdOnline;
    document.getElementById('apbd-offline').textContent = apbdOffline;
  });
```

### **B. Visual Indicators**
- **🟢 Hijau:** CSR Online (Icon 155)
- **🟠 Oranye:** CSR Offline (Icon 155)
- **🔵 Biru:** APBD Online (Icon 119)
- **🔴 Merah:** APBD Offline (Icon 119)

## 🔔 **Notifikasi Berdasarkan Kategori**

### **A. CSR Status Changes**
```javascript
// Notifikasi untuk CSR
if (ont.Icon === 155) {
  if (ont.status === 'ON') {
    add_notification(
      `CSR ${ont.name} kembali online`,
      "success",
      ont.id,
      ont.name
    );
  } else {
    add_notification(
      `CSR ${ont.name} offline - ${ont.status}`,
      "warning",
      ont.id,
      ont.name
    );
  }
}
```

### **B. APBD Status Changes**
```javascript
// Notifikasi untuk APBD
if (ont.Icon === 119) {
  if (ont.status === 'ON') {
    add_notification(
      `APBD ${ont.name} kembali online`,
      "success",
      ont.id,
      ont.name
    );
  } else {
    add_notification(
      `APBD ${ont.name} offline - ${ont.status}`,
      "warning",
      ont.id,
      ont.name
    );
  }
}
```

## 📈 **Monitoring Dashboard**

### **A. Real-time Status**
- **Update Interval:** Setiap 5 detik
- **Color Coding:** Otomatis berdasarkan Icon dan Status
- **Category Filter:** CSR vs APBD

### **B. Performance Metrics**
- **CSR Uptime:** Persentase CSR yang online
- **APBD Uptime:** Persentase APBD yang online
- **Overall Uptime:** Total uptime sistem

## 🎨 **Color Palette Reference**

### **Primary Colors**
```css
/* CSR Colors */
.csr-online { color: #27ae60; }    /* Hijau */
.csr-offline { color: #ff6b35; }   /* Oranye */

/* APBD Colors */
.apbd-online { color: #3498db; }   /* Biru */
.apbd-offline { color: #e74c3c; }  /* Merah */

/* Default Colors */
.default-online { color: #27ae60; }  /* Hijau */
.default-offline { color: #e74c3c; } /* Merah */
```

### **Status Indicators**
```css
/* Status Badges */
.status-csr-online {
  background-color: #27ae60;
  color: white;
}

.status-csr-offline {
  background-color: #ff6b35;
  color: white;
}

.status-apbd-online {
  background-color: #3498db;
  color: white;
}

.status-apbd-offline {
  background-color: #e74c3c;
  color: white;
}
```

## 📱 **Responsive Design**

### **A. Mobile View**
- Icon warna tetap konsisten
- Status text dengan prefix kategori
- Touch-friendly color indicators

### **B. Desktop View**
- Full color spectrum
- Hover effects dengan warna kategori
- Detailed status information

## 🔧 **Technical Implementation**

### **A. Data Structure**
```json
{
  "id": 1,
  "name": "Baciro",
  "ip": "10.239.1.53",
  "status": "ON",
  "Icon": 155,
  "category": "CSR"
}
```

### **B. Color Logic Function**
```javascript
function getStatusColor(icon, status) {
  if (icon === 119) {
    return status === 'ON' ? '#3498db' : '#e74c3c'; // APBD
  } else if (icon === 155) {
    return status === 'ON' ? '#27ae60' : '#ff6b35'; // CSR
  } else {
    return status === 'ON' ? '#27ae60' : '#e74c3c'; // Default
  }
}
```

## 📊 **Reporting & Analytics**

### **A. Daily Reports**
- **CSR Performance:** Uptime, response time
- **APBD Performance:** Availability, maintenance
- **Overall System:** Combined metrics

### **B. Trend Analysis**
- **Weekly Patterns:** Peak usage times
- **Monthly Trends:** Reliability improvements
- **Quarterly Reviews:** System optimization

## 🎯 **Best Practices**

### **A. Color Consistency**
- Gunakan warna yang sama di semua halaman
- Pastikan kontras yang cukup untuk accessibility
- Test dengan colorblind users

### **B. Status Updates**
- Update real-time setiap 5 detik
- Backup status changes ke database
- Log semua perubahan untuk audit

### **C. User Experience**
- Clear visual indicators
- Consistent terminology
- Intuitive color associations

## 📝 **Summary**

| Kategori | Icon | Online | Offline | Deskripsi |
|----------|------|--------|---------|-----------|
| **CSR** | 155 | 🟢 Hijau | 🟠 Oranye | Customer Service |
| **APBD** | 119 | 🔵 Biru | 🔴 Merah | Anggaran Daerah |
| **Umum** | Lain | 🟢 Hijau | 🔴 Merah | Kategori Lain |

**Sistem warna ini memudahkan operator untuk:**
- ✅ **Mengidentifikasi kategori perangkat dengan cepat**
- ✅ **Membedakan status online/offline secara visual**
- ✅ **Memprioritaskan maintenance berdasarkan kategori**
- ✅ **Melakukan troubleshooting yang lebih efisien**
