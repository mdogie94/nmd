import os
import re
from datetime import datetime
from bs4 import BeautifulSoup
from curl_cffi import requests
import pandas as pd

URL = "https://tibiavip.app/houses?status=auctioned&type=&world=Antica&auction=&town="
CSV_FILE = "historia_licytacji.csv"

def parse_bid_status(status_text: str, link_tag=None):
    clean_text = " ".join(status_text.split())
    
    gold_match = re.search(r"([\d\s,\.]+)\s*gold", clean_text, re.IGNORECASE)
    if gold_match:
        gold_str = re.sub(r"[^\d]", "", gold_match.group(1))
        gold_amount = int(gold_str) if gold_str else 0
    else:
        gold_amount = 0

    player_nick = "Brak ofert"
    if link_tag and link_tag.get_text(strip=True):
        player_nick = link_tag.get_text(strip=True)
    else:
        nick_match = re.search(r"by\s+([A-Za-z0-9'\-\s]+?)(?:\)|$|,)", clean_text, re.IGNORECASE)
        if nick_match:
            player_nick = nick_match.group(1).strip()

    return player_nick, gold_amount

def main():
    print(f"Pobieranie danych z: {URL}")
    resp = requests.get(URL, impersonate="chrome120", timeout=25)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, 'html.parser')
    table = soup.find('table')
    if not table:
        print("Nie znaleziono tabeli.")
        return

    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    current_records = []

    for row in table.find_all('tr')[1:]:
        cols = row.find_all('td')
        if len(cols) >= 3:
            house_name = cols[0].get_text(strip=True)
            town = cols[1].get_text(strip=True)
            bid_col = cols[-1]

            nick, gold = parse_bid_status(bid_col.get_text(strip=True), bid_col.find('a'))

            current_records.append({
                "Timestamp_UTC": now_str,
                "House Name": house_name,
                "Town": town,
                "Player Nick": nick,
                "Gold Amount": gold
            })

    if not current_records:
        print("Brak domków na licytacji.")
        return

    df_new = pd.DataFrame(current_records)

    if os.path.exists(CSV_FILE):
        df_new.to_csv(CSV_FILE, mode='a', header=False, index=False)
    else:
        df_new.to_csv(CSV_FILE, mode='w', header=True, index=False)

    print(f"Pomyślnie zaktualizowano {CSV_FILE} o {len(df_new)} rekordów.")

if __name__ == "__main__":
    main()
