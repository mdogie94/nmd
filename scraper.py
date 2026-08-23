import os
import urllib.parse
from datetime import datetime
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


def fetch_town_houses(town):
  town_encoded = urllib.parse.quote(town)
  url = f"https://api.tibiadata.com/v4/houses/{WORLD}/{town_encoded}"
  headers = {"User-Agent": "TibiaAuctionTracker/1.0"}

  try:
    resp = requests.get(url, headers=headers, timeout=20)
    if resp.status_code == 200:
      data = resp.json().get("houses", {})
      return (data.get("house_list") or []) + (
          data.get("guildhall_list") or []
      )
  except Exception:
    pass
  return []


def get_active_bids_only():
  active_bids = []
  now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

  print(f"--- Skanowanie aktywnych ofert na świecie: {WORLD} ---")

  for town in TOWNS:
    houses = fetch_town_houses(town)

    for h in houses:
      status = str(h.get("status", "")).lower()
      auction_info = h.get("auction") or {}
      auction_state = str(auction_info.get("state", "")).lower()
      is_auctioned = h.get("auctioned") is True or "auction" in status

      # Sprawdzamy TYLKO domki w trakcie licytacji
      if is_auctioned or "in progress" in auction_state:
        house_id = h.get("house_id")
        house_name = h.get("name", "N/A")

        player_nick = auction_info.get("current_bidder")
        gold_bid = auction_info.get("current_bid", 0)

        # Jeśli widok miasta nie ma jeszcze szczegółów licytacji, dopytujemy o ten konkretny domek
        if house_id and (not player_nick or gold_bid == 0):
          try:
            d_url = f"https://api.tibiadata.com/v4/house/{WORLD}/{house_id}"
            d_resp = requests.get(
                d_url,
                headers={"User-Agent": "TibiaAuctionTracker/1.0"},
                timeout=10,
            )
            if d_resp.status_code == 200:
              d_auction = (
                  d_resp.json().get("house", {}).get("auction", {}) or {}
              )
              player_nick = d_auction.get("current_bidder")
              gold_bid = d_auction.get("current_bid", 0)
          except Exception:
            pass

        # INTERESUJĄ NAS TYLKO AKTYWNE OFERTY (musi być nick licytującego i oferta > 0)
        if player_nick and int(gold_bid) > 0:
          print(
              f"  [LICYTACJA] {house_name} ({town}) -> Gracz: {player_nick} |"
              f" Oferta: {gold_bid} gp"
          )
          active_bids.append({
              "Timestamp_UTC": now_str,
              "House Name": house_name,
              "Town": town,
              "Player Nick": player_nick.strip(),
              "Gold Amount": int(gold_bid),
          })

  return active_bids


def main():
  records = get_active_bids_only()

  if records:
    df_new = pd.DataFrame(records)
    print(f"\n[+] Znaleziono {len(df_new)} aktywnych ofert z graczami.")

    if os.path.exists(CSV_FILE):
      df_new.to_csv(
          CSV_FILE, mode="a", header=False, index=False, encoding="utf-8-sig"
      )
    else:
      df_new.to_csv(
          CSV_FILE, mode="w", header=True, index=False, encoding="utf-8-sig"
      )
    print(f"[+] Dane zapisane do {CSV_FILE}.")
  else:
    print(
        "\n[i] Brak ofert w tej chwili (nikt aktualnie nie przelicytował"
        " żadnego domku)."
    )
    if not os.path.exists(CSV_FILE):
      cols = ["Timestamp_UTC", "House Name", "Town", "Player Nick", "Gold Amount"]
      pd.DataFrame(columns=cols).to_csv(
          CSV_FILE, index=False, encoding="utf-8-sig"
      )


if __name__ == "__main__":
  main()
