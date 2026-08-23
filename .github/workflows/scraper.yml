name: Tibia House Scraper

on:
  schedule:
    - cron: '0 * * * *'
  workflow_dispatch:

jobs:
  scrape:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - name: Pobierz kod repozytorium
        uses: actions/checkout@v4

      - name: Konfiguracja Pythona
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Instalacja bibliotek
        run: |
          python -m pip install --upgrade pip
          pip install curl_cffi beautifulsoup4 pandas

      - name: Uruchomienie skryptu
        run: python scraper.py

      - name: Zapisanie pliku CSV w repozytorium
        run: |
          git config --global user.name "GitHub Actions Bot"
          git config --global user.email "actions@github.com"
          git add historia_licytacji.csv
          git commit -m "Aktualizacja licytacji: $(date)" || exit 0
          git push
