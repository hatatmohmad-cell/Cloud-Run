name: Run GCP V2Ray Telegram Bot

on:
  workflow_dispatch:
  push:
    branches: [ main, master ]
  schedule:
    - cron: '0 */5 * * *'

jobs:
  run-bot:
    runs-on: ubuntu-latest
    timeout-minutes: 350
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies and Playwright Chromium
        run: |
          pip install --upgrade pip
          pip install -r requirements.txt
          playwright install --with-deps chromium

      - name: Run Telegram Bot
        env:
          BOT_TOKEN: ${{ secrets.BOT_TOKEN }}
        run: |
          python3 bot.py
