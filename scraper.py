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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def fetch_town_houses(town):
  town_encoded = urllib.parse.quote(town)
  url = f"https://api.tibiadata.com/v4/houses/{WORLD}/{town_encoded}"
  try:
    resp = requests.get(url, headers=HEADERS, timeout=8)
    if resp.status_code == 200:
      data = resp.json().get("houses", {})
      h_list = data.get("house_list") or []
      g_list = data.get("guildhall_list") or []
      return h_list + g_list
  except Exception as e:
    print(f"Błąd miasta {town}: {e}", flush=True)
  return []


def parse_auction_json(data):
  """Wyczerpujące wyszukiwanie gracza i kwoty w JSON z TibiaData."""
  bidder = None
  bid = 0

  house = data.get("house", {})
  status_obj = house.get("status", {})
  auction_obj = (
      house.get("auction")
      or status_obj.get("auction")
      or data.get("auction")
      or {}
  )

  # Sprawdzanie nicku gracza
  candidates_nick = [
      auction_obj.get("current_bidder"),
      auction_obj.get("highest_bidder"),
      auction_obj.get("bidder"),
      status_obj.get("current_bidder"),
      status_obj.get("highest_bidder"),
      status_obj.get("bidder"),
      house.get("highest_bidder"),
      house.get("bidder"),
  ]
  for c in candidates_nick:
    if c and str(c).strip().lower() not in [
        "",
        "none",
        "null",
        "false",
        "brak ofert",
        "no bidder",
    ]:
      bidder = str(c).strip()
      break

  # Sprawdzanie kwoty złota
  candidates_gold = [
      auction_obj.get("current_bid"),
      auction_obj.get("highest_bid"),
      auction_obj.get("bid"),
      status_obj.get("current_bid"),
      status_obj.get("highest_bid"),
      status_obj.get("bid"),
      house.get("highest_bid"),
      house.get("bid"),
  ]
  for g in candidates_gold:
    if g is not None:
      clean_num = re.sub(r"[^\d]", "", str(g))
      if clean_num:
        val = int(clean_num)
        if val > bid:
          bid = val

  return bidder, bid


def check_single_house(house_id, house_name, town, now_str):
  if not house_id:
    return None

  try:
    detail_url = f"https://api.tibiadata.com/v4/house/{WORLD}/{house_id}"
    resp = requests.get(detail_url, headers=HEADERS, timeout=6)

    if resp.status_code == 200:
      data = resp.json()
      bidder, gold_bid = parse_auction_json(data)

      if bidder and gold_bid > 0:
        print(
            f"  [+] Znaleziono: {house_name} ({town}) -> {bidder} ({gold_bid}"
            " gp)",
            flush=True,
        )
        return {
            "Timestamp_UTC": now_str,
            "House Name": house_name,
            "Town": str(town).strip(),
            "Player Nick": bidder,
            "Gold Amount": gold_bid,
        }
  except Exception as e:
    print(f"Błąd domku {house_id}: {e}", flush=True)
  return None


def get_all_active_auctions(now_str):
  houses_to_check = []
  for town in TOWNS:
    houses = fetch_town_houses(town)
    for h in houses:
      status = str(h.get("status", "")).lower()
      # Sprawdzamy każdy domek, który nie jest w 100% wynajęty bez licytacji
      if "rented" not in status or "auction" in status:
        h_id = h.get("house_id")
        h_name = str(h.get("name", "N/A")).strip().strip('"')
        if h_id:
          houses_to_check.append((h_id, h_name, town))

  print(
      f"Liczba domków do sprawdzenia w API: {len(houses_to_check)}", flush=True
  )

  bids = []
  with ThreadPoolExecutor(max_workers=20) as executor:
    futures = [
        executor.submit(check_single_house, item[0], item[1], item[2], now_str)
        for item in houses_to_check
    ]
    for future in as_completed(futures):
      res = future.result()
      if res:
        bids.append(res)
  return bids


def get_last_known_bids():
  """Zwraca słownik: klucz (nazwa_domku, miasto) -> (gracz, kwota) dla OSTATNIEGO wpisu."""
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
      # Zapamiętujemy stan
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

  df_combined["_dt"] = pd.to_datetime(
      df_combined["Timestamp_UTC"], errors="coerce"
  )
  cutoff = datetime.utcnow() - timedelta(days=DAYS_TO_KEEP)
  df_cleaned = df_combined[df_combined["_dt"] >= cutoff].copy()

  df_cleaned = df_cleaned.sort_values(by="_dt", ascending=False)
  df_cleaned = df_cleaned[cols]

  # Bezpieczny zapis z cudzysłowami
  df_cleaned.to_csv(
      CSV_FILE, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL
  )


def is_sniper_time(now_utc):
  summer = (now_utc.hour == 7 and now_utc.minute >= 55) or (
      now_utc.hour == 8 and now_utc.minute <= 2
  )
  winter = (now_utc.hour == 8 and now_utc.minute >= 55) or (
      now_utc.hour == 9 and now_utc.minute <= 2
  )
  return summer or winter


def main():
  now_utc = datetime.utcnow()
  now_str = now_utc.strftime("%Y-%m-%d %H:%M:%S")
  last_bids = get_last_known_bids()

  print(f"--- Skanowanie licytacji: {now_str} UTC ---", flush=True)

  if is_sniper_time(now_utc):
    print("=== TRYB TURBO-SNAJPER (09:55 - 10:02 EU) ===", flush=True)
    start_t = time.time()
    while time.time() - start_t < 420:
      curr = datetime.utcnow()
      if (curr.hour == 8 and curr.minute >= 2) or (
          curr.hour == 9 and curr.minute >= 2
      ):
        print("Koniec Server Save. Zamykam snajpera.", flush=True)
        break

      curr_str = curr.strftime("%Y-%m-%d %H:%M:%S")
      active_bids = get_all_active_auctions(curr_str)
      new_to_save = []

      for b in active_bids:
        key = (b["House Name"].lower(), b["Town"].lower())
        current_tuple = (b["Player Nick"], b["Gold Amount"])

        if key not in last_bids or last_bids[key] != current_tuple:
          last_bids[key] = current_tuple
          new_to_save.append(b)
          print(
              f"[{b['Timestamp_UTC']}] PRZEBICIE: {b['House Name']} ->"
              f" {b['Player Nick']} ({b['Gold Amount']} gp)",
              flush=True,
          )

      if new_to_save:
        append_and_clean_csv(new_to_save)

      is_critical = (curr.hour in [7, 8] and curr.minute == 59) or (
          curr.hour in [8, 9] and curr.minute == 0
      )
      time.sleep(1 if is_critical else 2)
  else:
    print("=== Sprawdzenie okresowe ===", flush=True)
    active_bids = get_all_active_auctions(now_str)
    new_to_save = []

    for b in active_bids:
      key = (b["House Name"].lower(), b["Town"].lower())
      current_tuple = (b["Player Nick"], b["Gold Amount"])

      if key not in last_bids or last_bids[key] != current_tuple:
        last_bids[key] = current_tuple
        new_to_save.append(b)
        print(
            f"  [+] NOWA ZMIANA: {b['House Name']} ({b['Town']}) ->"
            f" {b['Player Nick']} ({b['Gold Amount']} gp)",
            flush=True,
        )

    append_and_clean_csv(new_to_save)
    if new_to_save:
      print(f"Pomyślnie dopisano {len(new_to_save)} nowych ofert.", flush=True)
    else:
      print("Brak nowych zmian w licytacjach.", flush=True)


if __name__ == "__main__":
  main()
