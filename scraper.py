import os
import re
from datetime import datetime
from bs4 import BeautifulSoup
from curl_cffi import requests
import pandas as pd

WORLD = "Antica"
CSV_FILE = "historia_licytacji.csv"

TOWNS = [
    "Ab'Dendriel", "Ankrahmun", "Carlin", "Darashia", "Edron", 
    "Farmine", "Gray Beach", "Issavi", "Kazordoon", "Liberty Bay", 
    "Marapur", "Port Hope", "Rathleton", "Svargrond", "Thais", 
    "Venore", "Yalahar"
]

def parse_auction_cell(cell_text):
    clean = " ".join(cell_text.split())
    
    gold_match = re.search(r"([\d\s,\.]+)\s*gold", clean, re.IGNORECASE)
    gold_amount = 0
    if gold_match:
        gold_str = re.sub(r"[^\d]", "", gold_match.group(1))
        gold_amount = int(gold_str) if gold_str else 0
        
    player_nick = None
    nick_match = re.search(r"by\s+([A-Za-z0-9'\-\s]+?)(?:\)|$|,)", clean, re.IGNORECASE)
    if nick_match:
        player_nick = nick_match.group(1).strip()
        
    return player_nick, gold_amount

def scrape_tibia_com():
    bids = []
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    post_url = "https://www.tibia.com/community/?subtopic=houses"

    print(f"--- Skanowanie Tibia.com formularzem POST dla świata: {WORLD} ---")

    for town in TOWNS:
        # Formularz Tibia.com wymaga dokładnie tych pól w zapytaniu POST
        payload = {
            "world": WORLD,
            "town": town,
            "state": "auctioned",
            "type": "houses",
            "order": "name"
        }

        try:
            resp = requests.post(
                post_url,
                data=payload,
                impersonate="chrome120",
                timeout=25
            )
            
            if resp.status_code != 200:
                print(f"[{town}] Błąd HTTP {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Wyszukujemy wszystkie tabele z danymi domków
            rows = soup.find_all("tr")
            town_bids = 0

            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 4:
                    house_name = cols[0].get_text(strip=True)
                    status_text = cols[3].get_text(strip=True)

                    # Sprawdzamy czy wiersz ma licytację i ofertę gracza (słowo 'by')
                    if "auction" in status_text.lower() and "by" in status_text.lower():
                        player_nick, gold_amount = parse_auction_cell(status_text)
                        
                        if player_nick and gold_amount > 0:
                            print(f"  [+] {house_name} ({town}) -> Nick: {player_nick} | Oferta: {gold_amount} gp")
                            bids.append({
                                "Timestamp_UTC": now_str,
                                "House Name": house_name,
                                "Town": town,
                                "Player Nick": player_nick,
                                "Gold Amount": gold_amount
                            })
                            town_bids += 1
                            
            print(f"[{town}] Zakończono, znaleziono aktywnych ofert: {town_bids}")

        except Exception as e:
            print(f"[{town}] Błąd: {e}")

    return bids

def main():
    records = scrape_tibia_com()
    
    if records:
        df_new = pd.DataFrame(records)
        print(f"\n==========================================")
        print(f"Sukces! Pobrano łącznie {len(df_new)} ofert z Tibia.com.")
        print(f"==========================================")
        
        if os.path.exists(CSV_FILE):
            df_new.to_csv(CSV_FILE, mode='a', header=False, index=False, encoding='utf-8-sig')
        else:
            df_new.to_csv(CSV_FILE, mode='w', header=True, index=False, encoding='utf-8-sig')
        print(f"[+] Zaktualizowano plik {CSV_FILE}.")
    else:
        print("\n[i] Brak licytacji z aktywnymi ofertami graczy.")
        if not os.path.exists(CSV_FILE):
            cols = ["Timestamp_UTC", "House Name", "Town", "Player Nick", "Gold Amount"]
            pd.DataFrame(columns=cols).to_csv(CSV_FILE, index=False, encoding='utf-8-sig')

if __name__ == "__main__":
    main()
