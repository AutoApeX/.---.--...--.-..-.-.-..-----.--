import pandas as pd
import numpy as np
import requests
import json
import os
from datetime import datetime
import time
import math

class TrendPulse:
    """
    TrendPulse - Advanced trend detection algorithm
    Generic momentum oscillator for crypto market analysis
    """
    
    def __init__(self):
        # Technical parameters for trend detection
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
    
    def calculate_trend_waves(self, price_source, ch_len=9, avg_len=12, smooth_len=3):
        """Core trend wave calculation - proprietary momentum analysis"""
        # Exponential smoothing of price source
        smooth_base = self.exponential_average(price_source, ch_len)
        
        # Deviation calculation
        price_deviation = self.exponential_average(abs(price_source - smooth_base), ch_len)
        
        # Normalized momentum index
        momentum_index = (price_source - smooth_base) / (0.015 * price_deviation)
        
        # Primary and secondary trend waves
        primary_wave = self.exponential_average(momentum_index, avg_len)
        secondary_wave = self.simple_average(primary_wave, smooth_len)
        
        # Signal conditions
        extreme_low = (primary_wave <= -60) & (secondary_wave <= -60)
        extreme_high = (secondary_wave >= 60) & (primary_wave >= 60)
        wave_cross = self.detect_crossover(primary_wave, secondary_wave)
        bullish_cross = primary_wave > secondary_wave
        bearish_cross = primary_wave < secondary_wave
        
        return {
            'primary': primary_wave, 'secondary': secondary_wave, 
            'extreme_low': extreme_low, 'extreme_high': extreme_high, 
            'cross_detected': wave_cross, 'bullish_cross': bullish_cross, 
            'bearish_cross': bearish_cross
        }
    
    def generate_signals(self, price_data):
        """Generate trading signals from price data"""
        if len(price_data) < 50:
            raise ValueError("Insufficient historical data")
            
        # Calculate average price (HLC3)
        price_data['avg_price'] = (price_data['high'] + price_data['low'] + price_data['close']) / 3
        
        # Generate trend waves
        waves = self.calculate_trend_waves(price_data['avg_price'])
        
        # Signal generation logic
        long_signal = (waves['cross_detected'] & waves['bullish_cross'] & waves['extreme_low'])
        short_signal = (waves['cross_detected'] & waves['bearish_cross'] & waves['extreme_high'])
        
        return {
            'timestamp': str(price_data.index[-1]),
            'long_signal': bool(long_signal.iloc[-1]) if not pd.isna(long_signal.iloc[-1]) else False,
            'short_signal': bool(short_signal.iloc[-1]) if not pd.isna(short_signal.iloc[-1]) else False
        }

def fetch_all_qualifying_assets(min_market_cap=50000000, min_volume_24h=30000000):
    """Fetch all cryptocurrency assets meeting market criteria"""
    try:
        print(f"🔍 Scanning market: Cap >= ${min_market_cap:,}, Volume >= ${min_volume_24h:,}")
        
        # API configuration
        api_key = os.environ.get('COINGECKO_API_KEY', '')
        headers = {'X-CG-Pro-API-Key': api_key} if api_key else {}
        
        all_qualified_assets = []
        current_page = 1
        excluded_types = {'USDT', 'USDC', 'DAI', 'BUSD', 'USDE', 'FDUSD', 'PYUSD', 'TUSD'}
        
        # Fetch all qualifying assets across multiple pages
        while True:
            print(f"📖 Processing page {current_page}...")
            
            api_url = "https://api.coingecko.com/api/v3/coins/markets"
            request_params = {
                'vs_currency': 'usd',
                'order': 'market_cap_desc',
                'per_page': 250,
                'page': current_page,
                'sparkline': 'false'
            }
            
            response = requests.get(api_url, params=request_params, headers=headers, timeout=20)
            response.raise_for_status()
            page_data = response.json()
            
            if not page_data:
                break
                
            qualifying_count = 0
            for asset in page_data:
                asset_market_cap = asset.get('market_cap') or 0
                asset_volume = asset.get('total_volume') or 0
                asset_symbol = asset['symbol'].upper()
                
                if asset_market_cap >= min_market_cap and asset_volume >= min_volume_24h:
                    if asset_symbol not in excluded_types:
                        all_qualified_assets.append({
                            'symbol': asset_symbol,
                            'name': asset['name'],
                            'market_cap': asset_market_cap,
                            'volume_24h': asset_volume,
                            'asset_id': asset['id']
                        })
                        qualifying_count += 1
                else:
                    if asset_market_cap < min_market_cap:
                        print(f"📊 Reached market cap threshold at page {current_page}")
                        return all_qualified_assets
            
            print(f"   Found {qualifying_count} qualifying assets on page {current_page}")
            
            if qualifying_count == 0:
                break
                
            current_page += 1
            time.sleep(1)  # Rate limiting
            
            if current_page > 15:  # Safety limit
                break
        
        print(f"🎯 TOTAL QUALIFYING ASSETS: {len(all_qualified_assets)}")
        return all_qualified_assets
        
    except Exception as e:
        print(f"❌ Error in market scan: {e}")
        return []

def get_price_history_with_retries(asset_id, retry_limit=3):
    """Fetch historical price data with automatic retry handling"""
    for attempt in range(retry_limit):
        try:
            api_key = os.environ.get('COINGECKO_API_KEY', '')
            headers = {'X-CG-Pro-API-Key': api_key} if api_key else {}
            
            data_url = f"https://api.coingecko.com/api/v3/coins/{asset_id}/ohlc"
            data_params = {'vs_currency': 'usd', 'days': 7}
            
            response = requests.get(data_url, params=data_params, headers=headers, timeout=15)
            
            if response.status_code == 429:
                wait_duration = 60
                print(f"   ⏳ Rate limit hit, waiting {wait_duration}s...")
                time.sleep(wait_duration)
                continue
                
            response.raise_for_status()
            historical_data = response.json()
            
            if not historical_data or len(historical_data) < 50:
                return None
                
            df = pd.DataFrame(historical_data, columns=['timestamp', 'open', 'high', 'low', 'close'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            df['volume'] = 1000  # Placeholder volume
            
            for column in ['open', 'high', 'low', 'close', 'volume']:
                df[column] = pd.to_numeric(df[column], errors='coerce')
            
            return df.tail(100)
            
        except Exception as e:
            if attempt == retry_limit - 1:
                print(f"   ❌ Failed after {retry_limit} attempts: {e}")
                return None
            time.sleep(2 ** attempt)
    
    return None

def send_trading_alert(asset_info, signal_direction):
    """Send trading alert via Telegram"""
    try:
        telegram_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        telegram_chat = os.environ.get('TELEGRAM_CHAT_ID')
        
        if not telegram_token or not telegram_chat:
            print("⚠️ Telegram configuration missing")
            return False
        
        alert_type = "🟢 LONG SIGNAL" if signal_direction == 'long' else "🔴 SHORT SIGNAL"
        alert_emoji = "🚀" if signal_direction == 'long' else "📉"
        
        alert_message = f"{alert_emoji} <b>TrendPulse Alert</b> {alert_emoji}\n\n"
        alert_message += f"💰 <b>Asset:</b> {asset_info['name']} ({asset_info['symbol']})\n"
        alert_message += f"🎯 <b>Signal:</b> {alert_type}\n\n"
        alert_message += f"<b>💹 Market Data:</b>\n"
        alert_message += f"📊 Market Cap: ${asset_info['market_cap']:,.0f}\n"
        alert_message += f"📈 24h Volume: ${asset_info['volume_24h']:,.0f}\n\n"
        alert_message += f"⏰ <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        alert_message += f"🤖 <i>TrendPulse Advanced Analysis</i>"
        
        telegram_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        telegram_data = {'chat_id': telegram_chat, 'text': alert_message, 'parse_mode': 'HTML'}
        
        telegram_response = requests.post(telegram_url, data=telegram_data, timeout=10)
        
        if telegram_response.status_code == 200:
            print(f"✅ Alert dispatched: {asset_info['symbol']} {alert_type}")
            return True
        else:
            print(f"❌ Telegram delivery failed: {telegram_response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Alert system error: {e}")
        return False

# Add this optimized version to your crypto_trend_scanner.py

def execute_market_scan():
    """Optimized market scan with better rate limiting"""
    scan_start = datetime.now()
    print("🌍 STARTING OPTIMIZED CRYPTO SCAN")
    print(f"⏰ Start: {scan_start.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    try:
        trend_analyzer = TrendPulse()
        
        # LIMIT COINS FOR RELIABLE EXECUTION
        MAX_COINS = 150  # Reduced for reliability
        all_assets = fetch_all_qualifying_assets()[:MAX_COINS]
        
        if not all_assets:
            print("❌ No qualifying assets found")
            return
        
        print(f"🎯 ANALYZING {len(all_assets)} COINS (LIMITED FOR STABILITY)")
        
        alerts_sent = 0
        processed = 0
        
        for index, asset in enumerate(all_assets, 1):
            try:
                print(f"📊 [{index}/{len(all_assets)}] {asset['symbol']}")
                
                # Get data with retries
                price_data = get_price_history_with_retries(asset['asset_id'])
                if not price_data:
                    continue
                
                # Analyze
                signals = trend_analyzer.generate_signals(price_data)
                processed += 1
                
                # Send alerts
                if signals['long_signal']:
                    if send_trading_alert(asset, 'long'):
                        alerts_sent += 1
                elif signals['short_signal']:
                    if send_trading_alert(asset, 'short'):
                        alerts_sent += 1
                
                # IMPROVED RATE LIMITING
                if index % 50 == 0:
                    print("   ⏳ Rate limit break (10s)...")
                    time.sleep(10)
                elif index % 20 == 0:
                    time.sleep(3)
                else:
                    time.sleep(1)  # 1 second between requests
                
            except Exception as e:
                print(f"   ❌ Error: {e}")
                continue
        
        duration = (datetime.now() - scan_start).total_seconds()
        print(f"\n✅ SCAN COMPLETE: {duration:.1f}s, {processed} coins, {alerts_sent} alerts")
        
    except Exception as e:
        print(f"🚨 Critical error: {e}")

        
        # Generate comprehensive execution summary
        scan_duration = (datetime.now() - scan_start).total_seconds()
        
        print("\n" + "=" * 65)
        print("🏆 COMPREHENSIVE MARKET SCAN COMPLETED")
        print("=" * 65)
        print(f"⏱️  Total execution time: {scan_duration:.1f} seconds ({scan_duration/60:.1f} minutes)")
        print(f"🌍 Total assets discovered: {len(all_assets)}")
        print(f"📊 Assets successfully processed: {assets_processed}")
        print(f"🟢 Long signals detected: {len(long_signals_detected)}")
        print(f"🔴 Short signals detected: {len(short_signals_detected)}")
        print(f"🚨 Total alerts dispatched: {alerts_dispatched}")
        print(f"❌ Processing errors: {len(processing_errors)}")
        
        if long_signals_detected:
            print(f"\n🟢 LONG SIGNALS: {', '.join(long_signals_detected)}")
        if short_signals_detected:
            print(f"\n🔴 SHORT SIGNALS: {', '.join(short_signals_detected)}")
            
        # Send execution summary via Telegram
        try:
            telegram_token = os.environ.get('TELEGRAM_BOT_TOKEN')
            telegram_chat = os.environ.get('TELEGRAM_CHAT_ID')
            
            if telegram_token and telegram_chat and (long_signals_detected or short_signals_detected):
                summary_message = f"📊 <b>TrendPulse Market Scan Complete</b>\n\n"
                summary_message += f"🌍 Assets processed: {assets_processed}\n"
                summary_message += f"🚨 Signals detected: {len(long_signals_detected + short_signals_detected)}\n"
                summary_message += f"⏱️ Execution time: {scan_duration/60:.1f} minutes\n\n"
                summary_message += f"<i>Comprehensive market coverage active ✅</i>"
                
                telegram_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
                requests.post(telegram_url, data={'chat_id': telegram_chat, 'text': summary_message, 'parse_mode': 'HTML'}, timeout=5)
        except:
            pass
            
    except Exception as e:
        print(f"🚨 Critical system error: {e}")

if __name__ == "__main__":
    execute_market_scan()
