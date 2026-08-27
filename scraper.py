from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime, timedelta
import os
import re
import time
import urllib.parse
import pandas as pd
import requests

WORLD = "Antica"
CSV_FILE = "historia_licytacji.csv"
DAYS_TO_KEEP = 14

TOWNS = [
    "Ab'Dendriel", "Ankrahmun", "Carlin", "Darashia", "Edron",
    "Farmine", "Gray Beach", "Issavi", "Kazordoon", "Liberty Bay",
    "Marapur", "Port Hope", "Rathleton", "Svargrond", "Thais",
    "Venore", "Yalahar"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

def fetch_town_houses(town):
    town_encoded = urllib.parse.quote(town)
    url = f"https://api.tibiadata.com/v4/houses/{WORLD}/{town_encoded}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json().get("houses", {})
            h_list = data.get("house_list") or []
            g_list = data.get("guildhall_list") or []
            return h_list + g_list
    except Exception as e:
        print(f"Błąd miasta {town}: {e}", flush=True)
    return []

def extract_bidder_and_gold(house_data):
    """Przeszukuje cały obiekt JSON pod kątem nicku i najwyższej kwoty."""
    bidder = None
    gold_bid = 0

    def recursive_search(obj):
        nonlocal bidder, gold_bid
        if isinstance(obj, dict):
            for k, v in obj.items():
                k_low = k.lower()
                # Szukamy licytującego
                if any(x in k_low for x in ["bidder", "current_bidder", "highest_bidder", "character"]):
                    if v and isinstance(v, str) and v.strip().lower() not in ["", "none", "null", "false", "brak ofert", "no bidder"]:
                        if not bidder:
                            bidder = v.strip()
                # Szukamy kwoty złota
                if any(x in k_low for x in ["bid", "current_bid", "highest_bid", "gold"]):
                    if v is not None and not isinstance(v, (dict, list)):
                        clean = re.sub(r"[^\d]", "", str(v))
                        if clean:
                            val = int(clean)
                            if val > gold_bid:
                                gold_bid = val
                recursive_search(v)
        elif isinstance(obj, list):
            for item in obj:
                recursive_search(item)

    recursive_search(house_data)
    return bidder, gold_bid

def check_single_house(house_id, house_name, town, now_str):
    if not house_id:
        return None

    try:
        detail_url = f"https://api.tibiadata.com/v4/house/{WORLD}/{house_id}"
        resp = requests.get(detail_url, headers=HEADERS, timeout=6)

        if resp.status_code == 200:
            data = resp.json()
            bidder, gold_bid = extract_bidder_and_gold(data)

            if bidder and gold_bid > 0:
                return {
                    "Timestamp_UTC": now_str,
                    "House Name": house_name,
                    "Town": str(town).strip(),
                    "Player Nick": bidder,
                    "Gold Amount": int(gold_bid),
                }
    except Exception:
        pass
    return None

def get_all_active_auctions(now_str):
    houses_to_check = []
    
    # Krok 1: Pobieramy listę ze wszystkich miast
    for town in TOWNS:
        houses = fetch_town_houses(town)
        for h in houses:
            # Sprawdzamy każdy domek, który ma obiekt 'auction' lub NIE ma czystego statusu 'rented' bez licytacji
            status = str(h.get("status", "")).lower()
            auction_field = h.get("auction")
            
            is_candidate = (
                auction_field is not None or
                "rented" not in status or
                "auction" in status or
                "auctioned" in status
            )
            
            if is_candidate:
                h_id = h.get("house_id")
                h_name = str(h.get("name", "N/A")).strip().strip('"')
                if h_id:
                    houses_to_check.append((h_id, h_name, town))

    print(f"Liczba domków zakwalifikowanych do sprawdzenia szczegółów: {len(houses_to_check)}", flush=True)

    # Krok 2: Sprawdzamy równolegle w 25 wątkach
    bids = []
    with ThreadPoolExecutor(max_workers=25) as executor:
        futures = [
            executor.submit(check_single_house, item[0], item[1], item[2], now_str)
            for item in houses_to_check
        ]
        for future in as_completed(futures):
            res = future.result()
            if res:
                print(f"  -> ZNALEZIONO OFERTĘ: {res['House Name']} ({res['Town']}) | {res['Player Nick']} | {res['Gold Amount']} gp", flush=True)
                bids.append(res)
    return bids

def get_last_known_bids():
    """Zwraca mapę: (nazwa_domku, miasto) -> (gracz, kwota) z ostatniego wpisu w pliku CSV."""
    if not os.path.exists(CSV_FILE):
        return {}
    try:
        df = pd.read_csv(CSV_FILE)
        if df.empty or "House Name" not in df.columns:
            return {}

        state = {}
        for _, row in df.iterrows():
            h_name = str(row["House Name"]).strip().lower()
            town = str(row["Town"]).strip().lower()
            nick = str(row["Player Nick"]).strip()
            try:
                gold = int(row["Gold Amount"])
            except Exception:
                gold = 0

            key = (h_name, town)
            if key not in state:
                state[key] = (nick, gold)

        return state
    except Exception:
        return {}

def append_and_clean_csv(new_records):
    cols = ["Timestamp_UTC", "House Name", "Town", "Player Nick", "Gold Amount"]

    if os.path.exists(CSV_FILE):
        try:
            df_existing = pd.read_csv(CSV_FILE)
        except Exception:
            df_existing = pd.DataFrame(columns=cols)
    else:
        df_existing = pd.DataFrame(columns=cols)

    if new_records:
        df_new = pd.DataFrame(new_records)
        df_combined = pd.concat([df_new, df_existing], ignore_index=True)
    else:
        df_combined = df_existing

    if df_combined.empty:
        return

    # Usuwamy dokładne duplikaty
    df_combined = df_combined.drop_duplicates(subset=["Timestamp_UTC", "House Name", "Town", "Gold Amount"])

    df_combined["_dt"] = pd.to_datetime(df_combined["Timestamp_UTC"], errors="coerce")
    cutoff = datetime.utcnow() - timedelta(days=DAYS_TO_KEEP)
    df_cleaned = df_combined[df_combined["_dt"] >= cutoff].copy()

    df_cleaned = df_cleaned.sort_values(by="_dt", ascending=False)
    df_cleaned = df_cleaned[cols]

    df_cleaned.to_csv(CSV_FILE, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)

def is_sniper_time(now_utc):
    summer = (now_utc.hour == 7 and now_utc.minute >= 55) or (now_utc.hour == 8 and now_utc.minute <= 2)
    winter = (now_utc.hour == 8 and now_utc.minute >= 55) or (now_utc.hour == 9 and now_utc.minute <= 2)
    return summer or winter

def main():
    now_utc = datetime.utcnow()
    now_str = now_utc.strftime("%Y-%m-%d %H:%M:%S")
    last_bids = get_last_known_bids()

    print(f"=== Uruchomienie skanera: {now_str} UTC ===", flush=True)

    if is_sniper_time(now_utc):
        print("=== START TRYBU TURBO-SNAJPER (09:55 - 10:02 EU) ===", flush=True)
        start_t = time.time()
        while time.time() - start_t < 420:
            curr = datetime.utcnow()
            if (curr.hour == 8 and curr.minute >= 2) or (curr.hour == 9 and curr.minute >= 2):
                print("Server Save zakończony. Zamykam snajpera.", flush=True)
                break

            curr_str = curr.strftime("%Y-%m-%d %H:%M:%S")
            active_bids = get_all_active_auctions(curr_str)
            new_to_save = []

            for b in active_bids:
                key = (b["House Name"].lower(), b["Town"].lower())
                curr_state = (b["Player Nick"], b["Gold Amount"])

                if key not in last_bids or last_bids[key] != curr_state:
                    last_bids[key] = curr_state
                    new_to_save.append(b)

            if new_to_save:
                append_and_clean_csv(new_to_save)

            is_critical = (curr.hour in [7, 8] and curr.minute == 59) or (curr.hour in [8, 9] and curr.minute == 0)
            time.sleep(1 if is_critical else 2)
    else:
        print("=== Sprawdzenie okresowe ===", flush=True)
        active_bids = get_all_active_auctions(now_str)
        new_to_save = []

        for b in active_bids:
            key = (b["House Name"].lower(), b["Town"].lower())
            curr_state = (b["Player Nick"], b["Gold Amount"])

            if key not in last_bids or last_bids[key] != curr_state:
                last_bids[key] = curr_state
                new_to_save.append(b)
                print(f"  [+] NOWY WPIS DO BAZY: {b['House Name']} ({b['Town']}) -> {b['Player Nick']} ({b['Gold Amount']} gp)", flush=True)

        if new_to_save:
            append_and_clean_csv(new_to_save)
            print(f"Pomyślnie dopisano {len(new_to_save)} nowych ofert do pliku CSV.", flush=True)
        else:
            print("Brak zmian w licytacjach od ostatniego sprawdzenia.", flush=True)

if __name__ == "__main__":
    main()
