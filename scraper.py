To którego kodu użyć? Tego co wysłałes teraz czy tego:


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
    "Ab'Dendriel",
    "Ankrahmun",
    "Carlin",
    "Darashia",
    "Edron",
    "Farmine",
    "Gray Beach",
    "Issavi",
    "Kazordoon",
    "Liberty Bay",
    "Marapur",
    "Port Hope",
    "Rathleton",
    "Svargrond",
    "Thais",
    "Venore",
    "Yalahar",
]

HEADERS = {"User-Agent": "TibiaAuctionTracker/1.0"}


def fetch_town_houses(town):
  town_encoded = urllib.parse.quote(town)
  url = f"https://api.tibiadata.com/v4/houses/{WORLD}/{town_encoded}"
  try:
    resp = requests.get(url, headers=HEADERS, timeout=6)
    if resp.status_code == 200:
      data = resp.json().get("houses", {})
      return (data.get("house_list") or []) + (
          data.get("guildhall_list") or []
      )
  except Exception:
    pass
  return []


def check_single_house(h, town, now_str):
  house_id = h.get("house_id")
  house_name = str(h.get("name", "N/A")).strip().strip('"')

  if not house_id:
    return None

  try:
    detail_url = f"https://api.tibiadata.com/v4/house/{WORLD}/{house_id}"
    resp = requests.get(detail_url, headers=HEADERS, timeout=4)

    if resp.status_code == 200:
      house_data = resp.json().get("house", {})
      status_obj = house_data.get("status", {})
      auction_obj = (
          house_data.get("auction") or status_obj.get("auction") or {}
      )

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

      if player_nick and str(player_nick).strip() not in [
          "",
          "None",
          "null",
          "Brak ofert",
      ]:
        return {
            "Timestamp_UTC": now_str,
            "House Name": house_name,
            "Town": str(town).strip(),
            "Player Nick": str(player_nick).strip(),
            "Gold Amount": int(gold_bid),
        }
  except Exception:
    pass
  return None


def get_all_bids():
  bids = []
  now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

  houses_to_check = []
  for town in TOWNS:
    houses = fetch_town_houses(town)
    for h in houses:
      status = str(h.get("status", "")).lower()
      if status not in ["rented", "rented (transfer)", "rented (moving)"]:
        houses_to_check.append((h, town))

  if not houses_to_check:
    return []

  with ThreadPoolExecutor(max_workers=25) as executor:
    futures = [
        executor.submit(check_single_house, item[0], item[1], now_str)
        for item in houses_to_check
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

  df_combined["_dt"] = pd.to_datetime(
      df_combined["Timestamp_UTC"], errors="coerce"
  )
  cutoff_date = datetime.utcnow() - timedelta(days=DAYS_TO_KEEP)
  df_cleaned = df_combined[df_combined["_dt"] >= cutoff_date]

  df_cleaned = df_cleaned.sort_values(by="_dt", ascending=False)
  df_cleaned = df_cleaned[cols]

  df_cleaned.to_csv(CSV_FILE, index=False, encoding="utf-8-sig")


def main():
  now_utc = datetime.utcnow()

  # Tryb Snajpera aktywuje się wyłącznie między 07:55 a 08:01 UTC (09:55 - 10:01 czasu polskiego)
  is_sniper_window = (now_utc.hour == 7 and now_utc.minute >= 55) or (
      now_utc.hour == 8 and now_utc.minute == 0
  )

  last_known_state = get_last_known_state()

  if is_sniper_window:
    print("=== TRYB SNAJPERA: monitoring co 3s ===", flush=True)
    start_time = time.time()
    # Maksymalnie 6 minut działania, żeby skrypt nigdy nie wisiał w nieskończoność
    while time.time() - start_time < 360:
      current_utc = datetime.utcnow()
      if current_utc.hour >= 8 and current_utc.second > 10:
        print("Server Save zakończony. Zamykam snajpera.", flush=True)
        break

      records = get_all_bids()
      updates = []
      for r in records:
        key = (r["House Name"].lower(), r["Town"].lower())
        current_state = (r["Player Nick"], r["Gold Amount"])

        if key not in last_known_state or last_known_state[key] != current_state:
          last_known_state[key] = current_state
          updates.append(r)
          print(
              f"  [+] PRZEBICIE: {r['House Name']} ({r['Town']}) ->"
              f" {r['Player Nick']} ({r['Gold Amount']} gp)",
              flush=True,
          )

      if updates:
        update_and_cleanup_csv(updates)

      time.sleep(3)
  else:
    print("=== Standardowe szybkie sprawdzenie ===", flush=True)
    records = get_all_bids()
    updates = []
    for r in records:
      key = (r["House Name"].lower(), r["Town"].lower())
      current_state = (r["Player Nick"], r["Gold Amount"])

      if key not in last_known_state or last_known_state[key] != current_state:
        last_known_state[key] = current_state
        updates.append(r)
        print(
            f"  [+] NOWY WPIS: {r['House Name']} ({r['Town']}) ->"
            f" {r['Player Nick']} ({r['Gold Amount']} gp)",
            flush=True,
        )

    update_and_cleanup_csv(updates)

    if updates:
      print(f"Zapisano {len(updates)} pozycji.", flush=True)
    else:
      print("Brak nowych zmian. Baza posortowana i oczyszczona.", flush=True)


if __name__ == "__main__":
  main()
    town_encoded = urllib.parse.quote(town)
    url = f"https://api.tibiadata.com/v4/houses/{WORLD}/{town_encoded}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code == 200:
            data = resp.json().get("houses", {})
            return (data.get("house_list") or []) + (data.get("guildhall_list") or [])
    except Exception:
        pass
    return []


def check_single_house(h, town, now_str):
    house_id = h.get("house_id")
    house_name = str(h.get("name", "N/A")).strip().strip('"')

    if not house_id:
        return None

    try:
        detail_url = f"https://api.tibiadata.com/v4/house/{WORLD}/{house_id}"
        resp = requests.get(detail_url, headers=HEADERS, timeout=5)

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
                    "Gold Amount": int(gold_bid),
                }
    except Exception:
        pass
    return None


def get_all_bids():
    bids = []
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    houses_to_check = []
    for town in TOWNS:
        houses = fetch_town_houses(town)
        for h in houses:
            status = str(h.get("status", "")).lower()
            if status not in ["rented", "rented (transfer)", "rented (moving)"]:
                houses_to_check.append((h, town))

    if not houses_to_check:
        return []

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(check_single_house, item[0], item[1], now_str) for item in houses_to_check]
        for future in as_completed(futures):
            res = future.result()
            if res:
                bids.append(res)

    return bids


def get_last_known_state():
    """Czyta ostatni zarejestrowany stan każdego domku z pliku CSV."""
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
    """Zapisuje nowe rekordy, usuwa wpisy starsze niż 7 dni i sortuje od najnowszego na górze."""
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

    # Parsowanie daty i usuwanie wpisów starszych niż 7 dni
    df_combined["_dt"] = pd.to_datetime(df_combined["Timestamp_UTC"], errors="coerce")
    cutoff_date = datetime.utcnow() - timedelta(days=DAYS_TO_KEEP)
    df_cleaned = df_combined[df_combined["_dt"] >= cutoff_date]

    # Najnowsze wpisy na samej górze
    df_cleaned = df_cleaned.sort_values(by="_dt", ascending=False)
    df_cleaned = df_cleaned[cols]

    df_cleaned.to_csv(CSV_FILE, index=False, encoding="utf-8-sig")


def main():
    now_utc = datetime.utcnow()
    # Okno snajpera: 07:55 - 08:00 UTC (09:55 - 10:00 czasu polskiego)
    is_sniper_window = now_utc.hour == 7 and now_utc.minute >= 55

    last_known_state = get_last_known_state()

    if is_sniper_window:
        print("=== TRYB SNAJPERA: monitoring co 3s do 10:00:05 CEST ===", flush=True)
        while True:
            current_utc = datetime.utcnow()
            if current_utc.hour >= 8 and current_utc.second > 5:
                print("Koniec Server Save. Zamykam snajpera.", flush=True)
                break

            records = get_all_bids()
            updates = []
            for r in records:
                key = (r["House Name"].lower(), r["Town"].lower())
                current_state = (r["Player Nick"], r["Gold Amount"])

                if key not in last_known_state or last_known_state[key] != current_state:
                    last_known_state[key] = current_state
                    updates.append(r)
                    print(
                        f"  [+] NOWE PRZEBICIE: {r['House Name']} ({r['Town']}) -> {r['Player Nick']} ({r['Gold Amount']} gp)",
                        flush=True,
                    )

            if updates:
                update_and_cleanup_csv(updates)

            time.sleep(3)
    else:
        print("=== Standardowe sprawdzenie stanu licytacji ===", flush=True)
        records = get_all_bids()
        updates = []
        for r in records:
            key = (r["House Name"].lower(), r["Town"].lower())
            current_state = (r["Player Nick"], r["Gold Amount"])

            if key not in last_known_state or last_known_state[key] != current_state:
                last_known_state[key] = current_state
                updates.append(r)
                print(
                    f"  [+] RZECZYWISTA ZMIANA: {r['House Name']} ({r['Town']}) -> {r['Player Nick']} ({r['Gold Amount']} gp)",
                    flush=True,
                )

        update_and_cleanup_csv(updates)

        if updates:
            print(f"Zapisano {len(updates)} nowych ofert na górze pliku.", flush=True)
        else:
            print("Brak zmian w ofertach. Historia wyczyszczona i posortowana.", flush=True)


if __name__ == "__main__":
    main()
