import os
import time
import urllib.parse
import re
import html
import csv
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import pandas as pd

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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def fetch_town_houses_list(town):
    town_encoded = urllib.parse.quote(town)
    url = f"https://api.tibiadata.com/v4/houses/{WORLD}/{town_encoded}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=6)
        if resp.status_code == 200:
            data = resp.json().get("houses", {})
            return (data.get("house_list") or []) + (data.get("guildhall_list") or [])
    except Exception:
        pass
    return []

def scrape_house_direct_tibia(house_id, house_name, town, now_str):
    if not house_id:
        return None

    url = f"https://www.tibia.com/community/?subtopic=houses&page=view&world={WORLD}&houseid={house_id}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=5)
        if resp.status_code == 200:
            page_text = html.unescape(resp.text)
            
            # Wzorzec 1: Bezpośrednio z tekstu strony CipSoftu
            bid_match = re.search(r"highest bid so far is\s+([\d,.]+)\s+gold", page_text, re.IGNORECASE)
            nick_match = re.search(r"submitted by\s+<a[^>]*>([^<]+)</a>", page_text, re.IGNORECASE)
            
            # Wzorzec 2 (fallback bez tagu <a>):
            if not nick_match:
                nick_match = re.search(r"submitted by\s+([^<.,\n\r]+?)(?:\.|\s*and|\s*\(|<|$)", page_text, re.IGNORECASE)

            if bid_match and nick_match:
                gold_str = re.sub(r"[^\d]", "", bid_match.group(1))
                bidder = nick_match.group(1).strip()
                bidder = re.sub(r"<[^>]*>", "", bidder).strip()

                if bidder and gold_str:
                    return {
                        "Timestamp_UTC": now_str,
                        "House Name": house_name,
                        "Town": str(town).strip(),
                        "Player Nick": bidder,
                        "Gold Amount": int(gold_str)
                    }
    except Exception as e:
        print(f"Błąd scrapingu domku {house_id}: {e}", flush=True)
    return None

def get_active_houses_to_track():
    candidates = []
    for town in TOWNS:
        houses = fetch_town_houses_list(town)
        for h in houses:
            status = str(h.get("status", "")).lower()
            auction_obj = h.get("auction")
            if auction_obj is not None or "rented" not in status or "auction" in status:
                h_id = h.get("house_id")
                h_name = str(h.get("name", "N/A")).strip().strip('"')
                if h_id:
                    candidates.append((h_id, h_name, town))
                    
    # Gwarantowany wpis dla Alai Flats
    if not any("Alai Flats" in str(c[1]) for c in candidates):
        candidates.append((10204, "Alai Flats, Flat 25", "Thais"))
        
    return candidates

def scan_houses_direct(houses_to_track, now_str):
    bids = []
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = [
            executor.submit(scrape_house_direct_tibia, item[0], item[1], item[2], now_str)
            for item in houses_to_track
        ]
        for future in as_completed(futures):
            res = future.result()
            if res:
                bids.append(res)
    return bids

def get_last_known_bids():
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
    now_str = now_utc.strftime('%Y-%m-%d %H:%M:%S')
    last_bids = get_last_known_bids()

    print(f"=== Skaner Direct-Tibia.com: {now_str} UTC ===", flush=True)

    if is_sniper_time(now_utc):
        print("=== TRYB TURBO-SNAJPER (09:55 - 10:02 EU) ===", flush=True)
        houses_to_track = get_active_houses_to_track()
        print(f"Śledzone domki ({len(houses_to_track)}):", flush=True)
        for h in houses_to_track:
            print(f" -> {h[1]} ({h[2]})", flush=True)

        start_t = time.time()
        while time.time() - start_t < 420:
            curr = datetime.utcnow()
            if (curr.hour == 8 and curr.minute >= 2) or (curr.hour == 9 and curr.minute >= 2):
                print("Server Save zakończony. Zamykam snajpera.", flush=True)
                break

            curr_str = curr.strftime('%Y-%m-%d %H:%M:%S')
            active_bids = scan_houses_direct(houses_to_track, curr_str)
            new_to_save = []

            for b in active_bids:
                key = (b["House Name"].lower(), b["Town"].lower())
                curr_state = (b["Player Nick"], b["Gold Amount"])

                if key not in last_bids or last_bids[key] != curr_state:
                    last_bids[key] = curr_state
                    new_to_save.append(b)
                    print(f"[{b['Timestamp_UTC']}] DIRECT PRZEBICIE: {b['House Name']} -> {b['Player Nick']} ({b['Gold Amount']} gp)", flush=True)

            if new_to_save:
                append_and_clean_csv(new_to_save)

            is_critical = (curr.hour in [7, 8] and curr.minute == 59) or (curr.hour in [8, 9] and curr.minute == 0)
            time.sleep(1 if is_critical else 2)
    else:
        print("=== Standardowe sprawdzenie ===", flush=True)
        houses_to_track = get_active_houses_to_track()
        active_bids = scan_houses_direct(houses_to_track, now_str)
        new_to_save = []

        for b in active_bids:
            key = (b["House Name"].lower(), b["Town"].lower())
            curr_state = (b["Player Nick"], b["Gold Amount"])

            if key not in last_bids or last_bids[key] != curr_state:
                last_bids[key] = curr_state
                new_to_save.append(b)
                print(f"  [+] ZNALEZIONO OFERTĘ: {b['House Name']} ({b['Town']}) -> {b['Player Nick']} ({b['Gold Amount']} gp)", flush=True)

        if new_to_save:
            append_and_clean_csv(new_to_save)
            print(f"Zapisano {len(new_to_save)} nowych ofert do CSV.", flush=True)
        else:
            print("Brak nowych zmian w licytacjach.", flush=True)

if __name__ == "__main__":
    main()
