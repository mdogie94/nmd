import csv
from datetime import datetime, timedelta
import html
import os
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        " like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8"
    ),
}


def fetch_town_houses_list(town):
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


def extract_from_json(house_id):
  """Zapasowe pobranie z JSON w razie braku dopasowania w HTML."""
  try:
    url = f"https://api.tibiadata.com/v4/house/{WORLD}/{house_id}"
    resp = requests.get(url, headers=HEADERS, timeout=4)
    if resp.status_code == 200:
      data = resp.json()
      bidder = None
      gold = 0

      def find_fields(obj):
        nonlocal bidder, gold
        if isinstance(obj, dict):
          for k, v in obj.items():
            kl = k.lower()
            if any(
                x in kl
                for x in [
                    "bidder",
                    "current_bidder",
                    "highest_bidder",
                    "character",
                ]
            ):
              if (
                  v
                  and isinstance(v, str)
                  and v.strip().lower()
                  not in ["", "none", "null", "false", "brak ofert"]
              ):
                if not bidder:
                  bidder = v.strip()
            if any(
                x in kl for x in ["bid", "current_bid", "highest_bid", "gold"]
            ):
              if v is not None and not isinstance(v, (dict, list)):
                clean = re.sub(r"[^\d]", "", str(v))
                if clean:
                  val = int(clean)
                  if val > gold:
                    gold = val
            find_fields(v)
        elif isinstance(obj, list):
          for item in obj:
            find_fields(item)

      find_fields(data)
      return bidder, gold
  except Exception:
    pass
  return None, 0


def check_house(house_id, house_name, town, now_str):
  if not house_id:
    return None

  # Metoda 1: Bezpośrednio Tibia.com HTML
  url = f"https://www.tibia.com/community/?subtopic=houses&page=view&world={WORLD}&houseid={house_id}"
  try:
    resp = requests.get(url, headers=HEADERS, timeout=4)
    if resp.status_code == 200:
      text = html.unescape(resp.text)

      # Wyszukiwanie kwoty
      bids = re.findall(
          r"(?:highest bid|current bid|bid so far is|auctioned.*?is)\s*[:]?\s*<b>?([\d,.]+)\s*gold",
          text,
          re.IGNORECASE,
      )
      if not bids:
        bids = re.findall(
            r"([\d,.]+)\s+gold\s+(?:and has been submitted|has been submitted)",
            text,
            re.IGNORECASE,
        )

      # Wyszukiwanie gracza
      nicks = re.findall(
          r"submitted by\s+<a[^>]*>([^<]+)</a>", text, re.IGNORECASE
      )
      if not nicks:
        nicks = re.findall(
            r"submitted by\s+<b>([^<]+)</b>", text, re.IGNORECASE
        )
      if not nicks:
        nicks = re.findall(
            r"submitted by\s+([A-Z][a-zA-Z\s]{1,25})(?:\.|\s*and|\s*\(|<|$)",
            text,
            re.IGNORECASE,
        )

      if bids and nicks:
        gold_str = re.sub(r"[^\d]", "", bids[0])
        bidder = nicks[0].strip()
        if bidder and gold_str and int(gold_str) > 0:
          print(
              f"  [HTML HIT] {house_name} -> {bidder} ({gold_str} gp)",
              flush=True,
          )
          return {
              "Timestamp_UTC": now_str,
              "House Name": house_name,
              "Town": str(town).strip(),
              "Player Nick": bidder,
              "Gold Amount": int(gold_str),
          }
  except Exception:
    pass

  # Metoda 2: Fallback do JSON API
  bidder, gold = extract_from_json(house_id)
  if bidder and gold > 0:
    print(f"  [JSON HIT] {house_name} -> {bidder} ({gold} gp)", flush=True)
    return {
        "Timestamp_UTC": now_str,
        "House Name": house_name,
        "Town": str(town).strip(),
        "Player Nick": bidder,
        "Gold Amount": int(gold),
    }

  return None


def get_active_houses():
  candidates = []
  for town in TOWNS:
    houses = fetch_town_houses_list(town)
    for h in houses:
      status = str(h.get("status", "")).lower()
      auction_obj = h.get("auction")
      if (
          auction_obj is not None
          or "rented" not in status
          or "auction" in status
      ):
        h_id = h.get("house_id")
        h_name = str(h.get("name", "N/A")).strip().strip('"')
        if h_id:
          candidates.append((h_id, h_name, town))

  # Gwarancja monitoringu Alai Flats
  if not any("Alai Flats" in str(c[1]) for c in candidates):
    candidates.append((10204, "Alai Flats, Flat 25", "Thais"))

  return candidates


def scan_all_targets(houses_to_track, now_str):
  bids = []
  with ThreadPoolExecutor(max_workers=25) as executor:
    futures = [
        executor.submit(check_house, item[0], item[1], item[2], now_str)
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

  df_combined = df_combined.drop_duplicates(
      subset=["Timestamp_UTC", "House Name", "Town", "Gold Amount"]
  )
  df_combined["_dt"] = pd.to_datetime(
      df_combined["Timestamp_UTC"], errors="coerce"
  )
  cutoff = datetime.utcnow() - timedelta(days=DAYS_TO_KEEP)
  df_cleaned = df_combined[df_combined["_dt"] >= cutoff].copy()
  df_cleaned = df_cleaned.sort_values(by="_dt", ascending=False)
  df_cleaned = df_cleaned[cols]

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

  print(f"=== Skaner Aukcji: {now_str} UTC ===", flush=True)
  houses_to_track = get_active_houses()
  print(f"Śledzone domki ({len(houses_to_track)}):", flush=True)
  for h in houses_to_track:
    print(f" -> {h[1]} ({h[2]})", flush=True)

  if is_sniper_time(now_utc):
    print("=== TRYB TURBO-SNAJPER (09:55 - 10:02 EU) ===", flush=True)
    start_t = time.time()
    while time.time() - start_t < 420:
      curr = datetime.utcnow()
      if (curr.hour == 8 and curr.minute >= 2) or (
          curr.hour == 9 and curr.minute >= 2
      ):
        print("Server Save zakończony. Zamykam snajpera.", flush=True)
        break

      curr_str = curr.strftime("%Y-%m-%d %H:%M:%S")
      active_bids = scan_all_targets(houses_to_track, curr_str)
      new_to_save = []

      for b in active_bids:
        key = (b["House Name"].lower(), b["Town"].lower())
        curr_state = (b["Player Nick"], b["Gold Amount"])

        if key not in last_bids or last_bids[key] != curr_state:
          last_bids[key] = curr_state
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
    print("=== Standardowe sprawdzenie ===", flush=True)
    active_bids = scan_all_targets(houses_to_track, now_str)
    new_to_save = []

    for b in active_bids:
      key = (b["House Name"].lower(), b["Town"].lower())
      curr_state = (b["Player Nick"], b["Gold Amount"])

      if key not in last_bids or last_bids[key] != curr_state:
        last_bids[key] = curr_state
        new_to_save.append(b)
        print(
            f"  [+] NOWY WPIS: {b['House Name']} ({b['Town']}) ->"
            f" {b['Player Nick']} ({b['Gold Amount']} gp)",
            flush=True,
        )

    if new_to_save:
      append_and_clean_csv(new_to_save)
      print(
          f"Pomyślnie zapisano {len(new_to_save)} nowych rekordów do CSV.",
          flush=True,
      )
    else:
      print("Brak nowych zmian w licytacjach.", flush=True)


if __name__ == "__main__":
  main()
