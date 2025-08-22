

# crypto_trend_scanner.py

import pandas as pd
import numpy as np
import requests
import yfinance as yf
import os
from datetime import datetime, timedelta
import time

class TrendPulse:
    """TrendPulse: Accurate 15-minute candle analysis with strict signal validation"""
    def __init__(self):
        self.ch_len = 9
        self.avg_len = 12
        self.smooth_len = 3

    def ema(self, src, length):
        return src.ewm(span=length, adjust=False).mean()

    def sma(self, src, length):
        return src.rolling(window=length).mean()

    def cross(self, s1, s2):
        """Detect crossovers between two series"""
        prev_diff = (s1.shift(1) - s2.shift(1))
        curr_diff = (s1 - s2)
        return ((prev_diff < 0) & (curr_diff > 0)) | ((prev_diff > 0) & (curr_diff < 0))

    def analyze(self, closes: pd.Series, debug_symbol=""):
        """Generate buy/sell signals from 15-minute closes with strict validation"""
        if len(closes) < self.ch_len + self.avg_len + 5:  # Need extra data for validation
            if debug_symbol:
                print(f"  ❌ {debug_symbol}: Insufficient data ({len(closes)} candles)")
            return False, False

        # Calculate HLC3 average (if you have OHLC data, use this instead of just closes)
        prices = closes

        # Your indicator calculation
        esa = self.ema(prices, self.ch_len)
        dev = self.ema(abs(prices - esa), self.ch_len)
        ci = (prices - esa) / (0.015 * dev)

        wt1 = self.ema(ci, self.avg_len)
        wt2 = self.sma(wt1, self.smooth_len)

        # Current values for debugging
        current_wt1 = wt1.iloc[-1]
        current_wt2 = wt2.iloc[-1]
        prev_wt1 = wt1.iloc[-2] if len(wt1) > 1 else current_wt1
        prev_wt2 = wt2.iloc[-2] if len(wt2) > 1 else current_wt2

        # Strict conditions
        oversold_zone = (current_wt1 <= -60) and (current_wt2 <= -60)
        overbought_zone = (current_wt2 >= 60) and (current_wt1 >= 60)
        
        # Crossover detection
        bullish_cross = (prev_wt1 <= prev_wt2) and (current_wt1 > current_wt2)
        bearish_cross = (prev_wt1 >= prev_wt2) and (current_wt1 < current_wt2)

        # Strict signal conditions - MUST be in extreme zones
        buy_signal = bullish_cross and oversold_zone
        sell_signal = bearish_cross and overbought_zone

        # Debug output
        if debug_symbol:
            print(f"  📊 {debug_symbol}:")
            print(f"     WT1: {current_wt1:.2f} | WT2: {current_wt2:.2f}")
            print(f"     Oversold: {oversold_zone} | Overbought: {overbought_zone}")
            print(f"     Bullish Cross: {bullish_cross} | Bearish Cross: {bearish_cross}")
            print(f"     BUY: {buy_signal} | SELL: {sell_signal}")

        return buy_signal, sell_signal

def fetch_gecko_coins(min_cap=50_000_000, min_vol=30_000_000, limit=111):
    """Fetch and filter coins by Market Cap and 24h Volume from CoinGecko"""
    api_key = os.environ.get('COINGECKO_API_KEY', '')
    url = "https://api.coingecko.com/api/v3/coins/markets"
    headers = {'x-cg-demo-api-key': api_key} if api_key else {}
    
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
    stablecoins = {'USDT', 'USDC', 'DAI', 'BUSD', 'USDE', 'FDUSD'}
    
    for coin in data:
        if (coin.get('market_cap', 0) >= min_cap and
            coin.get('total_volume', 0) >= min_vol and
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
    """Get 15-minute OHLC data from Yahoo Finance"""
    try:
        ticker = yf.Ticker(symbol)
        
        # Try direct 15-minute data first
        df = ticker.history(period="5d", interval="15m")
        if df is not None and len(df) >= 50:
            print(f"  ✅ Got 15m data: {len(df)} candles")
            return df.tail(100)  # Last 100 15-minute candles
        
        # Fallback to 5-minute data and resample to 15m
        df = ticker.history(period="3d", interval="5m")
        if df is not None and len(df) >= 150:
            df_15m = df.resample("15T").agg({
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last',
                'Volume': 'sum'
            }).dropna()
            
            if len(df_15m) >= 50:
                print(f"  ✅ Resampled 5m→15m: {len(df_15m)} candles")
                return df_15m.tail(100)
        
        return None
        
    except Exception as e:
        print(f"❌ Yahoo error for {symbol}: {e}")
        return None

def get_ist_time_12h():
    """Get IST time in 12-hour format without pytz dependency"""
    utc_now = datetime.utcnow()
    ist_now = utc_now + timedelta(hours=5, minutes=30)
    return ist_now.strftime('%I:%M %p %d-%m-%Y')

def send_telegram(coin, action, wt1_value, wt2_value):
    """Send Telegram alert with TradingView chart link and current day"""
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not token or not chat:
        return
    
    # Get IST time and day without pytz dependency
    utc_now = datetime.utcnow()
    ist_now = utc_now + timedelta(hours=5, minutes=30)
    time_str = ist_now.strftime('%I:%M %p %d-%m-%Y')
    day_str = ist_now.strftime('%A, %d %B %Y')
    
    # Build TradingView chart URL
    base_symbol = coin['symbol'].replace('-USD', '') + 'USD'
    tv_url = f"https://www.tradingview.com/chart/?symbol=COINBASE%3A{base_symbol}"
    
    emoji = '🟢' if action == 'buy' else '🔴'
    
    message = f"{emoji} *TrendPulse Alert* {emoji}\n"
    message += f"{coin['symbol']} — *{action.upper()}*\n"
    message += f"📊 WT1: {wt1_value:.2f} | WT2: {wt2_value:.2f}\n"
    message += f"💰 Cap: ${coin['market_cap']:,}\n"
    message += f"📈 Vol24h: ${coin['total_volume']:,}\n"
    message += f"🕐 {time_str} IST\n"
    message += f"📅 {day_str}\n"
    message += f"⏰ 15-minute timeframe\n\n"
    message += f"🔗 [View TradingView Chart]({tv_url})"
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {'chat_id': chat, 'text': message, 'parse_mode': 'Markdown'}
    
    try:
        response = requests.post(url, data=data, timeout=5)
        if response.status_code == 200:
            print(f"✅ Alert sent: {coin['symbol']} {action.upper()}")
        else:
            print(f"❌ Telegram error: {response.status_code}")
    except Exception as e:
        print(f"❌ Telegram exception: {e}")


def main():
    print("🕐 TrendPulse 15-Minute Scanner (Fixed Logic)")
    print("=" * 60)
    
    start_time = datetime.utcnow()
    tp = TrendPulse()
    
    coins = fetch_gecko_coins()
    if not coins:
        print("❌ No coins retrieved")
        return
    
    processed = 0
    signals = 0
    
    print(f"📊 Processing {len(coins)} coins on 15-minute timeframe...")
    print("=" * 60)
    
    for i, coin in enumerate(coins, 1):
        print(f"🔍 [{i}/{len(coins)}] {coin['symbol']} ({coin['name']})")
        
        # Get 15-minute data
        df = get_yahoo_data_15m(coin['symbol'])
        if df is None or len(df) < 30:
            print("  ❌ Insufficient data")
            continue
        
        processed += 1
        
        try:
            # Calculate HLC3 for more accurate signals
            hlc3 = (df['High'] + df['Low'] + df['Close']) / 3
            
            # Analyze with debug info for first few coins
            debug_symbol = coin['symbol'] if i <= 5 else ""  # Debug first 5 coins
            buy, sell = tp.analyze(hlc3, debug_symbol)
            
            # Get current indicator values for alert
            if len(hlc3) >= 25:
                # Recalculate for current values (for Telegram)
                esa = tp.ema(hlc3, tp.ch_len)
                dev = tp.ema(abs(hlc3 - esa), tp.ch_len)
                ci = (hlc3 - esa) / (0.015 * dev)
                wt1 = tp.ema(ci, tp.avg_len)
                wt2 = tp.sma(wt1, tp.smooth_len)
                
                current_wt1 = wt1.iloc[-1]
                current_wt2 = wt2.iloc[-1]
            else:
                current_wt1 = current_wt2 = 0
            
            if buy:
                send_telegram(coin, 'buy', current_wt1, current_wt2)
                signals += 1
                print("  🟢 BUY SIGNAL SENT!")
                
            elif sell:
                send_telegram(coin, 'sell', current_wt1, current_wt2)
                signals += 1
                print("  🔴 SELL SIGNAL SENT!")
            else:
                if debug_symbol:
                    print("  📊 No signal")
                
        except Exception as e:
            print(f"  ❌ Analysis error: {e}")
        
        # Rate limiting
        if i % 20 == 0:
            time.sleep(1)
        else:
            time.sleep(0.3)
    
    # Summary
    execution_time = (datetime.utcnow() - start_time).total_seconds()
    
    print(f"\n✅ 15-Minute Scan Complete:")
    print(f"   ⏱️  Time: {execution_time:.1f}s")
    print(f"   📊 Processed: {processed} coins")
    print(f"   🚨 Signals: {signals}")
    
    # Send summary
    try:
        token = os.environ.get('TELEGRAM_BOT_TOKEN')
        chat = os.environ.get('TELEGRAM_CHAT_ID')
        
        if token and chat:
            ist_time = get_ist_time_12h()
            summary = f"📊 *TrendPulse 15m Scan*\n"
            summary += f"Processed: {processed} coins\n"
            summary += f"Signals: {signals}\n"
            summary += f"Time: {execution_time:.1f}s\n"
            summary += f"🕐 {ist_time} IST"
            
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, data={'chat_id': chat, 'text': summary, 'parse_mode': 'Markdown'}, timeout=5)
    except:
        pass

if __name__ == "__main__":
    main()
