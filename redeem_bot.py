#!/usr/bin/env python3
"""
Polymarket Auto-Redeem Bot
Runs every 5 minutes. For each open position:
  1. If market resolved on-chain → redeem via CTF contract (collect $1.00/share)
  2. If price >= $0.97 on CLOB   → sell immediately (lock in near-full value)
  3. Otherwise                   → hold
"""

import time
import json
import logging
import os
from urllib.parse import quote
from datetime import datetime
from typing import Optional

# ============================================================================
# PROXY SETUP — before py_clob_client imports
# ============================================================================
PROXY_USER = os.environ.get("PROXY_USER", "").strip()
PROXY_PASS = os.environ.get("PROXY_PASS", "").strip()
PROXY_HOST = os.environ.get("PROXY_HOST", "pr.oxylabs.io:7777").strip()

if PROXY_USER and PROXY_PASS:
    PROXY_URL = f"http://{quote(PROXY_USER,safe='')}:{quote(PROXY_PASS,safe='')}@{PROXY_HOST}"
    os.environ["HTTP_PROXY"]  = PROXY_URL
    os.environ["HTTPS_PROXY"] = PROXY_URL
    os.environ["http_proxy"]  = PROXY_URL
    os.environ["https_proxy"] = PROXY_URL
    import httpx
    _orig_init = httpx.Client.__init__
    def _proxy_init(self, *args, **kwargs):
        kwargs.setdefault("proxy", PROXY_URL)
        _orig_init(self, *args, **kwargs)
    httpx.Client.__init__ = _proxy_init
    try:
        import py_clob_client.http_helpers.helpers as _clob_helpers
        _clob_helpers._http_client = httpx.Client(proxy=PROXY_URL, http2=True, timeout=30)
        print("✅ ClobClient patched with proxy")
    except Exception as e:
        print(f"⚠️  Proxy patch: {e}")
    import requests as _req
    _SESSION = _req.Session()
    _SESSION.proxies = {"http": PROXY_URL, "https": PROXY_URL}
else:
    import requests as _req
    _SESSION = _req.Session()

# ============================================================================
# CLOB + Web3 imports
# ============================================================================
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import SELL
from web3 import Web3
from eth_account import Account

# ============================================================================
# CONFIG
# ============================================================================
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")
if not PRIVATE_KEY:
    raise ValueError("PRIVATE_KEY not set")

CLOB_HOST      = "https://clob.polymarket.com"
CHAIN_ID       = 137
WALLET         = Account.from_key(PRIVATE_KEY).address
SCAN_INTERVAL  = 300   # 5 minutes

LOG_FILE    = "redeem_bot.log"
REDEEM_LOG  = "redeem_log.json"

# Polygon contracts
USDC_ADDR = Web3.to_checksum_address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")
CTF_ADDR  = Web3.to_checksum_address("0x4D97DCd97eC945f40cF65F87097ACe5EA0476045")

# ============================================================================
# LOGGING
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ============================================================================
# SETUP
# ============================================================================
client = ClobClient(CLOB_HOST, key=PRIVATE_KEY, chain_id=CHAIN_ID)
client.set_api_creds(client.create_or_derive_api_creds())

# Web3 — direct (no proxy) for on-chain calls
_w3 = Web3(Web3.HTTPProvider(
    "https://rpc.ankr.com/polygon/e60a25f438f27fa6fc6a501b06f24aaed57b8f518096bc9d5666094a40a67fe7",
    request_kwargs={"timeout": 10}
))
_account = Account.from_key(PRIVATE_KEY)

CTF_ABI = [
    {
        "inputs": [
            {"name": "account", "type": "address"},
            {"name": "id", "type": "uint256"}
        ],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "collateralToken", "type": "address"},
            {"name": "parentCollectionId", "type": "bytes32"},
            {"name": "conditionId", "type": "bytes32"},
            {"name": "indexSets", "type": "uint256[]"}
        ],
        "name": "redeemPositions",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]
_ctf = _w3.eth.contract(address=CTF_ADDR, abi=CTF_ABI)

# ============================================================================
# REDEEM LOG
# ============================================================================
def load_log():
    try:
        with open(REDEEM_LOG) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"redeems": [], "sells": [], "total_collected": 0.0}

def save_log(log):
    with open(REDEEM_LOG, "w") as f:
        json.dump(log, f, indent=2)

redeem_log = load_log()

# ============================================================================
# HELPERS
# ============================================================================
def get_positions():
    """Fetch all open positions from Polymarket data API."""
    try:
        r = _SESSION.get(
            "https://data-api.polymarket.com/positions",
            params={"user": WALLET, "limit": 200},
            timeout=12
        )
        data = r.json()
        return data if isinstance(data, list) else data.get("positions", data.get("data", []))
    except Exception as e:
        logger.error(f"Failed to fetch positions: {e}")
        return []


def get_clob_bid(token_id: str) -> Optional[float]:
    """Get best bid (sell price) from CLOB. Returns None if market resolved/no book."""
    try:
        data = client.get_price(token_id, "SELL")
        price = float(data.get("price", 0) or 0)
        return price if price > 0 else None
    except Exception as e:
        err = str(e)
        if "404" in err or "No orderbook" in err or "no orderbook" in err.lower():
            return None   # market resolved
        logger.debug(f"Bid check failed {token_id[:20]}...: {e}")
        return None


def check_market_resolved(condition_id: str, token_id: str) -> tuple:
    """
    Returns (is_resolved, winning_price).
    Checks Gamma API for resolved status and CLOB for price.
    A market is truly resolved when Gamma marks it resolved=True.
    """
    resolved = False
    winning_price = None

    # Check Gamma API
    try:
        r = _SESSION.get(
            "https://gamma-api.polymarket.com/markets",
            params={"conditionId": condition_id},
            timeout=8
        )
        markets = r.json()
        if isinstance(markets, dict):
            markets = markets.get("data", markets.get("markets", [markets]))
        if markets:
            m = markets[0]
            resolved = bool(m.get("resolved") or m.get("closed"))
    except Exception:
        pass

    # Get current CLOB bid price regardless
    try:
        data = client.get_price(token_id, "SELL")
        p = float(data.get("price", 0) or 0)
        if p > 0:
            winning_price = p
    except Exception:
        pass

    return resolved, winning_price


def sell_via_clob(token_id: str, shares: float, bid: float, title: str, outcome: str) -> bool:
    """Sell position on CLOB at current bid price."""
    logger.info(f"💸 SELLING via CLOB: {title[:60]}")
    logger.info(f"   Outcome: {outcome} | Shares: {shares:.2f} | Bid: ${bid:.4f}")
    logger.info(f"   Proceeds: ${shares * bid:.2f}")
    try:
        order = OrderArgs(
            token_id=token_id,
            price=round(bid, 2),
            size=round(shares, 2),
            side=SELL,
            fee_rate_bps=0,
            nonce=0,
        )
        signed = client.create_order(order)
        result = client.post_order(signed, OrderType.GTC)
        order_id = result.get("orderID", "N/A")
        status   = result.get("status", "N/A")
        logger.info(f"   ✅ SOLD | Order: {order_id} | Status: {status}")

        redeem_log["sells"].append({
            "timestamp": datetime.now().isoformat(),
            "market": title,
            "outcome": outcome,
            "token_id": token_id,
            "shares": shares,
            "bid": bid,
            "proceeds": round(shares * bid, 4),
            "order_id": order_id,
        })
        redeem_log["total_collected"] = round(
            redeem_log.get("total_collected", 0) + shares * bid, 4
        )
        save_log(redeem_log)
        return True
    except Exception as e:
        logger.error(f"   ❌ CLOB sell failed: {e}")
        return False


def redeem_on_chain(token_id: str, condition_id: str, shares: float, title: str) -> bool:
    """
    Redeem a resolved winning position directly on the Polygon CTF contract.
    token_id is the ERC-1155 ID (decimal string).
    condition_id is the hex conditionId from Polymarket.
    """
    logger.info(f"🔗 ON-CHAIN REDEEM: {title[:60]}")
    try:
        # Verify we actually hold the token
        bal = _ctf.functions.balanceOf(WALLET, int(token_id)).call()
        if bal == 0:
            logger.info("   Token balance = 0, nothing to redeem")
            return False

        logger.info(f"   Token balance: {bal / 1e6:.4f} shares")

        # conditionId as bytes32
        cid_bytes = bytes.fromhex(condition_id.replace("0x", "").zfill(64))

        # Determine winning indexSet: 1 = YES won, 2 = NO won
        # We try both; the contract ignores zero-balance positions
        nonce = _w3.eth.get_transaction_count(WALLET)
        gas_price = _w3.eth.gas_price

        tx = _ctf.functions.redeemPositions(
            USDC_ADDR,
            b'\x00' * 32,          # parentCollectionId = 0 (top-level)
            cid_bytes,
            [1, 2]                 # redeem both YES and NO slots (contract pays winning one)
        ).build_transaction({
            "from": WALLET,
            "gas": 300000,
            "gasPrice": gas_price,
            "nonce": nonce,
        })

        signed = _account.sign_transaction(tx)
        raw    = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction", None)
        tx_hash = _w3.eth.send_raw_transaction(raw)
        logger.info(f"   ✅ Redeem TX: https://polygonscan.com/tx/{tx_hash.hex()}")

        # Wait for confirmation
        receipt = _w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        usdc_received = bal / 1e6  # approx (winning token → $1.00 each)
        logger.info(f"   ✅ Confirmed! Gas used: {receipt['gasUsed']} | ~${usdc_received:.2f} USDC received")

        redeem_log["redeems"].append({
            "timestamp": datetime.now().isoformat(),
            "market": title,
            "token_id": token_id,
            "condition_id": condition_id,
            "shares": bal / 1e6,
            "usdc_received": usdc_received,
            "tx": tx_hash.hex(),
        })
        redeem_log["total_collected"] = round(
            redeem_log.get("total_collected", 0) + usdc_received, 4
        )
        save_log(redeem_log)
        return True

    except Exception as e:
        logger.error(f"   ❌ On-chain redeem failed: {e}")
        return False

# ============================================================================
# MAIN SCAN
# ============================================================================
def scan():
    logger.info("")
    logger.info("=" * 65)
    logger.info(f"🔍 REDEEM SCAN — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 65)

    positions = get_positions()
    if not positions:
        logger.info("No open positions found.")
        return

    logger.info(f"Checking {len(positions)} positions...\n")

    sold = redeemed = held = 0

    for p in positions:
        token_id     = str(p.get("asset") or p.get("asset_id") or p.get("token_id") or "")
        condition_id = str(p.get("conditionId") or p.get("condition_id") or "")
        title        = str(p.get("title") or p.get("market") or p.get("question") or "Unknown")
        outcome      = str(p.get("outcome", "?"))
        shares       = float(p.get("size") or p.get("shares") or 0)
        cur_val      = float(p.get("currentValue") or p.get("value") or 0)

        if shares < 0.01 or not token_id:
            continue

        logger.info(f"📊 {title[:58]}")
        logger.info(f"   Outcome: {outcome} | Shares: {shares:.2f} | Value: ${cur_val:.2f}")

        # ── Check if market is confirmed resolved ─────────────────────────
        is_resolved, bid = check_market_resolved(condition_id, token_id)

        logger.info(f"   Resolved: {is_resolved} | CLOB bid: ${bid:.4f}" if bid else f"   Resolved: {is_resolved} | CLOB bid: none")

        if not is_resolved:
            logger.info("   ⏳ Market not yet resolved — holding for full $1.00 redemption")
            held += 1

        elif bid is not None and bid > 0:
            # Resolved and CLOB still has a book — sell via CLOB at market
            logger.info("   ✅ Market resolved — selling via CLOB")
            ok = sell_via_clob(token_id, shares, bid, title, outcome)
            if ok:
                sold += 1
            else:
                held += 1

        else:
            # Resolved and no CLOB book — redeem on-chain at $1.00
            logger.info("   ✅ Market resolved, no CLOB book — redeeming on-chain at $1.00/share")
            if condition_id:
                ok = redeem_on_chain(token_id, condition_id, shares, title)
                if ok:
                    redeemed += 1
                else:
                    held += 1
            else:
                logger.info("   ⚠️  No conditionId — cannot redeem on-chain")
                held += 1

        logger.info("")

    logger.info("=" * 65)
    logger.info(f"SCAN COMPLETE | Sold: {sold} | Redeemed: {redeemed} | Held: {held}")
    logger.info(f"Total collected all-time: ${redeem_log.get('total_collected', 0):.2f}")
    logger.info("=" * 65)


def run():
    logger.info("")
    logger.info("=" * 65)
    logger.info("🔄  POLYMARKET AUTO-REDEEM BOT")
    logger.info("=" * 65)
    logger.info(f"Wallet         : {WALLET}")
    logger.info(f"Strategy       : wait for full resolution at $1.00/share")
    logger.info(f"Scan interval  : every {SCAN_INTERVAL // 60} minutes")
    logger.info("=" * 65)

    scan_count = 0
    try:
        while True:
            scan_count += 1
            try:
                scan()
            except Exception as e:
                logger.error(f"Scan error: {e}")
            logger.info(f"\n⏰ Next scan in {SCAN_INTERVAL // 60} minutes...\n")
            time.sleep(SCAN_INTERVAL)
    except KeyboardInterrupt:
        logger.info("\n🛑 Redeem bot stopped")
        logger.info(f"Total collected: ${redeem_log.get('total_collected', 0):.2f}")


if __name__ == "__main__":
    run()
