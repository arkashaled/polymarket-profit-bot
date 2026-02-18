#!/usr/bin/env python3
"""
Autonomous Polymarket Trading Bot - Enhanced with Real-Time Data
Uses web search + GPT-4o to make informed trading decisions across ALL market types
"""

import sys
import time
import json
import logging
import requests
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY
from openai import OpenAI

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('autonomous_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# CONFIGURATION
import os
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")
if not PRIVATE_KEY:
    raise ValueError("PRIVATE_KEY environment variable is not set")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set")
CHAIN_ID = 137
HOST = "https://clob.polymarket.com"

# Trading parameters
MAX_POSITION_USD = 15.0
CONFIDENCE_THRESHOLD = 0.72
MAX_SPREAD_PCT = 4.0
MIN_LIQUIDITY = 50000
SCAN_INTERVAL_SECONDS = 300
MAX_MARKETS_PER_SCAN = 1000

# Market category detection keywords
SPORTS_KEYWORDS = ['win', 'score', 'goal', 'match', 'game', 'championship', 'league',
                   'cup', 'team', 'player', 'fc', 'nfl', 'nba', 'mlb', 'nhl', 'ufc',
                   'tournament', 'playoff', 'vs', 'over', 'under', 'spread']

POLITICS_KEYWORDS = ['president', 'election', 'vote', 'congress', 'senate', 'party',
                     'democrat', 'republican', 'trump', 'biden', 'policy', 'bill',
                     'governor', 'primary', 'candidate', 'approval', 'poll']

CRYPTO_KEYWORDS = ['bitcoin', 'btc', 'eth', 'ethereum', 'crypto', 'price', 'token',
                   'blockchain', 'defi', 'nft', 'altcoin', 'solana', 'binance',
                   'coinbase', 'sec', 'etf', 'market cap']

FINANCIAL_KEYWORDS = ['fed', 'interest rate', 'inflation', 'gdp', 'recession', 'market',
                      'stock', 'ipo', 'earnings', 'revenue', 'merger', 'acquisition',
                      'bankruptcy', 'economy', 'treasury', 'bond', 'yield']

GEOPOLITICAL_KEYWORDS = ['war', 'ceasefire', 'peace', 'nato', 'russia', 'ukraine',
                         'china', 'iran', 'israel', 'sanctions', 'military', 'treaty',
                         'diplomacy', 'conflict', 'nuclear']


@dataclass
class Market:
    token_id: str
    question: str
    price: float
    spread_pct: float
    liquidity: float


ABSURD_KEYWORDS = [
    'jesus', 'christ', 'god', 'alien', 'ufo', 'extraterrestrial', 'rapture',
    'apocalypse', 'end of the world', 'zombie', 'vampire', 'dragon', 'unicorn',
    'time travel', 'flat earth', 'illuminati', 'bigfoot', 'loch ness',
    'second coming', 'antichrist', 'armageddon', 'messiah', 'resurrection',
    'gta vi', 'gta 6',  # meme markets involving GTA release
]


def is_absurd_market(question: str) -> bool:
    """Block joke/meme/unverifiable markets that GPT cannot reason about reliably"""
    q = question.lower()
    return any(k in q for k in ABSURD_KEYWORDS)


def detect_market_category(question: str) -> str:
    """Detect what type of market this is"""
    q = question.lower()

    if any(k in q for k in CRYPTO_KEYWORDS):
        return "CRYPTO"
    elif any(k in q for k in POLITICS_KEYWORDS):
        return "POLITICS"
    elif any(k in q for k in SPORTS_KEYWORDS):
        return "SPORTS"
    elif any(k in q for k in FINANCIAL_KEYWORDS):
        return "FINANCIAL"
    elif any(k in q for k in GEOPOLITICAL_KEYWORDS):
        return "GEOPOLITICAL"
    else:
        return "GENERAL"


def fetch_real_time_data(question: str, category: str, openai_client: OpenAI) -> str:
    """Use GPT-4o with web search to fetch real-time context for any market"""
    try:
        # Build targeted search query based on market category
        today = datetime.now().strftime("%B %Y")

        if category == "SPORTS":
            search_prompt = f"""Search for current information about this prediction market: "{question}"

Find and provide:
1. Recent match results or current standings
2. Team/player injuries or lineup news
3. Head-to-head statistics
4. Current form (last 5 games)
5. Expert predictions and odds from multiple bookmakers
6. Any relevant news from the last 48 hours

Today's date: {today}
Be specific with numbers and statistics."""

        elif category == "CRYPTO":
            search_prompt = f"""Search for current information about this prediction market: "{question}"

Find and provide:
1. Current price and 24h/7d price movement
2. Recent news or events affecting this
3. On-chain data or trading volume if relevant
4. Expert analyst predictions
5. Key support/resistance levels
6. Any regulatory news

Today's date: {today}
Be specific with numbers."""

        elif category == "POLITICS":
            search_prompt = f"""Search for current information about this prediction market: "{question}"

Find and provide:
1. Latest polling data with sources
2. Recent relevant news (last 48 hours)
3. Expert political analyst views
4. Prediction market consensus from other platforms (Metaculus, PredictIt)
5. Historical base rates for similar events
6. Key factors that could change the outcome

Today's date: {today}
Be specific with poll numbers and dates."""

        elif category == "FINANCIAL":
            search_prompt = f"""Search for current information about this prediction market: "{question}"

Find and provide:
1. Current market data and recent trends
2. Expert economist or analyst forecasts
3. Fed or government statements if relevant
4. Historical precedents
5. Key upcoming events that could affect the outcome
6. Consensus estimate from major banks/institutions

Today's date: {today}
Be specific with numbers and dates."""

        elif category == "GEOPOLITICAL":
            search_prompt = f"""Search for current information about this prediction market: "{question}"

Find and provide:
1. Latest news from last 48 hours
2. Official statements from key parties
3. Expert geopolitical analyst views
4. Historical precedents for similar situations
5. Key upcoming events or deadlines
6. Prediction market consensus from other platforms

Today's date: {today}
Be specific."""

        else:
            search_prompt = f"""Search for current information about this prediction market: "{question}"

Find and provide:
1. Latest relevant news (last 48 hours)
2. Expert opinions or forecasts
3. Historical base rates for similar events
4. Key factors affecting the outcome
5. Any data that helps assess probability

Today's date: {today}
Be specific with numbers."""

        # Use gpt-4o-search-preview for real web search (OpenAI's search model)
        response = openai_client.chat.completions.create(
            model="gpt-4o-search-preview",
            messages=[{"role": "user", "content": search_prompt}],
            max_tokens=2000
        )

        # Extract the research content
        content = response.choices[0].message.content
        if content and len(content.strip()) > 100:
            logger.debug(f"Web search returned {len(content)} chars of context")
            return content.strip()

        # If response too short, fall through to fallback
        logger.debug(
            f"Web search returned insufficient content ({len(content) if content else 0} chars), using fallback")
        raise Exception("Insufficient content from web search")

    except Exception as e:
        logger.debug(f"Web search failed, using GPT knowledge: {e}")

        # Fallback: ask GPT to use its training knowledge
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{
                    "role": "user",
                    "content": f"""What do you know about this prediction market topic: "{question}"

Provide relevant context including:
- Base rates and historical precedents
- Key factors affecting probability
- Any relevant recent knowledge you have
- What experts typically predict for this type of event

Today's date: {datetime.now().strftime("%B %d, %Y")}"""
                }],
                temperature=0.2,
                max_tokens=1500
            )
            return response.choices[0].message.content.strip()
        except:
            return "Limited context available for this market."


class AutonomousBot:
    def __init__(self):
        logger.info("Initializing Enhanced Autonomous Trading Bot...")

        from eth_account import Account
        account = Account.from_key(PRIVATE_KEY)
        self.wallet_address = account.address

        self.clob = ClobClient(HOST, key=PRIVATE_KEY, chain_id=CHAIN_ID)
        self.clob.set_api_creds(self.clob.create_or_derive_api_creds())
        self.openai = OpenAI(api_key=OPENAI_API_KEY)

        self.scans_completed = 0
        self.trades_executed = 0
        self.total_deployed = 0.0
        self.recent_purchases = {}

        logger.info("✅ Enhanced bot initialized")
        logger.info(f"Wallet: {self.wallet_address}")
        logger.info("🔍 Real-time data fetching: ENABLED")

    def find_markets(self) -> List[Market]:
        """Find tradeable markets"""
        try:
            logger.info("🔍 Scanning for tradeable markets...")

            response = requests.get(
                "https://gamma-api.polymarket.com/events",
                params={
                    "limit": 1000,
                    "closed": "false",
                    "order": "liquidity",
                    "ascending": "false"
                },
                timeout=10
            )

            if response.status_code != 200:
                logger.error("Failed to fetch markets")
                return []

            events = response.json()
            markets = []

            for event in events:
                if len(markets) >= MAX_MARKETS_PER_SCAN:
                    break

                for market in event.get('markets', []):
                    liquidity = float(market.get('liquidityClob', 0))

                    if liquidity < MIN_LIQUIDITY:
                        continue

                    token_ids_raw = market.get('clobTokenIds', [])
                    if isinstance(token_ids_raw, str):
                        try:
                            token_ids = json.loads(token_ids_raw)
                        except:
                            continue
                    else:
                        token_ids = token_ids_raw

                    if not token_ids:
                        continue

                    token_id = token_ids[0]

                    try:
                        buy_price = self.clob.get_price(token_id, "BUY")
                        sell_price = self.clob.get_price(token_id, "SELL")

                        best_bid = float(buy_price.get('price', 0))
                        best_ask = float(sell_price.get('price', 0))

                        if best_bid <= 0 or best_ask <= 0:
                            continue

                        mid_price = (best_bid + best_ask) / 2
                        spread = best_ask - best_bid
                        spread_pct = (spread / best_ask) * 100

                        if spread_pct > MAX_SPREAD_PCT:
                            continue

                        if mid_price < 0.20 or mid_price > 0.80:
                            continue

                        markets.append(Market(
                            token_id=token_id,
                            question=market.get('question', ''),
                            price=mid_price,
                            spread_pct=spread_pct,
                            liquidity=liquidity
                        ))

                        if len(markets) >= MAX_MARKETS_PER_SCAN:
                            break

                    except Exception:
                        continue

            logger.info(f"✅ Found {len(markets)} tradeable markets")
            return markets

        except Exception as e:
            logger.error(f"Market scan failed: {e}")
            return []

    def analyze_market(self, market: Market) -> Optional[Dict]:
        """Analyze market with real-time data + GPT-4o"""
        try:
            buy_price_data = self.clob.get_price(market.token_id, "BUY")
            sell_price_data = self.clob.get_price(market.token_id, "SELL")

            best_bid = float(buy_price_data.get('price', 0))
            best_ask = float(sell_price_data.get('price', 0))
            mid_price = (best_bid + best_ask) / 2

            # Step 0: Block joke/meme/unverifiable markets
            if is_absurd_market(market.question):
                logger.info(f"   🚫 BLOCKED: Absurd/meme market — skipping")
                return None

            # Step 1: Detect market category
            category = detect_market_category(market.question)
            logger.info(f"   📂 Category: {category}")

            # Step 2: Fetch real-time context
            logger.info(f"   🌐 Fetching real-time data...")
            real_time_context = fetch_real_time_data(
                market.question, category, self.openai
            )
            logger.info(f"   ✅ Context fetched ({len(real_time_context)} chars)")

            # Step 3: GPT-4o analysis with full context
            today = datetime.now().strftime("%B %d, %Y")

            prompt = f"""You are an expert prediction market trader with access to real-time data.
Today's date: {today}

MARKET: {market.question}
YOU ARE EVALUATING: The YES/YES outcome of this market (buying YES tokens)
CATEGORY: {category}

CURRENT MARKET DATA:
- Current price: {mid_price * 100:.1f}% (implied probability that YES resolves)
- Buy price: ${best_ask:.4f}
- Bid price: ${best_bid:.4f}  
- Spread: {market.spread_pct:.1f}%
- Liquidity: ${market.liquidity:,.0f}

IMPORTANT: You are always assessing whether the YES outcome will happen.
fair_value should reflect the true probability that the YES outcome resolves correctly.
Only BUY if YES is more likely than the market implies.

REAL-TIME RESEARCH DATA:
{real_time_context}

YOUR TASK:
Based on the real-time data above, determine if this market is MISPRICED.

Analysis framework:
1. What is the TRUE probability based on real-time data?
2. Is the market price LOWER than fair value by >5%? (edge required)
3. Is the research data conclusive enough to act?
4. What are the key risks that could make this trade wrong?
5. Devil's advocate: What's the strongest argument AGAINST buying?

STRICT CRITERIA FOR BUY:
- Your fair value estimate must be >5% higher than current price
- Confidence must be ≥ 72% based on real data (not just intuition)
- Research must provide concrete evidence, not just general knowledge
- If data is ambiguous or contradictory → HOLD

Respond ONLY with JSON:
{{
    "action": "BUY or HOLD",
    "confidence": 0.0-1.0,
    "fair_value": 0.0-1.0,
    "market_price": {mid_price:.4f},
    "edge": "fair_value minus market_price as percentage",
    "category": "{category}",
    "key_evidence": "top 2-3 data points that support this decision",
    "main_risk": "biggest risk if this trade goes wrong",
    "reasoning": "detailed explanation referencing specific real-time data"
}}"""

            response = self.openai.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=1200
            )

            content = response.choices[0].message.content.strip()

            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error: {e}")
                return None

            if not all(k in data for k in ['action', 'confidence', 'fair_value', 'reasoning']):
                logger.error(f"Missing required fields: {data}")
                return None

            # Log the full analysis
            logger.info(f"   📊 GPT Decision: {data['action']}")
            logger.info(f"   🎯 Fair value: {float(data['fair_value']):.0%} vs Market: {mid_price:.0%}")
            logger.info(f"   💪 Confidence: {data['confidence']:.0%}")
            logger.info(f"   📝 Evidence: {data.get('key_evidence', 'N/A')}")
            logger.info(f"   ⚠️  Risk: {data.get('main_risk', 'N/A')}")
            logger.info(f"   💭 Reasoning: {data['reasoning']}")

            fair_value = float(data['fair_value'])
            if data['action'] == 'BUY' and fair_value < 0.60:
                logger.info(f"   🚫 GUARDRAIL: Fair value {fair_value:.0%} below 60% minimum — HOLD")
                return None

            if data['action'] == 'BUY' and data['confidence'] >= CONFIDENCE_THRESHOLD:
                logger.info(f"   ✅ BUY SIGNAL CONFIRMED!")
                return {
                    'action': 'BUY',
                    'confidence': data['confidence'],
                    'price': best_ask,
                    'reasoning': data['reasoning'],
                    'key_evidence': data.get('key_evidence', ''),
                    'main_risk': data.get('main_risk', ''),
                    'category': category,
                    'fair_value': fair_value
                }
            else:
                logger.info(f"   ⏭️  HOLD - insufficient edge or confidence")
                return None

        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return None

    def execute_trade(self, market: Market, signal: Dict) -> bool:
        """Execute BUY order"""
        try:
            price = signal['price']
            shares = MAX_POSITION_USD / price

            logger.info(f"\n💰 EXECUTING TRADE")
            logger.info(f"   Market: {market.question[:60]}")
            logger.info(f"   Category: {signal.get('category', 'N/A')}")
            logger.info(f"   Shares: {shares:.2f} @ ${price:.4f}")
            logger.info(f"   Cost: ${shares * price:.2f}")
            logger.info(f"   Fair value: {float(signal.get('fair_value', 0)):.0%}")
            logger.info(f"   Evidence: {signal.get('key_evidence', 'N/A')[:100]}")

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

            logger.info(f"   ✅ TRADE EXECUTED!")
            logger.info(f"   Order ID: {result.get('orderID', 'N/A')}")
            logger.info(f"   Status: {result.get('status', 'N/A')}")

            # Log to file with full context
            with open("trades_log.json", "a") as f:
                trade_record = {
                    "timestamp": datetime.now().isoformat(),
                    "market": market.question,
                    "category": signal.get('category', 'UNKNOWN'),
                    "token_id": market.token_id,
                    "action": "BUY",
                    "price": price,
                    "shares": shares,
                    "confidence": signal['confidence'],
                    "fair_value": signal.get('fair_value', 0),
                    "key_evidence": signal.get('key_evidence', ''),
                    "main_risk": signal.get('main_risk', ''),
                    "reasoning": signal['reasoning'],
                    "order_id": result.get('orderID')
                }
                f.write(json.dumps(trade_record) + "\n")

            self.trades_executed += 1
            self.total_deployed += MAX_POSITION_USD

            return True

        except Exception as e:
            logger.error(f"❌ Trade failed: {e}")
            return False

    def run_scan(self):
        """Run one complete scan cycle"""
        try:
            logger.info("")
            logger.info("=" * 70)
            logger.info(f"🔄 SCAN #{self.scans_completed + 1}")
            logger.info("=" * 70)

            markets = self.find_markets()

            if not markets:
                logger.info("No tradeable markets found")
                return

            for market in markets:
                if market.token_id in self.recent_purchases:
                    time_since = (datetime.now() - self.recent_purchases[market.token_id]).total_seconds()
                    if time_since < 3600:
                        continue

                logger.info(f"\n📊 Analyzing: {market.question[:60]}...")
                logger.info(
                    f"   Price: {market.price:.0%}, Spread: {market.spread_pct:.1f}%, Liquidity: ${market.liquidity:,.0f}")

                signal = self.analyze_market(market)

                if signal:
                    success = self.execute_trade(market, signal)
                    if success:
                        self.recent_purchases[market.token_id] = datetime.now()
                        time.sleep(10)
                else:
                    logger.info("   💤 No BUY signal")

                time.sleep(3)  # Rate limiting between markets

            self.scans_completed += 1

            logger.info("")
            logger.info("=" * 70)
            logger.info("📊 SESSION STATISTICS")
            logger.info("=" * 70)
            logger.info(f"Scans completed: {self.scans_completed}")
            logger.info(f"Trades executed: {self.trades_executed}")
            logger.info(f"Capital deployed: ${self.total_deployed:.2f}")
            logger.info("=" * 70)

        except Exception as e:
            logger.error(f"Scan failed: {e}")
            import traceback
            traceback.print_exc()

    def run(self):
        """Run bot continuously"""
        logger.info("")
        logger.info("=" * 70)
        logger.info("🤖 ENHANCED AUTONOMOUS TRADING BOT STARTED")
        logger.info("=" * 70)
        logger.info(f"Max position: ${MAX_POSITION_USD}")
        logger.info(f"Confidence threshold: {CONFIDENCE_THRESHOLD:.0%}")
        logger.info(f"Max spread: {MAX_SPREAD_PCT:.1f}%")
        logger.info(f"Scan interval: {SCAN_INTERVAL_SECONDS}s")
        logger.info(f"Real-time data: ENABLED")
        logger.info("=" * 70)

        try:
            while True:
                self.run_scan()
                logger.info(f"\n⏰ Next scan in {SCAN_INTERVAL_SECONDS}s...")
                time.sleep(SCAN_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            logger.info("\n\n🛑 Bot stopped by user")
            logger.info(f"Final: {self.trades_executed} trades, ${self.total_deployed:.2f} deployed")
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    # Auto-start for cloud deployment
    bot = AutonomousBot()
    bot.run()