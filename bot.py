import ccxt
import time
import logging
from dotenv import load_dotenv
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# Exchange API keys from environment variables (example for Binance and KuCoin)
EXCHANGES = {
    'binance': {
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_API_SECRET'),
    },
    'kucoin': {
        'apiKey': os.getenv('KUCOIN_API_KEY'),
        'secret': os.getenv('KUCOIN_API_SECRET'),
    },
    'kraken': {
        'apiKey': os.getenv('KRAKEN_API_KEY'),
        'secret': os.getenv('KRAKEN_API_SECRET'),
    },
    # Add more exchanges as needed
}

# Initialize exchange clients
def init_exchanges():
    clients = {}
    for name, creds in EXCHANGES.items():
        if hasattr(ccxt, name):
            clients[name] = getattr(ccxt, name)({
                'apiKey': creds['apiKey'],
                'secret': creds['secret'],
                'enableRateLimit': True
            })
    return clients

# Fetch prices for a symbol from all exchanges
def fetch_prices(clients, symbol):
    prices = {}
    for name, client in clients.items():
        try:
            ticker = client.fetch_ticker(symbol)
            prices[name] = ticker['last']
        except Exception as e:
            logging.warning(f"Error fetching price from {name}: {e}")
    return prices

# Find spatial arbitrage opportunities
def find_spatial_arbitrage(prices, min_profit=1):
    opps = []
    sorted_prices = sorted(prices.items(), key=lambda x: x[1])
    if len(sorted_prices) < 2:
        return opps
    buy_exchange, buy_price = sorted_prices[0]
    sell_exchange, sell_price = sorted_prices[-1]
    profit = sell_price - buy_price
    if profit > min_profit:
        opps.append({
            'buy_exchange': buy_exchange,
            'sell_exchange': sell_exchange,
            'buy_price': buy_price,
            'sell_price': sell_price,
            'profit': profit
        })
    return opps

# Triangular arbitrage detection (basic example)
def find_triangular_arbitrage(client, base_symbol='BTC', quote_symbol='USDT', inter_symbol='ETH'):
    """
    Looks for triangular arbitrage opportunities between base, quote, and intermediate symbols.
    Example: BTC/USDT, ETH/USDT, BTC/ETH
    """
    try:
        # Fetch tickers
        ticker1 = client.fetch_ticker(f"{base_symbol}/{quote_symbol}")
        ticker2 = client.fetch_ticker(f"{inter_symbol}/{quote_symbol}")
        ticker3 = client.fetch_ticker(f"{base_symbol}/{inter_symbol}")
        # Calculate implied price
        implied_price = ticker2['last'] * ticker3['last']
        actual_price = ticker1['last']
        profit = implied_price - actual_price
        if profit > 0:
            return [{
                'step1': f'Buy {inter_symbol} with {quote_symbol}',
                'step2': f'Buy {base_symbol} with {inter_symbol}',
                'step3': f'Sell {base_symbol} for {quote_symbol}',
                'profit': profit
            }]
    except Exception as e:
        logging.warning(f"Error in triangular arbitrage: {e}")
    return []

# Trade execution (market order)
def execute_trade(client, side, symbol, amount):
    """
    Executes a market order. Side: 'buy' or 'sell'.
    """
    try:
        order = client.create_market_order(symbol, side, amount)
        logging.info(f"Executed {side} order: {order}")
        return order
    except Exception as e:
        logging.error(f"Trade execution failed: {e}")
        return None

# Fetch trading fee for a symbol from an exchange
def get_trading_fee(client, symbol, side='taker'):
    try:
        market = client.markets[symbol] if symbol in client.markets else client.load_markets()[symbol]
        return market.get(f'{side}Fee', 0.001)  # Default to 0.1% if not found
    except Exception as e:
        logging.warning(f"Could not fetch fee for {symbol}: {e}")
        return 0.001

# Check if order book has enough liquidity for the amount
def check_order_book_liquidity(client, symbol, amount, side='buy'):
    try:
        order_book = client.fetch_order_book(symbol)
        if side == 'buy':
            # Check if enough volume on asks
            total = 0
            for price, vol in order_book['asks']:
                total += vol
                if total >= amount:
                    return True
        else:
            # Check if enough volume on bids
            total = 0
            for price, vol in order_book['bids']:
                total += vol
                if total >= amount:
                    return True
        return False
    except Exception as e:
        logging.warning(f"Order book check failed for {symbol}: {e}")
        return False

# Update profit calculation to use actual fees
def calculate_profit(buy_price, sell_price, amount, buy_fee, sell_fee):
    gross = (sell_price - buy_price) * amount
    total_fees = (buy_price * amount * buy_fee) + (sell_price * amount * sell_fee)
    net = gross - total_fees
    return net

# Trade logging
def log_trade(trade_info, filename='trades.log'):
    """
    Logs trade info to a file.
    """
    try:
        with open(filename, 'a') as f:
            f.write(str(trade_info) + '\n')
        logging.info(f"Trade logged: {trade_info}")
    except Exception as e:
        logging.error(f"Failed to log trade: {e}")

# Send alerts (email or log)
def send_alert(message):
    """
    Sends an alert via email. Configure SMTP in environment variables. Logs if email fails.
    """
    smtp_server = os.getenv('SMTP_SERVER')
    smtp_port = os.getenv('SMTP_PORT', 587)
    smtp_user = os.getenv('SMTP_USER')
    smtp_pass = os.getenv('SMTP_PASS')
    recipient = os.getenv('ALERT_EMAIL')
    if smtp_server and smtp_user and smtp_pass and recipient:
        try:
            msg = MIMEMultipart()
            msg['From'] = smtp_user
            msg['To'] = recipient
            msg['Subject'] = 'Arbitrage Bot Alert'
            msg.attach(MIMEText(message, 'plain'))
            server = smtplib.SMTP(smtp_server, int(smtp_port))
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipient, msg.as_string())
            server.quit()
            logging.info(f"Alert sent: {message}")
        except Exception as e:
            logging.error(f"Failed to send email alert: {e}")
            logging.info(f"ALERT: {message}")
    else:
        logging.info(f"ALERT: {message}")

SIMULATION_MODE = True
TRADE_AMOUNT = 0.001   # Example amount for BTC/USDT

if __name__ == "__main__":
    clients = init_exchanges()
    symbol = 'BTC/USDT'
    while True:
        prices = fetch_prices(clients, symbol)
        opps = find_spatial_arbitrage(prices)
        for opp in opps:
            buy_client = clients[opp['buy_exchange']]
            sell_client = clients[opp['sell_exchange']]
            # Get trading fees
            buy_fee = get_trading_fee(buy_client, symbol, side='taker')
            sell_fee = get_trading_fee(sell_client, symbol, side='taker')
            # Check order book liquidity
            has_buy_liquidity = check_order_book_liquidity(buy_client, symbol, TRADE_AMOUNT, side='buy')
            has_sell_liquidity = check_order_book_liquidity(sell_client, symbol, TRADE_AMOUNT, side='sell')
            if not (has_buy_liquidity and has_sell_liquidity):
                logging.info(f"Not enough liquidity for {symbol} on {opp['buy_exchange']} or {opp['sell_exchange']}")
                continue
            # Calculate profit after fees
            profit = calculate_profit(opp['buy_price'], opp['sell_price'], TRADE_AMOUNT, buy_fee, sell_fee)
            opp['calculated_profit'] = profit
            opp['buy_fee'] = buy_fee
            opp['sell_fee'] = sell_fee
            logging.info(f"Arbitrage Opportunity: {opp}")
            send_alert(f"Arbitrage Opportunity: {opp}")
            if not SIMULATION_MODE:
                # Execute buy and sell (market orders)
                buy_order = execute_trade(buy_client, 'buy', symbol, TRADE_AMOUNT)
                sell_order = execute_trade(sell_client, 'sell', symbol, TRADE_AMOUNT)
                trade_info = {
                    'opportunity': opp,
                    'buy_order': buy_order,
                    'sell_order': sell_order
                }
                log_trade(trade_info)
            else:
                # Log simulated trade
                trade_info = {
                    'opportunity': opp,
                    'simulated': True
                }
                log_trade(trade_info)
        time.sleep(10) 