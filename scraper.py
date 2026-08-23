import os
import re
from datetime import datetime
from bs4 import BeautifulSoup
import pandas as pd
import requests

URL = "https://tibiavip.app/houses?status=auctioned&type=&world=Antica&auction=&town="
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
CSV_FILE = "historia_licytacji.csv"


def parse_bid_status(status_text: str, link_tag=None):
  clean_text = " ".join(status_text.split())
  gold_match = re.search(r"([\d\s,\.]+)\s*gold", clean_text, re.IGNORECASE)
  gold_amount = (
      re.sub(r"[^\d]", "", gold_match.group(1)) if gold_match else "0"
  )

  player_nick = "Brak ofert"
  if link_tag and link_tag.get_text(strip=True):
    player_nick = link_tag.get_text(strip=True)
  else:
    nick_match = re.search(
        r"by\s+([A-Za-z0-9'\-\s]+?)(?:\)|$|,)", clean_text, re.IGNORECASE
    )
    if nick_match:
      player_nick = nick_match.group(1).strip()

  return player_nick, gold_amount


def main():
  resp = requests.get(URL, headers=HEADERS, timeout=15)
  resp.raise_for_status()
  soup = BeautifulSoup(resp.text, "html.parser")
  table = soup.find("table")
  if not table:
    print("Nie znaleziono tabeli.")
    return

  now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
  new_records = []

  for row in table.find_all("tr")[1:]:
    cols = row.find_all("td")
    if len(cols) >= 3:
      house_name = cols[0].get_text(strip=True)
      town = cols[1].get_text(strip=True)
      bid_col = cols[-1]
      nick, gold = parse_bid_status(
          bid_col.get_text(strip=True), bid_col.find("a")
      )

      new_records.append({
          "Timestamp_UTC": now_str,
          "House Name": house_name,
          "Town": town,
          "Player Nick": nick,
          "Gold Amount": gold,
      })

  if not new_records:
    print("Brak rekordów do zapisania.")
    return

  df_new = pd.DataFrame(new_records)

  if os.path.exists(CSV_FILE):
    df_new.to_csv(CSV_FILE, mode="a", header=False, index=False)
  else:
    df_new.to_csv(CSV_FILE, mode="w", header=True, index=False)

  print(f"Zapisano {len(df_new)} wierszy.")


if __name__ == "__main__":
  main()
