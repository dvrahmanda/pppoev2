#!/usr/bin/env python3
"""
Script untuk menguji fitur notifikasi
Menambahkan beberapa notifikasi contoh ke sistem
"""

import json
import requests
from datetime import datetime, timedelta

# URL base aplikasi
BASE_URL = "http://localhost:5000"

def add_sample_notifications():
    """Menambahkan notifikasi contoh ke sistem"""
    
    # Data notifikasi contoh
    sample_notifications = [
        {
            "message": "ONT baru ditambahkan: ONT Test 1 (XM000999)",
            "type": "success",
            "timestamp": (datetime.now() - timedelta(hours=2)).isoformat()
        },
        {
            "message": "Status ONT Baciro RW 20-1 berubah: OFF → ON",
            "type": "info",
            "timestamp": (datetime.now() - timedelta(hours=1, minutes=30)).isoformat()
        },
        {
            "message": "ONT Bausasran RW 2 mengalami RTO sebanyak 2 kali",
            "type": "warning",
            "timestamp": (datetime.now() - timedelta(hours=1)).isoformat()
        },
        {
            "message": "ONT Bausasran RW 3 mengalami RTO sebanyak 5 kali",
            "type": "error",
            "timestamp": (datetime.now() - timedelta(minutes=45)).isoformat()
        },
        {
            "message": "ONT diperbarui: Bausasran RW 5 (XM000409) → Bausasran RW 5 Updated (XM000409)",
            "type": "info",
            "timestamp": (datetime.now() - timedelta(minutes=30)).isoformat()
        },
        {
            "message": "Status ONT Baciro RW 10 berubah: ON → OFF",
            "type": "warning",
            "timestamp": (datetime.now() - timedelta(minutes=15)).isoformat()
        },
        {
            "message": "ONT dihapus: ONT Test 2 (XM000888)",
            "type": "warning",
            "timestamp": (datetime.now() - timedelta(minutes=5)).isoformat()
        }
    ]
    
    print("Menambahkan notifikasi contoh...")
    
    for i, notification in enumerate(sample_notifications, 1):
        try:
            response = requests.post(
                f"{BASE_URL}/api/notifications",
                json=notification,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                print(f"✓ Notifikasi {i} berhasil ditambahkan: {notification['message'][:50]}...")
            else:
                print(f"✗ Gagal menambahkan notifikasi {i}: {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            print("✗ Tidak dapat terhubung ke server. Pastikan aplikasi Flask berjalan di http://localhost:5000")
            return
        except Exception as e:
            print(f"✗ Error: {e}")

def check_notifications():
    """Mengecek notifikasi yang ada"""
    try:
        response = requests.get(f"{BASE_URL}/api/notifications")
        if response.status_code == 200:
            notifications = response.json()
            print(f"\nTotal notifikasi: {len(notifications)}")
            
            unread_count = sum(1 for n in notifications if not n.get('read', False))
            print(f"Notifikasi belum dibaca: {unread_count}")
            
            if notifications:
                print("\n5 notifikasi terbaru:")
                for i, notif in enumerate(notifications[:5], 1):
                    status = "✓" if notif.get('read', False) else "●"
                    print(f"{i}. {status} [{notif['type'].upper()}] {notif['message']}")
                    
        else:
            print(f"✗ Gagal mengambil notifikasi: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("✗ Tidak dapat terhubung ke server")
    except Exception as e:
        print(f"✗ Error: {e}")

def main():
    print("=== Test Fitur Notifikasi ===\n")
    
    # Cek notifikasi yang ada
    print("1. Mengecek notifikasi yang ada...")
    check_notifications()
    
    # Tambah notifikasi contoh
    print("\n2. Menambahkan notifikasi contoh...")
    add_sample_notifications()
    
    # Cek lagi setelah menambah
    print("\n3. Mengecek notifikasi setelah penambahan...")
    check_notifications()
    
    print("\n=== Test Selesai ===")
    print("\nUntuk melihat notifikasi:")
    print(f"- Buka browser ke: {BASE_URL}/notifications")
    print(f"- Atau ke halaman admin: {BASE_URL}/admin")

if __name__ == "__main__":
    main() 