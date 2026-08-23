import os
import requests
import pandas as pd
from datetime import datetime

WORLD = "Antica"
CSV_FILE = "historia_licytacji.csv"

TOWNS = [
    "Ab'Dendriel", "Ankrahmun", "Carlin", "Darashia", "Edron", 
    "Farmine", "Gray Beach", "Issavi", "Kazordoon", "Liberty Bay", 
    "Moonfall", "Port Hope", "Rathleton", "Silvertides", "Svargrond", 
    "Thais", "Venore", "Yalahar"
]

def get_auctioned_houses():
    auctioned = []
    
    for town in TOWNS:
        url = f"https://api.tibiadata.com/v4/houses/{WORLD}/{town}"
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                continue
            
            data = resp.json()
            house_list = data.get("houses", {}).get("house_list", [])
            
            for h in house_list:
                status = h.get("status", "")
                
                # Interesują nas tylko domki licytowane (auctioned)
                if status == "auctioned":
                    auction_info = h.get("auction", {})
                    
                    current_bid = auction_info.get("current_bid", 0)
                    bidder = auction_info.get("current_bidder", "Brak ofert")
                    if not bidder:
                        bidder = "Brak ofert"
                    
                    auctioned.append({
                        "Timestamp_UTC": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                        "World": WORLD,
                        "House Name": h.get("name"),
                        "Town": town,
                        "Size (SQM)": h.get("size"),
                        "Rent (Gold)": h.get("rent"),
                        "Player Nick": bidder,
                        "Gold Amount": current_bid
                    })
        except Exception as e:
            print(f"Błąd przy pobieraniu miasta {town}: {e}")
            
    return auctioned

def main():
    print(f"Pobieranie licytacji ze świata {WORLD}...")
    records = get_auctioned_houses()
    
    if not records:
        print("Brak trwających licytacji w tym momencie.")
        return

    df_new = pd.DataFrame(records)
    print(f"\nZnaleziono {len(df_new)} licytowanych domków:")
    print(df_new[["House Name", "Town", "Player Nick", "Gold Amount"]].to_string(index=False))

    # Zapis i dopisywanie do pliku CSV
    if os.path.exists(CSV_FILE):
        df_new.to_csv(CSV_FILE, mode='a', header=False, index=False, encoding='utf-8-sig')
    else:
        df_new.to_csv(CSV_FILE, mode='w', header=True, index=False, encoding='utf-8-sig')

    print(f"\n[+] Pomyślnie zaktualizowano {CSV_FILE}!")

if __name__ == "__main__":
    main()
