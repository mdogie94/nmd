import os
import urllib.parse
from datetime import datetime
import pandas as pd
import requests

WORLD = "Antica"
CSV_FILE = "historia_licytacji.csv"

TOWNS = [
    "Ab'Dendriel", "Ankrahmun", "Carlin", "Darashia", "Edron", 
    "Farmine", "Gray Beach", "Issavi", "Kazordoon", "Liberty Bay", 
    "Marapur", "Port Hope", "Rathleton", "Svargrond", "Thais", 
    "Venore", "Yalahar"
]

def get_auctioned_bids():
    bids = []
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    headers = {"User-Agent": "TibiaAuctionTracker/1.0"}

    print(f"--- Skanowanie licytacji na świecie: {WORLD} ---")

    for town in TOWNS:
        town_encoded = urllib.parse.quote(town)
        url = f"https://api.tibiadata.com/v4/houses/{WORLD}/{town_encoded}"

        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                continue

            data = resp.json()
            houses_data = data.get("houses", {})
            house_list = (houses_data.get("house_list") or []) + (houses_data.get("guildhall_list") or [])

            for h in house_list:
                status = str(h.get("status", "")).lower()
                is_auctioned = h.get("auctioned") is True or "auction" in status
                
                # Jeśli domek jest na aukcji, pobieramy jego pełną kartę
                if is_auctioned:
                    house_id = h.get("house_id")
                    house_name = h.get("name", "N/A")

                    if not house_id:
                        continue

                    # Pobieranie szczegółów aukcji konkretnego domku
                    detail_url = f"https://api.tibiadata.com/v4/house/{WORLD}/{house_id}"
                    d_resp = requests.get(detail_url, headers=headers, timeout=15)
                    
                    if d_resp.status_code == 200:
                        house_details = d_resp.json().get("house", {})
                        auction_info = house_details.get("auction", {})

                        player_nick = auction_info.get("current_bidder")
                        gold_bid = auction_info.get("current_bid", 0)

                        # Filtrujemy tylko oferty ze złożonym bidem gracza
                        if player_nick and int(gold_bid) > 0:
                            print(f"  [+] {house_name} ({town}) -> Gracz: {player_nick} | Oferta: {gold_bid} gp")
                            bids.append({
                                "Timestamp_UTC": now_str,
                                "House Name": house_name,
                                "Town": town,
                                "Player Nick": player_nick.strip(),
                                "Gold Amount": int(gold_bid)
                            })
        except Exception as e:
            print(f"[{town}] Błąd: {e}")

    return bids

def main():
    records = get_auctioned_bids()

    if records:
        df_new = pd.DataFrame(records)
        print(f"\n==========================================")
        print(f"Pobrano łącznie {len(df_new)} aktywnych licytacji z ofertami.")
        print(f"==========================================")

        if os.path.exists(CSV_FILE):
            df_new.to_csv(CSV_FILE, mode='a', header=False, index=False, encoding='utf-8-sig')
        else:
            df_new.to_csv(CSV_FILE, mode='w', header=True, index=False, encoding='utf-8-sig')
        print(f"[+] Zapisano w {CSV_FILE}.")
    else:
        print("\n[i] Brak ofert w tej chwili na Antice.")
        if not os.path.exists(CSV_FILE):
            cols = ["Timestamp_UTC", "House Name", "Town", "Player Nick", "Gold Amount"]
            pd.DataFrame(columns=cols).to_csv(CSV_FILE, index=False, encoding='utf-8-sig')

if __name__ == "__main__":
    main()
