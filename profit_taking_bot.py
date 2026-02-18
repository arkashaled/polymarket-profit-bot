#!/usr/bin/env python3
"""
Autonomous Profit-Taking Bot for Polymarket
Monitors positions and sells based on profit/loss thresholds
"""
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import SELL
from web3 import Web3
from eth_account import Account
import time
import json
from datetime import datetime
import logging

# ============================================================================
# CONFIGURATION - ADJUST THESE SETTINGS
# ============================================================================

PRIVATE_KEY = "0x5e79cadc71b17e7a7d11159cf2914a427abd3819faa0eaad1633bfe20508674b"  # Your wallet private key

# Profit/Loss Thresholds
TAKE_PROFIT_PCT = 15.0  # Sell if position is up 15% or more
STOP_LOSS_PCT = -10.0  # Sell if position is down 10% or more

# Scan Settings
SCAN_INTERVAL_SECONDS = 600  # 10 minutes (600 seconds)

# Trading Settings
MIN_POSITION_VALUE = 0.50  # Only sell positions worth at least $0.50

# Logging
LOG_FILE = "profit_taking_bot.log"
TRADES_LOG = "profit_taking_trades.json"

# ============================================================================
# SETUP
# ============================================================================

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Get wallet address
account = Account.from_key(PRIVATE_KEY)
WALLET_ADDRESS = account.address

# Initialize Polymarket client
client = ClobClient(
    "https://clob.polymarket.com",
    key=PRIVATE_KEY,
    chain_id=137
)

# Set API credentials
client.set_api_creds(client.create_or_derive_api_creds())

# Setup Web3
w3 = Web3(Web3.HTTPProvider('https://polygon-rpc.com'))

CTF_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
CTF_ABI = [{
    "inputs": [{"name": "account", "type": "address"}, {"name": "id", "type": "uint256"}],
    "name": "balanceOf",
    "outputs": [{"name": "", "type": "uint256"}],
    "stateMutability": "view",
    "type": "function"
}]

ctf_contract = w3.eth.contract(address=CTF_ADDRESS, abi=CTF_ABI)

# Load or initialize trades log
try:
    with open(TRADES_LOG, 'r') as f:
        trades_log = json.load(f)
except FileNotFoundError:
    trades_log = {
        "purchases": {},  # token_id: {price, shares, timestamp}
        "sales": [],
        "total_profit": 0.0,
        "resolved_markets": []  # List of resolved token IDs to skip
    }


def save_trades_log():
    """Save trades log to file"""
    with open(TRADES_LOG, 'w') as f:
        json.dump(trades_log, f, indent=2)


def record_purchase(token_id, price, shares):
    """Record a purchase for profit/loss tracking"""
    trades_log["purchases"][token_id] = {
        "buy_price": price,
        "shares": shares,
        "timestamp": datetime.now().isoformat()
    }
    save_trades_log()


def record_sale(token_id, sell_price, shares, pnl, pnl_pct):
    """Record a sale"""
    purchase = trades_log["purchases"].get(token_id, {})

    trades_log["sales"].append({
        "token_id": token_id,
        "buy_price": purchase.get("buy_price", 0),
        "sell_price": sell_price,
        "shares": shares,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "timestamp": datetime.now().isoformat()
    })

    trades_log["total_profit"] += pnl

    # Remove from active purchases
    if token_id in trades_log["purchases"]:
        del trades_log["purchases"][token_id]

    save_trades_log()


def get_all_positions():
    """Scan wallet for all Polymarket positions - auto-discover tokens"""
    logger.info("🔍 Scanning wallet for positions...")

    token_ids = set()

    # Method 1: Check our own trades log for known purchases
    for token_id in trades_log["purchases"].keys():
        token_ids.add(token_id)

    logger.info(f"   Found {len(token_ids)} tokens from profit-taking purchase history")

    # Method 2: Check autonomous_bot's trade log if it exists
    try:
        with open('trades_log.json', 'r') as f:
            lines = f.readlines()

            # Track most recent purchase per token only
            token_purchases = {}  # token_id: {price, shares, timestamp}

            for line in lines:
                try:
                    trade = json.loads(line.strip())
                    token_id = trade.get('token_id')
                    timestamp = trade.get('timestamp', '')

                    if token_id:
                        # Keep only the most recent purchase for each token
                        if token_id not in token_purchases or timestamp > token_purchases[token_id].get('timestamp',
                                                                                                        ''):
                            token_purchases[token_id] = {
                                'price': trade.get('price', 0),
                                'shares': trade.get('shares', 0),
                                'timestamp': timestamp
                            }

                except json.JSONDecodeError:
                    continue

            # Now add tokens and record purchases
            for token_id, purchase_info in token_purchases.items():
                token_ids.add(str(token_id))
                # Record most recent purchase for P&L tracking
                if str(token_id) not in trades_log["purchases"]:
                    record_purchase(str(token_id), purchase_info['price'], purchase_info['shares'])

            if token_ids:
                logger.info(f"   ✅ Found {len(token_ids)} tokens from buy bot log (most recent only)")
    except FileNotFoundError:
        logger.debug("   No buy bot trade log found yet")
    except Exception as e:
        logger.debug(f"   Error reading buy bot log: {e}")

    # Method 3: Query Polygonscan API for all ERC1155 transfers
    try:
        logger.info("   Querying Polygonscan for token transfers...")

        import requests

        params = {
            "module": "account",
            "action": "token1155tx",
            "contractaddress": CTF_ADDRESS,
            "address": WALLET_ADDRESS,
            "page": 1,
            "offset": 100,
            "sort": "desc",
            "apikey": "YourApiKeyToken"
        }

        response = requests.get(
            "https://api.polygonscan.com/api",
            params=params,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()

            if data.get('status') == '1' and data.get('result'):
                transfers = data['result']

                for transfer in transfers:
                    if transfer.get('to', '').lower() == WALLET_ADDRESS.lower():
                        token_id = transfer.get('tokenID')
                        if token_id:
                            token_ids.add(str(token_id))

                logger.info(f"   ✅ Polygonscan added more tokens - total: {len(token_ids)}")
            else:
                logger.info(f"   Polygonscan: no new tokens (using existing {len(token_ids)})")
        else:
            logger.info(f"   Polygonscan unavailable (using {len(token_ids)} known tokens)")

    except Exception as e:
        logger.debug(f"   Polygonscan skipped: {e}")

    # Method 3b: Polymarket Data API - most reliable direct source
    try:
        import requests as req
        r = req.get(
            "https://data-api.polymarket.com/positions",
            params={"user": WALLET_ADDRESS, "limit": 500},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            positions_list = data if isinstance(data, list) else data.get('positions', data.get('data', []))
            before = len(token_ids)
            for pos in positions_list:
                tid = pos.get('asset') or pos.get('token_id') or pos.get('tokenId')
                size = float(pos.get('size', pos.get('amount', pos.get('shares', 0))) or 0)
                if tid and size > 0.01:
                    token_ids.add(str(tid))
            added = len(token_ids) - before
            logger.info(f"   ✅ Data API added {added} tokens - total: {len(token_ids)}")
    except Exception as e:
        logger.debug(f"   Data API skipped: {e}")

    # Method 4: Try direct blockchain scanning with small range
    try:
        latest_block = w3.eth.block_number
        from_block = max(0, latest_block - 500)  # Very small: 500 blocks

        transfer_topic = w3.keccak(text="TransferSingle(address,address,address,uint256,uint256)").hex()

        logs = w3.eth.get_logs({
            'fromBlock': from_block,
            'toBlock': 'latest',
            'address': CTF_ADDRESS,
            'topics': [transfer_topic]
        })

        for log in logs:
            if len(log['topics']) >= 4:
                to_address = '0x' + log['topics'][3].hex()[-40:]
                if to_address.lower() == WALLET_ADDRESS.lower():
                    data = log['data'].hex()[2:]
                    token_id = int(data[:64], 16)
                    token_ids.add(str(token_id))

        logger.info(f"   Blockchain scan complete - total tokens: {len(token_ids)}")

    except Exception as e:
        logger.debug(f"   Blockchain scan skipped: {e}")

    # Method 5: If still nothing, check if buy bot is writing to autonomous_bot.log
    if len(token_ids) == 0:
        try:
            logger.info("   Checking autonomous_bot.log for recent trades...")
            with open('autonomous_bot.log', 'r') as f:
                # Read last 1000 lines
                lines = f.readlines()[-1000:]
                for line in lines:
                    # Look for "token_id=" in log lines
                    if 'token_id=' in line:
                        parts = line.split('token_id=')
                        if len(parts) > 1:
                            # Extract token ID (next word/number)
                            token_str = parts[1].split()[0].strip(',;&')
                            if token_str.isdigit():
                                token_ids.add(token_str)

            if token_ids:
                logger.info(f"   ✅ Found {len(token_ids)} tokens from buy bot logs")
        except:
            pass

    if len(token_ids) == 0:
        logger.warning("   ⚠️  No tokens discovered. Wallet may be empty or buy bot hasn't traded yet.")
        return []

    # Check balances
    positions = []

    # Filter out resolved markets first
    active_tokens = [t for t in token_ids if t not in trades_log.get("resolved_markets", [])]

    if len(active_tokens) < len(token_ids):
        skipped = len(token_ids) - len(active_tokens)
        logger.info(f"   ⏭️  Skipped {skipped} resolved market(s)")

    logger.info(f"   Checking balances for {len(active_tokens)} active tokens...")

    for token_id in active_tokens:
        try:
            # First check blockchain balance - retry on rate limit
            balance = None
            for attempt in range(3):
                try:
                    balance = ctf_contract.functions.balanceOf(WALLET_ADDRESS, int(token_id)).call()
                    break
                except Exception as re:
                    if 'rate limit' in str(re).lower() or '-32090' in str(re):
                        time.sleep(2 + attempt * 2)
                    else:
                        raise re
            if balance is None:
                logger.debug(f"   Rate limit failed for {token_id[:20]}... after 3 attempts")
                continue
            balance_decimal = balance / 1e6
            time.sleep(0.15)  # 150ms between calls to stay under rate limit

            if balance_decimal > 0.0001:
                # Now check if we have open orders that lock these tokens
                try:
                    open_orders = client.get_orders(asset_id=token_id)

                    # Calculate locked balance in open orders
                    locked_balance = 0.0
                    for order in open_orders:
                        if order.get('owner', '').lower() == WALLET_ADDRESS.lower():
                            locked_balance += float(order.get('size_matched', 0))

                    # Available balance = blockchain balance - locked in orders
                    available_balance = balance_decimal - locked_balance

                    if available_balance > 0.0001:
                        positions.append({
                            'token_id': token_id,
                            'shares': available_balance
                        })
                        logger.info(
                            f"   ✅ Found {available_balance:.6f} shares in token {token_id[:20]}... ({locked_balance:.6f} locked in orders)")
                    elif locked_balance > 0:
                        logger.info(f"   ⏭️  Skipping token {token_id[:20]}... - all shares locked in open orders")

                except Exception as e:
                    # If we can't check orders, use blockchain balance
                    logger.debug(f"   Couldn't check orders for {token_id[:20]}..., using blockchain balance")
                    positions.append({
                        'token_id': token_id,
                        'shares': balance_decimal
                    })
                    logger.info(f"   ✅ Found {balance_decimal:.6f} shares in token {token_id[:20]}...")

        except Exception as e:
            logger.warning(f"   ⚠️  Error checking {token_id[:20]}...: {e}")
            continue

    logger.info(f"   ✅ Found {len(positions)} active positions")
    return positions


def get_market_price(token_id):
    """Get current market BID price for a token"""
    try:
        bid_data = client.get_price(token_id, "BUY")
        return float(bid_data['price'])
    except Exception as e:
        error_msg = str(e)
        if '404' in error_msg or 'No orderbook' in error_msg:
            logger.info(f"   ⏭️  Market resolved - skipping (no orderbook)")
            return None
        else:
            logger.error(f"   Error getting price for {token_id[:20]}...: {e}")
            return None


def should_sell(token_id, current_price, shares):
    """Determine if position should be sold based on profit/loss"""

    # Check if we have purchase data
    if token_id not in trades_log["purchases"]:
        logger.info(f"   ℹ️  No purchase record - assuming bought at current price")
        # Record it now for future tracking
        record_purchase(token_id, current_price, shares)
        return False, 0.0, 0.0

    purchase = trades_log["purchases"][token_id]
    buy_price = purchase["buy_price"]

    # Calculate P&L
    current_value = current_price * shares
    purchase_value = buy_price * shares
    pnl = current_value - purchase_value
    pnl_pct = ((current_price - buy_price) / buy_price) * 100

    # Check thresholds
    if pnl_pct >= TAKE_PROFIT_PCT:
        logger.info(f"   🎯 TAKE PROFIT! {pnl_pct:.1f}% gain (target: {TAKE_PROFIT_PCT}%)")
        return True, pnl, pnl_pct
    elif pnl_pct <= STOP_LOSS_PCT:
        logger.info(f"   🛑 STOP LOSS! {pnl_pct:.1f}% loss (threshold: {STOP_LOSS_PCT}%)")
        return True, pnl, pnl_pct
    else:
        logger.info(f"   📊 Hold: {pnl_pct:+.1f}% (TP: {TAKE_PROFIT_PCT}%, SL: {STOP_LOSS_PCT}%)")
        return False, pnl, pnl_pct


def sell_position(token_id, shares, current_price, pnl, pnl_pct):
    """Execute sell order"""
    logger.info(f"   💰 Executing SELL order...")
    logger.info(f"      Shares: {shares:.6f}")
    logger.info(f"      Price: ${current_price:.4f}")
    logger.info(f"      Value: ${shares * current_price:.2f}")

    try:
        order = OrderArgs(
            token_id=token_id,
            price=current_price,
            size=shares,
            side=SELL,
            fee_rate_bps=0,
            nonce=0
        )

        signed_order = client.create_order(order)
        result = client.post_order(signed_order, OrderType.GTC)

        logger.info(f"   ✅ SOLD!")
        logger.info(f"      Order ID: {result.get('orderID', 'N/A')}")
        logger.info(f"      Status: {result.get('status', 'N/A')}")
        logger.info(f"      P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%)")

        # Record the sale
        record_sale(token_id, current_price, shares, pnl, pnl_pct)

        return True

    except Exception as e:
        logger.error(f"   ❌ Sell failed: {e}")
        return False


def scan_and_sell():
    """Main scanning and selling loop"""
    logger.info("")
    logger.info("=" * 70)
    logger.info("📊 SCANNING POSITIONS")
    logger.info("=" * 70)

    positions = get_all_positions()

    if not positions:
        logger.info("No positions found")
        return

    logger.info("")

    sold_count = 0
    held_count = 0
    total_pnl = 0.0

    for i, pos in enumerate(positions, 1):
        token_id = pos['token_id']
        shares = pos['shares']

        logger.info(f"Position {i}/{len(positions)}:")
        logger.info(f"   Token: {token_id[:20]}...")
        logger.info(f"   Shares: {shares:.6f}")

        # Get current price
        current_price = get_market_price(token_id)

        if current_price is None:
            logger.info(f"   ⏭️  Skipping - market resolved or unavailable")

            # Add to resolved markets list so we never check it again
            if "resolved_markets" not in trades_log:
                trades_log["resolved_markets"] = []

            if token_id not in trades_log["resolved_markets"]:
                trades_log["resolved_markets"].append(token_id)
                logger.info(f"   🧹 Added to resolved markets - will skip in future scans")

            # Remove from purchases tracking
            if token_id in trades_log["purchases"]:
                del trades_log["purchases"][token_id]

            save_trades_log()
            continue

        current_value = shares * current_price
        logger.info(f"   Current Price: ${current_price:.4f}")
        logger.info(f"   Current Value: ${current_value:.2f}")

        if current_value < MIN_POSITION_VALUE:
            logger.info(f"   ⏭️  Skipping - too small (< ${MIN_POSITION_VALUE})")
            continue

        # Check if should sell
        should_sell_flag, pnl, pnl_pct = should_sell(token_id, current_price, shares)

        if should_sell_flag:
            if sell_position(token_id, shares, current_price, pnl, pnl_pct):
                sold_count += 1
                total_pnl += pnl
        else:
            held_count += 1
            total_pnl += pnl

        logger.info("")

    # Summary
    logger.info("=" * 70)
    logger.info("SCAN COMPLETE")
    logger.info("=" * 70)
    logger.info(f"Positions sold: {sold_count}")
    logger.info(f"Positions held: {held_count}")
    logger.info(f"Session P&L: ${total_pnl:+.2f}")
    logger.info(f"Total All-Time P&L: ${trades_log['total_profit']:+.2f}")
    logger.info("=" * 70)


def main():
    """Main bot loop"""
    logger.info("")
    logger.info("=" * 70)
    logger.info("🤖 POLYMARKET PROFIT-TAKING BOT")
    logger.info("=" * 70)
    logger.info(f"Wallet: {WALLET_ADDRESS}")
    logger.info(f"Take Profit: +{TAKE_PROFIT_PCT}%")
    logger.info(f"Stop Loss: {STOP_LOSS_PCT}%")
    logger.info(f"Scan Interval: {SCAN_INTERVAL_SECONDS}s ({SCAN_INTERVAL_SECONDS // 60} minutes)")
    logger.info("=" * 70)
    logger.info("")
    logger.info("Bot is running... Press Ctrl+C to stop")
    logger.info("")

    scan_count = 0

    try:
        while True:
            scan_count += 1
            logger.info(f"⏰ Scan #{scan_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            try:
                scan_and_sell()
            except Exception as e:
                logger.error(f"Error during scan: {e}")
                import traceback
                traceback.print_exc()

            logger.info("")
            logger.info(f"💤 Next scan in {SCAN_INTERVAL_SECONDS // 60} minutes...")
            logger.info("")

            time.sleep(SCAN_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        logger.info("")
        logger.info("=" * 70)
        logger.info("🛑 Bot stopped by user")
        logger.info("=" * 70)
        logger.info(f"Total scans completed: {scan_count}")
        logger.info(f"Total all-time P&L: ${trades_log['total_profit']:+.2f}")
        logger.info("=" * 70)


if __name__ == "__main__":
    main()