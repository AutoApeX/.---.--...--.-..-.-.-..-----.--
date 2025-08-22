

import pandas as pd
import numpy as np
import requests
import os
from datetime import datetime, timedelta

class TrendPulse:
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

    def analyze(self, closes):
        if len(closes) < 25:
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

        buy = bool(crossed.iloc[-1] and up.iloc[-1] and oversold.iloc[-1])
        sell = bool(crossed.iloc[-1] and dn.iloc[-1] and overbought.iloc[-1])
        return buy, sell

def fetch_markets():
    """Fixed version - solves 400 error"""
    api_key = os.environ.get('COINGECKO_API_KEY', '')
    
    # Use pro API domain if you have API key
    if api_key:
        base_url = "https://pro-api.coingecko.com/api/v3"
        headers = {'x-cg-pro-api-key': api_key}
    else:
        base_url = "https://api.coingecko.com/api/v3" 
        headers = {}
    
    url = f"{base_url}/coins/markets"
    params = {
        'vs_currency': 'usd',
        'order': 'market_cap_desc',
        'per_page': 100,
        'page': 1,
        'sparkline': 'true'
    }
    
    r = requests.get(url, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()

def resample_to_30m(sparkline_prices):
    """Convert hourly prices to 30m intervals"""
    if not sparkline_prices or len(sparkline_prices) < 48:
        return pd.Series([])
    
    # Take last 168 hours (7 days)
    prices = sparkline_prices[-168:]
    
    # Create 30-minute intervals by interpolating
    extended_prices = []
    for i in range(len(prices)-1):
        extended_prices.append(prices[i])
        # Add interpolated midpoint for 30m interval
        midpoint = (prices[i] + prices[i+1]) / 2
        extended_prices.append(midpoint)
    extended_prices.append(prices[-1])
    
    return pd.Series(extended_prices[-100:])  # Last 100 30m intervals

def send_telegram(coin, action):
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat:
        return
    
    emoji = '🟢' if action=='buy' else '🔴'
    text = (f"{emoji} *TrendPulse Alert* {emoji}\n"
            f"{coin['symbol'].upper()} — *{action.upper()}*\n"
            f"⏰ 30m Analysis\n"
            f"📊 Cap: ${coin['market_cap']:,}\n"
            f"📈 Vol: ${coin['total_volume']:,}\n"
            f"🕐 {datetime.utcnow().strftime('%H:%M UTC')}")
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={'chat_id':chat,'text':text,'parse_mode':'Markdown'}, timeout=5)

def main():
    print("🕐 30-Minute TrendPulse Scanner Starting...")
    
    tp = TrendPulse()
    data = fetch_markets()
    
    signals = 0
    processed = 0
    
    for coin in data:
        if coin['market_cap'] < 50_000_000 or coin['total_volume'] < 30_000_000:
            continue
        
        sparkline = coin.get('sparkline_in_7d', {}).get('price', [])
        if not sparkline:
            continue
            
        prices_30m = resample_to_30m(sparkline)
        if len(prices_30m) < 25:
            continue
            
        processed += 1
        buy, sell = tp.analyze(prices_30m)
        
        if buy:
            send_telegram(coin, 'buy')
            signals += 1
            print(f"🟢 BUY: {coin['symbol'].upper()}")
        elif sell:
            send_telegram(coin, 'sell')
            signals += 1
            print(f"🔴 SELL: {coin['symbol'].upper()}")
    
    print(f"✅ Processed {processed} coins, {signals} signals")

if __name__ == "__main__":
    main()
