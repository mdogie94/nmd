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


def get_all_bids():
  bids = []
  now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
      )
  }

  print(
      f"--- Rozpoczynam pełne skanowanie licytacji dla świata: {WORLD} ---"
  )

  for town in TOWNS:
    town_encoded = urllib.parse.quote(town)
    url = f"https://api.tibiadata.com/v4/houses/{WORLD}/{town_encoded}"

    try:
      resp = requests.get(url, headers=headers, timeout=20)
      if resp.status_code != 200:
        continue

      data = resp.json()
      houses_obj = data.get("houses", {})
      house_list = (houses_obj.get("house_list") or []) + (
          houses_obj.get("guildhall_list") or []
      )

      for h in house_list:
        house_id = h.get("house_id")
        status = str(h.get("status", "")).lower()

        # Pomijamy tylko domki definitywnie wynajęte
        if status in ["rented", "rented (transfer)", "rented (moving)"]:
          continue

        if not house_id:
          continue

        # Odpytujemy o szczegóły domku
        detail_url = f"https://api.tibiadata.com/v4/house/{WORLD}/{house_id}"
        d_resp = requests.get(detail_url, headers=headers, timeout=15)

        if d_resp.status_code == 200:
          house_data = d_resp.json().get("house", {})
          status_detail = house_data.get("status", {})
          auction_data = (
              house_data.get("auction")
              or status_detail.get("auction")
              or {}
          )

          # Pobieramy nick i kwotę z różnych możliwych struktur API
          player_nick = (
              auction_data.get("current_bidder")
              or auction_data.get("bidder")
              or status_detail.get("current_bidder")
              or status_detail.get("highest_bidder")
          )

          gold_bid = (
              auction_data.get("current_bid")
              or auction_data.get("bid")
              or status_detail.get("current_bid")
              or status_detail.get("highest_bid")
              or 0
          )

          house_name = house_data.get("name") or h.get("name", "N/A")

          # Jeśli licytacja trwa i jest gracz składający ofertę
          if player_nick and str(player_nick).strip() not in [
              "",
              "None",
              "null",
              "Brak ofert",
          ]:
            print(
                f"  [+] ZNALEZIONO OFERTĘ: {house_name} ({town}) -> Gracz:"
                f" {player_nick} | {gold_bid} gp"
            )
            bids.append({
                "Timestamp_UTC": now_str,
                "House Name": house_name,
                "Town": town,
                "Player Nick": str(player_nick).strip(),
                "Gold Amount": int(gold_bid),
            })
    except Exception as e:
      print(f"[{town}] Błąd: {e}")

  return bids


def main():
  records = get_all_bids()

  if records:
    df_new = pd.DataFrame(records)
    print(f"\n==========================================")
    print(f"Sukces! Pobrano {len(df_new)} ofert licytacji.")
    print(f"==========================================")

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
        "\n[i] Skrypt zakończył działanie. W tym momencie żaden domek nie ma"
        " aktywnej oferty gracza."
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
