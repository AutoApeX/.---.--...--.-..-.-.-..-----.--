
import pandas as pd
import numpy as np
import requests
import os
from datetime import datetime
import time

class TrendPulse:
    """TrendPulse: Proprietary hourly analysis on close prices"""
    def __init__(self):
        self.ch_len = 9
        self.avg_len = 12
        self.smooth_len = 3

    def ema(self, src, length):
        return src.ewm(span=length, adjust=False).mean()

    def sma(self, src, length):
        return src.rolling(window=length).mean()

    def cross(self, s1, s2):
        p = s1.shift(1) - s2.shift(1)
        c = s1 - s2
        return ((p < 0) & (c > 0)) | ((p > 0) & (c < 0))

    def analyze(self, closes: pd.Series):
        """Generate buy/sell signals from hourly closes only"""
        if len(closes) < self.ch_len + self.avg_len:
            return False, False

        esa = self.ema(closes, self.ch_len)
        dev = self.ema(abs(closes - esa), self.ch_len)
        ci = (closes - esa) / (0.015 * dev)

        wt1 = self.ema(ci, self.avg_len)
        wt2 = self.sma(wt1, self.smooth_len)

        oversold = (wt1 <= -60) & (wt2 <= -60)
        overbought = (wt2 >= 60) & (wt1 >= 60)
        crossed = self.cross(wt1, wt2)
        up = wt1 > wt2
        dn = wt1 < wt2

        idx = -1
        buy = bool(crossed.iloc[idx] and up.iloc[idx] and oversold.iloc[idx])
        sell = bool(crossed.iloc[idx] and dn.iloc[idx] and overbought.iloc[idx])
        return buy, sell

def fetch_markets(limit=100):
    """Fetch top coins with 7d hourly sparkline"""
    api_key = os.environ.get('COINGECKO_API_KEY', '')
    headers = {'X-CG-Pro-API-Key': api_key} if api_key else {}
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        'vs_currency': 'usd',
        'order': 'market_cap_desc',
        'per_page': limit,
        'page': 1,
        'sparkline': 'true'
    }
    r = requests.get(url, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()

def send_telegram(coin, action):
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat:
        return
    emoji = '🟢' if action=='buy' else '🔴'
    text = (f"{emoji} *TrendPulse Alert* {emoji}\n"
            f"{coin['symbol']} — *{action.upper()}*\n"
            f"Cap: ${coin['market_cap']:,}\n"
            f"Vol24h: ${coin['total_volume']:,}\n"
            f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={'chat_id':chat,'text':text,'parse_mode':'Markdown'},timeout=5)

def main():
    tp = TrendPulse()
    data = fetch_markets(limit=100)
    for c in data:
        if c['market_cap'] < 50_000_000 or c['total_volume'] < 30_000_000:
            continue
        closes = pd.Series(c['sparkline_in_7d']['price'])
        buy, sell = tp.analyze(closes)
        if buy: send_telegram(c, 'buy')
        if sell: send_telegram(c, 'sell')
    # Completion notice
    send_telegram({'symbol':'🔔','market_cap':0,'total_volume':0},'scan complete')

if __name__ == "__main__":
    main()
