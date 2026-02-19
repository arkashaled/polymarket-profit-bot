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

## 🚀 Getting Started

### Prerequisites

Before you begin, you'll need:

- **Python 3.11+** installed on your machine
- **OpenAI API key** (for GPT-4o) - Get one at [platform.openai.com](https://platform.openai.com)
- **Oxylabs residential proxy account** - Sign up at [oxylabs.io](https://oxylabs.io)
- **Polymarket wallet** with:
  - Private key exported from MetaMask
  - At least $50 USDC on Polygon network
  - Smart contract approvals (we'll set this up in Step 3 - only needs to be done once)

### Step 1: Clone and Install

```bash
# Clone the repository
git clone https://github.com/arkashaled/polymarket-profit-bot.git
cd polymarket-profit-bot

# Install Python dependencies
pip install -r requirements.txt
```

### Step 2: Configure Credentials

**Edit `Autonomous_bot.py`:**
1. Open the file in your editor
2. Find line ~20: `PRIVATE_KEY = os.environ.get("PRIVATE_KEY")`
3. Replace with: `PRIVATE_KEY = "0xYOUR_PRIVATE_KEY_HERE"`
4. Find line ~30: `OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")`
5. Replace with: `OPENAI_API_KEY = "sk-YOUR_OPENAI_KEY_HERE"`

**Edit `profit_taking_bot.py`:**
1. Open the file in your editor
2. Find line ~20: `PRIVATE_KEY = os.environ.get("PRIVATE_KEY")`
3. Replace with: `PRIVATE_KEY = "0xYOUR_PRIVATE_KEY_HERE"` (same as trading bot)
4. Find lines ~60-62 (proxy credentials):
   ```python
   PROXY_USER = os.environ.get("PROXY_USER", "customer-...")
   PROXY_PASS = os.environ.get("PROXY_PASS", "...")
   ```
5. Replace the default values with your Oxylabs credentials

**Note:** For production deployment, use environment variables instead of hardcoding keys (see Railway deployment section).

### Step 3: Approve Trading Contracts

**CRITICAL:** The bots need permission to spend your USDC and move your tokens. Run these approvals once:

**A) Approve USDC spending (for buying positions):**

```bash
python3 << 'EOF'
from web3 import Web3
from eth_account import Account

PRIVATE_KEY = "YOUR_PRIVATE_KEY_HERE"  # Replace with your key
w3 = Web3(Web3.HTTPProvider('https://polygon-rpc.com'))

USDC = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
EXCHANGES = [
    "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E",  # CTF Exchange
    "0xC5d563A36AE78145C45a50134d48A1215220f80a",  # Neg Risk CTF
    "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296",  # Neg Risk Adapter
]

usdc_abi = [{"constant": False, "inputs": [{"name": "_spender", "type": "address"}, 
             {"name": "_value", "type": "uint256"}], "name": "approve", 
             "outputs": [{"name": "", "type": "bool"}], "type": "function"}]

usdc = w3.eth.contract(address=USDC, abi=usdc_abi)
account = Account.from_key(PRIVATE_KEY)

for exchange in EXCHANGES:
    tx = usdc.functions.approve(exchange, 2**256-1).build_transaction({
        'from': account.address,
        'gas': 100000,
        'gasPrice': w3.eth.gas_price,
        'nonce': w3.eth.get_transaction_count(account.address),
    })
    
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"✅ USDC approval: https://polygonscan.com/tx/{tx_hash.hex()}")
    
    import time
    time.sleep(10)  # Wait between transactions

print("✅ USDC approvals complete!")
EOF
```

**B) Approve token transfers (for selling positions):**

```bash
python3 << 'EOF'
from web3 import Web3
from eth_account import Account

PRIVATE_KEY = "YOUR_PRIVATE_KEY_HERE"  # Replace with your key
w3 = Web3(Web3.HTTPProvider('https://polygon-rpc.com'))

CTF_CONTRACT = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
EXCHANGES = [
    "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E",  # CTF Exchange
    "0xC5d563A36AE78145C45a50134d48A1215220f80a",  # Neg Risk CTF
]

ctf_abi = [{"constant": False, "inputs": [{"name": "_operator", "type": "address"}, 
            {"name": "_approved", "type": "bool"}], "name": "setApprovalForAll", 
            "outputs": [], "type": "function"}]

ctf = w3.eth.contract(address=CTF_CONTRACT, abi=ctf_abi)
account = Account.from_key(PRIVATE_KEY)

for exchange in EXCHANGES:
    tx = ctf.functions.setApprovalForAll(exchange, True).build_transaction({
        'from': account.address,
        'gas': 100000,
        'gasPrice': w3.eth.gas_price,
        'nonce': w3.eth.get_transaction_count(account.address),
    })
    
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"✅ Token approval: https://polygonscan.com/tx/{tx_hash.hex()}")
    
    import time
    time.sleep(10)  # Wait between transactions

print("✅ Token approvals complete!")
print("\n🎉 Setup complete! Both bots can now trade.")
EOF
```

**Wait 1-2 minutes for all transactions to confirm on Polygon.**

### Step 4: Run the Bots

**Option A - Run Both Bots (Recommended):**

```bash
# Terminal 1 - Trading Bot
python3 Autonomous_bot.py

# Terminal 2 - Profit-Taking Bot
python3 profit_taking_bot.py
```

**Option B - Run Trading Bot Only:**

```bash
python3 Autonomous_bot.py
```

**Option C - Run Profit-Taking Bot Only:**

```bash
python3 profit_taking_bot.py
```

The bots will run continuously until you press `Ctrl+C`.

---

## ☁️ Deploy to Railway (24/7 Cloud Hosting)

To run the bots 24/7 without keeping your computer on:

### Step 1: Push to Your GitHub

```bash
# Create a new private repository on GitHub
# Then push your configured code:
git init
git add .
git commit -m "initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### Step 2: Deploy on Railway

1. Go to [railway.app](https://railway.app) and sign up
2. Click **New Project** → **Deploy from GitHub repo**
3. Select your repository
4. Railway will auto-detect the `Dockerfile` and deploy

### Step 3: Set Environment Variables

In Railway dashboard:
1. Go to your service → **Variables** tab
2. Click **+ New Variable** and add:
   - `PRIVATE_KEY` = `0x...` (your wallet key)
   - `OPENAI_API_KEY` = `sk-...` (your OpenAI key)
   - `PROXY_USER` = `customer-...` (your Oxylabs user)
   - `PROXY_PASS` = `...` (your Oxylabs password)

### Step 4: Verify Deployment

1. Go to **Deployments** tab
2. Wait for "Build successful" → "Deployed"
3. Click **View Logs** to see bot output

The bots will now run 24/7 with auto-restart on crashes.

---

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

### "not enough balance / allowance" Error

**Problem:** Bot fails with `PolyApiException: not enough balance / allowance`

**Solution:** You need to approve both USDC spending AND token transfers. Run **both** approval scripts from Step 3:
1. USDC approvals (3 exchanges) - enables buying
2. Token approvals (2 exchanges) - enables selling

Verify approvals succeeded on Polygonscan before trying again.

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

### Replacement Transaction Underpriced
- Previous transaction still pending
- Wait 15-30 seconds between approval transactions
- Check Polygonscan for pending transactions

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

---

**Built with:** Python • Polymarket CLOB API • Web3.py • Oxylabs Proxies • Railway
