
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

# Global counters for thread safety
results_lock = threading.Lock()
total_processed = 0
total_alerts = 0
successful_signals = []

def get_fast_coin_list(limit=100):
    """Get limited coin list for fast execution"""
    try:
        print(f"🔍 Fetching top {limit} coins (optimized for speed)...")
        
        api_key = os.environ.get('COINGECKO_API_KEY', '')
        headers = {'X-CG-Pro-API-Key': api_key} if api_key else {}
        
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            'vs_currency': 'usd',
            'order': 'market_cap_desc',
            'per_page': limit,
            'page': 1,
            'sparkline': 'false'
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=15)
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
        return qualified_coins
        
    except Exception as e:
        print(f"❌ Error fetching coins: {e}")
        return []

def get_price_data_fast(asset_id):
    """Fast price data retrieval with timeout"""
    try:
        api_key = os.environ.get('COINGECKO_API_KEY', '')
        headers = {'X-CG-Pro-API-Key': api_key} if api_key else {}
        
        url = f"https://api.coingecko.com/api/v3/coins/{asset_id}/ohlc"
        params = {'vs_currency': 'usd', 'days': 7}
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data or len(data) < 50:
            return None
            
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df['volume'] = 1000
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df.tail(100)
        
    except Exception as e:
        return None

def send_alert_fast(coin, signal_type):
    """Fast alert sending"""
    try:
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        chat_id = os.environ.get('TELEGRAM_CHAT_ID')
        
        if not bot_token or not chat_id:
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
        return False

def analyze_single_coin(coin_data):
    """Analyze one coin (for parallel processing)"""
    global total_processed, total_alerts, successful_signals
    
    try:
        cipher = TrendPulse()
        
        # Get price data
        price_df = get_price_data_fast(coin_data['asset_id'])
        if price_df is None:
            return None
            
        # Generate signals
        signals = cipher.generate_signals(price_df)
        
        with results_lock:
            global total_processed
            total_processed += 1
        
        # Send alerts
        if signals['long_signal']:
            if send_alert_fast(coin_data, 'long'):
                with results_lock:
                    global total_alerts
                    total_alerts += 1
                    successful_signals.append(f"{coin_data['symbol']} LONG")
                    
        elif signals['short_signal']:
            if send_alert_fast(coin_data, 'short'):
                with results_lock:
                    global total_alerts
                    total_alerts += 1
                    successful_signals.append(f"{coin_data['symbol']} SHORT")
        
        return coin_data['symbol']
        
    except Exception as e:
        return None

def execute_fast_scan():
    """Execute optimized parallel crypto scan"""
    global total_processed, total_alerts, successful_signals
    
    start_time = datetime.now()
    print("⚡ FAST CRYPTO SCANNER STARTING")
    print("=" * 50)
    print(f"⏰ Start: {start_time.strftime('%H:%M:%S UTC')}")
    
    try:
        # Reset counters
        total_processed = 0
        total_alerts = 0
        successful_signals = []
        
        # Get coins (limited for speed)
        coins = get_fast_coin_list(limit=100)  # Reduced for 5-10 minute execution
        
        if not coins:
            print("❌ No coins to analyze")
            return
        
        print(f"🎯 PARALLEL ANALYSIS OF {len(coins)} COINS")
        print("💪 Using 15 concurrent threads...")
        
        # Parallel processing with ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=15) as executor:
            # Submit all analysis tasks
            future_to_coin = {executor.submit(analyze_single_coin, coin): coin for coin in coins}
            
            # Process results as they complete
            completed = 0
            for future in as_completed(future_to_coin):
                completed += 1
                symbol = future.result()
                
                if completed % 20 == 0:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    print(f"⏳ Progress: {completed}/{len(coins)} coins ({elapsed:.0f}s)")
                
                # Gentle rate limiting
                if completed % 50 == 0:
                    time.sleep(2)
        
        # Final results
        total_time = (datetime.now() - start_time).total_seconds()
        
        print("\n" + "=" * 50)
        print("🎉 FAST SCAN COMPLETE")
        print("=" * 50)
        print(f"⏱️  Total time: {total_time:.1f} seconds ({total_time/60:.1f} minutes)")
        print(f"📊 Coins processed: {total_processed}")
        print(f"🚨 Alerts sent: {total_alerts}")
        print(f"🏃 Speed: {total_processed/(total_time/60):.1f} coins/minute")
        
        if successful_signals:
            print(f"📈 Signals: {', '.join(successful_signals)}")
            
        # Send summary
        if total_processed > 0:
            try:
                bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
                chat_id = os.environ.get('TELEGRAM_CHAT_ID')
                
                if bot_token and chat_id:
                    summary = f"⚡ <b>Fast TrendPulse Scan</b>\n\n"
                    summary += f"📊 Analyzed: {total_processed} coins\n"
                    summary += f"🚨 Alerts: {total_alerts}\n"
                    summary += f"⏱️ Time: {total_time:.1f}s\n"
                    summary += f"🏃 Speed: {total_processed/(total_time/60):.0f}/min"
                    
                    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                    requests.post(url, data={'chat_id': chat_id, 'text': summary, 'parse_mode': 'HTML'}, timeout=5)
            except:
                pass
            
    except Exception as e:
        print(f"🚨 Error: {e}")

if __name__ == "__main__":
    execute_fast_scan()

