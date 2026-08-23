from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import os
import urllib.parse
import pandas as pd
import requests

WORLD = "Antica"
CSV_FILE = "historia_licytacji.csv"

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
    resp = requests.get(url, headers=HEADERS, timeout=10)
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
  house_name = h.get("name", "N/A")

  if not house_id:
    return None

  try:
    detail_url = f"https://api.tibiadata.com/v4/house/{WORLD}/{house_id}"
    resp = requests.get(detail_url, headers=HEADERS, timeout=6)

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
        print(
            f"  [+] Trafiono: {house_name} ({town}) | Gracz: {player_nick} |"
            f" {gold_bid} gp",
            flush=True,
        )
        return {
            "Timestamp_UTC": now_str,
            "House Name": house_name,
            "Town": town,
            "Player Nick": str(player_nick).strip(),
            "Gold Amount": int(gold_bid),
        }
  except Exception:
    pass
  return None


def get_all_bids():
  bids = []
  now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

  print(
      f"--- Szybkie skanowanie licytacji dla świata: {WORLD} ---", flush=True
  )

  # Krok 1: Pobieramy listę domków ze wszystkich miast
  houses_to_check = []
  for town in TOWNS:
    houses = fetch_town_houses(town)
    for h in houses:
      status = str(h.get("status", "")).lower()
      # Sprawdzamy tylko te, które nie są wynajęte
      if status not in ["rented", "rented (transfer)", "rented (moving)"]:
        houses_to_check.append((h, town))

  print(
      f"Znaleziono {len(houses_to_check)} potencjalnych domków. Sprawdzam"
      " równolegle...",
      flush=True,
  )

  # Krok 2: Sprawdzamy wszystkie domki równolegle w 20 wątkach
  with ThreadPoolExecutor(max_workers=20) as executor:
    futures = [
        executor.submit(check_single_house, item[0], item[1], now_str)
        for item in houses_to_check
    ]
    for future in as_completed(futures):
      res = future.result()
      if res:
        bids.append(res)

  return bids


def main():
  records = get_all_bids()

  if records:
    df_new = pd.DataFrame(records)
    print(
        f"\n[+] Sukces! Znaleziono {len(df_new)} ofert z graczami.", flush=True
    )

    if os.path.exists(CSV_FILE):
      df_new.to_csv(
          CSV_FILE, mode="a", header=False, index=False, encoding="utf-8-sig"
      )
    else:
      df_new.to_csv(
          CSV_FILE, mode="w", header=True, index=False, encoding="utf-8-sig"
      )
    print(f"[+] Zaktualizowano plik {CSV_FILE}.", flush=True)
  else:
    print(
        "\n[i] W tym momencie nikt nie złożył nowej oferty na licytowane"
        " domki.",
        flush=True,
    )
    if not os.path.exists(CSV_FILE):
      cols = [
          "Timestamp_UTC",
          "House Name",
          "Town",
          "Player Nick",
          "Gold Amount",
      ]
      pd.DataFrame(columns=cols).to_csv(
          CSV_FILE, index=False, encoding="utf-8-sig"
      )


if __name__ == "__main__":
  main()
