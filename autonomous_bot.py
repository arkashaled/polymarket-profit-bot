#!/usr/bin/env python3
"""
Autonomous Polymarket Trading Bot - SPORTS ONLY
Uses GPT + (optional) web-search model to fetch real-time sports context and trade.
"""

import time
import json
import logging
import os
import requests
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY
from openai import OpenAI


# =========================
# LOGGING
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("autonomous_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# =========================
# CONFIG (NO SECRETS HERE)
# =========================
CHAIN_ID = 137
HOST = "https://clob.polymarket.com"

# Trading parameters
MAX_POSITION_USD = 40.0
CONFIDENCE_THRESHOLD = 0.72
MAX_SPREAD_PCT = 4.0
MIN_LIQUIDITY = 50000
SCAN_INTERVAL_SECONDS = 300
MAX_MARKETS_PER_SCAN = 10000

# Only sports keywords (keep improving this list)
SPORTS_KEYWORDS = [
    "win", "winner", "champion", "championship", "title",
    "match", "game", "series", "finals", "playoffs", "conference",
    "qualify", "advance", "reach", "make the playoffs", "top", "seed",
    "goal", "score", "points", "rebounds", "assists",
    "set", "ace", "break", "tournament",
    "nfl", "nba", "mlb", "nhl", "ufc", "atp", "wta", "fifa", "uefa",
    "premier league", "laliga", "bundesliga", "serie a", "ucl", "euros", "world cup",
    "vs", " v ", "over", "under", "spread", "handicap", "moneyline", "o/u", "presidential", "2028", "Democratic"
]

ABSURD_KEYWORDS = [
    "jesus", "christ", "god", "alien", "ufo", "extraterrestrial", "rapture",
    "apocalypse", "end of the world", "zombie", "vampire", "dragon", "unicorn",
    "time travel", "flat earth", "illuminati", "bigfoot", "loch ness",
    "second coming", "antichrist", "armageddon", "messiah", "resurrection",
    "gta vi", "gta 6", "Bitcoin", "BTC", "Iran"
]


@dataclass
class Market:
    token_id: str
    question: str
    price: float
    spread_pct: float
    liquidity: float


def is_absurd_market(question: str) -> bool:
    q = question.lower()
    return any(k in q for k in ABSURD_KEYWORDS)


def detect_market_category(question: str) -> str:
    """Binary classifier: SPORTS or OTHER."""
    q = question.lower()
    if any(k in q for k in SPORTS_KEYWORDS):
        return "SPORTS"
    return "OTHER"


def fetch_real_time_data_sports(question: str, openai_client: OpenAI) -> str:
    """
    Sports-only real-time context fetch.
    Tries gpt-4o-search-preview first, then falls back to gpt-4o.
    """
    today = datetime.now().strftime("%B %d, %Y")

    search_prompt = f"""Search for current information about this sports prediction market: "{question}"

Find and provide:
1. Recent match results or standings (with dates)
2. Injuries / lineup / suspensions news
3. Head-to-head stats (if relevant)
4. Current form (last 5 matches) with scores
5. Bookmaker odds from multiple books (and implied probability)
6. Any relevant news from the last 48 hours

Today's date: {today}
Be specific with numbers, dates, and sources.
"""

    # First attempt: OpenAI search model (if you have access)
    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o-search-preview",
            messages=[{"role": "user", "content": search_prompt}],
            max_tokens=2000,
        )
        content = (resp.choices[0].message.content or "").strip()
        if len(content) >= 120:
            return content
        raise RuntimeError("Search response too short")
    except Exception as e:
        logger.debug(f"Web-search model failed or unavailable, fallback to gpt-4o: {e}")

    # Fallback: GPT-4o without browsing
    try:
        fallback_prompt = f"""You are analyzing a sports prediction market: "{question}"
Provide the best available context from your knowledge:
- Typical base rates / league tendencies
- Key factors that drive outcomes (injuries, schedule congestion, home/away, motivation)
- What data you would normally check
State clearly what you *don't* know without live browsing.

Today's date: {today}
"""
        resp = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": fallback_prompt}],
            temperature=0.2,
            max_tokens=1500,
        )
        return (resp.choices[0].message.content or "Limited context available.").strip()
    except Exception:
        return "Limited context available."


class AutonomousBot:
    def __init__(self):
        logger.info("Initializing SPORTS-only Autonomous Trading Bot...")

        import os
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")
if not PRIVATE_KEY:
    raise ValueError("PRIVATE_KEY environment variable is not set")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set")


       # if not private_key:
            raise SystemExit("Missing env var POLYMARKET_PRIVATE_KEY")
        if not openai_key:
            raise SystemExit("Missing env var OPENAI_API_KEY")

        from eth_account import Account
        acct = Account.from_key(private_key)
        self.wallet_address = acct.address

        self.clob = ClobClient(HOST, key=private_key, chain_id=CHAIN_ID)
        self.clob.set_api_creds(self.clob.create_or_derive_api_creds())

        self.openai = OpenAI(api_key=openai_key)

        self.scans_completed = 0
        self.trades_executed = 0
        self.total_deployed = 0.0
        self.recent_purchases: Dict[str, datetime] = {}

        logger.info("✅ Bot initialized")
        logger.info(f"Wallet: {self.wallet_address}")
        logger.info("Mode: SPORTS ONLY")

    def find_markets(self) -> List[Market]:
        """Find tradeable SPORTS markets only."""
        try:
            logger.info("🔍 Scanning for SPORTS markets...")

            response = requests.get(
                "https://gamma-api.polymarket.com/events",
                params={
                    "limit": 10000,
                    "closed": "false",
                    "order": "liquidity",
                    "ascending": "false"
                },
                timeout=10
            )

            if response.status_code != 200:
                logger.error(f"Failed to fetch markets (HTTP {response.status_code})")
                return []

            events = response.json()
            markets: List[Market] = []

            for event in events:
                if len(markets) >= MAX_MARKETS_PER_SCAN:
                    break

                for market in event.get("markets", []):
                    if len(markets) >= MAX_MARKETS_PER_SCAN:
                        break

                    question = market.get("question", "") or ""
                    if not question:
                        continue

                    # Hard block meme/unverifiable
                    if is_absurd_market(question):
                        continue

                    # SPORTS ONLY
                    if detect_market_category(question) != "SPORTS":
                        continue

                    # Optional stricter sports heuristic: most match markets include vs/v
                    ql = question.lower()


                    liquidity = float(market.get("liquidityClob", 0) or 0)
                    if liquidity < MIN_LIQUIDITY:
                        continue

                    token_ids_raw = market.get("clobTokenIds", [])
                    if isinstance(token_ids_raw, str):
                        try:
                            token_ids = json.loads(token_ids_raw)
                        except Exception:
                            continue
                    else:
                        token_ids = token_ids_raw

                    if not token_ids:
                        continue

                    token_id = token_ids[0]

                    try:
                        buy_price = self.clob.get_price(token_id, "BUY")
                        sell_price = self.clob.get_price(token_id, "SELL")

                        best_bid = float(buy_price.get("price", 0) or 0)
                        best_ask = float(sell_price.get("price", 0) or 0)
                        if best_bid <= 0 or best_ask <= 0:
                            continue

                        mid_price = (best_bid + best_ask) / 2.0
                        spread = best_ask - best_bid
                        spread_pct = (spread / best_ask) * 100.0

                        if spread_pct > MAX_SPREAD_PCT:
                            continue

                        # Avoid very high/low probs where edge is harder / fills worse
                        if mid_price < 0.20 or mid_price > 0.80:
                            continue

                        markets.append(Market(
                            token_id=token_id,
                            question=question,
                            price=mid_price,
                            spread_pct=spread_pct,
                            liquidity=liquidity
                        ))

                    except Exception:
                        continue

            logger.info(f"✅ Found {len(markets)} SPORTS markets")
            return markets

        except Exception as e:
            logger.error(f"Market scan failed: {e}")
            return []

    def analyze_market(self, market: Market) -> Optional[Dict]:
        """Analyze SPORTS market with real-time context + GPT."""
        try:
            # Defensive: SPORTS ONLY
            if detect_market_category(market.question) != "SPORTS":
                return None

            buy_price_data = self.clob.get_price(market.token_id, "BUY")
            sell_price_data = self.clob.get_price(market.token_id, "SELL")

            best_bid = float(buy_price_data.get("price", 0) or 0)
            best_ask = float(sell_price_data.get("price", 0) or 0)
            if best_bid <= 0 or best_ask <= 0:
                return None

            mid_price = (best_bid + best_ask) / 2.0

            logger.info("   🌐 Fetching sports context...")
            real_time_context = fetch_real_time_data_sports(market.question, self.openai)
            logger.info(f"   ✅ Context fetched ({len(real_time_context)} chars)")

            today = datetime.now().strftime("%B %d, %Y")

            prompt = f"""You are an expert SPORTS prediction market trader with access to real-time context.
Today's date: {today}

MARKET: {market.question}
YOU ARE EVALUATING: Buying YES outcome tokens.

CURRENT MARKET DATA:
- Implied YES probability (mid): {mid_price * 100:.1f}%
- Buy (ask): ${best_ask:.4f}
- Sell (bid): ${best_bid:.4f}
- Spread: {market.spread_pct:.1f}%
- Liquidity: ${market.liquidity:,.0f}

REAL-TIME CONTEXT:
{real_time_context}

TASK:
Estimate TRUE probability for YES based on the context.
BUY only if:
- fair_value >= market_price + 0.05 (>=5% absolute edge)
- confidence >= 0.72
- evidence is concrete (scores, injuries, odds), not vibes

Respond ONLY with JSON:
{{
  "action": "BUY or HOLD",
  "confidence": 0.0-1.0,
  "fair_value": 0.0-1.0,
  "market_price": {mid_price:.4f},
  "edge": "fair_value - market_price (absolute)",
  "key_evidence": "top 2-3 concrete data points",
  "main_risk": "biggest risk",
  "reasoning": "brief, specific"
}}
"""

            resp = self.openai.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=900
            )

            content = (resp.choices[0].message.content or "").strip()
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error: {e} content={content[:200]}")
                return None

            required = ["action", "confidence", "fair_value"]
            if not all(k in data for k in required):
                logger.error(f"Missing required fields: {data}")
                return None

            action = str(data["action"]).upper()
            confidence = float(data["confidence"])
            fair_value = float(data["fair_value"])

            logger.info(f"   📊 Decision: {action}")
            logger.info(f"   🎯 Fair: {fair_value:.0%} vs Market: {mid_price:.0%}")
            logger.info(f"   💪 Confidence: {confidence:.0%}")
            logger.info(f"   🧾 Evidence: {data.get('key_evidence','N/A')}")
            logger.info(f"   ⚠️  Risk: {data.get('main_risk','N/A')}")

            # Guardrails
            if action != "BUY":
                return None

            edge_abs = fair_value - mid_price
            if edge_abs < 0.05:
                logger.info("   ⏭️  HOLD: Edge < 5%")
                return None

            if confidence < CONFIDENCE_THRESHOLD:
                logger.info("   ⏭️  HOLD: Confidence below threshold")
                return None

            if fair_value < 0.60:
                logger.info("   ⏭️  HOLD: Fair value < 60% guardrail")
                return None

            return {
                "action": "BUY",
                "confidence": confidence,
                "price": best_ask,
                "reasoning": data.get("reasoning", ""),
                "key_evidence": data.get("key_evidence", ""),
                "main_risk": data.get("main_risk", ""),
                "fair_value": fair_value
            }

        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return None

    def execute_trade(self, market: Market, signal: Dict) -> bool:
        """Execute BUY order."""
        try:
            price = float(signal["price"])
            shares = MAX_POSITION_USD / price

            logger.info("\n💰 EXECUTING BUY")
            logger.info(f"   Market: {market.question[:80]}")
            logger.info(f"   Shares: {shares:.2f} @ ${price:.4f}")
            logger.info(f"   Cost: ${shares * price:.2f}")
            logger.info(f"   Fair: {float(signal.get('fair_value', 0)):.0%}")
            logger.info(f"   Evidence: {str(signal.get('key_evidence',''))[:120]}")

            order = OrderArgs(
                token_id=market.token_id,
                price=price,
                size=shares,
                side=BUY,
                fee_rate_bps=0,
                nonce=0
            )

            signed_order = self.clob.create_order(order)
            result = self.clob.post_order(signed_order, OrderType.GTC)

            logger.info("   ✅ ORDER POSTED")
            logger.info(f"   Order ID: {result.get('orderID', 'N/A')}")
            logger.info(f"   Status: {result.get('status', 'N/A')}")

            with open("trades_log.json", "a") as f:
                trade_record = {
                    "timestamp": datetime.now().isoformat(),
                    "market": market.question,
                    "token_id": market.token_id,
                    "action": "BUY",
                    "price": price,
                    "shares": shares,
                    "confidence": signal.get("confidence"),
                    "fair_value": signal.get("fair_value"),
                    "key_evidence": signal.get("key_evidence", ""),
                    "main_risk": signal.get("main_risk", ""),
                    "reasoning": signal.get("reasoning", ""),
                    "order_id": result.get("orderID")
                }
                f.write(json.dumps(trade_record) + "\n")

            self.trades_executed += 1
            self.total_deployed += MAX_POSITION_USD
            return True

        except Exception as e:
            logger.error(f"❌ Trade failed: {e}")
            return False

    def run_scan(self):
        """Run one scan cycle."""
        try:
            logger.info("")
            logger.info("=" * 70)
            logger.info(f"🔄 SCAN #{self.scans_completed + 1} (SPORTS ONLY)")
            logger.info("=" * 70)

            markets = self.find_markets()
            if not markets:
                logger.info("No tradeable sports markets found")
                return

            for market in markets:
                # Cooldown: don’t re-buy same token within 1 hour
                if market.token_id in self.recent_purchases:
                    delta = (datetime.now() - self.recent_purchases[market.token_id]).total_seconds()
                    if delta < 3600:
                        continue

                logger.info(f"\n📊 Analyzing: {market.question[:80]}...")
                logger.info(f"   Price: {market.price:.0%}, Spread: {market.spread_pct:.1f}%, Liq: ${market.liquidity:,.0f}")

                signal = self.analyze_market(market)
                if signal:
                    ok = self.execute_trade(market, signal)
                    if ok:
                        self.recent_purchases[market.token_id] = datetime.now()
                        time.sleep(10)
                else:
                    logger.info("   💤 No BUY signal")

                time.sleep(2.5)

            self.scans_completed += 1

            logger.info("")
            logger.info("=" * 70)
            logger.info("📊 SESSION STATS")
            logger.info("=" * 70)
            logger.info(f"Scans: {self.scans_completed}")
            logger.info(f"Trades: {self.trades_executed}")
            logger.info(f"Deployed: ${self.total_deployed:.2f}")
            logger.info("=" * 70)

        except Exception as e:
            logger.error(f"Scan failed: {e}")
            import traceback
            traceback.print_exc()

    def run(self):
        logger.info("")
        logger.info("=" * 70)
        logger.info("🤖 AUTONOMOUS BOT STARTED (SPORTS ONLY)")
        logger.info("=" * 70)
        logger.info(f"Max position: ${MAX_POSITION_USD}")
        logger.info(f"Confidence threshold: {CONFIDENCE_THRESHOLD:.0%}")
        logger.info(f"Max spread: {MAX_SPREAD_PCT:.1f}%")
        logger.info(f"Min liquidity: {MIN_LIQUIDITY}")
        logger.info(f"Scan interval: {SCAN_INTERVAL_SECONDS}s")
        logger.info("=" * 70)

        try:
            while True:
                self.run_scan()
                logger.info(f"\n⏰ Next scan in {SCAN_INTERVAL_SECONDS}s...")
                time.sleep(SCAN_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            logger.info("\n🛑 Bot stopped by user")
            logger.info(f"Final: {self.trades_executed} trades, ${self.total_deployed:.2f} deployed")
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    bot = AutonomousBot()
    bot.run()
