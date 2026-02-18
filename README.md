# 🤖 Polymarket Trading System

Dual-bot autonomous trading system for Polymarket with intelligent market analysis and automated profit-taking.

## 🎯 System Overview

This system consists of two coordinated bots:

### 1. **Autonomous Trading Bot** 
- AI-powered market analysis using GPT-4
- Real-time web search for sports/events data
- Automated buy decisions based on edge detection
- Multi-market support (sports, politics, crypto, AI)

### 2. **Profit-Taking Bot**
- Monitors open positions 24/7
- Automated profit-taking at +70%
- Stop-loss protection at -10%
- Smart position tracking across both bots

## 📊 Features

### Autonomous Trading Bot
- **AI Market Analysis**: GPT-4o with real-time web search
- **Edge Detection**: Only buys when edge > 5% and confidence > 72%
- **Fair Value Minimum**: 60% probability threshold (no long-shots)
- **Absurd Market Filter**: Blocks meme/religious/paranormal markets
- **Multi-Market Coverage**: Sports, politics, crypto, AI, geopolitics
- **Risk Management**: $5 max position size, 4% max spread

### Profit-Taking Bot
- **Automated Profit-Taking**: Sells positions at +70% profit
- **Stop-Loss Protection**: Exits positions at -10% loss
- **24/7 Monitoring**: Scans every 10 minutes
- **Smart Discovery**: Multi-source token discovery
- **Geo-Bypass**: Residential proxy routing
- **Clean Logging**: Only active positions displayed

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- OpenAI API key (for GPT-4o)
- Oxylabs residential proxy account
- Polymarket wallet with private key
- USDC on Polygon network

### Installation

```bash
# Clone repository
git clone https://github.com/arkashaled/polymarket-profit-bot.git
cd polymarket-profit-bot

# Install dependencies
pip install -r requirements.txt

# Configure credentials in both scripts:
# Autonomous_bot.py:
# - PRIVATE_KEY (wallet private key)
# - OPENAI_API_KEY (for GPT-4o analysis)
# 
# profit_taking_bot.py:
# - PRIVATE_KEY (same wallet)
# - PROXY credentials (Oxylabs)

# Run both bots (recommended)
python3 Autonomous_bot.py &
python3 profit_taking_bot.py &

# Or run individually
python3 Autonomous_bot.py      # Trading bot only
python3 profit_taking_bot.py   # Profit-taking only
```

### Deploy to Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app)

1. Fork this repository
2. Create new Railway project from GitHub
3. Railway auto-detects `Dockerfile` and deploys
4. Bot runs 24/7 with auto-restart on crashes

## ⚙️ Configuration

### Autonomous Trading Bot (`Autonomous_bot.py`)

```python
# Trading Parameters
MAX_POSITION_USD = 5.00          # Max bet per market
CONFIDENCE_THRESHOLD = 72        # Min confidence to buy (%)
FAIR_VALUE_MINIMUM = 60          # Min fair value to buy (%)
MAX_SPREAD_PCT = 4.0             # Max spread tolerance
MIN_LIQUIDITY = 50000            # Min market liquidity ($)
SCAN_INTERVAL_SECONDS = 300      # Scan every 5 minutes

# AI Configuration
OPENAI_MODEL = "gpt-4o-search-preview"  # Web search enabled
MAX_TOKENS_SEARCH = 2000         # Context size for research
MAX_TOKENS_ANALYSIS = 1200       # Output size for decisions
```

**Key Filters:**
- **Edge Requirement**: Only buys when edge > 5%
- **Confidence Gate**: Must be >72% confident in analysis
- **Fair Value Floor**: Won't buy YES tokens below 60% probability
- **Absurd Market Blocklist**: Auto-blocks religious/paranormal/meme markets

### Profit-Taking Bot (`profit_taking_bot.py`)

```python
TAKE_PROFIT_PCT = 70.0   # Sell at +70% profit
STOP_LOSS_PCT = -10.0    # Sell at -10% loss
SCAN_INTERVAL_SECONDS = 600  # Check every 10 minutes
MIN_POSITION_VALUE = 0.50    # Ignore positions < $0.50
```

## 🌍 Proxy Configuration

The bot uses Oxylabs residential proxies to bypass Polymarket's geo-restrictions.

**Allowed countries** (not blocked by Polymarket):
- 🇳🇱 Netherlands (`cc-nl`) - Recommended
- 🇪🇸 Spain (`cc-es`)
- 🇸🇪 Sweden (`cc-se`)
- 🇳🇴 Norway (`cc-no`)
- 🇩🇰 Denmark (`cc-dk`)
- 🇮🇪 Ireland (`cc-ie`)

Change country by updating:
```python
PROXY_USER = "customer-YOUR_USER-cc-nl"  # Change 'nl' to desired country
```

**Blocked countries:** US, UK, FR, DE, IT, AU, SG, and [30+ others](https://docs.polymarket.com/developers/CLOB/geoblock)

## 📈 How It Works

### Autonomous Trading Bot Workflow

1. **Market Discovery**: Scans Polymarket for active markets via Gamma API
   - Filters by minimum liquidity ($50k+)
   - Excludes resolved/expired markets
   - Applies absurd market blocklist

2. **AI Research**: For each market, GPT-4o performs deep analysis
   - Real-time web search for current data (injuries, polls, odds)
   - Fetches 4000-5000 chars of context
   - Analyzes 1200 tokens of reasoning

3. **Decision Engine**: Evaluates buy opportunity
   - Calculates fair value (true probability)
   - Compares to market price → **edge**
   - Applies guardrails:
     - Edge > 5%?
     - Confidence > 72%?
     - Fair value > 60%?
     - Spread < 4%?

4. **Execution**: If all criteria met → **BUY**
   - Places $5 limit order
   - Logs to `trades_log.json`
   - Sleeps 5 minutes, repeat

5. **Repeat**: Continuous 5-minute scan cycle

### Profit-Taking Bot Workflow

1. **Discovery**: Scans wallet for open positions via:
   - Trading bot's `trades_log.json`
   - Polymarket Data API
   - Polygon blockchain events
   
2. **Balance Check**: Verifies on-chain balances via Alchemy RPC

3. **Entry Price**: Fetches average entry price from Polymarket trade history API

4. **Decision**: Compares current price vs entry price
   - If P&L ≥ +70% → **SELL** (take profit)
   - If P&L ≤ -10% → **SELL** (stop loss)
   - Otherwise → **HOLD**

5. **Execution**: Places market sell order via Polymarket CLOB API

6. **Repeat**: Sleeps 10 minutes, then scans again

## 📝 Output Examples

### Autonomous Trading Bot

```
======================================================================
🤖 AUTONOMOUS POLYMARKET BOT
======================================================================
Wallet: 0x9846...a032
Max Position: $5.00
Confidence Threshold: 72%
Fair Value Minimum: 60%
Scan Interval: 300s
======================================================================

🔍 Analyzing market: Will Arsenal win the EPL 2024-25?
   Market Price: $0.69 (69%)
   
   🌐 Researching via web search...
   📊 Found 4,523 chars of context (injuries, form, odds)
   
   🧠 AI Analysis:
   Fair Value: 74%
   Confidence: 85%
   Edge: +5.8%
   
   ✅ GUARDRAILS PASSED
   Edge: 5.8% > 5.0% ✓
   Confidence: 85% > 72% ✓
   Fair Value: 74% > 60% ✓
   Spread: 2.1% < 4.0% ✓
   
   💰 BUYING 7.25 shares @ $0.69
   ✅ Order placed! ID: 0x3f2a...
   
💤 Next scan in 5 minutes...
```

### Profit-Taking Bot

```
======================================================================
🤖 POLYMARKET PROFIT-TAKING BOT
======================================================================
Wallet: 0x9846...a032
Take Profit: +70.0%
Stop Loss: -10.0%
Scan Interval: 600s (10 minutes)
======================================================================

--- Position 1 ---
   Token: 71634047218945647363...
   Shares: 36.21
   Current Price: $0.6700
   Current Value: $24.26
   Entry Price: $0.6900 | P&L: -2.9% ($-0.72)
   📊 Hold: -2.9% (TP: 70.0%, SL: -10.0%)

--- Position 2 ---
   Token: 40081275558852222228...
   Shares: 43.18
   Current Price: $0.7900
   Current Value: $34.11
   Entry Price: $0.4630 | P&L: +70.6% ($+14.11)
   🎯 TAKE PROFIT! +70.6% gain (target: 70.0%)
   💰 Executing SELL order...
   ✅ SOLD!
   Order ID: 0x7ad986d3...
   P&L: $+14.11 (+70.6%)

======================================================================
SCAN COMPLETE
======================================================================
Positions sold: 1
Positions held: 7
Session P&L: $+14.11
Total All-Time P&L: $+30.45
======================================================================
```

## 🛠️ Troubleshooting

### 403 Geoblock Error
- Your proxy country is blocked by Polymarket
- Switch to an allowed country (see Proxy Configuration)

### 401 RPC Error
- Polygon RPC endpoint is down/rate limited
- Bot automatically uses Alchemy public RPC
- Alternative: Sign up for free Alchemy API key

### Missing Positions
- Resolved markets are automatically filtered
- Dust positions (<$0.50) are skipped
- Check `profit_taking_trades.json` for blacklisted tokens

### Proxy Connection Failed (522)
- Oxylabs residential pool exhausted
- Switch to different country
- Check Oxylabs dashboard for bandwidth limits

## 📊 File Structure

```
polymarket-profit-bot/
├── Autonomous_bot.py          # AI-powered trading bot
├── profit_taking_bot.py       # Profit-taking/stop-loss bot
├── requirements.txt           # Python dependencies
├── Dockerfile                # Railway deployment config
├── start.sh                  # Multi-bot auto-restart wrapper
├── railway.toml              # Railway settings
├── trades_log.json           # Trading bot history (generated)
├── profit_taking_trades.json # Profit bot history (generated)
└── README.md                 # This file
```

### Generated Files (gitignored)
- `trades_log.json` - Trading bot purchase/sell history
- `profit_taking_trades.json` - Entry prices and profit tracking
- `autonomous_bot.log` - Trading bot detailed logs
- `profit_taking_bot.log` - Profit bot detailed logs

## 🔐 Security

- **Never commit private keys** to GitHub
- Use environment variables for sensitive data in production
- The bot creates `profit_taking_trades.json` locally (gitignored)

## 📜 License

MIT License - see LICENSE file for details

## ⚠️ Disclaimer

This bot is for educational purposes. Cryptocurrency trading involves substantial risk. Use at your own discretion. Not financial advice.

## 🤝 Contributing

Pull requests welcome! For major changes, please open an issue first.

## 📞 Support

- Issues: [GitHub Issues](https://github.com/arkashaled/polymarket-profit-bot/issues)
- Polymarket Docs: [docs.polymarket.com](https://docs.polymarket.com)
- Oxylabs Support: [oxylabs.io/support](https://oxylabs.io/support)

---

**Built with:** Python • Polymarket CLOB API • Web3.py • Oxylabs Proxies • Railway
