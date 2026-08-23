import os
import requests
import pandas as pd
from datetime import datetime

WORLD = "Antica"
CSV_FILE = "historia_licytacji.csv"

# Kompletna lista wszystkich miast w Tibii z domkami i guildhallami
TOWNS = [
    "Ab'Dendriel",
    "Ankrahmun",
    "Bounac",
    "Carlin",
    "Cormaya",
    "Darashia",
    "Edron",
    "Farmine",
    "Fibula",
    "Gnomprona",
    "Gray Beach",
    "Issavi",
    "Kazordoon",
    "Liberty Bay",
    "Marapur",
    "Moonfall",
    "Outlaw Camp",
    "Port Hope",
    "Rathleton",
    "Roshamuul",
    "Silvertides",
    "Svargrond",
    "Thais",
    "Venore",
    "Waterfall",
    "Yalahar"
]

def get_all_bids():
    bids = []
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"Pobieranie listy domków dla świata: {WORLD}...")
    
    for town in TOWNS:
        url = f"https://api.tibiadata.com/v4/houses/{WORLD}/{town}"
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                continue
            
            data = resp.json()
            house_list = data.get("houses", {}).get("house_list", [])
            
            for h in house_list:
                status = str(h.get("status", "")).lower()
                
                # Szukamy domków wystawionych na licytację
                if "auction" in status:
                    house_id = h.get("house_id")
                    house_name = h.get("name", "N/A")
                    
                    player_nick = "Brak ofert"
                    gold_amount = 0
                    
                    # Odpytanie o szczegóły konkretnej licytacji (cena + nick)
                    if house_id:
                        try:
                            detail_url = f"https://api.tibiadata.com/v4/house/{WORLD}/{house_id}"
                            d_resp = requests.get(detail_url, timeout=10)
                            if d_resp.status_code == 200:
                                d_json = d_resp.json().get("house", {})
                                auction_data = d_json.get("auction", {})
                                
                                gold_amount = auction_data.get("current_bid", 0)
                                player_nick = auction_data.get("current_bidder") or "Brak ofert"
                        except Exception as ex:
                            print(f"Nie udało się pobrać szczegółów dla domku {house_name}: {ex}")
                    
                    print(f"-> Znaleziono: {house_name} ({town}) | {player_nick} | {gold_amount} gold")
                    
                    bids.append({
                        "Timestamp_UTC": now_str,
                        "World": WORLD,
                        "House Name": house_name,
                        "Town": town,
                        "Size (SQM)": h.get("size", "N/A"),
                        "Rent (Gold)": h.get("rent", "N/A"),
                        "Player Nick": player_nick,
                        "Gold Amount": gold_amount
                    })
        except Exception as e:
            print(f"Błąd dla miasta {town}: {e}")
            
    return bids

def main():
    records = get_all_bids()
    
    if records:
        df_new = pd.DataFrame(records)
        print(f"\n[+] Znaleziono łącznie {len(df_new)} licytacji.")
        
        if os.path.exists(CSV_FILE):
            df_new.to_csv(CSV_FILE, mode='a', header=False, index=False, encoding='utf-8-sig')
        else:
            df_new.to_csv(CSV_FILE, mode='w', header=True, index=False, encoding='utf-8-sig')
        print(f"[+] Zaktualizowano plik {CSV_FILE}.")
    else:
        print("\n[!] W tym momencie żaden domek nie jest licytowany na Antice.")

if __name__ == "__main__":
    main()
