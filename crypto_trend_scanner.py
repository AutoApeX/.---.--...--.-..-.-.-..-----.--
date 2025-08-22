

import pandas as pd
import numpy as np
import requests
import os
from datetime import datetime
import time

class TrendPulse:
    """TrendPulse: Working 30-minute analysis"""
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

    def analyze(self, prices):
        """Analyze price series for signals"""
        if len(prices) < 25:
            return False, False

        esa = self.ema(prices, self.ch_len)
        dev = self.ema(abs(prices - esa), self.ch_len)
        ci = (prices - esa) / (0.015 * dev)
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

def get_coin_list():
    """Get coin list without sparkline - avoids 400 errors"""
    api_key = os.environ.get('COINGECKO_API_KEY', '')
    
    # Always use public API endpoint to avoid authentication issues
    url = "https://api.coingecko.com/api/v3/coins/markets"
    
    # Use demo API key header format if available
    headers = {}
    if api_key:
        headers = {'x-cg-demo-api-key': api_key}
    
    params = {
        'vs_currency': 'usd',
        'order': 'market_cap_desc',
        'per_page': 100,
        'page': 1
        # NO sparkline parameter - this causes 400 errors
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=20)
        print(f"📡 API Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ Error details: {response.text[:300]}")
            
        response.raise_for_status()
        return response.json()
        
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return []

def get_price_data(coin_id):
    """Get simple price history"""
    api_key = os.environ.get('COINGECKO_API_KEY', '')
    
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    
    headers = {}
    if api_key:
        headers = {'x-cg-demo-api-key': api_key}
    
    params = {
        'vs_currency': 'usd',
        'days': 2,  # Just 2 days for 30-minute intervals
        'interval': 'hourly'
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return None
            
        data = response.json()
        
        # Extract prices and convert to 30-minute intervals
        prices = [point[1] for point in data['prices']]
        
        # Create 30-minute intervals by interpolation
        if len(prices) >= 24:  # Need at least 24 hours
            extended_prices = []
            for i in range(len(prices)-1):
                extended_prices.append(prices[i])
                # Add midpoint for 30-minute interval
                midpoint = (prices[i] + prices[i+1]) / 2
                extended_prices.append(midpoint)
            extended_prices.append(prices[-1])
            
            return pd.Series(extended_prices[-48:])  # Last 48 30-minute intervals
            
        return None
        
    except Exception as e:
        return None

def send_telegram(coin, action):
    """Send Telegram alert"""
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not token or not chat:
        print("⚠️ Telegram not configured")
        return
    
    emoji = '🟢' if action == 'buy' else '🔴'
    signal = action.upper()
    
    message = f"{emoji} *TrendPulse Alert* {emoji}\n"
    message += f"{coin['symbol'].upper()} — *{signal}*\n"
    message += f"⏰ 30m Timeframe\n"
    message += f"📊 Cap: ${coin['market_cap']:,}\n"
    message += f"📈 Vol: ${coin['total_volume']:,}\n"
    message += f"🕐 {datetime.utcnow().strftime('%H:%M UTC')}"
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {
        'chat_id': chat,
        'text': message,
        'parse_mode': 'Markdown'
    }
    
    try:
        response = requests.post(url, data=data, timeout=5)
        if response.status_code == 200:
            print(f"✅ Alert sent: {coin['symbol']} {signal}")
        else:
            print(f"❌ Telegram failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Telegram error: {e}")

def main():
    """Main execution function"""
    print("🕐 TrendPulse 30m Scanner Starting...")
    start_time = datetime.utcnow()
    
    tp = TrendPulse()
    
    # Get coin list
    coins = get_coin_list()
    if not coins:
        print("❌ Failed to get coin list")
        return
    
    print(f"📊 Processing {len(coins)} coins...")
    
    signals_count = 0
    processed_count = 0
    
    for i, coin in enumerate(coins):
        # Filter by market cap and volume
        if coin['market_cap'] < 50_000_000 or coin['total_volume'] < 30_000_000:
            continue
        
        print(f"  [{i+1}/{len(coins)}] {coin['symbol']} - ${coin['market_cap']:,.0f}")
        
        # Get price data
        prices = get_price_data(coin['id'])
        if prices is None or len(prices) < 25:
            continue
        
        processed_count += 1
        
        # Analyze for signals
        buy, sell = tp.analyze(prices)
        
        if buy:
            send_telegram(coin, 'buy')
            signals_count += 1
            print(f"    🟢 BUY signal detected!")
            
        elif sell:
            send_telegram(coin, 'sell')
            signals_count += 1
            print(f"    🔴 SELL signal detected!")
        
        # Rate limiting
        time.sleep(0.2)  # 5 calls per second max
    
    # Summary
    execution_time = (datetime.utcnow() - start_time).total_seconds()
    
    print(f"\n✅ Scan Complete:")
    print(f"   ⏱️  Time: {execution_time:.1f} seconds")
    print(f"   📊 Processed: {processed_count} coins")
    print(f"   🚨 Signals: {signals_count}")
    
    # Send completion notice
    try:
        token = os.environ.get('TELEGRAM_BOT_TOKEN')
        chat = os.environ.get('TELEGRAM_CHAT_ID')
        
        if token and chat:
            summary = f"📊 *TrendPulse Scan Complete*\n"
            summary += f"Processed: {processed_count} coins\n"
            summary += f"Signals: {signals_count}\n"
            summary += f"Time: {execution_time:.1f}s"
            
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, data={
                'chat_id': chat,
                'text': summary,
                'parse_mode': 'Markdown'
            }, timeout=5)
    except:
        pass

if __name__ == "__main__":
    main()
