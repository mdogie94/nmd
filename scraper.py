from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import json
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

HEADERS = {
    "User-Agent": "TibiaAuctionTracker/2.0",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def fetch_town_houses(town):
  town_encoded = urllib.parse.quote(town)
  url = f"https://api.tibiadata.com/v4/houses/{WORLD}/{town_encoded}?_t={int(time.time())}"
  try:
    resp = requests.get(url, headers=HEADERS, timeout=8)
    if resp.status_code == 200:
      data = resp.json().get("houses", {})
      return (data.get("house_list") or []) + (
          data.get("guildhall_list") or []
      )
  except Exception:
    pass
  return []


def parse_auction_data(data):
  """Pancerne wyciąganie danych o licytacji z każdego możliwego miejsca w JSON."""
  house = data.get("house", {})

  # Szukamy obiektu auction
  auction = house.get("auction") or house.get("status", {}).get("auction") or {}

  bidder = (
      auction.get("current_bidder")
      or auction.get("highest_bidder")
      or auction.get("bidder")
      or auction.get("character")
      or house.get("status", {}).get("current_bidder")
      or house.get("status", {}).get("highest_bidder")
  )

  bid = (
      auction.get("current_bid")
      or auction.get("highest_bid")
      or auction.get("bid")
      or house.get("status", {}).get("current_bid")
      or house.get("status", {}).get("highest_bid")
      or 0
  )

  # Czyszczenie wartości
  if bidder:
    bidder = str(bidder).strip()
    if bidder.lower() in ["", "none", "null", "brak ofert", "false"]:
      bidder = None

  try:
    bid = int(str(bid).replace(",", "").replace(".", "").strip())
  except Exception:
    bid = 0

  return bidder, bid


def check_single_house(house_id, house_name, town, now_str):
  if not house_id:
    return None

  try:
    detail_url = f"https://api.tibiadata.com/v4/house/{WORLD}/{house_id}?_t={int(time.time() * 1000)}"
    resp = requests.get(detail_url, headers=HEADERS, timeout=4)

    if resp.status_code == 200:
      data = resp.json()
      bidder, gold_bid = parse_auction_data(data)

      if bidder and gold_bid > 0:
        return {
            "Timestamp_UTC": now_str,
            "House Name": house_name,
            "Town": str(town).strip(),
            "Player Nick": bidder,
            "Gold Amount": gold_bid,
        }
  except Exception:
    pass
  return None


def build_hotlist():
  hotlist = []
  for town in TOWNS:
    houses = fetch_town_houses(town)
    for h in houses:
      status = str(h.get("status", "")).lower()
      # Sprawdzamy wszystko poza w 100% bezpiecznie wynajętymi bez licytacji
      if "rented" not in status or "auction" in status:
        h_id = h.get("house_id")
        h_name = str(h.get("name", "N/A")).strip().strip('"')
        if h_id:
          hotlist.append({"id": h_id, "name": h_name, "town": town})
  return hotlist


def scan_hotlist(hotlist, now_str):
  bids = []
  with ThreadPoolExecutor(max_workers=30) as executor:
    futures = [
        executor.submit(
            check_single_house,
            item["id"],
            item["name"],
            item["town"],
            now_str,
        )
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

  df_combined["_dt"] = pd.to_datetime(
      df_combined["Timestamp_UTC"], errors="coerce"
  )
  cutoff_date = datetime.utcnow() - timedelta(days=DAYS_TO_KEEP)
  df_cleaned = df_combined[df_combined["_dt"] >= cutoff_date]

  # Usuwanie ewentualnych duplikatów
  df_cleaned = df_cleaned.drop_duplicates(
      subset=["House Name", "Town", "Player Nick", "Gold Amount"]
  )

  df_cleaned = df_cleaned.sort_values(by="_dt", ascending=False)
  df_cleaned = df_cleaned[cols]

  df_cleaned.to_csv(CSV_FILE, index=False, encoding="utf-8-sig")


def is_sniper_active(now_utc):
  in_summer = (now_utc.hour == 7 and now_utc.minute >= 55) or (
      now_utc.hour == 8 and now_utc.minute <= 2
  )
  in_winter = (now_utc.hour == 8 and now_utc.minute >= 55) or (
      now_utc.hour == 9 and now_utc.minute <= 2
  )
  return in_summer or in_winter


def main():
  now_utc = datetime.utcnow()
  last_known_state = get_last_known_state()

  if is_sniper_active(now_utc):
    print("=== TRYB TURBO-SNAJPERA: Okno 09:55 - 10:02 EU ===", flush=True)
    hotlist = build_hotlist()
    print(f"Obserwowane domki ({len(hotlist)}):", flush=True)
    for item in hotlist:
      print(f" -> {item['name']} ({item['town']})", flush=True)

    start_time = time.time()
    while time.time() - start_time < 420:
      current_utc = datetime.utcnow()
      if (current_utc.hour == 8 and current_utc.minute >= 2) or (
          current_utc.hour == 9 and current_utc.minute >= 2
      ):
        print("Koniec Server Save. Zamykam snajpera.", flush=True)
        break

      now_str = current_utc.strftime("%Y-%m-%d %H:%M:%S")
      records = scan_hotlist(hotlist, now_str)
      updates = []

      for r in records:
        key = (r["House Name"].lower(), r["Town"].lower())
        current_state = (r["Player Nick"], r["Gold Amount"])

        if key not in last_known_state or last_known_state[key] != current_state:
          last_known_state[key] = current_state
          updates.append(r)
          print(
              f"[{r['Timestamp_UTC']}] PRZEBICIE: {r['House Name']} ->"
              f" {r['Player Nick']} ({r['Gold Amount']} gp)",
              flush=True,
          )

      if updates:
        update_and_cleanup_csv(updates)

      is_critical = (
          current_utc.hour in [7, 8] and current_utc.minute == 59
      ) or (current_utc.hour in [8, 9] and current_utc.minute == 0)
      time.sleep(1 if is_critical else 2)

  else:
    print("=== Sprawdzenie okresowe (co 15 minut) ===", flush=True)
    hotlist = build_hotlist()
    records = scan_hotlist(hotlist, now_utc.strftime("%Y-%m-%d %H:%M:%S"))
    updates = []

    for r in records:
      key = (r["House Name"].lower(), r["Town"].lower())
      current_state = (r["Player Nick"], r["Gold Amount"])

      if key not in last_known_state or last_known_state[key] != current_state:
        last_known_state[key] = current_state
        updates.append(r)
        print(
            f"  [+] AKTUALIZACJA: {r['House Name']} ({r['Town']}) ->"
            f" {r['Player Nick']} ({r['Gold Amount']} gp)",
            flush=True,
        )

    update_and_cleanup_csv(updates)
    if updates:
      print(f"Zapisano {len(updates)} nowych rekordów.", flush=True)
    else:
      print("Brak nowych zmian w licytacjach.", flush=True)


if __name__ == "__main__":
  main()
