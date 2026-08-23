import os
import urllib.parse
from datetime import datetime
import pandas as pd
import requests

WORLD = "Antica"
CSV_FILE = "historia_licytacji.csv"

# Oficjalne miasta z domkami w Tibii
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


def fetch_houses_for_town(town):
  town_encoded = urllib.parse.quote(town)
  url = f"https://api.tibiadata.com/v4/houses/{WORLD}/{town_encoded}"
  headers = {"User-Agent": "TibiaAuctionTracker/1.0"}

  try:
    resp = requests.get(url, headers=headers, timeout=20)
    if resp.status_code != 200:
      print(f"[{town}] Błąd HTTP {resp.status_code}")
      return []

    data = resp.json()
    houses_obj = data.get("houses", {})
    house_list = (
        houses_obj.get("house_list", [])
        or houses_obj.get("guildhall_list", [])
        or []
    )
    return house_list
  except Exception as e:
    print(f"[{town}] Wyjątek połączenia: {e}")
    return []


def get_all_bids():
  bids = []
  now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

  print(
      f"--- Rozpoczynam skanowanie świata: {WORLD} ({len(TOWNS)} miast) ---"
  )

  for town in TOWNS:
    houses = fetch_houses_for_town(town)
    town_auction_count = 0

    for h in houses:
      status = str(h.get("status", "")).lower()
      auction_data = h.get("auction") or {}
      is_auctioned = (
          h.get("auctioned") is True
          or "auction" in status
          or bool(auction_data)
          or status not in ["rented", "rented (transfer)", "rented (moving)"]
      )

      # Jeśli domek jest na aukcji lub ma dane licytacji
      if is_auctioned and status != "rented":
        house_name = h.get("name", "Nieznany")
        house_id = h.get("house_id")

        # Próba wyciągnięcia bidu z listy
        gold_amount = (
            auction_data.get("current_bid")
            or h.get("rent")
            or auction_data.get("bid")
            or 0
        )
        player_nick = (
            auction_data.get("current_bidder")
            or auction_data.get("bidder")
            or "Brak ofert"
        )

        # Jeśli brak szczegółów licytacji, dopytaj o szczegóły konkretnego domku
        if (player_nick == "Brak ofert" or gold_amount == 0) and house_id:
          try:
            detail_url = (
                f"https://api.tibiadata.com/v4/house/{WORLD}/{house_id}"
            )
            d_resp = requests.get(
                detail_url,
                headers={"User-Agent": "TibiaAuctionTracker/1.0"},
                timeout=10,
            )
            if d_resp.status_code == 200:
              d_house = d_resp.json().get("house", {})
              d_auction = d_house.get("auction", {})
              if d_auction:
                gold_amount = d_auction.get("current_bid", gold_amount)
                player_nick = d_auction.get("current_bidder", player_nick)
          except Exception:
            pass

        bids.append({
            "Timestamp_UTC": now_str,
            "World": WORLD,
            "House Name": house_name,
            "Town": town,
            "Size (SQM)": h.get("size", "N/A"),
            "Rent (Gold)": h.get("rent", "N/A"),
            "Player Nick": player_nick,
            "Gold Amount": gold_amount,
        })
        town_auction_count += 1
        print(
            f"  [+] {house_name} ({town}) -> Nick: {player_nick} | Oferta:"
            f" {gold_amount} gp"
        )

    print(
        f"[{town}] Sprawdzono {len(houses)} domków, znaleziono licytowanych:"
        f" {town_auction_count}"
    )

  return bids


def main():
  records = get_all_bids()

  if records:
    df_new = pd.DataFrame(records)
    print(f"\n==========================================")
    print(f"Sukces! Znaleziono łącznie {len(df_new)} licytacji.")
    print(f"==========================================")

    if os.path.exists(CSV_FILE):
      df_new.to_csv(
          CSV_FILE, mode="a", header=False, index=False, encoding="utf-8-sig"
      )
    else:
      df_new.to_csv(
          CSV_FILE, mode="w", header=True, index=False, encoding="utf-8-sig"
      )
    print(f"Pomyślnie dopisano dane do {CSV_FILE}.")
  else:
    print(
        "\n[!] W tym momencie żaden domek we wszystkich miastach nie jest na"
        " licytacji."
    )
    if not os.path.exists(CSV_FILE):
      cols = [
          "Timestamp_UTC",
          "World",
          "House Name",
          "Town",
          "Size (SQM)",
          "Rent (Gold)",
          "Player Nick",
          "Gold Amount",
      ]
      pd.DataFrame(columns=cols).to_csv(
          CSV_FILE, index=False, encoding="utf-8-sig"
      )


if __name__ == "__main__":
  main()
