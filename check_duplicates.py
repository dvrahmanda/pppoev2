#!/usr/bin/env python3
"""
Script untuk memeriksa data duplikat di file onts.json
"""

import json
from collections import defaultdict

def load_onts_data():
    """Memuat data dari onts.json"""
    try:
        with open('onts.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print("File onts.json tidak ditemukan")
        return []
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return []

def check_duplicates(data):
    """Memeriksa data duplikat berdasarkan berbagai kriteria"""
    
    print("=== Pemeriksaan Data Duplikat ===\n")
    
    # 1. Duplikat berdasarkan id_pelanggan
    print("1. Memeriksa duplikat berdasarkan id_pelanggan...")
    id_pelanggan_count = defaultdict(list)
    for item in data:
        id_pelanggan = item.get('id_pelanggan', '')
        id_pelanggan_count[id_pelanggan].append(item)
    
    duplicates_id_pelanggan = {k: v for k, v in id_pelanggan_count.items() if len(v) > 1}
    
    if duplicates_id_pelanggan:
        print(f"   ❌ Ditemukan {len(duplicates_id_pelanggan)} id_pelanggan yang duplikat:")
        for id_pelanggan, items in duplicates_id_pelanggan.items():
            print(f"      - {id_pelanggan}: {len(items)} item")
            for item in items:
                print(f"        * ID: {item['id']}, Nama: {item['name']}")
    else:
        print("   ✅ Tidak ada duplikat berdasarkan id_pelanggan")
    
    # 2. Duplikat berdasarkan IP
    print("\n2. Memeriksa duplikat berdasarkan IP...")
    ip_count = defaultdict(list)
    for item in data:
        ip = item.get('ip', '').strip()
        if ip:  # Hanya IP yang tidak kosong
            ip_count[ip].append(item)
    
    duplicates_ip = {k: v for k, v in ip_count.items() if len(v) > 1}
    
    if duplicates_ip:
        print(f"   ❌ Ditemukan {len(duplicates_ip)} IP yang duplikat:")
        for ip, items in duplicates_ip.items():
            print(f"      - {ip}: {len(items)} item")
            for item in items:
                print(f"        * ID: {item['id']}, Nama: {item['name']}, ID Pelanggan: {item['id_pelanggan']}")
    else:
        print("   ✅ Tidak ada duplikat berdasarkan IP")
    
    # 3. Duplikat berdasarkan nama
    print("\n3. Memeriksa duplikat berdasarkan nama...")
    name_count = defaultdict(list)
    for item in data:
        name = item.get('name', '').strip()
        if name:  # Hanya nama yang tidak kosong
            name_count[name].append(item)
    
    duplicates_name = {k: v for k, v in name_count.items() if len(v) > 1}
    
    if duplicates_name:
        print(f"   ❌ Ditemukan {len(duplicates_name)} nama yang duplikat:")
        for name, items in duplicates_name.items():
            print(f"      - {name}: {len(items)} item")
            for item in items:
                print(f"        * ID: {item['id']}, ID Pelanggan: {item['id_pelanggan']}, IP: {item['ip']}")
    else:
        print("   ✅ Tidak ada duplikat berdasarkan nama")
    
    # 4. Duplikat berdasarkan koordinat
    print("\n4. Memeriksa duplikat berdasarkan koordinat...")
    coord_count = defaultdict(list)
    for item in data:
        lat = item.get('latitude', 0)
        lon = item.get('longitude', 0)
        if lat != 0 and lon != 0:  # Hanya koordinat yang valid
            coord_key = f"{lat},{lon}"
            coord_count[coord_key].append(item)
    
    duplicates_coord = {k: v for k, v in coord_count.items() if len(v) > 1}
    
    if duplicates_coord:
        print(f"   ❌ Ditemukan {len(duplicates_coord)} koordinat yang duplikat:")
        for coord, items in duplicates_coord.items():
            print(f"      - {coord}: {len(items)} item")
            for item in items:
                print(f"        * ID: {item['id']}, Nama: {item['name']}, ID Pelanggan: {item['id_pelanggan']}")
    else:
        print("   ✅ Tidak ada duplikat berdasarkan koordinat")
    
    # 5. Duplikat berdasarkan ID
    print("\n5. Memeriksa duplikat berdasarkan ID...")
    id_count = defaultdict(list)
    for item in data:
        item_id = item.get('id', 0)
        id_count[item_id].append(item)
    
    duplicates_id = {k: v for k, v in id_count.items() if len(v) > 1}
    
    if duplicates_id:
        print(f"   ❌ Ditemukan {len(duplicates_id)} ID yang duplikat:")
        for item_id, items in duplicates_id.items():
            print(f"      - ID {item_id}: {len(items)} item")
            for item in items:
                print(f"        * Nama: {item['name']}, ID Pelanggan: {item['id_pelanggan']}")
    else:
        print("   ✅ Tidak ada duplikat berdasarkan ID")
    
    # 6. Statistik umum
    print("\n6. Statistik Data:")
    print(f"   - Total item: {len(data)}")
    print(f"   - Unique id_pelanggan: {len(id_pelanggan_count)}")
    print(f"   - Unique IP: {len(ip_count)}")
    print(f"   - Unique nama: {len(name_count)}")
    print(f"   - Unique koordinat: {len(coord_count)}")
    print(f"   - Unique ID: {len(id_count)}")
    
    # 7. Data dengan koordinat 0,0
    print("\n7. Data dengan koordinat 0,0 (mungkin tidak valid):")
    invalid_coords = [item for item in data if item.get('latitude', 0) == 0 and item.get('longitude', 0) == 0]
    if invalid_coords:
        print(f"   ⚠️  Ditemukan {len(invalid_coords)} item dengan koordinat 0,0:")
        for item in invalid_coords[:10]:  # Tampilkan 10 pertama
            print(f"      - ID: {item['id']}, Nama: {item['name']}, ID Pelanggan: {item['id_pelanggan']}")
        if len(invalid_coords) > 10:
            print(f"      ... dan {len(invalid_coords) - 10} item lainnya")
    else:
        print("   ✅ Tidak ada data dengan koordinat 0,0")
    
    # 8. Data dengan IP kosong
    print("\n8. Data dengan IP kosong:")
    empty_ip = [item for item in data if not item.get('ip', '').strip()]
    if empty_ip:
        print(f"   ⚠️  Ditemukan {len(empty_ip)} item dengan IP kosong:")
        for item in empty_ip[:10]:  # Tampilkan 10 pertama
            print(f"      - ID: {item['id']}, Nama: {item['name']}, ID Pelanggan: {item['id_pelanggan']}")
        if len(empty_ip) > 10:
            print(f"      ... dan {len(empty_ip) - 10} item lainnya")
    else:
        print("   ✅ Tidak ada data dengan IP kosong")

def main():
    print("Memuat data dari onts.json...")
    data = load_onts_data()
    
    if not data:
        print("Tidak ada data untuk diperiksa")
        return
    
    check_duplicates(data)
    
    print("\n=== Pemeriksaan Selesai ===")

if __name__ == "__main__":
    main() 