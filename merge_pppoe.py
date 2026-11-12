import json
import re
from pathlib import Path

# --- GLOBAL CONFIGURATION / MAPS ---
WILAYAH_TO_KODE = {
    "waduk": "WDK",
    "ngembes": "NBS",
    "pengkok": "PGK",
    "gunungmaruk": "GM",
    "baran": "BRN",
    "ngasemayu": "NA",
    "trosari": "TRS",
    "salam": "SLM"
}

KODE_TO_WILAYAH = {v.lower(): k for k, v in WILAYAH_TO_KODE.items()}

# --- HELPER FUNCTIONS ---
def clean_string(text):
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"\(.*?\)", "", text)
    return text.replace(" ", "").replace("/", "").replace("-", "")

def get_normalized_parts(user_name):
    user_name = user_name.lower().strip()
    if "-" in user_name:
        parts = user_name.split("-", 1)
        return parts[0], parts[1]
    return "", user_name

def normalize_salam_name(name):
    name = name.lower()
    name = re.sub(r"\(.*?\)", "", name)
    name = name.replace(" ", "").replace("/", "")
    
    if "-" in name:
        parts = name.split("-", 1)
        prefix = parts[0]
        rest = parts[1]
        if prefix in KODE_TO_WILAYAH:
            return KODE_TO_WILAYAH[prefix] + rest
    return name


# --- CORE FUNCTIONS ---

def load_data(salam_file: str, pppoe_file: str, manual_file: str):
    """Membaca data menggunakan pathlib dengan dukungan tipe data List"""
    base_path = Path(__file__).parent
    salam_path = base_path / "data" / salam_file
    pppoe_path = base_path / "data" / pppoe_file
    manual_path = base_path / "data" / manual_file

    # Validasi file
    if not salam_path.exists() or not pppoe_path.exists():
        raise FileNotFoundError("Salah satu atau kedua file input utama (KMZ/Mentah) tidak ditemukan!")
        
    salam_data = json.loads(salam_path.read_text(encoding='utf-8'))
    
    # PERBAIKAN: Jika pppoes_temp.json berbentuk list, langsung load tanpa .get()
    pppoe_raw = json.loads(pppoe_path.read_text(encoding='utf-8'))
    if isinstance(pppoe_raw, dict):
        pppoe_list = pppoe_raw.get("pppoe", [])
    else:
        pppoe_list = pppoe_raw # Jika tipe datanya sudah berupa List []

    manual_list = []
    if manual_path.exists():
        try:
            manual_list = json.loads(manual_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            manual_list = []

    return salam_data, pppoe_list, manual_list

def process_merge(salam_data, pppoe_list, manual_list):
    """Logika inti penggabungan data"""
    salam_dict = {}
    for node in salam_data:
        clean_node_key = normalize_salam_name(node.get("name", ""))
        salam_dict[clean_node_key] = node

    final_result = []
    database_dict = {}
    for m in manual_list:
        if 'user' in m:
            database_dict[clean_string(m['user'])] = m
        elif 'username_pppoe' in m:  
            database_dict[clean_string(m['username_pppoe'])] = m
    
    for item in pppoe_list:
        user_name = item.get("user", "").strip()
        if not user_name:
            continue
            
        wilayah_panjang, sisa_nama = get_normalized_parts(user_name)
        if wilayah_panjang in WILAYAH_TO_KODE:
            kode_singkat = WILAYAH_TO_KODE[wilayah_panjang]
            lokasi_final = f"{kode_singkat}-{sisa_nama.capitalize()}"
        else:
            lokasi_final = user_name.upper()
            
        node_id = "-"
        latitude_final = "-"
        longitude_final = "-"
        
        clean_user_key = clean_string(user_name)
        if clean_user_key in salam_dict:
            matched_node = salam_dict[clean_user_key]
            node_id = matched_node.get("id")
            latitude_final = matched_node.get("latitude", "-")
            longitude_final = matched_node.get("longitude", "-")
        else:
            for clean_salam_key, node_item in salam_dict.items():
                if clean_user_key in clean_salam_key or clean_salam_key in clean_user_key:
                    node_id = node_item.get("id")
                    latitude_final = node_item.get("latitude", "-")
                    longitude_final = node_item.get("longitude", "-")
                    break

        ip_final = item.get("ip", "-")

        if clean_user_key in database_dict:
            save_data_web = database_dict[clean_user_key]
            if save_data_web.get("ip") and save_data_web.get("ip") != "-":
                ip_final = save_data_web.get("ip")
            if save_data_web.get("lokasi") and save_data_web.get("lokasi") != "-":
                lokasi_final = save_data_web.get("lokasi")
            if save_data_web.get("latitude") and save_data_web.get("latitude") != "-":
                latitude_final = save_data_web.get("latitude")
            if save_data_web.get("longitude") and save_data_web.get("longitude") != "-":
                longitude_final = save_data_web.get("longitude")
            if save_data_web.get("id") and save_data_web.get("id") != "-":
                node_id = save_data_web.get("id")
            elif save_data_web.get("id_pelanggan") and save_data_web.get("id_pelanggan") != "-":
                node_id = save_data_web.get("id_pelanggan")
                    
        combined_item = {
            "router": item.get("router", "-"),
            "icon": 119,
            "id": node_id,
            "user": user_name,              
            "lokasi": lokasi_final,
            "latitude": latitude_final,
            "longitude": longitude_final,
            "coordinate": f"{latitude_final},{longitude_final}",
            "mac": item.get("mac", "-"),
            "ip": ip_final,
            "uptime": item.get("uptime", "-"),
            "status": item.get("status", "OFFLINE"),
        }
        final_result.append(combined_item)
        
    # PERBAIKAN: Langsung mengembalikan final_result (berupa List []), tidak dibungkus dict
    return final_result 

def save_data(data, output_file: str):
    """Menyimpan hasil akhir menggunakan pathlib"""
    output_path = Path(__file__).parent / "data" / output_file
    output_path.write_text(json.dumps(data, indent=4), encoding='utf-8')
    print(f"Success! Data saved to: {output_path.resolve()}")


# --- MAIN EXECUTION BLOCK ---
def main():
    salam_file = "salam-pathuk.json"
    pppoe_file = "pppoes_temp.json"
    output_file = "pppoes.json"
    manual_file = "user_manual.json"
    
    try:
        # 1. Ambil Data
        salam_data, pppoe_list, manual_list = load_data(salam_file, pppoe_file, manual_file)
        # 2. Proses/Merge Data
        processed_data = process_merge(salam_data, pppoe_list, manual_list)
        # 3. Simpan Hasil
        save_data(processed_data, output_file)
        
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()