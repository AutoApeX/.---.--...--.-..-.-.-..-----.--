

# crypto_trend_scanner.py

# crypto_trend_scanner.py

import pandas as pd
import numpy as np
import requests
import yfinance as yf
import os
import json
from pathlib import Path
from datetime import datetime, timedelta
import time

ALERT_CACHE_FILE = Path("last_alerts.json")

def load_alert_cache():
    if ALERT_CACHE_FILE.exists():
        return json.loads(ALERT_CACHE_FILE.read_text())
    return {}

def save_alert_cache(cache):
    ALERT_CACHE_FILE.write_text(json.dumps(cache))

class TrendPulse:
    """TrendPulse: Accurate 15-minute candle analysis"""
    def __init__(self):
        self.ch_len = 9
        self.avg_len = 12
        self.smooth_len = 3

    def ema(self, src, length):
        return src.ewm(span=length, adjust=False).mean()

    def sma(self, src, length):
        return src.rolling(window=length).mean()

    def cross(self, s1, s2):
        prev = s1.shift(1) - s2.shift(1)
        curr = s1 - s2
        return ((prev < 0) & (curr > 0)) | ((prev > 0) & (curr < 0))

    def analyze(self, closes: pd.Series, debug_symbol=""):
        if len(closes) < self.ch_len + self.avg_len + 5:
            return False, False
        prices = closes
        esa = self.ema(prices, self.ch_len)
        dev = self.ema(abs(prices - esa), self.ch_len)
        ci  = (prices - esa) / (0.015 * dev)
        wt1 = self.ema(ci, self.avg_len)
        wt2 = self.sma(wt1, self.smooth_len)

        current_wt1 = wt1.iloc[-1]; current_wt2 = wt2.iloc[-1]
        prev_wt1    = wt1.iloc[-2]; prev_wt2    = wt2.iloc[-2]

        oversold = (current_wt1 <= -60) and (current_wt2 <= -60)
        overbought = (current_wt2 >= 60) and (current_wt1 >= 60)
        bullish_cross = (prev_wt1 <= prev_wt2) and (current_wt1 > current_wt2)
        bearish_cross = (prev_wt1 >= prev_wt2) and (current_wt1 < current_wt2)

        buy = bullish_cross and oversold
        sell = bearish_cross and overbought

        if debug_symbol:
            print(f"  📊 {debug_symbol}: WT1={current_wt1:.2f}, WT2={current_wt2:.2f}, "
                  f"oversold={oversold}, overbought={overbought}, "
                  f"bullish_cross={bullish_cross}, bearish_cross={bearish_cross}")

        return buy, sell

def fetch_gecko_coins(min_cap=50_000_000, min_vol=30_000_000, limit=111):
    api_key = os.environ.get('COINGECKO_API_KEY', '')
    url     = "https://api.coingecko.com/api/v3/coins/markets"
    headers = {'x-cg-demo-api-key': api_key} if api_key else {}
    params  = {
        'vs_currency': 'usd',
        'order': 'market_cap_desc',
        'per_page': limit,
        'page': 1,
    }
    try:
        r    = requests.get(url, params=params, headers=headers, timeout=20)
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

def get_yahoo_data_15m(symbol):
    """Get 15-minute data from Yahoo Finance"""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="5d", interval="15m")
        if df is not None and len(df) >= 50:
            return df.tail(100)
        df = ticker.history(period="3d", interval="5m")
        if df is not None and len(df) >= 150:
            df15 = df.resample("15T").agg({
                'Open':'first','High':'max','Low':'min','Close':'last'
            }).dropna()
            return df15.tail(100)
        return None
    except Exception as e:
        print(f"❌ Yahoo error for {symbol}: {e}")
        return None

def get_ist_time_12h():
    utc = datetime.utcnow()
    ist = utc + timedelta(hours=5, minutes=30)
    return ist.strftime('%I:%M %p %d-%m-%Y'), ist.strftime('%A, %d %B %Y')

def tradingview_url_bybit(symbol):
    """Construct TradingView URL for Bybit USDT pair and verify availability"""
    pair = symbol.replace('-USD','') + 'USDT'
    url = f"https://www.tradingview.com/chart/?symbol=BYBIT%3A{pair}"
    try:
        resp = requests.head(url, timeout=5)
        return url if resp.status_code==200 else None
    except:
        return None

def send_telegram(coin, action, wt1, wt2, cache):
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat  = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat:
        return

    time_str, day_str = get_ist_time_12h()
    tv_url = tradingview_url_bybit(coin['symbol'])
    if not tv_url:
        print(f"❌ No Bybit chart for {coin['symbol']} – skipping alert")
        return

    key = f"{coin['symbol']}_{action}_{time_str}"
    if key in cache:
        print(f"⏭️ Duplicate alert {key} – skipped")
        return

    emoji = '🟢' if action=='buy' else '🔴'
    message = (
        f"{emoji} *TrendPulse Alert* {emoji}\n"
        f"{coin['symbol']} — *{action.upper()}*\n"
        f"📊 WT1: {wt1:.2f} | WT2: {wt2:.2f}\n"
        f"💰 Cap: ${coin['market_cap']:,}\n"
        f"📈 Vol24h: ${coin['total_volume']:,}\n"
        f"🕐 {time_str} IST\n"
        f"📅 {day_str}\n"
        f"⏰ 15-minute timeframe\n\n"
        f"🔗 [Bybit USDT Chart]({tv_url})"
    )

    url  = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {'chat_id':chat,'text':message,'parse_mode':'Markdown'}
    try:
        res = requests.post(url, data=data, timeout=5)
        if res.status_code==200:
            print(f"✅ Alert sent: {coin['symbol']} {action.upper()}")
            cache[key] = True
        else:
            print(f"❌ Telegram error: {res.status_code}")
    except Exception as e:
        print(f"❌ Telegram exception: {e}")

def main():
    print("🕐 TrendPulse 15m Scanner with Bybit Charts")
    cache = load_alert_cache()
    tp = TrendPulse()
    coins = fetch_gecko_coins()
    processed = signals = 0

    for i, coin in enumerate(coins,1):
        print(f"[{i}/{len(coins)}] {coin['symbol']}")
        df = get_yahoo_data_15m(coin['symbol'])
        if df is None or len(df)<30:
            continue
        processed += 1
        hlc3 = (df['High']+df['Low']+df['Close'])/3
        buy, sell = tp.analyze(hlc3, coin['symbol'] if i<=5 else "")
        wt1 = tp.ema((hlc3- tp.ema(hlc3,tp.ch_len))/(0.015* tp.ema(abs(hlc3-tp.ema(hlc3,tp.ch_len)),tp.ch_len)),tp.avg_len).iloc[-1]
        wt2 = tp.sma(tp.ema((hlc3- tp.ema(hlc3,tp.ch_len))/(0.015* tp.ema(abs(hlc3-tp.ema(hlc3,tp.ch_len)),tp.ch_len)),tp.avg_len),tp.smooth_len).iloc[-1]
        if buy:
            send_telegram(coin,'buy',wt1,wt2,cache); signals+=1
        elif sell:
            send_telegram(coin,'sell',wt1,wt2,cache); signals+=1
        time.sleep(0.5)

    save_alert_cache(cache)
    print(f"✅ Done: {processed} coins, {signals} signals")

if __name__=="__main__":
    main()
