"""
╔═══════════════════════════════════════════════════════════════════╗
║                    NEWS_CRYPTO_BOT v1.0                           ║
║       Smart Crypto News + AI Analysis Bot                        ║
║                                                                   ║
║  Features:                                                        ║
║    📰 5 sources (CoinDesk, The Block, CoinGecko, CryptoPanic,    ║
║                  CoinTelegraph)                                   ║
║    🤖 Gemini AI analysis (sentiment + impact + reasoning)         ║
║    🔗 Portfolio integration (reads DCA_BOT data)                  ║
║    🔔 Smart alerts (breaking + important + daily digest)          ║
║    📊 Per-coin sentiment tracking                                 ║
║    🌐 Arabic + English UI                                         ║
║                                                                   ║
║  للأغراض التعليمية فقط — ليس نصيحة مالية                          ║
╚═══════════════════════════════════════════════════════════════════╝
"""

import os
import re
import json
import time
import hashlib
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple
from xml.etree import ElementTree as ET

import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)


# ══════════════════════════════════════════════════════════════════
# 1. CONFIG
# ══════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("NEWS_BOT")

# ── Environment Variables ──
BOT_TOKEN          = os.environ.get("BOT_TOKEN", "").strip()
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "").strip()
CLAUDE_API_KEY     = os.environ.get("CLAUDE_API_KEY", "").strip()
OPENAI_API_KEY     = os.environ.get("OPENAI_API_KEY", "").strip()
CRYPTOPANIC_KEY    = os.environ.get("CRYPTOPANIC_KEY", "").strip()
COINGECKO_KEY      = os.environ.get("COINGECKO_KEY", "").strip()

# ── Storage Path ──
DATA_DIR = os.environ.get("DATA_DIR", "/data").rstrip("/")
if not os.path.exists(DATA_DIR) and not os.access("/", os.W_OK):
    DATA_DIR = "./data"

DCA_DATA_DIR = os.environ.get("DCA_DATA_DIR", "/data").rstrip("/")

# ── API Endpoints ──
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Single primary model — proven working in CRYPTO_SCANNER_BOT.
# If Google deprecates this, use /gemdebug to find a replacement.
GEMINI_MODEL = "gemini-2.5-flash"

# Claude API (Anthropic) — strategic deep analysis
CLAUDE_BASE = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL = "claude-opus-4-5"           # latest Opus (best reasoning)
CLAUDE_FALLBACK = "claude-sonnet-4-5"      # cheaper fallback

# OpenAI API — execution recommendations
OPENAI_BASE = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-4o"                     # primary
OPENAI_FALLBACK = "gpt-4o-mini"             # cheaper fallback

RSS_FEEDS = {
    "CoinDesk":      "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "The Block":     "https://www.theblock.co/rss.xml",
    "CoinTelegraph": "https://cointelegraph.com/rss",
}

COINGECKO_NEWS_URL  = "https://api.coingecko.com/api/v3/news"
COINGECKO_RSS_URL   = "https://www.coingecko.com/en/news.rss"
CRYPTOPANIC_URL     = "https://cryptopanic.com/api/v1/posts/"
CRYPTOPANIC_FREE_URL = "https://cryptopanic.com/api/free/v1/posts/"

# ── Limits ──
MAX_ARTICLE_AGE_HOURS = 4
MAX_ARTICLES_PER_FETCH = 15
ALERT_COOLDOWN_HOURS = 4
GEMINI_TIMEOUT = 25
HTTP_TIMEOUT = (5, 20)

# ── Coin Detection (lowercase keys for matching) ──
KNOWN_COINS = {
    "BTC":   ["bitcoin", "btc"],
    "ETH":   ["ethereum", "ether", "eth"],
    "SOL":   ["solana", "sol"],
    "BNB":   ["binance coin", "bnb"],
    "XRP":   ["xrp", "ripple"],
    "ADA":   ["cardano", "ada"],
    "DOGE":  ["dogecoin", "doge"],
    "AVAX":  ["avalanche", "avax"],
    "DOT":   ["polkadot", "dot"],
    "MATIC": ["polygon", "matic"],
    "LINK":  ["chainlink", "link"],
    "UNI":   ["uniswap"],
    "AAVE":  ["aave"],
    "ATOM":  ["cosmos", "atom"],
    "NEAR":  ["near protocol", "near"],
    "HBAR":  ["hedera", "hbar"],
    "ARB":   ["arbitrum", "arb"],
    "OP":    ["optimism"],
    "PEPE":  ["pepe"],
    "SHIB":  ["shiba inu", "shib"],
    "WIF":   ["dogwifhat", "wif"],
    "BONK":  ["bonk"],
    "ONDO":  ["ondo finance", "ondo"],
    "PYTH":  ["pyth network", "pyth"],
    "RENDER":["render", "rndr"],
    "TAO":   ["bittensor", "tao"],
    "FET":   ["fetch.ai", "fetch"],
    "HYPE":  ["hyperliquid", "hype"],
    "SUI":   ["sui"],
    "APT":   ["aptos"],
    "INJ":   ["injective"],
    "SEI":   ["sei network"],
    "TIA":   ["celestia", "tia"],
    "JUP":   ["jupiter"],
    "ENS":   ["ens", "ethereum name service"],
    "MKR":   ["makerdao", "maker", "mkr"],
    "LDO":   ["lido"],
    "GRT":   ["the graph", "grt"],
    "FIL":   ["filecoin"],
    "LTC":   ["litecoin", "ltc"],
    "BCH":   ["bitcoin cash"],
    "TRX":   ["tron"],
    "USDT":  ["tether"],
    "USDC":  ["usdc"],
}

TZ_RIYADH = timezone(timedelta(hours=3))


# ══════════════════════════════════════════════════════════════════
# 2. STORAGE LAYER
# ══════════════════════════════════════════════════════════════════

def _ensure_data_dir():
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except Exception as e:
        log.warning(f"[STORAGE] cannot create {DATA_DIR}: {e}")


def storage_load(filename: str, default: Any = None) -> Any:
    _ensure_data_dir()
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"[STORAGE] failed to load {filename}: {e}")
        return default if default is not None else {}


def storage_save(filename: str, data: Any) -> bool:
    _ensure_data_dir()
    path = os.path.join(DATA_DIR, filename)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except Exception as e:
        log.warning(f"[STORAGE] failed to save {filename}: {e}")
        return False


def now_iso() -> str:
    return datetime.now(TZ_RIYADH).isoformat()


def now_str() -> str:
    return datetime.now(TZ_RIYADH).strftime("%H:%M:%S")


# ══════════════════════════════════════════════════════════════════
# 3. HTTP HELPER
# ══════════════════════════════════════════════════════════════════

_session = requests.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)",
    "Accept": "application/json, application/rss+xml, text/xml, */*",
})


def safe_request(method: str, url: str,
                 params: Optional[dict] = None,
                 headers: Optional[dict] = None,
                 json_body: Optional[dict] = None,
                 timeout: tuple = HTTP_TIMEOUT,
                 retries: int = 2) -> Optional[Any]:
    """Resilient HTTP request with retry."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            h = dict(_session.headers)
            if headers:
                h.update(headers)
            r = _session.request(method, url, params=params, headers=h,
                                 json=json_body, timeout=timeout)
            if r.status_code == 200:
                ctype = r.headers.get("Content-Type", "")
                if "json" in ctype.lower():
                    try:
                        return r.json()
                    except ValueError:
                        return r.text
                return r.text
            elif r.status_code == 429:
                last_err = "429 rate limit"
                time.sleep(2 ** attempt)
                continue
            elif r.status_code in (401, 403):
                return {"_auth_error": r.status_code,
                        "_text": (r.text or "")[:200]}
            else:
                last_err = f"HTTP {r.status_code}"
        except requests.exceptions.Timeout:
            last_err = "timeout"
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:80]}"
        if attempt < retries:
            time.sleep(1)
    log.warning(f"[HTTP] {method} {url[:60]} → {last_err}")
    return None


# ══════════════════════════════════════════════════════════════════
# 4. NEWS FETCHERS (5 sources)
# ══════════════════════════════════════════════════════════════════

def _parse_rss_date(date_str: str) -> int:
    """Parse various RSS date formats to unix timestamp (seconds)."""
    if not date_str:
        return int(time.time())
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%a, %d %b %Y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
    ]
    date_str = date_str.strip()
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except ValueError:
            continue
    # Fallback: try GMT/UTC suffixes
    try:
        cleaned = re.sub(r"\s*(GMT|UTC|\+0000)\s*$", "", date_str).strip()
        dt = datetime.strptime(cleaned, "%a, %d %b %Y %H:%M:%S")
        return int(dt.replace(tzinfo=timezone.utc).timestamp())
    except Exception:
        return int(time.time())


def _strip_html(text: str) -> str:
    """Quick HTML strip (no BeautifulSoup needed)."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"&#\d+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_rss_feed(name: str, url: str) -> List[Dict]:
    """Fetch and parse RSS feed. Returns standardized articles."""
    raw = safe_request("GET", url, timeout=(5, 15))
    if not raw or not isinstance(raw, str):
        return []

    articles = []
    try:
        # Strip BOM and parse
        if raw.startswith("\ufeff"):
            raw = raw[1:]
        root = ET.fromstring(raw)

        # Find items (RSS 2.0 or Atom)
        items = root.findall(".//item")
        if not items:
            # Try Atom format
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            items = root.findall("atom:entry", ns)

        for item in items[:MAX_ARTICLES_PER_FETCH]:
            try:
                # Title
                title_el = item.find("title")
                title = (title_el.text or "").strip() if title_el is not None else ""

                # Link
                link_el = item.find("link")
                link = ""
                if link_el is not None:
                    link = (link_el.text or link_el.get("href") or "").strip()

                # Description / Summary
                desc_el = item.find("description") or item.find("summary")
                desc = ""
                if desc_el is not None:
                    desc = _strip_html(desc_el.text or "")

                # Date
                date_el = (item.find("pubDate")
                           or item.find("published")
                           or item.find("updated"))
                pub_ts = _parse_rss_date(date_el.text) if date_el is not None else int(time.time())

                if not title or not link:
                    continue

                articles.append({
                    "title":   title,
                    "summary": desc[:500],
                    "url":     link,
                    "source":  name,
                    "ts":      pub_ts,
                    "id":      hashlib.md5(link.encode()).hexdigest()[:16],
                })
            except Exception as e:
                log.debug(f"[RSS] item parse: {e}")
                continue

    except ET.ParseError as e:
        log.warning(f"[RSS] {name} parse error: {e}")
        return []
    except Exception as e:
        log.warning(f"[RSS] {name} error: {e}")
        return []

    log.info(f"[RSS] {name}: {len(articles)} articles")
    return articles


def fetch_coingecko_news() -> List[Dict]:
    """
    Fetch news from CoinGecko News API.
    Falls back to RSS if API unavailable (free tier was deprecated mid-2025).
    """
    headers = {}
    if COINGECKO_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_KEY

    # Try API first (works with paid keys)
    data = safe_request("GET", COINGECKO_NEWS_URL, headers=headers,
                        timeout=(5, 15))

    if data and isinstance(data, dict) and data.get("data"):
        articles = []
        for item in data.get("data", [])[:MAX_ARTICLES_PER_FETCH]:
            try:
                attrs = item.get("attributes", {}) or item
                title = attrs.get("title", "").strip()
                desc = _strip_html(attrs.get("description", ""))
                link = attrs.get("url", "")
                ts = attrs.get("updated_at") or attrs.get("created_at")
                if isinstance(ts, str):
                    pub_ts = _parse_rss_date(ts)
                elif isinstance(ts, (int, float)):
                    pub_ts = int(ts)
                else:
                    pub_ts = int(time.time())
                if not title or not link:
                    continue
                articles.append({
                    "title":   title,
                    "summary": desc[:500],
                    "url":     link,
                    "source":  "CoinGecko",
                    "ts":      pub_ts,
                    "id":      hashlib.md5(link.encode()).hexdigest()[:16],
                })
            except Exception:
                continue
        if articles:
            log.info(f"[CG_NEWS] API: {len(articles)} articles")
            return articles

    # Fallback: RSS feed (always works, no auth)
    log.info("[CG_NEWS] API failed, trying RSS fallback")
    rss_articles = fetch_rss_feed("CoinGecko", COINGECKO_RSS_URL)
    return rss_articles


def fetch_cryptopanic() -> List[Dict]:
    """
    Fetch news from CryptoPanic.
    With key: uses authenticated endpoint
    Without key: tries free endpoint (limited data but no auth)
    """
    if CRYPTOPANIC_KEY:
        # Authenticated mode
        params = {"auth_token": CRYPTOPANIC_KEY, "filter": "hot"}
        data = safe_request("GET", CRYPTOPANIC_URL, params=params,
                            timeout=(5, 15))
    else:
        # Free public mode (CryptoPanic restricted public endpoint mid-2025)
        # Try free endpoint with minimal params
        params = {"public": "true"}
        data = safe_request("GET", CRYPTOPANIC_FREE_URL, params=params,
                            timeout=(5, 15))
        # If free endpoint also fails, return empty (not critical)
        if not data or (isinstance(data, dict) and "_auth_error" in data):
            log.info("[CP] free endpoint unavailable, skipping")
            return []

    if not data or not isinstance(data, dict):
        return []
    if "_auth_error" in data:
        log.warning(f"[CP] auth error {data.get('_auth_error')}")
        return []

    articles = []
    for item in data.get("results", [])[:MAX_ARTICLES_PER_FETCH]:
        try:
            title = item.get("title", "").strip()
            link = item.get("url", "") or item.get("source", {}).get("url", "")
            ts_str = item.get("published_at", "")
            pub_ts = _parse_rss_date(ts_str) if ts_str else int(time.time())

            currencies = item.get("currencies", [])
            tagged_coins = [c.get("code", "").upper() for c in currencies if c.get("code")]

            votes = item.get("votes", {})
            cp_sentiment = "neutral"
            if votes.get("positive", 0) > votes.get("negative", 0) * 1.5:
                cp_sentiment = "bullish"
            elif votes.get("negative", 0) > votes.get("positive", 0) * 1.5:
                cp_sentiment = "bearish"

            if not title or not link:
                continue

            articles.append({
                "title":   title,
                "summary": "",
                "url":     link,
                "source":  "CryptoPanic",
                "ts":      pub_ts,
                "id":      hashlib.md5(link.encode()).hexdigest()[:16],
                "tagged_coins": tagged_coins,
                "cp_sentiment": cp_sentiment,
            })
        except Exception:
            continue

    log.info(f"[CP] {len(articles)} articles")
    return articles


def fetch_all_news() -> List[Dict]:
    """Fetch from all 5 sources, deduplicate, sort by recency."""
    all_articles = []

    # 3 RSS feeds
    for name, url in RSS_FEEDS.items():
        try:
            all_articles.extend(fetch_rss_feed(name, url))
        except Exception as e:
            log.warning(f"[FETCH] {name}: {e}")

    # CoinGecko
    try:
        all_articles.extend(fetch_coingecko_news())
    except Exception as e:
        log.warning(f"[FETCH] CoinGecko: {e}")

    # CryptoPanic
    try:
        all_articles.extend(fetch_cryptopanic())
    except Exception as e:
        log.warning(f"[FETCH] CryptoPanic: {e}")

    # Deduplicate by ID
    seen = set()
    unique = []
    for a in all_articles:
        if a["id"] not in seen:
            seen.add(a["id"])
            unique.append(a)

    # Filter by age
    cutoff_ts = int(time.time()) - (MAX_ARTICLE_AGE_HOURS * 3600)
    fresh = [a for a in unique if a["ts"] >= cutoff_ts]

    # Sort newest first
    fresh.sort(key=lambda x: x["ts"], reverse=True)

    log.info(f"[FETCH] total: {len(all_articles)}, unique: {len(unique)}, fresh: {len(fresh)}")
    return fresh


# ══════════════════════════════════════════════════════════════════
# 5. COIN DETECTION + PORTFOLIO INTEGRATION
# ══════════════════════════════════════════════════════════════════

# Pre-build regex patterns for coin detection
_COIN_PATTERNS = {}
for symbol, names in KNOWN_COINS.items():
    # Match symbol as standalone word OR any of its names
    patterns = [r"\b" + re.escape(symbol) + r"\b"]
    for name in names:
        patterns.append(r"\b" + re.escape(name) + r"\b")
    _COIN_PATTERNS[symbol] = re.compile(
        "|".join(patterns), re.IGNORECASE
    )


def detect_coins_in_text(text: str) -> List[str]:
    """Extract crypto symbols mentioned in text."""
    if not text:
        return []
    found = []
    for symbol, pattern in _COIN_PATTERNS.items():
        if pattern.search(text):
            found.append(symbol)
    return found


def enrich_with_coins(articles: List[Dict]) -> List[Dict]:
    """Add 'coins' field to each article."""
    for a in articles:
        # If CryptoPanic already tagged, prefer that
        coins = a.get("tagged_coins", [])
        if not coins:
            text = f"{a.get('title','')} {a.get('summary','')}"
            coins = detect_coins_in_text(text)
        # Filter to known coins only
        a["coins"] = [c for c in coins if c in KNOWN_COINS]
    return articles


def get_portfolio_coins() -> List[str]:
    """Read DCA_BOT portfolio to get user's coin list (if available)."""
    portfolio_path = os.path.join(DCA_DATA_DIR, "portfolio_latest.json")
    if not os.path.exists(portfolio_path):
        return []
    try:
        with open(portfolio_path, "r", encoding="utf-8") as f:
            p = json.load(f)
        unified = p.get("unified", [])
        # Skip stables
        coins = [a["asset"] for a in unified
                 if not a.get("is_stable", False)]
        return coins
    except Exception as e:
        log.debug(f"[PORTFOLIO] read failed: {e}")
        return []


def filter_by_portfolio(articles: List[Dict],
                        portfolio_coins: List[str]) -> List[Dict]:
    """Mark articles relevant to user's portfolio."""
    pset = set(portfolio_coins)
    for a in articles:
        article_coins = set(a.get("coins", []))
        a["portfolio_match"] = list(article_coins & pset)
        a["is_portfolio_relevant"] = len(a["portfolio_match"]) > 0
    return articles


# ══════════════════════════════════════════════════════════════════
# 6. GEMINI AI ANALYZER
# ══════════════════════════════════════════════════════════════════

def gemini_analyze(article: Dict) -> Optional[Dict]:
    """
    Analyze article with Gemini. Simple, robust, scanner_bot-style.
    Returns: {sentiment, impact, reasoning_ar, summary_ar, action_hint} or None
    """
    if not GEMINI_API_KEY:
        return None

    title = article.get("title", "")
    summary = article.get("summary", "")[:300]
    coins = article.get("coins", [])
    coins_str = ", ".join(coins) if coins else "general crypto market"

    prompt = f"""Analyze this crypto news. Reply with ONLY a JSON object (no markdown, no code fences, no extra text):

TITLE: {title}
SUMMARY: {summary}
COINS: {coins_str}

JSON format:
{{"sentiment":"bullish OR bearish OR neutral","impact":"high OR medium OR low","reasoning_ar":"3 short Arabic sentences","summary_ar":"1-2 Arabic sentences summary","action_hint":"1 short Arabic suggestion"}}

Rules:
- impact=high if news could move price 5%+ in 24h
- impact=medium for partnerships/tech updates
- impact=low for minor news
- sentiment from crypto market perspective"""

    url = f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 800,
        }
    }

    # Retry on rate limit (Gemini free tier: 10 RPM for 2.5-flash)
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            r = _session.post(url, headers=headers, json=body, timeout=(10, 30))
        except Exception as e:
            log.warning(f"[GEMINI] request failed: {type(e).__name__}: {e}")
            return None

        if r.status_code == 200:
            break  # success
        elif r.status_code == 429:
            wait = 5 * (attempt + 1)  # 5s, 10s, 15s
            log.info(f"[GEMINI] rate limit, waiting {wait}s (attempt {attempt+1}/{max_attempts})")
            time.sleep(wait)
            continue
        else:
            log.warning(f"[GEMINI] HTTP {r.status_code}: {r.text[:120]}")
            return None
    else:
        log.warning(f"[GEMINI] all {max_attempts} attempts hit rate limit")
        return None

    # Extract text from response
    try:
        data = r.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, ValueError) as e:
        log.warning(f"[GEMINI] response parse: {e}")
        return None

    # Strip code fences (Gemini often adds them despite instructions)
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    text = text.strip()

    # Try direct JSON parse
    parsed = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Fallback: find first {...} block
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                log.warning(f"[GEMINI] JSON unparseable: {text[:80]}")
                return None

    if not parsed or "sentiment" not in parsed or "impact" not in parsed:
        log.warning(f"[GEMINI] missing fields: {text[:80]}")
        return None

    return {
        "sentiment":    str(parsed.get("sentiment", "neutral")).lower(),
        "impact":       str(parsed.get("impact", "low")).lower(),
        "reasoning_ar": parsed.get("reasoning_ar", ""),
        "summary_ar":   parsed.get("summary_ar", ""),
        "action_hint":  parsed.get("action_hint", ""),
    }



# ── Binance Market Data ──
BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/24hr"

# Coins → Binance USDT pairs (most liquid market)
_BINANCE_SYMBOLS = {
    "BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT",
    "BNB": "BNBUSDT", "XRP": "XRPUSDT", "ADA": "ADAUSDT",
    "DOGE": "DOGEUSDT", "AVAX": "AVAXUSDT", "DOT": "DOTUSDT",
    "MATIC": "MATICUSDT", "LINK": "LINKUSDT", "UNI": "UNIUSDT",
    "AAVE": "AAVEUSDT", "ATOM": "ATOMUSDT", "NEAR": "NEARUSDT",
    "HBAR": "HBARUSDT", "ARB": "ARBUSDT", "OP": "OPUSDT",
    "PEPE": "PEPEUSDT", "SHIB": "SHIBUSDT", "WIF": "WIFUSDT",
    "BONK": "BONKUSDT", "ONDO": "ONDOUSDT", "PYTH": "PYTHUSDT",
    "RENDER": "RENDERUSDT", "TAO": "TAOUSDT", "FET": "FETUSDT",
    "HYPE": "HYPEUSDT", "SUI": "SUIUSDT", "APT": "APTUSDT",
    "INJ": "INJUSDT", "SEI": "SEIUSDT", "TIA": "TIAUSDT",
    "JUP": "JUPUSDT", "ENS": "ENSUSDT", "MKR": "MKRUSDT",
    "LDO": "LDOUSDT", "GRT": "GRTUSDT", "FIL": "FILUSDT",
    "LTC": "LTCUSDT", "BCH": "BCHUSDT", "TRX": "TRXUSDT",
}


def get_market_context(coin: str) -> Optional[Dict]:
    """
    Fetch real-time price + 24h stats from Binance.
    Returns: {price, high_24h, low_24h, change_pct_24h, volume_usd_24h} or None
    """
    symbol = _BINANCE_SYMBOLS.get(coin.upper())
    if not symbol:
        return None

    try:
        r = _session.get(BINANCE_TICKER_URL, params={"symbol": symbol},
                         timeout=(5, 10))
        if r.status_code != 200:
            log.debug(f"[MARKET] {symbol}: HTTP {r.status_code}")
            return None
        data = r.json()
        price = float(data.get("lastPrice", 0))
        high = float(data.get("highPrice", 0))
        low = float(data.get("lowPrice", 0))
        change_pct = float(data.get("priceChangePercent", 0))
        volume_usd = float(data.get("quoteVolume", 0))

        if price <= 0:
            return None

        return {
            "coin": coin.upper(),
            "symbol": symbol,
            "price": price,
            "high_24h": high,
            "low_24h": low,
            "change_pct_24h": change_pct,
            "volume_usd_24h": volume_usd,
        }
    except Exception as e:
        log.debug(f"[MARKET] {coin} fetch failed: {e}")
        return None


def get_market_context_multi(coins: List[str], max_coins: int = 3) -> List[Dict]:
    """Fetch market context for top N coins from a list."""
    contexts = []
    for coin in coins[:max_coins]:
        ctx = get_market_context(coin)
        if ctx:
            contexts.append(ctx)
    return contexts


def format_market_context_for_prompt(contexts: List[Dict]) -> str:
    """Format market data as plain text for inclusion in AI prompts."""
    if not contexts:
        return "No market data available."

    lines = ["REAL-TIME MARKET DATA (from Binance, NOW):"]
    for ctx in contexts:
        coin = ctx["coin"]
        price = ctx["price"]
        high = ctx["high_24h"]
        low = ctx["low_24h"]
        change = ctx["change_pct_24h"]
        vol_m = ctx["volume_usd_24h"] / 1_000_000

        # Smart formatting based on price magnitude
        if price >= 100:
            price_str = f"${price:,.2f}"
            high_str = f"${high:,.2f}"
            low_str = f"${low:,.2f}"
        elif price >= 1:
            price_str = f"${price:.4f}"
            high_str = f"${high:.4f}"
            low_str = f"${low:.4f}"
        else:
            price_str = f"${price:.8f}"
            high_str = f"${high:.8f}"
            low_str = f"${low:.8f}"

        change_sign = "+" if change >= 0 else ""
        lines.append(
            f"  {coin}: {price_str} ({change_sign}{change:.2f}%) | "
            f"24h Range: {low_str}-{high_str} | Vol: ${vol_m:.1f}M"
        )

    return "\n".join(lines)


def claude_analyze(article: Dict, market_contexts: Optional[List[Dict]] = None) -> Optional[Dict]:
    """
    🟣 Claude — Strategic Analyst.
    Deep reasoning, historical context, risk assessment.
    market_contexts: real-time price data from Binance (passed from caller)
    Returns: {scenario_ar, risks_ar, historical_ar, confidence}
    """
    if not CLAUDE_API_KEY:
        return None

    title = article.get("title", "")
    summary = article.get("summary", "")[:400]
    coins = article.get("coins", [])
    portfolio_match = article.get("portfolio_match", [])
    gemini_result = article.get("ai", {})

    coins_str = ", ".join(coins) if coins else "general crypto market"
    portfolio_str = ", ".join(portfolio_match) if portfolio_match else "none"
    gemini_sentiment = gemini_result.get("sentiment", "unknown")
    gemini_impact = gemini_result.get("impact", "unknown")

    # Format market data for prompt
    market_section = ""
    if market_contexts:
        market_section = f"\n\n{format_market_context_for_prompt(market_contexts)}\n"

    prompt = f"""You are a senior crypto market strategist. Analyze this news with DEEP reasoning.

NEWS:
TITLE: {title}
SUMMARY: {summary}
COINS: {coins_str}
USER_PORTFOLIO_AFFECTED: {portfolio_str}

PRIOR ANALYSIS (Gemini):
- Sentiment: {gemini_sentiment}
- Impact: {gemini_impact}
{market_section}
YOUR TASK: Provide strategic analysis. Reply with ONLY this JSON (no markdown, no code fences):

{{
  "scenario_ar": "السيناريو الأرجح خلال 24-48 ساعة (3-4 أسطر بالعربي)",
  "risks_ar": "أهم 2-3 مخاطر يجب الحذر منها (بالعربي)",
  "historical_ar": "سياق تاريخي: متى حدث شيء مشابه وما كانت النتيجة (سطرين بالعربي)",
  "confidence": "high OR medium OR low",
  "agree_with_gemini": true OR false
}}

CRITICAL: If market data is provided above, USE THE REAL CURRENT PRICES in your scenario.
Do NOT invent price levels — use ONLY what's shown in REAL-TIME MARKET DATA section above.
If no market data, write scenarios in % terms (e.g. '+5%') without specific dollar amounts."""

    headers = {
        "Content-Type": "application/json",
        "x-api-key": CLAUDE_API_KEY,
        "anthropic-version": "2023-06-01",
    }
    body = {
        "model": CLAUDE_MODEL,
        "max_tokens": 800,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        r = _session.post(CLAUDE_BASE, headers=headers, json=body, timeout=(10, 35))
    except Exception as e:
        log.warning(f"[CLAUDE] request failed: {type(e).__name__}: {e}")
        return None

    # Try fallback model if primary fails with 404 or model error
    if r.status_code in (404, 400):
        log.info(f"[CLAUDE] {CLAUDE_MODEL} unavailable, trying {CLAUDE_FALLBACK}")
        body["model"] = CLAUDE_FALLBACK
        try:
            r = _session.post(CLAUDE_BASE, headers=headers, json=body, timeout=(10, 35))
        except Exception as e:
            log.warning(f"[CLAUDE] fallback failed: {e}")
            return None

    if r.status_code != 200:
        log.warning(f"[CLAUDE] HTTP {r.status_code}: {r.text[:120]}")
        return None

    try:
        data = r.json()
        content = data.get("content", [])
        if not content:
            return None
        text = content[0].get("text", "").strip()
    except (KeyError, IndexError, ValueError) as e:
        log.warning(f"[CLAUDE] response parse: {e}")
        return None

    # Strip code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    text = text.strip()

    parsed = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                log.warning(f"[CLAUDE] JSON unparseable: {text[:80]}")
                return None

    if not parsed:
        return None

    return {
        "scenario_ar":      parsed.get("scenario_ar", ""),
        "risks_ar":         parsed.get("risks_ar", ""),
        "historical_ar":    parsed.get("historical_ar", ""),
        "confidence":       str(parsed.get("confidence", "medium")).lower(),
        "agree_with_gemini": bool(parsed.get("agree_with_gemini", True)),
    }


def openai_analyze(article: Dict, market_contexts: Optional[List[Dict]] = None) -> Optional[Dict]:
    """
    🔵 OpenAI GPT-4o — Market Voice / Execution Advisor.
    Specific actionable recommendations + price levels based on REAL market data.
    market_contexts: real-time price data from Binance (passed from caller)
    Returns: {action_ar, levels, time_window_ar, conviction, market_data}
    """
    if not OPENAI_API_KEY:
        return None

    title = article.get("title", "")
    summary = article.get("summary", "")[:400]
    coins = article.get("coins", [])
    portfolio_match = article.get("portfolio_match", [])
    gemini_result = article.get("ai", {})
    claude_result = article.get("claude", {})

    coins_str = ", ".join(coins) if coins else "general crypto market"
    portfolio_str = ", ".join(portfolio_match) if portfolio_match else "none"

    context_lines = [
        f"Gemini sentiment: {gemini_result.get('sentiment', 'N/A')}",
        f"Gemini impact: {gemini_result.get('impact', 'N/A')}",
    ]
    if claude_result:
        context_lines.append(f"Claude scenario: {claude_result.get('scenario_ar', 'N/A')[:100]}")
        context_lines.append(f"Claude confidence: {claude_result.get('confidence', 'N/A')}")
    context_str = "\n".join(context_lines)

    # Format market data for prompt (CRITICAL for accurate recommendations)
    market_section = ""
    if market_contexts:
        market_section = f"\n{format_market_context_for_prompt(market_contexts)}\n"
        price_rule = """
CRITICAL PRICE RULES:
- USE ONLY the prices shown above in REAL-TIME MARKET DATA section
- DO NOT invent or guess price levels — they MUST come from the data above
- For support: use the 24h low or near it
- For resistance: use the 24h high or near it
- For stop_loss: use a value below the 24h low
- ALL price values must be plain numbers (e.g. 76490 not "$76,490")"""
    else:
        price_rule = """
NO MARKET DATA PROVIDED:
- Set support, resistance, stop_loss ALL to null
- Give percentage-based advice instead (e.g. "stop loss 5% below entry")
- DO NOT invent specific dollar amounts"""

    prompt = f"""You are a crypto trading desk advisor. Give SPECIFIC actionable advice.

NEWS:
TITLE: {title}
SUMMARY: {summary}
COINS: {coins_str}
USER_PORTFOLIO_AFFECTED: {portfolio_str}

EXISTING ANALYSIS:
{context_str}
{market_section}{price_rule}

YOUR TASK: Practical execution recommendations. Reply with ONLY this JSON:

{{
  "action_ar": "1-3 توصيات تنفيذية محددة بالعربي",
  "levels": {{
    "support": number OR null,
    "resistance": number OR null,
    "stop_loss": number OR null
  }},
  "time_window_ar": "متى يجب اتخاذ القرار",
  "conviction": "high OR medium OR low",
  "primary_coin_affected": "ticker OR 'multiple'"
}}

Be DECISIVE but never financial advice."""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}",
    }
    body = {
        "model": OPENAI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 600,
        "response_format": {"type": "json_object"},
    }

    try:
        r = _session.post(OPENAI_BASE, headers=headers, json=body, timeout=(10, 35))
    except Exception as e:
        log.warning(f"[OPENAI] request failed: {type(e).__name__}: {e}")
        return None

    # Fallback to gpt-4o-mini if primary fails
    if r.status_code in (404, 400):
        log.info(f"[OPENAI] {OPENAI_MODEL} issue, trying {OPENAI_FALLBACK}")
        body["model"] = OPENAI_FALLBACK
        try:
            r = _session.post(OPENAI_BASE, headers=headers, json=body, timeout=(10, 35))
        except Exception as e:
            log.warning(f"[OPENAI] fallback failed: {e}")
            return None

    if r.status_code != 200:
        log.warning(f"[OPENAI] HTTP {r.status_code}: {r.text[:120]}")
        return None

    try:
        data = r.json()
        text = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, ValueError) as e:
        log.warning(f"[OPENAI] response parse: {e}")
        return None

    # OpenAI with json_object format gives clean JSON, but be safe
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)

    parsed = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                log.warning(f"[OPENAI] JSON unparseable: {text[:80]}")
                return None

    if not parsed:
        return None

    levels = parsed.get("levels", {}) or {}
    return {
        "action_ar":             parsed.get("action_ar", ""),
        "support":               levels.get("support"),
        "resistance":            levels.get("resistance"),
        "stop_loss":             levels.get("stop_loss"),
        "time_window_ar":        parsed.get("time_window_ar", ""),
        "conviction":            str(parsed.get("conviction", "medium")).lower(),
        "primary_coin_affected": parsed.get("primary_coin_affected", ""),
        "market_data":           market_contexts or [],  # store for display
    }


def council_analyze(article: Dict, tier: str = "fast") -> Dict:
    """
    🤝 Council Coordinator — Routes article through AI tiers.

    Tiers:
    - "fast":    Gemini only (default for all news)
    - "deep":    Gemini + Claude (for important news)
    - "council": Gemini + Claude + GPT-4o (for breaking news)

    Returns updated article dict (in-place too).
    """
    # Tier 1: Gemini (always first, fast)
    if "ai" not in article:
        gem = gemini_analyze(article)
        if gem:
            article["ai"] = gem

    if tier == "fast":
        return article

    # Tier 2: Claude (deep reasoning)
    if "claude" not in article and CLAUDE_API_KEY:
        clde = claude_analyze(article)
        if clde:
            article["claude"] = clde

    if tier == "deep":
        return article

    # Tier 3: OpenAI (execution advice)
    if "openai" not in article and OPENAI_API_KEY:
        oai = openai_analyze(article)
        if oai:
            article["openai"] = oai

    return article


def determine_tier(article: Dict) -> str:
    """
    Decide which AI tier to use based on article importance.
    """
    ai = article.get("ai", {})
    impact = ai.get("impact", "low")
    is_portfolio = article.get("is_portfolio_relevant", False)

    # Council (full team) for breaking news affecting portfolio
    if impact == "high" and is_portfolio:
        return "council"

    # Deep (Gemini + Claude) for any important news
    if impact == "high" or is_portfolio:
        return "deep"

    # Fast (Gemini only) for everything else
    return "fast"


def should_analyze(article: Dict) -> bool:
    """
    Decide if article deserves Gemini analysis (saves quota).
    Strategy: only analyze if relevant to portfolio OR has coin mentions.
    """
    if article.get("is_portfolio_relevant"):
        return True
    if len(article.get("coins", [])) > 0:
        return True
    # Otherwise: skip generic news (no coins detected)
    return False


def enrich_with_ai(articles: List[Dict],
                    max_to_analyze: int = 8,
                    enable_council: bool = True) -> List[Dict]:
    """
    Run AI analysis on relevant articles using Council pattern.

    Phase 1 (always): Gemini analyzes all candidates
    Phase 2 (council): Claude + OpenAI for important ones (limited!)

    NOTE: Council in pipeline is conservative (saves quota).
    For full council on a specific article, use /council command.
    """
    candidates = [a for a in articles if should_analyze(a)]
    candidates = candidates[:max_to_analyze]

    log.info(f"[AI] Phase 1 (Gemini): {len(candidates)} articles...")

    # Phase 1: Gemini for all candidates
    gemini_success = 0
    for a in candidates:
        try:
            ai = gemini_analyze(a)
            if ai:
                a["ai"] = ai
                gemini_success += 1
            time.sleep(0.5)  # Increased from 0.3 to avoid rate limit
        except Exception as e:
            log.warning(f"[AI] {a.get('title','?')[:40]}: {e}")

    log.info(f"[AI] Gemini: {gemini_success}/{len(candidates)} succeeded")

    # Phase 2: Conservative council escalation
    # Only for the SINGLE highest-priority article (saves cost+time)
    if enable_council:
        council_targets = []
        deep_targets = []
        for a in candidates:
            if not a.get("ai"):
                continue
            tier = determine_tier(a)
            if tier == "council":
                council_targets.append(a)
            elif tier == "deep":
                deep_targets.append(a)

        # CONSERVATIVE: only top 1 council, top 2 deep (saves quota for /council manual)
        council_targets = council_targets[:1]
        deep_targets = deep_targets[:2]

        if council_targets:
            log.info(f"[AI] Phase 2a (Council): {len(council_targets)} articles")
            for a in council_targets:
                try:
                    # Fetch real-time market context for this article's coins
                    article_coins = a.get("coins", [])
                    market_ctx = get_market_context_multi(article_coins, max_coins=3)
                    if CLAUDE_API_KEY:
                        clde = claude_analyze(a, market_contexts=market_ctx)
                        if clde:
                            a["claude"] = clde
                        time.sleep(0.5)
                    if OPENAI_API_KEY:
                        oai = openai_analyze(a, market_contexts=market_ctx)
                        if oai:
                            a["openai"] = oai
                        time.sleep(0.3)
                except Exception as e:
                    log.warning(f"[COUNCIL] {a.get('title','?')[:40]}: {e}")

        if deep_targets:
            log.info(f"[AI] Phase 2b (Deep): {len(deep_targets)} articles")
            for a in deep_targets:
                try:
                    article_coins = a.get("coins", [])
                    market_ctx = get_market_context_multi(article_coins, max_coins=2)
                    if CLAUDE_API_KEY:
                        clde = claude_analyze(a, market_contexts=market_ctx)
                        if clde:
                            a["claude"] = clde
                        time.sleep(0.3)
                except Exception as e:
                    log.warning(f"[DEEP] {a.get('title','?')[:40]}: {e}")

    return articles


# ══════════════════════════════════════════════════════════════════
# 7. MAIN PIPELINE
# ══════════════════════════════════════════════════════════════════

def run_news_pipeline(do_ai: bool = True) -> List[Dict]:
    """
    Full pipeline: fetch → enrich → analyze → save.
    Returns processed article list.
    """
    log.info("[PIPELINE] starting...")

    # Step 1: Fetch
    articles = fetch_all_news()
    if not articles:
        return []

    # Step 2: Enrich with coin detection
    articles = enrich_with_coins(articles)

    # Step 3: Match against user portfolio
    portfolio = get_portfolio_coins()
    articles = filter_by_portfolio(articles, portfolio)

    # Step 4: AI analysis (only on relevant ones)
    if do_ai and GEMINI_API_KEY:
        articles = enrich_with_ai(articles, max_to_analyze=8)

    # Step 5: Save snapshot
    storage_save("news_latest.json", {
        "timestamp": now_iso(),
        "portfolio_coins": portfolio,
        "count": len(articles),
        "articles": articles,
    })

    log.info(f"[PIPELINE] done. {len(articles)} articles.")
    return articles


# ══════════════════════════════════════════════════════════════════
# 8. FORMATTERS
# ══════════════════════════════════════════════════════════════════

_SENTIMENT_EMOJI = {
    "bullish": "🟢",
    "bearish": "🔴",
    "neutral": "🟡",
}

_IMPACT_EMOJI = {
    "high":   "🔥",
    "medium": "⚠️",
    "low":    "📰",
}

_SENTIMENT_AR = {
    "bullish": "إيجابي",
    "bearish": "سلبي",
    "neutral": "محايد",
}

_IMPACT_AR = {
    "high":   "عالٍ",
    "medium": "متوسط",
    "low":    "منخفض",
}


def _time_ago(ts: int) -> str:
    """Human-readable time since timestamp."""
    diff = int(time.time()) - ts
    if diff < 60:
        return "الآن"
    if diff < 3600:
        return f"منذ {diff // 60} دقيقة"
    if diff < 86400:
        return f"منذ {diff // 3600} ساعة"
    return f"منذ {diff // 86400} يوم"


def format_article_brief(a: Dict, idx: Optional[int] = None) -> str:
    """One-liner article format for /news list."""
    title = a.get("title", "")[:90]
    source = a.get("source", "?")
    age = _time_ago(a.get("ts", int(time.time())))
    coins = a.get("coins", [])

    ai = a.get("ai", {})
    sent_emoji = _SENTIMENT_EMOJI.get(ai.get("sentiment", "neutral"), "")
    impact_emoji = _IMPACT_EMOJI.get(ai.get("impact", ""), "")

    coins_str = ""
    if coins:
        coins_str = f" [{', '.join(coins[:3])}]"

    prefix = f"{idx}. " if idx is not None else ""
    return (f"{prefix}{sent_emoji}{impact_emoji} *{title}*\n"
            f"   📡 {source} · {age}{coins_str}\n"
            f"   🔗 [قراءة]({a.get('url','')})")


def format_article_detailed(a: Dict) -> str:
    """Full article format with AI analysis."""
    title = a.get("title", "")
    source = a.get("source", "?")
    age = _time_ago(a.get("ts", int(time.time())))
    coins = a.get("coins", [])
    portfolio_match = a.get("portfolio_match", [])
    ai = a.get("ai", {})

    lines = []

    # Header
    impact_emoji = _IMPACT_EMOJI.get(ai.get("impact", "low"), "📰")
    sent_emoji = _SENTIMENT_EMOJI.get(ai.get("sentiment", "neutral"), "")

    if portfolio_match:
        lines.append(f"🚨 *خبر يخص محفظتك*")
    else:
        lines.append(f"{impact_emoji} *خبر كريبتو*")
    lines.append("")

    # Title + meta
    lines.append(f"📰 *{title}*")
    lines.append(f"📡 {source} · {age}")

    if coins:
        coins_str = ", ".join(coins[:5])
        lines.append(f"🪙 العملات: `{coins_str}`")

    if portfolio_match:
        lines.append(f"💼 من محفظتك: *{', '.join(portfolio_match)}*")

    lines.append("")

    # AI analysis
    if ai:
        sent = ai.get("sentiment", "neutral")
        impact = ai.get("impact", "low")
        lines.append(f"🤖 *تحليل AI:*")
        lines.append(f"   📊 Sentiment: {sent_emoji} {_SENTIMENT_AR.get(sent, sent)}")
        lines.append(f"   ⚡ Impact: {_IMPACT_AR.get(impact, impact)}")

        summary = ai.get("summary_ar", "")
        if summary:
            lines.append("")
            lines.append(f"📝 *الملخص:*")
            lines.append(f"   {summary}")

        reasoning = ai.get("reasoning_ar", "")
        if reasoning:
            lines.append("")
            lines.append(f"💡 *لماذا؟*")
            lines.append(f"   {reasoning}")

        action = ai.get("action_hint", "")
        if action:
            lines.append("")
            lines.append(f"🎯 *اقتراح:* {action}")

    lines.append("")
    lines.append(f"🔗 [قراءة الخبر كاملاً]({a.get('url','')})")
    lines.append("")
    lines.append("⚠️ _تحليل آلي — تنفيذ يدوي 100%_")

    return "\n".join(lines)


def format_council_alert(a: Dict) -> str:
    """
    🤝 Council format — full 3-AI analysis for breaking news.
    Used for high-impact news affecting user's portfolio.
    """
    title = a.get("title", "")
    source = a.get("source", "?")
    age = _time_ago(a.get("ts", int(time.time())))
    coins = a.get("coins", [])
    portfolio_match = a.get("portfolio_match", [])

    gem = a.get("ai", {})
    clde = a.get("claude", {})
    oai = a.get("openai", {})

    lines = []

    # ── Header ──
    if clde and oai:
        lines.append("🚨🚨 *تنبيه أحمر — خبر عالي الأهمية*")
    elif clde:
        lines.append("🚨 *تنبيه — تحليل عميق*")
    else:
        lines.append("🚨 *تنبيه*")
    lines.append("")

    lines.append(f"📰 *{title}*")
    lines.append(f"📡 {source} · {age}")

    if coins:
        lines.append(f"🪙 العملات: `{', '.join(coins[:5])}`")
    if portfolio_match:
        lines.append(f"💼 *من محفظتك:* `{', '.join(portfolio_match)}`")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")

    # ── 🟢 Gemini (Quick Eye) ──
    if gem:
        sent = gem.get("sentiment", "neutral")
        impact = gem.get("impact", "low")
        sent_emoji = _SENTIMENT_EMOJI.get(sent, "")
        lines.append("")
        lines.append("🟢 *العين السريعة (Gemini):*")
        lines.append(f"   📊 Sentiment: {sent_emoji} {_SENTIMENT_AR.get(sent, sent)}")
        lines.append(f"   ⚡ Impact: {_IMPACT_AR.get(impact, impact)}")
        summary = gem.get("summary_ar", "")
        if summary:
            lines.append(f"   📝 {summary}")

    # ── 🟣 Claude (Strategic Analyst) ──
    if clde:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("")
        lines.append("🟣 *المحلل الاستراتيجي (Claude):*")
        scenario = clde.get("scenario_ar", "")
        if scenario:
            lines.append(f"")
            lines.append(f"   🎯 *السيناريو:*")
            lines.append(f"   {scenario}")
        risks = clde.get("risks_ar", "")
        if risks:
            lines.append(f"")
            lines.append(f"   ⚠️ *المخاطر:*")
            lines.append(f"   {risks}")
        historical = clde.get("historical_ar", "")
        if historical:
            lines.append(f"")
            lines.append(f"   📚 *سياق تاريخي:*")
            lines.append(f"   {historical}")

        confidence = clde.get("confidence", "medium")
        agree = clde.get("agree_with_gemini", True)
        agree_str = "متفق مع Gemini" if agree else "*يخالف Gemini*"
        lines.append(f"")
        lines.append(f"   🎚 ثقة: `{confidence}` · {agree_str}")

    # ── 🔵 OpenAI (Market Voice) ──
    if oai:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("")
        lines.append("🔵 *صوت السوق (GPT-4o):*")

        # Show REAL market data first (from Binance)
        market_data = oai.get("market_data", []) or []
        if market_data:
            lines.append("")
            lines.append("   📊 *السعر الحالي (Binance):*")
            for ctx in market_data[:3]:
                coin = ctx.get("coin", "?")
                price = ctx.get("price", 0)
                change = ctx.get("change_pct_24h", 0)
                high = ctx.get("high_24h", 0)
                low = ctx.get("low_24h", 0)

                # Format prices intelligently
                if price >= 100:
                    p_str = f"${price:,.2f}"
                    h_str = f"${high:,.2f}"
                    l_str = f"${low:,.2f}"
                elif price >= 1:
                    p_str = f"${price:.4f}"
                    h_str = f"${high:.4f}"
                    l_str = f"${low:.4f}"
                else:
                    p_str = f"${price:.6f}"
                    h_str = f"${high:.6f}"
                    l_str = f"${low:.6f}"

                sign = "+" if change >= 0 else ""
                arrow = "🟢" if change >= 0 else "🔴"
                lines.append(f"   • {coin}: `{p_str}` {arrow} {sign}{change:.2f}%")
                lines.append(f"     24h: `{l_str}` ↔ `{h_str}`")

        action = oai.get("action_ar", "")
        if action:
            lines.append(f"")
            lines.append(f"   🎯 *توصية تنفيذية:*")
            lines.append(f"   {action}")

        # Price levels (now backed by real data)
        support = oai.get("support")
        resistance = oai.get("resistance")
        stop_loss = oai.get("stop_loss")

        def _fmt_level(val):
            """Format level: handle int/float/string/null."""
            if val is None or val == "null" or val == "":
                return None
            try:
                num = float(val)
                if num >= 100:
                    return f"${num:,.2f}"
                elif num >= 1:
                    return f"${num:.4f}"
                else:
                    return f"${num:.6f}"
            except (ValueError, TypeError):
                return str(val)

        s_str = _fmt_level(support)
        r_str = _fmt_level(resistance)
        sl_str = _fmt_level(stop_loss)

        if any([s_str, r_str, sl_str]):
            lines.append(f"")
            lines.append(f"   📈 *مستويات تداول:*")
            if s_str:
                lines.append(f"   • Support: `{s_str}`")
            if r_str:
                lines.append(f"   • Resistance: `{r_str}`")
            if sl_str:
                lines.append(f"   • Stop Loss: `{sl_str}`")

        time_window = oai.get("time_window_ar", "")
        if time_window:
            lines.append(f"")
            lines.append(f"   ⏰ *نافذة القرار:* {time_window}")

        conviction = oai.get("conviction", "medium")
        lines.append(f"")
        lines.append(f"   🎚 قناعة: `{conviction}`")

    # ── 🤝 Council Verdict ──
    if clde and oai:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("")
        gemini_sent = gem.get("sentiment", "neutral")
        claude_agrees = clde.get("agree_with_gemini", True)
        confidence = clde.get("confidence", "medium")
        conviction = oai.get("conviction", "medium")

        if claude_agrees and confidence == "high" and conviction == "high":
            verdict = "🎯 *إجماع 3/3 — قناعة عالية*"
        elif claude_agrees:
            verdict = "✅ *Claude متفق مع Gemini*"
        else:
            verdict = "⚠️ *Claude يخالف — تحقق إضافي مطلوب*"

        lines.append(f"🤝 *Council Verdict:*")
        lines.append(f"   {verdict}")

    lines.append("")
    lines.append(f"🔗 [قراءة الخبر كاملاً]({a.get('url','')})")
    lines.append("")
    lines.append("⚠️ _تحليل آلي بـ 3 خبراء — تنفيذ يدوي 100%_")
    lines.append("⚠️ _ليست نصيحة مالية_")

    return "\n".join(lines)


def format_news_list(articles: List[Dict],
                      filter_coin: Optional[str] = None,
                      max_count: int = 10) -> str:
    """Format multiple articles as a list."""
    if filter_coin:
        articles = [a for a in articles
                    if filter_coin.upper() in a.get("coins", [])]
        title_suffix = f" — {filter_coin.upper()}"
    else:
        title_suffix = ""

    articles = articles[:max_count]

    if not articles:
        return f"⚪ لا توجد أخبار حالياً{title_suffix}"

    lines = [f"📰 *آخر الأخبار{title_suffix}* ({len(articles)})",
             f"🕐 {now_str()}",
             "━━━━━━━━━━━━━━━━━━━━",
             ""]

    for i, a in enumerate(articles, 1):
        lines.append(format_article_brief(a, idx=i))
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("⚠️ _معلومات فقط — ليست توصية_")
    return "\n".join(lines)


def compute_sentiment_overview(articles: List[Dict]) -> Dict[str, Any]:
    """Aggregate sentiment per coin."""
    by_coin: Dict[str, Dict] = {}
    for a in articles:
        ai = a.get("ai", {})
        sent = ai.get("sentiment", "neutral")
        for coin in a.get("coins", []):
            if coin not in by_coin:
                by_coin[coin] = {"bullish": 0, "bearish": 0, "neutral": 0}
            by_coin[coin][sent] += 1
    return by_coin


def format_sentiment(coin: Optional[str] = None) -> str:
    """Format sentiment overview."""
    snapshot = storage_load("news_latest.json", {})
    articles = snapshot.get("articles", [])

    if not articles:
        return "⚪ لا توجد بيانات بعد. أرسل `/news` أولاً."

    overview = compute_sentiment_overview(articles)

    if coin:
        coin = coin.upper()
        if coin not in overview:
            return f"⚪ لا توجد أخبار حديثة عن `{coin}`"
        data = overview[coin]
        total = sum(data.values())
        if total == 0:
            return f"⚪ لا توجد بيانات لـ `{coin}`"

        bull_pct = (data["bullish"] / total) * 100
        bear_pct = (data["bearish"] / total) * 100
        neut_pct = (data["neutral"] / total) * 100

        if bull_pct >= 60:
            verdict = "🟢 *إيجابي قوي*"
        elif bull_pct >= 40:
            verdict = "🟡 *مائل للإيجاب*"
        elif bear_pct >= 60:
            verdict = "🔴 *سلبي قوي*"
        elif bear_pct >= 40:
            verdict = "🟠 *مائل للسلب*"
        else:
            verdict = "⚪ *محايد*"

        return (f"📊 *Sentiment لـ {coin}*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"بناءً على {total} خبر آخر 4 ساعات:\n\n"
                f"🟢 إيجابي: `{data['bullish']}` ({bull_pct:.0f}%)\n"
                f"🔴 سلبي:   `{data['bearish']}` ({bear_pct:.0f}%)\n"
                f"🟡 محايد:  `{data['neutral']}` ({neut_pct:.0f}%)\n\n"
                f"الخلاصة: {verdict}")

    # All coins overview
    if not overview:
        return "⚪ لا توجد عملات في الأخبار الحديثة."

    sorted_coins = sorted(overview.items(),
                          key=lambda x: sum(x[1].values()),
                          reverse=True)[:15]

    lines = ["📊 *Sentiment Overview*",
             f"🕐 {now_str()}",
             "━━━━━━━━━━━━━━━━━━━━",
             ""]
    for coin, data in sorted_coins:
        total = sum(data.values())
        if total == 0:
            continue
        bull_pct = (data["bullish"] / total) * 100
        if bull_pct >= 60:
            emoji = "🟢"
        elif bull_pct >= 40:
            emoji = "🟡"
        elif data["bearish"] / total >= 0.6:
            emoji = "🔴"
        else:
            emoji = "⚪"
        lines.append(f"{emoji} *{coin}* — {bull_pct:.0f}% bullish ({total} خبر)")

    return "\n".join(lines)


def format_daily_digest(articles: List[Dict]) -> str:
    """Daily summary message (8am)."""
    lines = ["📊 *ملخص اليوم — صباح الخير ☀️*",
             f"🕐 {now_str()}",
             "━━━━━━━━━━━━━━━━━━━━",
             ""]

    # Top 5 by impact
    high_impact = [a for a in articles
                   if a.get("ai", {}).get("impact") == "high"]
    portfolio_news = [a for a in articles if a.get("is_portfolio_relevant")]

    if portfolio_news:
        lines.append(f"💼 *{len(portfolio_news)} خبر يخص محفظتك:*")
        for a in portfolio_news[:5]:
            lines.append(format_article_brief(a))
        lines.append("")

    if high_impact:
        lines.append(f"🔥 *{len(high_impact)} خبر عالي التأثير:*")
        for a in high_impact[:5]:
            if a not in portfolio_news:
                lines.append(format_article_brief(a))
        lines.append("")

    # Sentiment overview
    overview = compute_sentiment_overview(articles)
    if overview:
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("📊 *Sentiment Snapshot:*")
        sorted_coins = sorted(overview.items(),
                              key=lambda x: sum(x[1].values()),
                              reverse=True)[:8]
        for coin, data in sorted_coins:
            total = sum(data.values())
            if total == 0:
                continue
            bull_pct = (data["bullish"] / total) * 100
            emoji = "🟢" if bull_pct >= 50 else "🔴" if data["bearish"]/total >= 0.5 else "🟡"
            lines.append(f"   {emoji} {coin}: {bull_pct:.0f}% bullish")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("⚠️ _تحليل آلي — تنفيذ يدوي 100%_")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# 9. CONNECTIVITY TEST
# ══════════════════════════════════════════════════════════════════

def run_connectivity_test() -> Dict[str, Any]:
    """Test all 5 sources + Gemini + Storage."""
    results = {}

    # RSS feeds
    for name, url in RSS_FEEDS.items():
        start = time.time()
        try:
            articles = fetch_rss_feed(name, url)
            elapsed = int((time.time() - start) * 1000)
            results[name] = {
                "ok": len(articles) > 0,
                "count": len(articles),
                "elapsed_ms": elapsed,
            }
        except Exception as e:
            results[name] = {"ok": False, "error": str(e)[:80],
                             "elapsed_ms": 0}

    # CoinGecko
    start = time.time()
    try:
        cg = fetch_coingecko_news()
        results["CoinGecko"] = {
            "ok": len(cg) > 0,
            "count": len(cg),
            "elapsed_ms": int((time.time() - start) * 1000),
        }
    except Exception as e:
        results["CoinGecko"] = {"ok": False, "error": str(e)[:80]}

    # CryptoPanic
    start = time.time()
    try:
        cp = fetch_cryptopanic()
        results["CryptoPanic"] = {
            "ok": len(cp) > 0,
            "count": len(cp),
            "elapsed_ms": int((time.time() - start) * 1000),
        }
    except Exception as e:
        results["CryptoPanic"] = {"ok": False, "error": str(e)[:80]}

    # Gemini
    if GEMINI_API_KEY:
        start = time.time()
        try:
            test_article = {
                "title": "Bitcoin reaches new all-time high above $100,000",
                "summary": "BTC surged past $100K driven by ETF inflows.",
                "coins": ["BTC"],
            }
            ai = gemini_analyze(test_article)
            elapsed = int((time.time() - start) * 1000)
            results["Gemini"] = {
                "ok": ai is not None,
                "elapsed_ms": elapsed,
                "model": GEMINI_MODEL,
            }
            if ai:
                results["Gemini"]["sample_sentiment"] = ai.get("sentiment", "?")
        except Exception as e:
            results["Gemini"] = {"ok": False, "error": str(e)[:80]}
    else:
        results["Gemini"] = {"ok": False, "error": "GEMINI_API_KEY missing"}

    # Claude (only test if key present, avoid burning quota otherwise)
    if CLAUDE_API_KEY:
        start = time.time()
        try:
            test_article = {
                "title": "Bitcoin reaches new all-time high above $100,000",
                "summary": "BTC surged past $100K driven by ETF inflows.",
                "coins": ["BTC"],
                "ai": {"sentiment": "bullish", "impact": "high"},
            }
            clde = claude_analyze(test_article)
            elapsed = int((time.time() - start) * 1000)
            results["Claude"] = {
                "ok": clde is not None,
                "elapsed_ms": elapsed,
                "model": CLAUDE_MODEL,
            }
            if clde:
                results["Claude"]["sample_confidence"] = clde.get("confidence", "?")
        except Exception as e:
            results["Claude"] = {"ok": False, "error": str(e)[:80]}
    else:
        results["Claude"] = {"ok": False, "error": "CLAUDE_API_KEY missing", "skipped": True}

    # OpenAI (only test if key present)
    if OPENAI_API_KEY:
        start = time.time()
        try:
            test_article = {
                "title": "Bitcoin reaches new all-time high above $100,000",
                "summary": "BTC surged past $100K driven by ETF inflows.",
                "coins": ["BTC"],
                "ai": {"sentiment": "bullish", "impact": "high"},
            }
            oai = openai_analyze(test_article)
            elapsed = int((time.time() - start) * 1000)
            results["OpenAI"] = {
                "ok": oai is not None,
                "elapsed_ms": elapsed,
                "model": OPENAI_MODEL,
            }
            if oai:
                results["OpenAI"]["sample_conviction"] = oai.get("conviction", "?")
        except Exception as e:
            results["OpenAI"] = {"ok": False, "error": str(e)[:80]}
    else:
        results["OpenAI"] = {"ok": False, "error": "OPENAI_API_KEY missing", "skipped": True}

    # Storage
    storage_ok = storage_save("_health_check.json", {"ts": now_iso()})
    results["Storage"] = {"ok": storage_ok, "path": DATA_DIR}

    # Portfolio link
    portfolio_coins = get_portfolio_coins()
    results["Portfolio"] = {
        "ok": len(portfolio_coins) > 0,
        "coins_count": len(portfolio_coins),
        "coins": portfolio_coins[:10],
    }

    return results


# ══════════════════════════════════════════════════════════════════
# 10. BACKGROUND JOBS (Monitor + Daily Digest)
# ══════════════════════════════════════════════════════════════════

def _alert_in_cooldown(article_id: str) -> bool:
    cooldowns = storage_load("alert_cooldowns.json", {})
    last = cooldowns.get(article_id)
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last)
        return (datetime.now(TZ_RIYADH) - last_dt) < \
               timedelta(hours=ALERT_COOLDOWN_HOURS)
    except Exception:
        return False


def _mark_alert_sent(article_id: str):
    cooldowns = storage_load("alert_cooldowns.json", {})
    cooldowns[article_id] = now_iso()
    cutoff = datetime.now(TZ_RIYADH) - timedelta(days=2)
    cleaned = {k: v for k, v in cooldowns.items()
               if _try_parse_iso(v) > cutoff}
    storage_save("alert_cooldowns.json", cleaned)


def _try_parse_iso(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return datetime.now(TZ_RIYADH) - timedelta(days=99)


async def news_monitor_job(context: ContextTypes.DEFAULT_TYPE):
    """Background job: every 30 min, fetch + alert on important news."""
    job_data = context.job.data or {}
    chat_id = job_data.get("chat_id")
    if not chat_id:
        return

    log.info(f"[MONITOR] news scan for chat {chat_id}")

    try:
        loop = asyncio.get_event_loop()
        articles = await loop.run_in_executor(None, run_news_pipeline, True)

        # Filter: high impact OR portfolio-relevant medium+
        alerts_to_send = []
        for a in articles:
            if _alert_in_cooldown(a["id"]):
                continue
            ai = a.get("ai", {})
            impact = ai.get("impact", "low")
            is_portfolio = a.get("is_portfolio_relevant", False)

            if impact == "high":
                alerts_to_send.append(a)
            elif impact == "medium" and is_portfolio:
                alerts_to_send.append(a)

        # Limit to 3 per scan to avoid spam
        alerts_to_send = alerts_to_send[:3]

        for alert in alerts_to_send:
            try:
                # Decide format: Council for breaking+portfolio, detailed for others
                ai = alert.get("ai", {})
                impact = ai.get("impact", "low")
                is_portfolio = alert.get("is_portfolio_relevant", False)
                use_council = (impact == "high" and is_portfolio
                               and alert.get("claude") and alert.get("openai"))

                if use_council:
                    msg = format_council_alert(alert)
                else:
                    msg = format_article_detailed(alert)

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=msg,
                    parse_mode="Markdown",
                    disable_web_page_preview=False,
                )
                _mark_alert_sent(alert["id"])
                await asyncio.sleep(2)  # gap between alerts
            except Exception as e:
                log.warning(f"[MONITOR] send failed: {e}")

        log.info(f"[MONITOR] sent {len(alerts_to_send)} alerts")
    except Exception as e:
        log.exception(f"[MONITOR] error: {e}")


async def daily_digest_job(context: ContextTypes.DEFAULT_TYPE):
    """Background job: every 24h at 8am, send digest."""
    job_data = context.job.data or {}
    chat_id = job_data.get("chat_id")
    if not chat_id:
        return

    log.info(f"[DIGEST] generating daily digest for {chat_id}")
    try:
        loop = asyncio.get_event_loop()
        articles = await loop.run_in_executor(None, run_news_pipeline, True)
        msg = format_daily_digest(articles)
        await context.bot.send_message(
            chat_id=chat_id, text=msg, parse_mode="Markdown"
        )
    except Exception as e:
        log.exception(f"[DIGEST] error: {e}")


# ══════════════════════════════════════════════════════════════════
# 11. TELEGRAM HANDLERS
# ══════════════════════════════════════════════════════════════════

async def cmd_start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📰 *NEWS CRYPTO BOT v2.1*\n"
        "_Smart Crypto News + AI Council_\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "*🤝 Council of 3 AI Experts:*\n"
        "🟢 Gemini — العين السريعة\n"
        "🟣 Claude — المحلل الاستراتيجي\n"
        "🔵 GPT-4o — صوت السوق\n\n"
        "*المصادر (5):*\n"
        "📡 CoinDesk + The Block + CoinTelegraph\n"
        "📡 CoinGecko News + CryptoPanic\n\n"
        "*الميزات:*\n"
        "🤖 تحليل ذكي بـ 3 خبراء AI\n"
        "💼 ربط مع محفظتك من DCA BOT\n"
        "🔔 تنبيهات فورية للأخبار العاجلة\n"
        "📊 Sentiment overview لكل عملة\n"
        "📅 ملخص يومي تلقائي\n\n"
        "*الأوامر:*\n"
        "`/start`           القائمة\n"
        "`/test`            فحص شامل + Council\n"
        "`/news`            آخر الأخبار\n"
        "`/news BTC`        أخبار عملة معينة\n"
        "`/breaking`        الأخبار العاجلة\n"
        "`/council`         🤝 تحليل بـ 3 خبراء ⭐\n"
        "`/council BTC`     Council لخبر عن عملة\n"
        "`/sentiment`       sentiment لكل العملات\n"
        "`/digest`          ملخص يومي الآن\n"
        "`/sources`         حالة المصادر\n"
        "`/monitor`         تشغيل/إيقاف التنبيهات\n\n"
        "*أنواع التنبيهات:*\n"
        "🚨🚨 Council تنبيه (high + portfolio)\n"
        "🚨 خبر عاجل (high impact)\n"
        "💼 خبر يخص محفظتك\n"
        "📅 ملخص يومي (8 صباحاً)\n\n"
        "⚠️ _تحليل آلي — ليس نصيحة مالية_"
    )
    await u.message.reply_text(msg, parse_mode="Markdown")


async def cmd_gemdebug(u: Update, c: ContextTypes.DEFAULT_TYPE):
    """Deep Gemini diagnostic — tries all 5 models with detailed errors."""
    msg = await u.message.reply_text("⏳ تشخيص Gemini بكل النماذج...")

    if not GEMINI_API_KEY:
        await msg.delete()
        await u.message.reply_text(
            "❌ *GEMINI_API_KEY مفقود*\n\n"
            "أضفه في Railway → Variables.",
            parse_mode="Markdown"
        )
        return

    loop = asyncio.get_event_loop()

    def _run_full_diag():
        results = []
        test_prompt = """Analyze this and respond in JSON only.
TITLE: Bitcoin reaches new ATH above $100K
COINS: BTC

Respond with: {"sentiment": "bullish", "impact": "high"}"""

        # Test primary + common alternatives
        models_to_test = [GEMINI_MODEL, "gemini-2.5-pro", "gemini-2.0-flash-001",
                          "gemini-2.0-flash-lite-001"]
        for model in models_to_test:
            url = f"{GEMINI_BASE}/models/{model}:generateContent"
            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": GEMINI_API_KEY,
            }
            body = {
                "contents": [{"parts": [{"text": test_prompt}]}],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 200,
                },
            }
            start = time.time()
            try:
                r = _session.post(url, headers=headers, json=body,
                                  timeout=(10, 30))
                elapsed = int((time.time() - start) * 1000)
                if r.status_code == 200:
                    try:
                        data = r.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            text = candidates[0].get("content", {}).get(
                                "parts", [{}])[0].get("text", "")[:60]
                            results.append({
                                "model": model, "ok": True,
                                "ms": elapsed,
                                "preview": text.replace("\n", " "),
                            })
                        else:
                            results.append({
                                "model": model, "ok": False,
                                "ms": elapsed,
                                "err": "no candidates",
                            })
                    except Exception as e:
                        results.append({
                            "model": model, "ok": False,
                            "ms": elapsed,
                            "err": f"parse: {str(e)[:40]}",
                        })
                else:
                    err_body = (r.text or "")[:200]
                    # Try to extract Google's error message
                    try:
                        err_json = r.json()
                        err_msg = err_json.get("error", {}).get("message", "")
                        err_body = err_msg[:120] if err_msg else err_body
                    except Exception:
                        pass
                    results.append({
                        "model": model, "ok": False,
                        "ms": elapsed,
                        "status": r.status_code,
                        "err": err_body,
                    })
            except requests.exceptions.Timeout:
                results.append({
                    "model": model, "ok": False,
                    "ms": int((time.time() - start) * 1000),
                    "err": "timeout (>30s)",
                })
            except Exception as e:
                results.append({
                    "model": model, "ok": False,
                    "ms": int((time.time() - start) * 1000),
                    "err": f"{type(e).__name__}",
                })

        # Also test list-models endpoint to see what's actually available
        try:
            r = _session.get(
                f"{GEMINI_BASE}/models",
                headers={"x-goog-api-key": GEMINI_API_KEY},
                timeout=(5, 15),
            )
            available = []
            if r.status_code == 200:
                try:
                    data = r.json()
                    for m in data.get("models", []):
                        name = m.get("name", "").replace("models/", "")
                        methods = m.get("supportedGenerationMethods", [])
                        if "generateContent" in methods:
                            available.append(name)
                except Exception:
                    pass
            return results, available
        except Exception:
            return results, []

    results, available = await loop.run_in_executor(None, _run_full_diag)

    # Build report
    key_preview = (f"{GEMINI_API_KEY[:8]}...{GEMINI_API_KEY[-4:]}"
                   if len(GEMINI_API_KEY) > 12 else "(short)")

    lines = [
        "🔬 *Gemini Deep Diagnostic*",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🔑 Key length: `{len(GEMINI_API_KEY)}` chars",
        f"🔑 Preview: `{key_preview}`",
        "",
        "*اختبار النماذج:*",
    ]

    any_ok = False
    for r in results:
        model = r["model"]
        ms = r.get("ms", 0)
        if r["ok"]:
            any_ok = True
            preview = r.get("preview", "")[:50]
            lines.append(f"✅ `{model}` ({ms}ms)")
            if preview:
                lines.append(f"   _{preview}_")
        else:
            err = r.get("err", "?")[:80]
            status = r.get("status", "")
            status_str = f" [{status}]" if status else ""
            lines.append(f"❌ `{model}`{status_str}")
            lines.append(f"   _{err}_")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")

    # Smart diagnosis
    if any_ok:
        lines.append("🎯 *النتيجة:* بعض النماذج تعمل ✅")
        lines.append("   استخدم البوت بشكل طبيعي.")
    else:
        # Analyze failure pattern
        all_403 = all(r.get("status") == 403 for r in results if not r["ok"])
        all_400 = all(r.get("status") == 400 for r in results if not r["ok"])
        all_404 = all(r.get("status") == 404 for r in results if not r["ok"])
        any_quota = any("quota" in str(r.get("err", "")).lower() for r in results)
        any_invalid = any("invalid" in str(r.get("err", "")).lower() for r in results)

        if all_403 or any_invalid:
            lines.append("🩺 *التشخيص:* مشكلة authentication")
            lines.append("   • الـ API key غير صحيح أو محظور")
            lines.append("   • تحقّق من aistudio.google.com/apikey")
        elif any_quota:
            lines.append("🩺 *التشخيص:* تجاوز الحد المجاني")
            lines.append("   • انتظر 24 ساعة")
            lines.append("   • أو فعّل billing في Google Cloud")
        elif all_404:
            lines.append("🩺 *التشخيص:* النماذج غير متوفرة")
            lines.append("   • قد تكون قائمة النماذج تغيّرت")
        elif all_400:
            lines.append("🩺 *التشخيص:* request format غلط")
        else:
            lines.append("🩺 *التشخيص:* مشكلة شبكة أو timeout")

    # Show available models if we got them
    if available:
        lines.append("")
        lines.append(f"📋 *النماذج المتاحة لمفتاحك* ({len(available)}):")
        # Show first 8 only
        for m in available[:8]:
            lines.append(f"   • `{m}`")
        if len(available) > 8:
            lines.append(f"   _... و {len(available)-8} أخرى_")

    await msg.delete()
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_test(u: Update, c: ContextTypes.DEFAULT_TYPE):
    msg = await u.message.reply_text("⏳ فحص شامل (5 مصادر + Gemini)...")
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, run_connectivity_test)

    lines = ["🔍 *نتيجة الفحص:*\n", "*المصادر:*"]

    sources = ["CoinDesk", "The Block", "CoinTelegraph", "CoinGecko",
               "CryptoPanic"]
    for src in sources:
        r = results.get(src, {})
        if r.get("ok"):
            lines.append(f"✅ {src}: {r.get('count', 0)} خبر | "
                         f"{r.get('elapsed_ms', 0)}ms")
        else:
            err = r.get("error", "?")[:60]
            lines.append(f"❌ {src}: _{err}_")

    lines.append("")
    lines.append("*🤝 Council of AI Experts:*")

    # Gemini (always available)
    g = results.get("Gemini", {})
    if g.get("ok"):
        lines.append(f"🟢 Gemini: ✅ {g.get('elapsed_ms', 0)}ms · `{g.get('sample_sentiment', '?')}`")
    else:
        lines.append(f"🟢 Gemini: ❌ _{g.get('error','?')[:50]}_")

    # Claude
    cl = results.get("Claude", {})
    if cl.get("skipped"):
        lines.append(f"🟣 Claude: ⚪ _مفتاح غير موجود_")
    elif cl.get("ok"):
        lines.append(f"🟣 Claude: ✅ {cl.get('elapsed_ms', 0)}ms · `{cl.get('sample_confidence', '?')}`")
    else:
        lines.append(f"🟣 Claude: ❌ _{cl.get('error','?')[:50]}_")

    # OpenAI
    oa = results.get("OpenAI", {})
    if oa.get("skipped"):
        lines.append(f"🔵 OpenAI: ⚪ _مفتاح غير موجود_")
    elif oa.get("ok"):
        lines.append(f"🔵 OpenAI: ✅ {oa.get('elapsed_ms', 0)}ms · `{oa.get('sample_conviction', '?')}`")
    else:
        lines.append(f"🔵 OpenAI: ❌ _{oa.get('error','?')[:50]}_")

    lines.append("")
    lines.append("*التخزين:*")
    s = results.get("Storage", {})
    icon = "✅" if s.get("ok") else "❌"
    lines.append(f"{icon} Storage: `{s.get('path','?')}`")

    p = results.get("Portfolio", {})
    if p.get("ok"):
        coins_str = ", ".join(p.get("coins", [])[:8])
        lines.append(f"✅ Portfolio (DCA): {p.get('coins_count')} عملة")
        lines.append(f"   `{coins_str}`")
    else:
        lines.append(f"⚪ Portfolio: غير متصل (DCA data غير موجود)")

    # Summary
    ok_sources = sum(1 for s in sources if results.get(s, {}).get("ok"))
    ai_count = sum(1 for k in ["Gemini", "Claude", "OpenAI"]
                   if results.get(k, {}).get("ok"))
    lines.append("")
    if ok_sources >= 3 and ai_count == 3:
        lines.append(f"🎯 *الحالة:* ممتاز ({ok_sources}/5 + Council 3/3) ⭐")
    elif ok_sources >= 3 and ai_count >= 1:
        lines.append(f"✅ *الحالة:* جيد ({ok_sources}/5 + AI {ai_count}/3)")
    elif ok_sources >= 2:
        lines.append(f"⚠️ *الحالة:* محدود ({ok_sources}/5)")
    else:
        lines.append("🚨 *الحالة:* غير جاهز")

    await msg.delete()
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_news(u: Update, c: ContextTypes.DEFAULT_TYPE):
    args = c.args
    coin = args[0].upper() if args else None

    msg = await u.message.reply_text(
        f"⏳ جاري جلب الأخبار{' لـ ' + coin if coin else ''}..."
    )

    loop = asyncio.get_event_loop()
    articles = await loop.run_in_executor(None, run_news_pipeline, True)

    formatted = format_news_list(articles, filter_coin=coin, max_count=10)

    await msg.delete()
    await u.message.reply_text(formatted, parse_mode="Markdown",
                                disable_web_page_preview=True)


async def cmd_breaking(u: Update, c: ContextTypes.DEFAULT_TYPE):
    msg = await u.message.reply_text("⏳ جاري البحث عن الأخبار العاجلة...")

    snapshot = storage_load("news_latest.json", {})
    articles = snapshot.get("articles", [])

    # Check freshness — refresh if older than 30 min
    snap_age_min = 999
    if snapshot.get("timestamp"):
        try:
            snap_dt = datetime.fromisoformat(snapshot["timestamp"])
            snap_age_min = (datetime.now(TZ_RIYADH) - snap_dt).total_seconds() / 60
        except Exception:
            pass

    # Refetch if no articles, no AI, or older than 30 min
    has_ai = any(a.get("ai") for a in articles)
    if not articles or not has_ai or snap_age_min > 30:
        try:
            await msg.edit_text("⏳ جلب الأخبار الحديثة + تحليل AI...")
        except Exception:
            pass
        loop = asyncio.get_event_loop()
        articles = await loop.run_in_executor(None, run_news_pipeline, True)

    # Find high-impact news
    high = [a for a in articles
            if a.get("ai", {}).get("impact") == "high"]

    # Find portfolio-relevant news
    portfolio_news = [a for a in articles
                      if a.get("is_portfolio_relevant", False)
                      and a not in high]

    # Find medium-impact news (fallback if no high)
    medium = [a for a in articles
              if a.get("ai", {}).get("impact") == "medium"
              and a not in high and a not in portfolio_news]

    await msg.delete()

    # Decision tree
    if high:
        lines = [f"🚨 *أخبار عاجلة* ({len(high)})",
                 f"🕐 {now_str()} · _آخر تحديث: منذ {int(snap_age_min)}د_",
                 "━━━━━━━━━━━━━━━━━━━━",
                 ""]
        for a in high[:5]:
            lines.append(format_article_brief(a))
            lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("💡 لتحليل عميق بـ 3 خبراء AI:")
        lines.append("`/council` — للخبر العاجل الأهم")

    elif portfolio_news:
        lines = [f"💼 *لا أخبار عاجلة، لكن {len(portfolio_news)} يخص محفظتك*",
                 f"🕐 {now_str()}",
                 "━━━━━━━━━━━━━━━━━━━━",
                 ""]
        for a in portfolio_news[:5]:
            lines.append(format_article_brief(a))
            lines.append("")

    elif medium:
        lines = [f"📰 *لا أخبار عاجلة، لكن {len(medium)} متوسط الأهمية*",
                 f"🕐 {now_str()}",
                 "━━━━━━━━━━━━━━━━━━━━",
                 ""]
        for a in medium[:5]:
            lines.append(format_article_brief(a))
            lines.append("")

    else:
        # Truly nothing relevant
        total = len(articles)
        await u.message.reply_text(
            f"⚪ *السوق هادئ الآن*\n\n"
            f"تم فحص `{total}` خبر — لا يوجد ما يستحق التنبيه.\n"
            f"🕐 آخر تحديث: منذ {int(snap_age_min)} دقيقة\n\n"
            "*ماذا يعني هذا؟*\n"
            "• 🟢 السوق مستقر\n"
            "• 📊 لا تطورات كبيرة\n"
            "• ✅ لا داعي للقلق\n\n"
            "💡 جرّب `/news` لرؤية كل الأخبار",
            parse_mode="Markdown"
        )
        return

    await u.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


async def cmd_council(u: Update, c: ContextTypes.DEFAULT_TYPE):
    """🤝 Council analysis — full 3 AI experts on top breaking news."""
    args = c.args
    filter_coin = args[0].upper() if args else None

    msg = await u.message.reply_text(
        "🤝 *Council جاري التحليل...*\n"
        "🟢 Gemini → 🟣 Claude → 🔵 GPT-4o\n"
        "_قد يستغرق 15-30 ثانية_",
        parse_mode="Markdown"
    )

    loop = asyncio.get_event_loop()

    # Try cached snapshot first (much faster!)
    snapshot = storage_load("news_latest.json", {})
    articles = snapshot.get("articles", [])

    # Check if snapshot is fresh (less than 1 hour old) and has AI analysis
    snap_age_minutes = 999
    if snapshot.get("timestamp"):
        try:
            snap_dt = datetime.fromisoformat(snapshot["timestamp"])
            snap_age_minutes = (datetime.now(TZ_RIYADH) - snap_dt).total_seconds() / 60
        except Exception:
            pass

    has_ai = any(a.get("ai") for a in articles)

    # Refetch if no articles, no AI, or older than 60 min
    if not articles or not has_ai or snap_age_minutes > 60:
        log.info(f"[COUNCIL] refreshing (age={snap_age_minutes:.0f}min, has_ai={has_ai})")
        articles = await loop.run_in_executor(None, run_news_pipeline, True)
    else:
        log.info(f"[COUNCIL] using cached articles (age={snap_age_minutes:.0f}min)")

    # Filter by coin if specified
    if filter_coin:
        articles = [a for a in articles if filter_coin in a.get("coins", [])]

    # Find highest-priority article (must have AI analysis already)
    candidates = [
        a for a in articles
        if a.get("ai", {}).get("impact") == "high"
    ]
    if not candidates:
        candidates = [
            a for a in articles
            if a.get("is_portfolio_relevant", False) and a.get("ai")
        ]
    if not candidates:
        candidates = [
            a for a in articles
            if a.get("ai", {}).get("impact") == "medium"
        ]

    if not candidates:
        await msg.delete()
        suffix = f" لـ {filter_coin}" if filter_coin else ""
        await u.message.reply_text(
            f"⚪ *لا توجد أخبار مهمة الآن{suffix}*\n\n"
            "Council يستخدم لأخبار high-impact أو portfolio-relevant.\n"
            "السوق هادئ حالياً.",
            parse_mode="Markdown"
        )
        return

    target = candidates[0]

    # Update progress message — fetch market data first
    try:
        await msg.edit_text(
            f"🤝 *Council يحلل:*\n"
            f"_{target.get('title', '')[:80]}_\n\n"
            "📊 جلب أسعار Binance...",
            parse_mode="Markdown"
        )
    except Exception:
        pass

    # Step 1: Fetch real-time market context from Binance
    target_coins = target.get("coins", [])
    def _fetch_market():
        return get_market_context_multi(target_coins, max_coins=3)

    market_contexts = await loop.run_in_executor(None, _fetch_market)
    log.info(f"[COUNCIL] fetched market data for {len(market_contexts)} coins")

    # Step 2: Run Claude with market context
    try:
        await msg.edit_text(
            f"🤝 *Council يحلل:*\n"
            f"_{target.get('title', '')[:80]}_\n\n"
            "🟣 Claude يفكر مع بيانات السوق...",
            parse_mode="Markdown"
        )
    except Exception:
        pass

    def _run_claude():
        return claude_analyze(target, market_contexts=market_contexts)

    clde = await loop.run_in_executor(None, _run_claude)
    if clde:
        target["claude"] = clde

    # Step 3: Run OpenAI with market context
    try:
        await msg.edit_text(
            f"🤝 *Council يحلل:*\n"
            f"_{target.get('title', '')[:80]}_\n\n"
            "🔵 GPT-4o يكتب التوصية مع الأسعار الحقيقية...",
            parse_mode="Markdown"
        )
    except Exception:
        pass

    def _run_openai():
        return openai_analyze(target, market_contexts=market_contexts)

    oai = await loop.run_in_executor(None, _run_openai)
    if oai:
        target["openai"] = oai

    # Save updated article
    snap = storage_load("news_latest.json", {})
    snap_articles = snap.get("articles", [])
    for i, a in enumerate(snap_articles):
        if a.get("id") == target.get("id"):
            snap_articles[i] = target
            break
    snap["articles"] = snap_articles
    storage_save("news_latest.json", snap)

    formatted = format_council_alert(target)

    await msg.delete()
    await u.message.reply_text(
        formatted,
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


async def cmd_sentiment(u: Update, c: ContextTypes.DEFAULT_TYPE):
    args = c.args
    coin = args[0].upper() if args else None

    # Check if snapshot has AI-analyzed articles, refresh if not
    snapshot = storage_load("news_latest.json", {})
    articles = snapshot.get("articles", [])
    has_ai = any(a.get("ai") for a in articles)

    if not articles or not has_ai:
        msg = await u.message.reply_text(
            "⏳ جاري التحليل بـ AI..."
        )
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, run_news_pipeline, True)
        await msg.delete()

    formatted = format_sentiment(coin)
    await u.message.reply_text(formatted, parse_mode="Markdown")


async def cmd_digest(u: Update, c: ContextTypes.DEFAULT_TYPE):
    msg = await u.message.reply_text("⏳ جاري إعداد الملخص اليومي...")

    loop = asyncio.get_event_loop()
    articles = await loop.run_in_executor(None, run_news_pipeline, True)

    formatted = format_daily_digest(articles)

    await msg.delete()
    await u.message.reply_text(formatted, parse_mode="Markdown")


async def cmd_sources(u: Update, c: ContextTypes.DEFAULT_TYPE):
    snapshot = storage_load("news_latest.json", {})
    articles = snapshot.get("articles", [])

    by_source: Dict[str, int] = {}
    for a in articles:
        src = a.get("source", "?")
        by_source[src] = by_source.get(src, 0) + 1

    lines = ["📡 *حالة المصادر*",
             f"🕐 {now_str()}",
             "━━━━━━━━━━━━━━━━━━━━",
             ""]

    all_sources = ["CoinDesk", "The Block", "CoinTelegraph",
                   "CoinGecko", "CryptoPanic"]
    for src in all_sources:
        count = by_source.get(src, 0)
        icon = "✅" if count > 0 else "⚪"
        lines.append(f"{icon} {src}: {count} خبر")

    lines.append("")
    lines.append(f"📊 إجمالي: {len(articles)} خبر")
    last_update = snapshot.get("timestamp", "")
    if last_update:
        try:
            dt = datetime.fromisoformat(last_update)
            age = (datetime.now(TZ_RIYADH) - dt).seconds // 60
            lines.append(f"🕐 آخر تحديث: منذ {age} دقيقة")
        except Exception:
            pass

    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_monitor(u: Update, c: ContextTypes.DEFAULT_TYPE):
    chat_id = u.effective_chat.id
    args_text = " ".join(c.args).lower() if c.args else ""

    if "off" in args_text or "stop" in args_text or "وقف" in args_text:
        action = "stop"
    elif "on" in args_text or "start" in args_text or "تشغيل" in args_text:
        action = "start"
    else:
        existing = c.job_queue.get_jobs_by_name(f"news_monitor_{chat_id}")
        action = "stop" if existing else "start"

    if action == "stop":
        for j in c.job_queue.get_jobs_by_name(f"news_monitor_{chat_id}"):
            j.schedule_removal()
        for j in c.job_queue.get_jobs_by_name(f"news_digest_{chat_id}"):
            j.schedule_removal()

        cfg = storage_load("user_settings.json", {})
        cfg[str(chat_id)] = {"monitor_active": False}
        storage_save("user_settings.json", cfg)

        await u.message.reply_text(
            "⛔ *تم إيقاف المراقبة*\n\n"
            "لن تستلم أي تنبيهات تلقائية.",
            parse_mode="Markdown"
        )
        return

    # Start monitoring
    for j in c.job_queue.get_jobs_by_name(f"news_monitor_{chat_id}"):
        j.schedule_removal()
    for j in c.job_queue.get_jobs_by_name(f"news_digest_{chat_id}"):
        j.schedule_removal()

    c.job_queue.run_repeating(
        news_monitor_job,
        interval=1800,   # every 30 min
        first=60,        # first run after 1 min
        data={"chat_id": chat_id},
        name=f"news_monitor_{chat_id}",
    )

    c.job_queue.run_repeating(
        daily_digest_job,
        interval=86400,   # every 24 hours
        first=3600,       # first run after 1 hour
        data={"chat_id": chat_id},
        name=f"news_digest_{chat_id}",
    )

    cfg = storage_load("user_settings.json", {})
    cfg[str(chat_id)] = {"monitor_active": True}
    storage_save("user_settings.json", cfg)

    await u.message.reply_text(
        "🔔 *تم تفعيل المراقبة الذكية*\n\n"
        "*التنبيهات التلقائية:*\n"
        "   ⏱ كل 30 دقيقة — فحص الأخبار + AI\n"
        "   📊 كل 24 ساعة — ملخص يومي\n\n"
        "*أنواع التنبيهات:*\n"
        "   🚨 خبر عالي التأثير (high impact)\n"
        "   💼 خبر يخص عملة في محفظتك\n\n"
        f"❄️ Cooldown: {ALERT_COOLDOWN_HOURS} ساعات لكل خبر\n"
        "📵 حد أقصى: 3 تنبيهات لكل scan\n\n"
        "للإيقاف: `/monitor off`",
        parse_mode="Markdown"
    )


async def handle_msg(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not u.message or not u.message.text:
        return
    text = u.message.text.strip().lower()

    if text in ("اخبار", "أخبار", "news"):
        await cmd_news(u, c)
        return
    if text in ("عاجل", "breaking"):
        await cmd_breaking(u, c)
        return
    if text in ("ملخص", "digest", "summary"):
        await cmd_digest(u, c)
        return

    await u.message.reply_text(
        "🤖 لم أفهم الأمر.\n\nأرسل `/start` لرؤية الأوامر.",
        parse_mode="Markdown"
    )


async def error_handler(update, context):
    log.warning(f"[ERR] {context.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ خطأ مؤقت. حاول مرة أخرى."
            )
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════
# 12. MAIN
# ══════════════════════════════════════════════════════════════════

async def _post_init(app):
    try:
        await app.bot.delete_webhook(drop_pending_updates=True)
        log.info("✅ Webhook cleared")
    except Exception as e:
        log.warning(f"webhook clear failed: {e}")


def _print_banner():
    gem_status = "✅" if GEMINI_API_KEY else "⚪"
    cl_status = "✅" if CLAUDE_API_KEY else "⚪"
    oa_status = "✅" if OPENAI_API_KEY else "⚪"
    cp_status = "✅" if CRYPTOPANIC_KEY else "⚪ public mode"

    print("=" * 70)
    print("  📰 NEWS_CRYPTO_BOT v2.1 — Smart News + AI Council ✅")
    print("=" * 70)
    print(f"  🤝 Council of AI Experts:")
    print(f"    🟢 Gemini      : {gem_status}  ({GEMINI_MODEL})")
    print(f"    🟣 Claude      : {cl_status}  ({CLAUDE_MODEL})")
    print(f"    🔵 OpenAI      : {oa_status}  ({OPENAI_MODEL})")
    print(f"  المصادر         :")
    print(f"    📡 CoinDesk    : RSS")
    print(f"    📡 The Block   : RSS")
    print(f"    📡 CoinTelegraph: RSS")
    print(f"    📡 CoinGecko   : API")
    print(f"    📡 CryptoPanic : {cp_status}")
    print(f"  Storage          : {DATA_DIR}")
    print(f"  Portfolio link   : {DCA_DATA_DIR}/portfolio_latest.json")
    print(f"  Coin DB          : {len(KNOWN_COINS)} coins tracked")
    print("=" * 70)
    print("  أرسل /start في تيليقرام لبدء الاستخدام")
    print("=" * 70)


def main():
    if not BOT_TOKEN:
        print("=" * 70)
        print("  ❌ ERROR: BOT_TOKEN غير موجود في environment")
        print("  أضفه في Railway → Variables → BOT_TOKEN")
        print("=" * 70)
        return

    if not GEMINI_API_KEY:
        log.warning("⚠️ GEMINI_API_KEY not set — AI analysis disabled")

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(_post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("test", cmd_test))
    app.add_handler(CommandHandler("gemdebug", cmd_gemdebug))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("breaking", cmd_breaking))
    app.add_handler(CommandHandler("council", cmd_council))
    app.add_handler(CommandHandler("sentiment", cmd_sentiment))
    app.add_handler(CommandHandler("digest", cmd_digest))
    app.add_handler(CommandHandler("sources", cmd_sources))
    app.add_handler(CommandHandler("monitor", cmd_monitor))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_msg
    ))
    app.add_error_handler(error_handler)

    _print_banner()

    app.run_polling(drop_pending_updates=True,
                    allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
