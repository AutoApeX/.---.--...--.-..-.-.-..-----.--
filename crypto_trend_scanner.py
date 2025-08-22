

import pandas as pd
import numpy as np
import requests
import yfinance as yf
import os
from datetime import datetime
import time

class TrendPulse:
    """TrendPulse: 30-minute candle analysis"""
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
        """Generate buy/sell signals from 30-minute closes"""
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

        buy = bool(crossed.iloc[-1] and up.iloc[-1] and oversold.iloc[-1])
        sell = bool(crossed.iloc[-1] and dn.iloc[-1] and overbought.iloc[-1])
        return buy, sell

def fetch_gecko_coins(min_cap=50_000_000, min_vol=30_000_000, limit=250):
    """Fetch and filter coins by Market Cap and 24h Volume from CoinGecko"""
    api_key = os.environ.get('COINGECKO_API_KEY', '')
    url = "https://api.coingecko.com/api/v3/coins/markets"
    headers = {}
    if api_key:
        headers = {'x-cg-demo-api-key': api_key}
    params = {
        'vs_currency': 'usd',
        'order': 'market_cap_desc',
        'per_page': limit,
        'page': 1,
    }
    try:
        r = requests.get(url, params=params, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"❌ CoinGecko error: {e}")
        return []

    filtered = []
    stablecoins = {'USDT','USDC','DAI','BUSD','USDE','FDUSD'}
    for coin in data:
        if (coin.get('market_cap',0) >= min_cap and
            coin.get('total_volume',0) >= min_vol and
            coin['symbol'].upper() not in stablecoins):
            symbol = coin['symbol'].upper() + "-USD"
            filtered.append({
                'id': coin['id'],
                'symbol': symbol,
                'name': coin['name'],
                'market_cap': coin['market_cap'],
                'total_volume': coin['total_volume']
            })
    print(f"✅ Filtered {len(filtered)} coins from CoinGecko")
    return filtered

def get_yahoo_data(symbol):
    """Retrieve last 7 days of 30-minute OHLC from Yahoo Finance"""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="7d", interval="1h")
        if df is None or len(df) < 24:
            return None
        df30 = df.resample("30T").agg({
            'Open':'first','High':'max','Low':'min','Close':'last'
        }).dropna().tail(100)
        return df30
    except Exception as e:
        print(f"❌ Yahoo error for {symbol}: {e}")
        return None

def send_telegram(coin, action):
    """Send Telegram alert"""
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat  = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat:
        return
    emoji = '🟢' if action=='buy' else '🔴'
    message = (
        f"{emoji} *TrendPulse Alert* {emoji}\n"
        f"{coin['symbol']} — *{action.upper()}*\n"
        f"📊 Cap: ${coin['market_cap']:,}\n"
        f"📈 Vol24h: ${coin['total_volume']:,}\n"
        f"🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    )
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={'chat_id':chat,'text':message,'parse_mode':'Markdown'})

def main():
    print("🕐 Hybrid TrendPulse Scanner Starting...")
    tp = TrendPulse()
    coins = fetch_gecko_coins()
    processed = 0; signals = 0

    for coin in coins:
        print(f"🔍 Analyzing {coin['symbol']}...")
        df30 = get_yahoo_data(coin['symbol'])
        if df30 is None:
            continue
        processed += 1
        buy, sell = tp.analyze(df30['Close'])
        if buy:
            send_telegram(coin, 'buy'); signals += 1; print("  🟢 BUY")
        elif sell:
            send_telegram(coin, 'sell'); signals += 1; print("  🔴 SELL")
        else:
            print("  📊 No signal")
        time.sleep(1)

    print(f"✅ Completed: {processed} coins, {signals} signals")

if __name__=="__main__":
    main()
