#!/usr/bin/env python3
"""
Private trade dashboard — password protected.
Run: python3 dashboard.py
Then open: http://localhost:8888
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, quote
import json, os, base64, requests
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "sniper2026")
PORT               = 8888
WALLET             = "0x26806A9D42625d8912318C0A9611323Bd79c8B59"
TRADES_LOG         = os.path.join(os.path.dirname(__file__), "sniper_trades.json")

PROXY_USER = os.environ.get("PROXY_USER","").strip()
PROXY_PASS = os.environ.get("PROXY_PASS","").strip()
PROXY_HOST = os.environ.get("PROXY_HOST","pr.oxylabs.io:7777").strip()

def get_session():
    s = requests.Session()
    if PROXY_USER and PROXY_PASS:
        url = f"http://{quote(PROXY_USER,safe='')}:{quote(PROXY_PASS,safe='')}@{PROXY_HOST}"
        s.proxies = {"http": url, "https": url}
    return s

def load_trades():
    try:
        with open(TRADES_LOG) as f:
            return json.load(f)
    except Exception:
        return {"buys": [], "total_deployed": 0.0, "total_shares": 0}

def fetch_live_positions():
    try:
        s = get_session()
        r = s.get("https://data-api.polymarket.com/trades",
                   params={"user": WALLET, "limit": 50}, timeout=12)
        trades = r.json()
        if isinstance(trades, dict):
            trades = trades.get("data", trades.get("trades", []))
        return trades
    except Exception:
        return []

def fetch_positions():
    try:
        s = get_session()
        r = s.get("https://data-api.polymarket.com/positions",
                   params={"user": WALLET, "limit": 100}, timeout=12)
        data = r.json()
        if isinstance(data, list):
            return data
        return data.get("positions", data.get("data", []))
    except Exception:
        return []

def usdc_balance():
    try:
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(
            "https://rpc.ankr.com/polygon/e60a25f438f27fa6fc6a501b06f24aaed57b8f518096bc9d5666094a40a67fe7",
            request_kwargs={"timeout": 6}
        ))
        USDC = Web3.to_checksum_address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")
        abi  = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],
                 "name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"type":"function"}]
        bal = w3.eth.contract(address=USDC, abi=abi).functions.balanceOf(WALLET).call()
        return bal / 1e6
    except Exception:
        return None

def render_html():
    local_trades = load_trades()
    api_trades   = fetch_live_positions()   # ground truth from Polymarket
    balance      = usdc_balance()
    now          = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Merge: use API trades as the source of truth; fall back to local log
    if api_trades:
        # Deduplicate: keep only the most recent trade per (token_id, outcome)
        seen = {}
        for t in api_trades:
            ts      = str(t.get("timestamp",""))
            try:
                ts_int = int(ts)
                ts = datetime.utcfromtimestamp(ts_int).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                ts = ts[:19].replace("T"," ")

            market   = str(t.get("title","") or t.get("market","") or t.get("question",""))
            outcome  = str(t.get("outcome","?"))
            price    = float(t.get("price", 0))
            shares   = float(t.get("size", 0) or t.get("shares", 0))
            cost     = round(price * shares, 2)
            status   = str(t.get("status","matched"))
            token_id = str(t.get("asset_id") or t.get("asset") or t.get("token_id") or t.get("tokenId") or "")

            key = token_id if token_id else market  # deduplicate key
            entry = {"timestamp": ts, "market": market, "outcome": outcome,
                     "ask_price": price, "shares": shares, "cost": cost,
                     "status": status, "token_id": token_id}

            # Keep the entry with the largest shares (most complete position)
            if key not in seen or shares > seen[key]["shares"]:
                seen[key] = entry

        buys = list(seen.values())
        total_deployed = round(sum(b["cost"] for b in buys), 2)
    else:
        buys           = local_trades.get("buys", [])
        total_deployed = local_trades.get("total_deployed", 0)

    # Build rows
    rows = ""
    # Fetch current open positions → map token_id → current price
    live_prices = {}
    try:
        positions = fetch_positions()
        for p in positions:
            tid = str(p.get("asset") or p.get("asset_id") or p.get("token_id") or "")
            if not tid:
                continue
            size = float(p.get("size") or p.get("shares") or 0)
            cur  = float(p.get("currentValue") or 0)
            if size > 0:
                live_prices[tid] = round(cur / size, 4)
            else:
                live_prices[tid] = None
    except Exception:
        pass

    for b in buys:
        ts      = str(b.get("timestamp",""))[:19].replace("T"," ")
        market  = b.get("market","")
        outcome = b.get("outcome","")
        price   = float(b.get("ask_price", 0))
        shares  = float(b.get("shares", 0))
        cost    = float(b.get("cost", 0))
        status  = b.get("status","")
        token_id = b.get("token_id","")
        max_gain = shares - cost

        is_yes = outcome.upper() in ("YES","UP","OVER","TRUE")
        outcome_cls = "yes" if is_yes else "no"

        status_badge = (
            f'<span class="badge green">matched</span>' if "match" in status.lower()
            else f'<span class="badge yellow">live</span>' if "live" in status.lower()
            else f'<span class="badge gray">{status}</span>'
        )

        # Resolved column
        if not token_id:
            # No token_id stored — can't determine status
            resolved_cell = '<span class="badge gray">—</span>'
        elif token_id in live_prices:
            cur_price = live_prices[token_id]
            if cur_price is not None and cur_price >= 0.99:
                resolved_cell = '<span class="badge green">⚡ Near resolution</span>'
            else:
                resolved_cell = f'<span class="badge gray">Open ${cur_price:.3f}</span>' if cur_price else '<span class="badge gray">Open</span>'
        else:
            # token_id known but not in current positions → sold or resolved
            resolved_cell = '<span class="badge green">✅ Closed</span>'

        rows += f"""
        <tr>
          <td>{ts}</td>
          <td class="market" title="{market}">{market}</td>
          <td><span class="outcome {outcome_cls}">{outcome}</span></td>
          <td>${price:.3f}</td>
          <td>{shares:.0f}</td>
          <td>${cost:.2f}</td>
          <td class="gain">+${max_gain:.2f}</td>
          <td>{status_badge}</td>
          <td>{resolved_cell}</td>
        </tr>"""

    balance_str = f"${balance:.2f}" if balance is not None else "..."

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Sniper Bot Dashboard</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #0f0f13; color: #e0e0e0; padding: 24px; }}
    h1 {{ color: #fff; font-size: 22px; margin-bottom: 4px; }}
    .sub {{ color: #666; font-size: 13px; margin-bottom: 24px; }}
    .cards {{ display: flex; gap: 16px; margin-bottom: 28px; flex-wrap: wrap; }}
    .card {{ background: #1a1a24; border-radius: 10px; padding: 18px 24px; min-width: 160px; }}
    .card .label {{ color: #666; font-size: 12px; text-transform: uppercase; letter-spacing: .05em; }}
    .card .value {{ color: #fff; font-size: 26px; font-weight: 600; margin-top: 4px; }}
    .card .value.green {{ color: #4ade80; }}
    .card .value.blue  {{ color: #60a5fa; }}
    table {{ width: 100%; border-collapse: collapse; background: #1a1a24; border-radius: 10px; overflow: hidden; }}
    th {{ background: #12121a; color: #888; font-size: 11px; text-transform: uppercase;
          letter-spacing: .06em; padding: 12px 14px; text-align: left; }}
    td {{ padding: 11px 14px; font-size: 13px; border-top: 1px solid #22222e; }}
    tr:hover td {{ background: #1f1f2e; }}
    .market {{ max-width: 280px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #ccc; }}
    .outcome {{ padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
    .outcome.yes {{ background: #14532d; color: #4ade80; }}
    .outcome.no  {{ background: #450a0a; color: #f87171; }}
    .gain {{ color: #4ade80; }}
    .badge {{ padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
    .badge.green  {{ background: #14532d; color: #4ade80; }}
    .badge.yellow {{ background: #422006; color: #fbbf24; }}
    .badge.gray   {{ background: #1f2937; color: #9ca3af; }}
    .wallet {{ font-size: 11px; color: #444; margin-top: 20px; }}
    a {{ color: #60a5fa; }}
    .refresh-bar {{ height: 3px; background: #1a1a24; border-radius: 2px; margin-bottom: 20px; }}
    .refresh-bar-fill {{ height: 3px; background: #60a5fa; border-radius: 2px;
                         transition: width 1s linear; }}
    .countdown {{ font-size: 12px; color: #555; margin-bottom: 20px; }}
    .countdown span {{ color: #60a5fa; font-weight: 600; }}
  </style>
  <script>
    var total = 30;
    var remaining = total;
    function tick() {{
      remaining--;
      var pct = ((total - remaining) / total * 100);
      var el = document.getElementById('bar');
      var ct = document.getElementById('ct');
      if (el) el.style.width = pct + '%';
      if (ct) ct.textContent = remaining;
      if (remaining <= 0) {{ location.reload(); }}
      else {{ setTimeout(tick, 1000); }}
    }}
    window.onload = function() {{ setTimeout(tick, 1000); }};
  </script>
</head>
<body>
  <h1>🎯 Sniper Bot Dashboard</h1>
  <div class="sub">Last updated: {now}</div>
  <div class="refresh-bar"><div class="refresh-bar-fill" id="bar" style="width:0%"></div></div>
  <div class="countdown">Refreshing in <span id="ct">30</span>s</div>

  <div class="cards">
    <div class="card">
      <div class="label">USDC Balance</div>
      <div class="value blue">{balance_str}</div>
    </div>
    <div class="card">
      <div class="label">Total Deployed</div>
      <div class="value">${total_deployed:.2f}</div>
    </div>
    <div class="card">
      <div class="label">Trades Executed</div>
      <div class="value">{len(buys)}</div>
    </div>
    <div class="card">
      <div class="label">Max Possible Gain</div>
      <div class="value green">+${sum((b.get('shares',0) - b.get('cost',0)) for b in buys):.2f}</div>
    </div>
  </div>

  <table>
    <thead>
      <tr>
        <th>Time</th><th>Market</th><th>Outcome</th>
        <th>Price</th><th>Shares</th><th>Cost</th>
        <th>Max Gain</th><th>Status</th><th>Resolved</th>
      </tr>
    </thead>
    <tbody>
      {rows if rows else '<tr><td colspan="9" style="text-align:center;color:#555;padding:30px">No trades yet</td></tr>'}
    </tbody>
  </table>

  <div class="wallet">
    Wallet: <a href="https://polymarket.com/profile/{WALLET}" target="_blank">{WALLET}</a>
  </div>
</body>
</html>"""

# ── HTTP Handler ──────────────────────────────────────────────────────────────
REALM = "Sniper Dashboard"

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass  # suppress access logs

    def check_auth(self):
        auth = self.headers.get("Authorization","")
        if auth.startswith("Basic "):
            decoded = base64.b64decode(auth[6:]).decode()
            _, _, pwd = decoded.partition(":")
            if pwd == DASHBOARD_PASSWORD:
                return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", f'Basic realm="{REALM}"')
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Unauthorized")
        return False

    def do_GET(self):
        if not self.check_auth():
            return
        html = render_html().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

if __name__ == "__main__":
    print(f"🎯 Dashboard running at http://localhost:{PORT}")
    print(f"   Username: (anything)")
    print(f"   Password: {DASHBOARD_PASSWORD}")
    HTTPServer(("", PORT), Handler).serve_forever()
