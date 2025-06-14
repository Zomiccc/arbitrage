from flask import Flask, render_template, request, jsonify, redirect, url_for
import threading
import time
import json
import os
from datetime import datetime
import bot

app = Flask(__name__)

# Global variables for bot control
bot_thread = None
bot_running = False
bot_status = {
    'running': False,
    'start_time': None,
    'total_trades': 0,
    'total_profit': 0.0,
    'last_opportunity': None,
    'errors': []
}

# Configuration
config = {
    'simulation_mode': True,
    'trade_amount': 0.001,
    'min_profit': 1.0,
    'symbols': ['BTC/USDT', 'ETH/USDT', 'ADA/USDT'],
    'exchanges': ['binance', 'kucoin', 'kraken'],
    'check_interval': 10
}

@app.route('/')
def index():
    return render_template('index.html', bot_status=bot_status, config=config)

@app.route('/api/status')
def get_status():
    return jsonify(bot_status)

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    global config
    if request.method == 'POST':
        data = request.get_json()
        config.update(data)
        return jsonify({'status': 'success', 'config': config})
    return jsonify(config)

@app.route('/api/start', methods=['POST'])
def start_bot():
    global bot_thread, bot_running, bot_status
    if not bot_running:
        bot_running = True
        bot_status['running'] = True
        bot_status['start_time'] = datetime.now().isoformat()
        bot_thread = threading.Thread(target=run_bot)
        bot_thread.daemon = True
        bot_thread.start()
        return jsonify({'status': 'success', 'message': 'Bot started successfully'})
    return jsonify({'status': 'error', 'message': 'Bot is already running'})

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    global bot_running, bot_status
    bot_running = False
    bot_status['running'] = False
    return jsonify({'status': 'success', 'message': 'Bot stopped successfully'})

@app.route('/api/logs')
def get_logs():
    try:
        with open('trades.log', 'r') as f:
            logs = f.readlines()
        return jsonify({'logs': logs[-50:]})  # Return last 50 lines
    except FileNotFoundError:
        return jsonify({'logs': []})

@app.route('/api/opportunities')
def get_opportunities():
    try:
        with open('opportunities.json', 'r') as f:
            opportunities = json.load(f)
        return jsonify(opportunities)
    except FileNotFoundError:
        return jsonify([])

def run_bot():
    """Main bot loop that runs in a separate thread"""
    global bot_running, bot_status
    
    try:
        clients = bot.init_exchanges()
        while bot_running:
            for symbol in config['symbols']:
                if not bot_running:
                    break
                    
                try:
                    prices = bot.fetch_prices(clients, symbol)
                    opps = bot.find_spatial_arbitrage(prices, config['min_profit'])
                    
                    for opp in opps:
                        if not bot_running:
                            break
                            
                        # Calculate profit with fees
                        buy_client = clients[opp['buy_exchange']]
                        sell_client = clients[opp['sell_exchange']]
                        
                        buy_fee = bot.get_trading_fee(buy_client, symbol, 'taker')
                        sell_fee = bot.get_trading_fee(sell_client, symbol, 'taker')
                        
                        profit = bot.calculate_profit(
                            opp['buy_price'], opp['sell_price'], 
                            config['trade_amount'], buy_fee, sell_fee
                        )
                        
                        opp['calculated_profit'] = profit
                        opp['timestamp'] = datetime.now().isoformat()
                        
                        # Update bot status
                        bot_status['last_opportunity'] = opp
                        if profit > 0:
                            bot_status['total_trades'] += 1
                            bot_status['total_profit'] += profit
                        
                        # Log opportunity
                        log_opportunity(opp)
                        
                        # Send alert
                        bot.send_alert(f"Arbitrage Opportunity: {opp}")
                        
                        if not config['simulation_mode']:
                            # Execute trades
                            buy_order = bot.execute_trade(buy_client, 'buy', symbol, config['trade_amount'])
                            sell_order = bot.execute_trade(sell_client, 'sell', symbol, config['trade_amount'])
                            
                            trade_info = {
                                'opportunity': opp,
                                'buy_order': buy_order,
                                'sell_order': sell_order,
                                'timestamp': datetime.now().isoformat()
                            }
                            bot.log_trade(trade_info)
                
                except Exception as e:
                    error_msg = f"Error processing {symbol}: {str(e)}"
                    bot_status['errors'].append({
                        'timestamp': datetime.now().isoformat(),
                        'error': error_msg
                    })
                    bot.send_alert(error_msg)
            
            time.sleep(config['check_interval'])
    
    except Exception as e:
        error_msg = f"Bot crashed: {str(e)}"
        bot_status['errors'].append({
            'timestamp': datetime.now().isoformat(),
            'error': error_msg
        })
        bot.send_alert(error_msg)
    finally:
        bot_running = False
        bot_status['running'] = False

def log_opportunity(opp):
    """Log opportunity to JSON file"""
    try:
        opportunities = []
        try:
            with open('opportunities.json', 'r') as f:
                opportunities = json.load(f)
        except FileNotFoundError:
            pass
        
        opportunities.append(opp)
        
        # Keep only last 100 opportunities
        if len(opportunities) > 100:
            opportunities = opportunities[-100:]
        
        with open('opportunities.json', 'w') as f:
            json.dump(opportunities, f, indent=2)
    
    except Exception as e:
        print(f"Error logging opportunity: {e}")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)