import os
import re
from datetime import datetime
from bs4 import BeautifulSoup
import pandas as pd
import requests

WORLD = "Antica"
CSV_FILE = "historia_licytacji.csv"

# Wszystkie oficjalne miasta w Tibii
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


def parse_auction_cell(cell_text):
  """Wyciąga nick gracza i kwotę gold z komórki statusu na tibia.com.

  Przykład tekstu: 'auctioned (1000 gold; by Player Name)'
  """
  clean = " ".join(cell_text.split())

  # Szukamy kwoty gold
  gold_match = re.search(r"([\d\s,\.]+)\s*gold", clean, re.IGNORECASE)
  gold_amount = 0
  if gold_match:
    gold_str = re.sub(r"[^\d]", "", gold_match.group(1))
    gold_amount = int(gold_str) if gold_str else 0

  # Szukamy nicku gracza po słowie 'by'
  player_nick = None
  nick_match = re.search(
      r"by\s+([A-Za-z0-9'\-\s]+?)(?:\)|$|,)", clean, re.IGNORECASE
  )
  if nick_match:
    player_nick = nick_match.group(1).strip()

  return player_nick, gold_amount


def scrape_tibia_com():
  bids = []
  now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/120.0.0.0 Safari/537.36"
      )
  }

  print(f"--- Sprawdzanie licytacji na Tibia.com dla świata: {WORLD} ---")

  for town in TOWNS:
    # Pobieramy TYLKO domki na licytacji (order=auctioned)
    url = f"https://www.tibia.com/community/?subtopic=houses&world={WORLD}&town={town}&order=auctioned"

    try:
      resp = requests.get(url, headers=headers, timeout=20)
      if resp.status_code != 200:
        continue

      soup = BeautifulSoup(resp.text, "html.parser")
      table = soup.find("table", class_="TableContent")

      if not table:
        continue

      for row in table.find_all("tr"):
        cols = row.find_all("td")
        # Standardowy wiersz z domkiem ma 4 kolumny: Nazwa, Rozmiar, Czynsz, Status
        if len(cols) >= 4:
          house_name = cols[0].get_text(strip=True)
          status_text = cols[3].get_text(strip=True)

          # Filtrujemy tylko wiersze, które zawierają faktyczną licytację i ofertę ('by ...')
          if "auction" in status_text.lower() and "by" in status_text.lower():
            player_nick, gold_amount = parse_auction_cell(status_text)

            # Zapisujemy TYLKO jeśli jest licytujący i oferta > 0
            if player_nick and gold_amount > 0:
              print(
                  f"  [+] {house_name} ({town}) -> Gracz: {player_nick} |"
                  f" Oferta: {gold_amount} gp"
              )
              bids.append({
                  "Timestamp_UTC": now_str,
                  "House Name": house_name,
                  "Town": town,
                  "Player Nick": player_nick,
                  "Gold Amount": gold_amount,
              })
    except Exception as e:
      print(f"Błąd przy pobieraniu {town}: {e}")

  return bids


def main():
  records = scrape_tibia_com()

  if records:
    df_new = pd.DataFrame(records)
    print(f"\n[+] Pobrano {len(df_new)} aktywnych licytacji z ofertami.")

    if os.path.exists(CSV_FILE):
      df_new.to_csv(
          CSV_FILE, mode="a", header=False, index=False, encoding="utf-8-sig"
      )
    else:
      df_new.to_csv(
          CSV_FILE, mode="w", header=True, index=False, encoding="utf-8-sig"
      )
    print(f"[+] Zapisano w {CSV_FILE}.")
  else:
    print(
        "\n[i] W tym momencie nikt nie złożył żadnej oferty na licytowane"
        " domki."
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
