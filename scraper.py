from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import os
import time
import urllib.parse
import pandas as pd
import requests

WORLD = "Antica"
CSV_FILE = "historia_licytacji.csv"
DAYS_TO_KEEP = 7

TOWNS = [
    "Ab'Dendriel", "Ankrahmun", "Carlin", "Darashia", "Edron", 
    "Farmine", "Gray Beach", "Issavi", "Kazordoon", "Liberty Bay", 
    "Marapur", "Port Hope", "Rathleton", "Svargrond", "Thais", 
    "Venore", "Yalahar"
]

HEADERS = {
    "User-Agent": "TibiaAuctionTracker/1.0",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache"
}

def fetch_town_houses(town):
    town_encoded = urllib.parse.quote(town)
    url = f"https://api.tibiadata.com/v4/houses/{WORLD}/{town_encoded}?_t={int(time.time())}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=5)
        if resp.status_code == 200:
            data = resp.json().get("houses", {})
            return (data.get("house_list") or []) + (data.get("guildhall_list") or [])
    except Exception:
        pass
    return []

def check_single_house(house_id, house_name, town, now_str):
    if not house_id:
        return None

    try:
        detail_url = f"https://api.tibiadata.com/v4/house/{WORLD}/{house_id}?_t={int(time.time() * 1000)}"
        resp = requests.get(detail_url, headers=HEADERS, timeout=3)

        if resp.status_code == 200:
            house_data = resp.json().get("house", {})
            status_obj = house_data.get("status", {})
            auction_obj = house_data.get("auction") or status_obj.get("auction") or {}

            player_nick = (
                auction_obj.get("current_bidder")
                or auction_obj.get("bidder")
                or status_obj.get("current_bidder")
                or status_obj.get("highest_bidder")
            )

            gold_bid = (
                auction_obj.get("current_bid")
                or auction_obj.get("bid")
                or status_obj.get("current_bid")
                or status_obj.get("highest_bid")
                or 0
            )

            if player_nick and str(player_nick).strip() not in ["", "None", "null", "Brak ofert"]:
                return {
                    "Timestamp_UTC": now_str,
                    "House Name": house_name,
                    "Town": str(town).strip(),
                    "Player Nick": str(player_nick).strip(),
                    "Gold Amount": int(gold_bid)
                }
    except Exception:
        pass
    return None

def build_hotlist():
    """Wyszukuje wszystkie licytowane domki na serwerze i tworzy listę do natychmiastowego śledzenia."""
    hotlist = []
    for town in TOWNS:
        houses = fetch_town_houses(town)
        for h in houses:
            status = str(h.get("status", "")).lower()
            if "rented" not in status or "auction" in status:
                h_id = h.get("house_id")
                h_name = str(h.get("name", "N/A")).strip().strip('"')
                if h_id:
                    hotlist.append({"id": h_id, "name": h_name, "town": town})
    return hotlist

def scan_hotlist(hotlist, now_str):
    """Błyskawiczne odpytanie wyłącznie domków licytowanych (czas trwania: <0.5s)."""
    bids = []
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = [
            executor.submit(check_single_house, item["id"], item["name"], item["town"], now_str)
            for item in hotlist
        ]
        for future in as_completed(futures):
            res = future.result()
            if res:
                bids.append(res)
    return bids

def get_last_known_state():
    if not os.path.exists(CSV_FILE):
        return {}
    try:
        df = pd.read_csv(CSV_FILE)
        if df.empty or "House Name" not in df.columns:
            return {}

        df["dt"] = pd.to_datetime(df["Timestamp_UTC"], errors="coerce")
        df = df.sort_values(by="dt", ascending=True)

        last_state = {}
        for _, row in df.iterrows():
            h_name = str(row["House Name"]).strip().strip('"')
            town = str(row["Town"]).strip()
            nick = str(row["Player Nick"]).strip()
            try:
                gold = int(row["Gold Amount"])
            except (ValueError, TypeError):
                gold = 0

            key = (h_name.lower(), town.lower())
            last_state[key] = (nick, gold)

        return last_state
    except Exception:
        return {}

def update_and_cleanup_csv(new_records):
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

    df_combined["_dt"] = pd.to_datetime(df_combined["Timestamp_UTC"], errors="coerce")
    cutoff_date = datetime.utcnow() - timedelta(days=DAYS_TO_KEEP)
    df_cleaned = df_combined[df_combined["_dt"] >= cutoff_date]

    df_cleaned = df_cleaned.sort_values(by="_dt", ascending=False)
    df_cleaned = df_cleaned[cols]

    df_cleaned.to_csv(CSV_FILE, index=False, encoding="utf-8-sig")

def is_sniper_active(now_utc):
    # Okno snajpera: 09:55 - 10:02 EU (Czas letni: 07:55-08:02 UTC, Czas zimowy: 08:55-09:02 UTC)
    in_summer = (now_utc.hour == 7 and now_utc.minute >= 55) or (now_utc.hour == 8 and now_utc.minute <= 2)
    in_winter = (now_utc.hour == 8 and now_utc.minute >= 55) or (now_utc.hour == 9 and now_utc.minute <= 2)
    return in_summer or in_winter

def main():
    now_utc = datetime.utcnow()
    last_known_state = get_last_known_state()

    if is_sniper_active(now_utc):
        print("=== AKTYWACJA TURBO-SNAJPERA (09:55 - 10:02 EU) ===", flush=True)
        
        print("[1/2] Budowanie Hotlisty licytowanych domków...", flush=True)
        hotlist = build_hotlist()
        print(f"[+] Na liście obserwacyjnej: {len(hotlist)} domków.", flush=True)

        start_time = time.time()
        print("[2/2] Start pętli turbo (próbkowanie co 1-2s)...", flush=True)

        while time.time() - start_time < 420:
            current_utc = datetime.utcnow()

            # Zakończenie po Server Save (10:02:00 EU Time)
            if (current_utc.hour == 8 and current_utc.minute >= 2) or (current_utc.hour == 9 and current_utc.minute >= 2):
                print("Server Save zakończony (10:02 EU). Kończę pracę snajpera.", flush=True)
                break

            now_str = current_utc.strftime('%Y-%m-%d %H:%M:%S')
            records = scan_hotlist(hotlist, now_str)
            updates = []

            for r in records:
                key = (r["House Name"].lower(), r["Town"].lower())
                current_state = (r["Player Nick"], r["Gold Amount"])

                if key not in last_known_state or last_known_state[key] != current_state:
                    last_known_state[key] = current_state
                    updates.append(r)
                    print(f"[{r['Timestamp_UTC']}] TURBO PRZEBICIE: {r['House Name']} ({r['Town']}) -> {r['Player Nick']} ({r['Gold Amount']} gp)", flush=True)

            if updates:
                update_and_cleanup_csv(updates)

            # W krytycznym oknie 09:59 - 10:01 czekamy tylko 1 sekundę
            is_critical = (current_utc.hour in [7, 8] and current_utc.minute == 59) or (current_utc.hour in [8, 9] and current_utc.minute == 0)
            sleep_time = 1 if is_critical else 3
            time.sleep(sleep_time)

    else:
        print("=== Standardowe sprawdzenie co 15 minut ===", flush=True)
        hotlist = build_hotlist()
        records = scan_hotlist(hotlist, now_utc.strftime('%Y-%m-%d %H:%M:%S'))
        updates = []

        for r in records:
            key = (r["House Name"].lower(), r["Town"].lower())
            current_state = (r["Player Nick"], r["Gold Amount"])

            if key not in last_known_state or last_known_state[key] != current_state:
                last_known_state[key] = current_state
                updates.append(r)
                print(f"  [+] NOWY WPIS: {r['House Name']} ({r['Town']}) -> {r['Player Nick']} ({r['Gold Amount']} gp)", flush=True)

        update_and_cleanup_csv(updates)
        if updates:
            print(f"Zapisano {len(updates)} nowych pozycji.", flush=True)
        else:
            print("Brak nowych zmian. Baza posortowana i oczyszczona.", flush=True)

if __name__ == "__main__":
    main()
