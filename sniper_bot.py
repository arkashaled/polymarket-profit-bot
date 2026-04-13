#!/usr/bin/env python3
"""
Polymarket 98-Cent Sniper Bot
Scans ALL active markets every 10 seconds.
Buys $2 worth of EITHER the YES or NO token whenever its best-ask
price reaches $0.98 (98% implied probability of resolution).

Strategy: At $0.98 a token is almost certain to resolve at $1.00.
Spending $2 per trade captures the final $0.02/share upside.
Cost per trade: $2.00.  Max gain: ~$0.04 (2.04% ROI).
"""

import time
import json
import logging
import os
import requests
from urllib.parse import quote
from datetime import datetime, timezone
from dateutil import parser as dateparser
from typing import Dict, List, Optional

# ============================================================================
# PROXY SETUP — must happen before py_clob_client imports
# ============================================================================
PROXY_USER = os.environ.get("PROXY_USER", "").strip()
PROXY_PASS = os.environ.get("PROXY_PASS", "").strip()
PROXY_HOST = os.environ.get("PROXY_HOST", "pr.oxylabs.io:7777").strip()

if PROXY_USER and PROXY_PASS:
    # URL-encode credentials so special chars (=, ~, @) don't break the URL
    _enc_user = quote(PROXY_USER, safe="")
    _enc_pass = quote(PROXY_PASS, safe="")
    PROXY_URL = f"http://{_enc_user}:{_enc_pass}@{PROXY_HOST}"

    os.environ["HTTP_PROXY"]  = PROXY_URL
    os.environ["HTTPS_PROXY"] = PROXY_URL
    os.environ["http_proxy"]  = PROXY_URL
    os.environ["https_proxy"] = PROXY_URL

    import httpx

    # Patch httpx.Client so every new client uses the proxy
    _orig_init = httpx.Client.__init__
    def _proxy_init(self, *args, **kwargs):
        kwargs.setdefault("proxy", PROXY_URL)
        _orig_init(self, *args, **kwargs)
    httpx.Client.__init__ = _proxy_init

    # Also patch the shared http client inside py_clob_client
    try:
        import py_clob_client.http_helpers.helpers as _clob_helpers
        _clob_helpers._http_client = httpx.Client(
            proxy=PROXY_URL, http2=True, timeout=30
        )
        print("✅ ClobClient HTTP helper patched with proxy")
    except Exception as _e:
        print(f"⚠️  Could not patch ClobClient helper: {_e}")

    _SESSION = requests.Session()
    _SESSION.proxies = {"http": PROXY_URL, "https": PROXY_URL}
    print(f"✅ Proxy configured: {PROXY_HOST}")
else:
    _SESSION = requests.Session()
    print("⚠️  No proxy configured — running without proxy")

# ============================================================================
# CLOB client imports (after proxy patch)
# ============================================================================
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

# ============================================================================
# CONFIGURATION
# ============================================================================
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")
if not PRIVATE_KEY:
    raise ValueError("PRIVATE_KEY environment variable is not set")

CLOB_HOST     = "https://clob.polymarket.com"
GAMMA_API     = "https://gamma-api.polymarket.com"
CHAIN_ID      = 137

# Sniper parameters
TARGET_PRICE  = 0.98   # Buy when ask <= this
MAX_ASK_PRICE = 0.99   # Skip if ask > this (avoid overpaying right at $1.00)
BUY_BUDGET    = 2.00   # Dollars to spend per trade
SCAN_INTERVAL = 10     # Seconds between scans
MARKET_TTL    = 300    # Seconds between full market-list refreshes

# Guard rails
MIN_LIQUIDITY     = 500    # Minimum market liquidity (USD) — low, sniper strategy
COOLDOWN_SECONDS  = 86400  # 24 h — don't re-buy same token

# Files
LOG_FILE   = "sniper_bot.log"
TRADES_LOG = "sniper_trades.json"

# ============================================================================
# LOGGING
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# SETUP
# ============================================================================
from eth_account import Account
_account       = Account.from_key(PRIVATE_KEY)
WALLET_ADDRESS = _account.address

client = ClobClient(CLOB_HOST, key=PRIVATE_KEY, chain_id=CHAIN_ID)
client.set_api_creds(client.create_or_derive_api_creds())

# ============================================================================
# TRADE LOG
# ============================================================================
def load_trades() -> dict:
    try:
        with open(TRADES_LOG, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"buys": [], "total_deployed": 0.0, "total_shares": 0, "bought_tokens": []}

def save_trades(log: dict):
    with open(TRADES_LOG, "w") as f:
        json.dump(log, f, indent=2)

trades_log = load_trades()

# Permanent set of token IDs already traded — persists across restarts
_bought_tokens: set = set(trades_log.get("bought_tokens", []))

# ============================================================================
# MARKET DISCOVERY
# Fetches all active markets, exposing BOTH YES and NO token IDs.
# ============================================================================
_market_cache: List[dict] = []
_market_cache_ts: float = 0.0

def refresh_market_list() -> List[dict]:
    """
    Fetch all active Polymarket markets from the Gamma API.
    Returns a flat list of token-level dicts — one entry per YES token and
    one per NO token (where available), each carrying:
      token_id, question, outcome ("YES"/"NO"), gamma_ask, liquidity
    """
    global _market_cache, _market_cache_ts

    logger.info("🔄 Refreshing market list from Gamma API...")
    try:
        resp = _SESSION.get(
            f"{GAMMA_API}/markets",
            params={
                "active":    "true",
                "closed":    "false",
                "limit":     5000,
                "order":     "volume24hr",
                "ascending": "false",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning(f"Gamma API HTTP {resp.status_code}")
            return _market_cache

        raw = resp.json()
        if isinstance(raw, dict):
            raw = raw.get("data", raw.get("markets", []))

        tokens: List[dict] = []

        # End-of-month deadline: last moment of the current month
        now = datetime.now(timezone.utc)
        end_of_month = datetime(now.year, now.month + 1 if now.month < 12 else 1,
                                1, tzinfo=timezone.utc) if now.month < 12 else \
                       datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)

        for m in raw:
            if m.get("closed") or m.get("resolved") or not m.get("active", True):
                continue

            question = (m.get("question") or "").strip()
            if not question:
                continue

            # ── Resolution deadline filter ────────────────────────────────
            # Only trade markets that resolve this month or sooner
            end_date_str = (m.get("endDate") or m.get("end_date") or
                            m.get("endDateIso") or m.get("resolutionDate") or "")
            if end_date_str:
                try:
                    end_dt = dateparser.parse(str(end_date_str))
                    if end_dt.tzinfo is None:
                        end_dt = end_dt.replace(tzinfo=timezone.utc)
                    if end_dt > end_of_month:
                        continue  # resolves after this month — skip
                except Exception:
                    pass  # if we can't parse the date, allow it through

            # Parse token IDs — [YES_id, NO_id]
            raw_ids = m.get("clobTokenIds", m.get("clob_token_ids", []))
            if isinstance(raw_ids, str):
                try:
                    raw_ids = json.loads(raw_ids)
                except Exception:
                    continue
            if not raw_ids:
                continue

            liquidity = 0.0
            try:
                liquidity = float(m.get("liquidityClob") or m.get("liquidity") or 0)
            except (TypeError, ValueError):
                pass

            outcomes = m.get("outcomes", ["YES", "NO"])
            if isinstance(outcomes, str):
                try:
                    outcomes = json.loads(outcomes)
                except Exception:
                    outcomes = ["YES", "NO"]

            # Emit one dict per token (YES and NO)
            for idx, token_id in enumerate(raw_ids):
                label = outcomes[idx] if idx < len(outcomes) else ("YES" if idx == 0 else "NO")

                # Gamma sometimes returns per-outcome prices via outcomePrices
                gamma_ask = None
                try:
                    prices_raw = m.get("outcomePrices")
                    if isinstance(prices_raw, str):
                        prices_raw = json.loads(prices_raw)
                    if isinstance(prices_raw, list) and idx < len(prices_raw):
                        gamma_ask = float(prices_raw[idx])
                except Exception:
                    pass

                # Fall back to top-level bestAsk (only meaningful for YES token)
                if gamma_ask is None and idx == 0:
                    try:
                        gamma_ask = float(m.get("bestAsk") or m.get("best_ask") or 0)
                    except (TypeError, ValueError):
                        pass

                tokens.append({
                    "token_id":  str(token_id),
                    "question":  question,
                    "outcome":   label,
                    "gamma_ask": gamma_ask,
                    "liquidity": liquidity,
                })

        _market_cache    = tokens
        _market_cache_ts = time.time()
        logger.info(f"✅ Market list refreshed: {len(tokens)} outcome tokens "
                    f"across {len(raw)} markets")
        return tokens

    except Exception as e:
        logger.error(f"Market list refresh failed: {e}")
        return _market_cache


def get_market_tokens() -> List[dict]:
    """Return cached token list, refreshing when stale."""
    if time.time() - _market_cache_ts > MARKET_TTL or not _market_cache:
        return refresh_market_list()
    return _market_cache


# ============================================================================
# PRICE CONFIRMATION
# ============================================================================
def confirm_ask(token_id: str) -> Optional[float]:
    """Return live best-ask price from CLOB, or None on error."""
    try:
        data = client.get_price(token_id, "BUY")
        price = float(data.get("price", 0) or 0)
        return price if price > 0 else None
    except Exception as e:
        logger.debug(f"Price check failed {token_id[:20]}...: {e}")
        return None


# ============================================================================
# BALANCE CHECK
# ============================================================================
def get_usdc_balance() -> float:
    """Return current USDC balance in USD (float). Returns 0.0 on error."""
    try:
        from web3 import Web3
        _w3 = Web3(Web3.HTTPProvider(
            "https://rpc.ankr.com/polygon/e60a25f438f27fa6fc6a501b06f24aaed57b8f518096bc9d5666094a40a67fe7",
            request_kwargs={"timeout": 8}
        ))
        USDC = Web3.to_checksum_address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")
        abi = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],
                "name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"type":"function"}]
        bal = _w3.eth.contract(address=USDC, abi=abi).functions.balanceOf(WALLET_ADDRESS).call()
        return bal / 1e6
    except Exception as e:
        logger.debug(f"Balance check failed: {e}")
        return 0.0


# ============================================================================
# TRADE EXECUTION
# ============================================================================
def buy_token(token_id: str, question: str, outcome: str, ask_price: float) -> bool:
    """
    Place a BUY order spending up to BUY_BUDGET dollars.
    If balance < BUY_BUDGET, spends whatever is available.
    Minimum 1 share — skips if balance < ask_price.
    """
    usdc_balance = get_usdc_balance()
    max_affordable = int(usdc_balance / ask_price)   # whole shares only

    if max_affordable < 1:
        logger.warning(f"   ⚠️  Skipping — balance ${usdc_balance:.2f} < ${ask_price:.2f} (need at least 1 share)")
        return False

    budget_shares = int(BUY_BUDGET / ask_price)      # shares from $2 budget
    shares = min(budget_shares if budget_shares >= 1 else 1, max_affordable)
    cost     = shares * ask_price
    max_gain = shares * (1.0 - ask_price)

    logger.info("")
    logger.info("🎯 SNIPE TRIGGERED")
    logger.info(f"   Market   : {question[:72]}")
    logger.info(f"   Outcome  : {outcome}")
    logger.info(f"   Token    : {token_id[:22]}...")
    logger.info(f"   Ask      : ${ask_price:.4f}")
    logger.info(f"   Balance  : ${usdc_balance:.2f}  →  buying {shares} shares (~${BUY_BUDGET:.2f} budget)")
    logger.info(f"   Cost     : ${cost:.2f}")
    logger.info(f"   Max gain : ${max_gain:.2f}  (if resolves at $1.00)")

    try:
        order = OrderArgs(
            token_id=token_id,
            price=round(ask_price, 2),   # Polymarket tick: ≤2 decimal places
            size=float(shares),
            side=BUY,
            fee_rate_bps=0,
            nonce=0,
        )
        signed  = client.create_order(order)
        result  = client.post_order(signed, OrderType.GTC)

        order_id = result.get("orderID", "N/A")
        status   = result.get("status",  "N/A")

        logger.info(f"   ✅ ORDER POSTED  |  ID: {order_id}  |  Status: {status}")

        record = {
            "timestamp":  datetime.now().isoformat(),
            "market":     question,
            "token_id":   token_id,
            "outcome":    outcome,
            "ask_price":  ask_price,
            "shares":     shares,
            "cost":       cost,
            "order_id":   order_id,
            "status":     status,
        }
        trades_log["buys"].append(record)
        trades_log["total_deployed"] = round(
            trades_log.get("total_deployed", 0) + cost, 4
        )
        trades_log["total_shares"] = (
            trades_log.get("total_shares", 0) + shares
        )
        # Permanently mark this token as bought so it's never traded again
        _bought_tokens.add(token_id)
        trades_log["bought_tokens"] = list(_bought_tokens)
        save_trades(trades_log)
        return True

    except Exception as e:
        logger.error(f"   ❌ Order failed: {e}")
        return False


# ============================================================================
# MAIN LOOP
# ============================================================================
def run():
    logger.info("")
    logger.info("=" * 70)
    logger.info("🎯  POLYMARKET 98-CENT SNIPER BOT  (YES + NO)")
    logger.info("=" * 70)
    logger.info(f"Wallet        : {WALLET_ADDRESS}")
    logger.info(f"Target ask    : ${TARGET_PRICE:.2f}  (buy when live ask ≥ this)")
    logger.info(f"Max ask       : ${MAX_ASK_PRICE:.2f}  (skip if ask > this)")
    logger.info(f"Budget/trade  : ${BUY_BUDGET:.2f}")
    logger.info(f"Shares/trade  : ~{int(BUY_BUDGET / TARGET_PRICE)} (at target price)")
    logger.info(f"Max gain/trade: ~${int(BUY_BUDGET / TARGET_PRICE) * (1 - TARGET_PRICE):.2f}")
    logger.info(f"Scan interval : {SCAN_INTERVAL}s")
    logger.info(f"Market refresh: every {MARKET_TTL}s")
    logger.info(f"Cooldown      : {COOLDOWN_SECONDS // 3600}h per token")
    logger.info("=" * 70)
    logger.info("")

    scan_count    = 0
    buy_count     = 0
    session_start = datetime.now()

    logger.info(f"   Already traded {len(_bought_tokens)} tokens (will never re-buy these)")

    try:
        while True:
            scan_count  += 1
            cycle_start  = time.time()

            logger.info(
                f"⏱  Scan #{scan_count} | {datetime.now().strftime('%H:%M:%S')} "
                f"| Session buys: {buy_count} "
                f"| Deployed: ${trades_log.get('total_deployed', 0):.2f}"
            )

            tokens     = get_market_tokens()
            candidates = 0

            for t in tokens:
                token_id  = t["token_id"]
                question  = t["question"]
                outcome   = t["outcome"]
                gamma_ask = t.get("gamma_ask")
                liquidity = t.get("liquidity", 0)

                # ── Never re-buy a token already traded (permanent, survives restarts)
                if token_id in _bought_tokens:
                    continue

                # ── Liquidity floor ───────────────────────────────────────
                if liquidity < MIN_LIQUIDITY:
                    continue

                # ── Fast pre-filter via Gamma price ───────────────────────
                if gamma_ask is not None:
                    if gamma_ask < TARGET_PRICE or gamma_ask > MAX_ASK_PRICE:
                        continue

                candidates += 1

                # ── Live price confirmation from CLOB ─────────────────────
                live_ask = confirm_ask(token_id)
                if live_ask is None:
                    continue

                if live_ask < TARGET_PRICE or live_ask > MAX_ASK_PRICE:
                    continue

                # ── BUY ───────────────────────────────────────────────────
                ok = buy_token(token_id, question, outcome, live_ask)
                if ok:
                    buy_count += 1
                    time.sleep(2)

            if candidates == 0:
                logger.info("   No tokens in $0.98–$0.99 range this scan")

            elapsed   = time.time() - cycle_start
            sleep_for = max(0.1, SCAN_INTERVAL - elapsed)
            logger.info(f"   Scan took {elapsed:.1f}s | sleeping {sleep_for:.1f}s")
            time.sleep(sleep_for)

    except KeyboardInterrupt:
        duration = datetime.now() - session_start
        logger.info("")
        logger.info("=" * 70)
        logger.info("🛑 Sniper bot stopped")
        logger.info("=" * 70)
        logger.info(f"Session duration : {str(duration).split('.')[0]}")
        logger.info(f"Total scans      : {scan_count}")
        logger.info(f"Total buys       : {buy_count}")
        logger.info(f"Total deployed   : ${trades_log.get('total_deployed', 0):.2f}")
        logger.info(f"Total shares     : {trades_log.get('total_shares', 0)}")
        logger.info("=" * 70)


if __name__ == "__main__":
    run()
