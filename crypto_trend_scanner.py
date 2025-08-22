
import pandas as pd
import numpy as np
import requests
import json
import os
from datetime import datetime
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

class TrendPulse:
    """High-performance TrendPulse for rapid analysis"""
    
    def __init__(self):
        self.channel_length = 9
        self.average_length = 12
        self.smoothing_length = 3
        
    def exponential_average(self, src, length):
        return src.ewm(span=length, adjust=False).mean()
    
    def simple_average(self, src, length):
        return src.rolling(window=length).mean()
    
    def detect_crossover(self, series1, series2):
        prev_diff = (series1.shift(1) - series2.shift(1))
        curr_diff = (series1 - series2)
        return ((prev_diff < 0) & (curr_diff > 0)) | ((prev_diff > 0) & (curr_diff < 0))
    
    def calculate_trend_waves(self, price_source):
        """Optimized trend calculation"""
        smooth_base = self.exponential_average(price_source, self.channel_length)
        price_deviation = self.exponential_average(abs(price_source - smooth_base), self.channel_length)
        momentum_index = (price_source - smooth_base) / (0.015 * price_deviation)
        primary_wave = self.exponential_average(momentum_index, self.average_length)
        secondary_wave = self.simple_average(primary_wave, self.smoothing_length)
        
        extreme_low = (primary_wave <= -60) & (secondary_wave <= -60)
        extreme_high = (secondary_wave >= 60) & (primary_wave >= 60)
        wave_cross = self.detect_crossover(primary_wave, secondary_wave)
        bullish_cross = primary_wave > secondary_wave
        bearish_cross = primary_wave < secondary_wave
        
        return wave_cross, bullish_cross, bearish_cross, extreme_low, extreme_high
    
    def generate_signals(self, price_data):
        """Fast signal generation"""
        if len(price_data) < 50:
            return {'long_signal': False, 'short_signal': False}
            
        price_data['avg_price'] = (price_data['high'] + price_data['low'] + price_data['close']) / 3
        wave_cross, bullish_cross, bearish_cross, extreme_low, extreme_high = self.calculate_trend_waves(price_data['avg_price'])
        
        long_signal = wave_cross.iloc[-1] and bullish_cross.iloc[-1] and extreme_low.iloc[-1]
        short_signal = wave_cross.iloc[-1] and bearish_cross.iloc[-1] and extreme_high.iloc[-1]
        
        return {
            'long_signal': bool(long_signal) if not pd.isna(long_signal) else False,
            'short_signal': bool(short_signal) if not pd.isna(short_signal) else False
        }

# Global counters
results_lock = threading.Lock()

def get_fast_coin_list(limit=100):
    """Get limited coin list for fast execution"""
    try:
        print(f"🔍 Fetching top {limit} coins (optimized for speed)...")
        
        api_key = os.environ.get('COINGECKO_API_KEY', '')
        headers = {'X-CG-Pro-API-Key': api_key} if api_key else {}
        
        if api_key:
            print("🔑 Using personal CoinGecko API key")
        else:
            print("⚠️ Using public CoinGecko API (may have stricter limits)")
        
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            'vs_currency': 'usd',
            'order': 'market_cap_desc',
            'per_page': limit,
            'page': 1,
            'sparkline': 'false'
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=15)
        print(f"🌐 CoinGecko API response: {response.status_code}")
        
        response.raise_for_status()
        data = response.json()
        
        qualified_coins = []
        stablecoins = {'USDT', 'USDC', 'DAI', 'BUSD', 'USDE', 'FDUSD'}
        
        for coin in data:
            if (coin.get('market_cap', 0) >= 50_000_000 and 
                coin.get('total_volume', 0) >= 30_000_000 and
                coin['symbol'].upper() not in stablecoins):
                
                qualified_coins.append({
                    'symbol': coin['symbol'].upper(),
                    'name': coin['name'],
                    'market_cap': coin['market_cap'],
                    'volume_24h': coin['total_volume'],
                    'asset_id': coin['id']
                })
        
        print(f"✅ Selected {len(qualified_coins)} qualified coins")
        
        # Debug: Show first 5 coins
        if qualified_coins:
            print("📊 Sample coins:")
            for coin in qualified_coins[:5]:
                print(f"   {coin['symbol']} ({coin['name']}) - ID: {coin['asset_id']}")
        
        return qualified_coins
        
    except Exception as e:
        print(f"❌ Error fetching coins: {e}")
        return []

def get_price_data_fast(asset_id):
    """Fast price data retrieval with enhanced debugging"""
    try:
        api_key = os.environ.get('COINGECKO_API_KEY', '')
        headers = {'X-CG-Pro-API-Key': api_key} if api_key else {}
        
        url = f"https://api.coingecko.com/api/v3/coins/{asset_id}/ohlc"
        params = {'vs_currency': 'usd', 'days': 7}
        
        response = requests.get(url, params=params, headers=headers, timeout=15)
        
        # Debug API response
        if response.status_code != 200:
            print(f"⚠️ API Error for {asset_id}: {response.status_code} - {response.text[:100]}")
            return None
        
        data = response.json()
        
        if not data or len(data) < 50:
            print(f"⚠️ Insufficient data for {asset_id}: {len(data) if data else 0} candles")
            return None
            
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df['volume'] = 1000
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df.tail(100)
        
    except Exception as e:
        print(f"❌ Error fetching data for {asset_id}: {e}")
        return None

def send_alert_fast(coin, signal_type):
    """Fast alert sending"""
    try:
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        chat_id = os.environ.get('TELEGRAM_CHAT_ID')
        
        if not bot_token or not chat_id:
            print("⚠️ Missing Telegram credentials")
            return False
        
        action = "🟢 LONG" if signal_type == 'long' else "🔴 SHORT"
        emoji = "🚀" if signal_type == 'long' else "📉"
        
        message = f"{emoji} <b>TrendPulse Alert</b>\n\n"
        message += f"💰 {coin['name']} ({coin['symbol']})\n"
        message += f"🎯 Signal: {action}\n"
        message += f"📊 Cap: ${coin['market_cap']:,.0f}\n"
        message += f"📈 Vol: ${coin['volume_24h']:,.0f}\n"
        message += f"⏰ {datetime.now().strftime('%H:%M UTC')}"
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML'}
        
        response = requests.post(url, data=data, timeout=5)
        return response.status_code == 200
        
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return False

def analyze_single_coin_debug(coin_data, counters):
    """Analyze one coin with detailed debugging"""
    try:
        print(f"🔍 Starting analysis for {coin_data['symbol']} (ID: {coin_data['asset_id']})")
        
        cipher = TrendPulse()
        
        # Get price data
        price_df = get_price_data_fast(coin_data['asset_id'])
        if price_df is None:
            print(f"❌ No data available for {coin_data['symbol']}")
            return None
            
        print(f"✅ Got {len(price_df)} candles for {coin_data['symbol']}")
        
        # Generate signals
        signals = cipher.generate_signals(price_df)
        
        print(f"📊 {coin_data['symbol']} signals: Long={signals['long_signal']}, Short={signals['short_signal']}")
        
        # Update processed counter
        with results_lock:
            counters['processed'] += 1
        
        # Send alerts
        signal_sent = None
        if signals['long_signal']:
            print(f"🟢 LONG SIGNAL DETECTED: {coin_data['symbol']}")
            if send_alert_fast(coin_data, 'long'):
                with results_lock:
                    counters['alerts'] += 1
                    counters['signals'].append(f"{coin_data['symbol']} LONG")
                signal_sent = "LONG"
                    
        elif signals['short_signal']:
            print(f"🔴 SHORT SIGNAL DETECTED: {coin_data['symbol']}")
            if send_alert_fast(coin_data, 'short'):
                with results_lock:
                    counters['alerts'] += 1
                    counters['signals'].append(f"{coin_data['symbol']} SHORT")
                signal_sent = "SHORT"
        
        return {'symbol': coin_data['symbol'], 'signal': signal_sent}
        
    except Exception as e:
        print(f"❌ Error analyzing {coin_data['symbol']}: {e}")
        return None

def execute_fast_scan():
    """Execute optimized parallel crypto scan with detailed debugging"""
    start_time = datetime.now()
    print("⚡ FAST CRYPTO SCANNER STARTING (DEBUG MODE)")
    print("=" * 60)
    print(f"⏰ Start: {start_time.strftime('%H:%M:%S UTC')}")
    
    try:
        # Initialize counters dictionary
        counters = {
            'processed': 0,
            'alerts': 0,
            'signals': []
        }
        
        # Get coins (limited for speed)
        coins = get_fast_coin_list(limit=20)  # Reduced to 20 for debugging
        
        if not coins:
            print("❌ No coins to analyze")
            return
        
        print(f"🎯 SEQUENTIAL ANALYSIS OF {len(coins)} COINS (DEBUG MODE)")
        print("🔍 Processing coins one by one for detailed debugging...")
        
        # Sequential processing for debugging (not parallel)
        for i, coin in enumerate(coins, 1):
            print(f"\n📊 [{i}/{len(coins)}] Processing {coin['symbol']}...")
            result = analyze_single_coin_debug(coin, counters)
            
            if result:
                print(f"✅ Completed {coin['symbol']}")
            else:
                print(f"❌ Failed {coin['symbol']}")
            
            # Small delay between coins
            time.sleep(0.5)
        
        # Final results
        total_time = (datetime.now() - start_time).total_seconds()
        
        print("\n" + "=" * 60)
        print("🎉 DEBUG SCAN COMPLETE")
        print("=" * 60)
        print(f"⏱️  Total time: {total_time:.1f} seconds ({total_time/60:.1f} minutes)")
        print(f"📊 Coins processed: {counters['processed']}")
        print(f"🚨 Alerts sent: {counters['alerts']}")
        
        if counters['processed'] > 0:
            print(f"🏃 Speed: {counters['processed']/(total_time/60):.1f} coins/minute")
        
        if counters['signals']:
            print(f"📈 Signals: {', '.join(counters['signals'])}")
        else:
            print("📊 No signals detected (normal - indicator is selective)")
            
        # Send summary
        try:
            bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
            chat_id = os.environ.get('TELEGRAM_CHAT_ID')
            
            if bot_token and chat_id:
                summary = f"🔍 <b>TrendPulse Debug Scan</b>\n\n"
                summary += f"📊 Analyzed: {counters['processed']} coins\n"
                summary += f"🚨 Alerts: {counters['alerts']}\n"
                summary += f"⏱️ Time: {total_time:.1f}s\n"
                summary += f"🤖 Debug mode active"
                
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                response = requests.post(url, data={'chat_id': chat_id, 'text': summary, 'parse_mode': 'HTML'}, timeout=5)
                
                if response.status_code == 200:
                    print("✅ Summary sent to Telegram")
                else:
                    print(f"❌ Failed to send summary: {response.status_code}")
        except Exception as e:
            print(f"❌ Summary error: {e}")
            
    except Exception as e:
        print(f"🚨 Critical error: {e}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    execute_fast_scan()

