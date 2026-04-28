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
CRYPTOPANIC_KEY    = os.environ.get("CRYPTOPANIC_KEY", "").strip()
COINGECKO_KEY      = os.environ.get("COINGECKO_KEY", "").strip()

# ── Storage Path ──
DATA_DIR = os.environ.get("DATA_DIR", "/data").rstrip("/")
if not os.path.exists(DATA_DIR) and not os.access("/", os.W_OK):
    DATA_DIR = "./data"

DCA_DATA_DIR = os.environ.get("DCA_DATA_DIR", "/data").rstrip("/")

# ── API Endpoints ──
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_MODEL = "gemini-2.5-flash"

RSS_FEEDS = {
    "CoinDesk":      "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "The Block":     "https://www.theblock.co/rss.xml",
    "CoinTelegraph": "https://cointelegraph.com/rss",
}

COINGECKO_NEWS_URL  = "https://api.coingecko.com/api/v3/news"
CRYPTOPANIC_URL     = "https://cryptopanic.com/api/v1/posts/"

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
    """Fetch news from CoinGecko News API."""
    headers = {}
    if COINGECKO_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_KEY

    data = safe_request("GET", COINGECKO_NEWS_URL, headers=headers,
                        timeout=(5, 15))
    if not data or not isinstance(data, dict):
        return []

    articles = []
    items = data.get("data", [])
    for item in items[:MAX_ARTICLES_PER_FETCH]:
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

    log.info(f"[CG_NEWS] {len(articles)} articles")
    return articles


def fetch_cryptopanic() -> List[Dict]:
    """Fetch news from CryptoPanic API."""
    params = {"public": "true", "filter": "hot"}
    if CRYPTOPANIC_KEY:
        params["auth_token"] = CRYPTOPANIC_KEY

    data = safe_request("GET", CRYPTOPANIC_URL, params=params,
                        timeout=(5, 15))
    if not data or not isinstance(data, dict):
        return []

    articles = []
    for item in data.get("results", [])[:MAX_ARTICLES_PER_FETCH]:
        try:
            title = item.get("title", "").strip()
            link = item.get("url", "")
            ts_str = item.get("published_at", "")
            pub_ts = _parse_rss_date(ts_str) if ts_str else int(time.time())

            # CryptoPanic provides currency tags directly
            currencies = item.get("currencies", [])
            tagged_coins = [c.get("code", "").upper() for c in currencies if c.get("code")]

            # Pre-classified sentiment (if available)
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
                "summary": "",  # CryptoPanic doesn't include summaries in free tier
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
    Send article to Gemini for analysis.
    Returns: {sentiment, impact, reasoning_ar, summary_ar, action_hint}
    """
    if not GEMINI_API_KEY:
        return None

    title = article.get("title", "")
    summary = article.get("summary", "")
    coins = article.get("coins", [])

    prompt = f"""You are a crypto market analyst. Analyze this news and respond in JSON only.

TITLE: {title}
SUMMARY: {summary[:300]}
COINS_MENTIONED: {', '.join(coins) if coins else 'general market'}

Respond with EXACTLY this JSON structure (no markdown, no extra text):
{{
  "sentiment": "bullish" | "bearish" | "neutral",
  "impact": "high" | "medium" | "low",
  "reasoning_ar": "3 short Arabic sentences explaining why",
  "summary_ar": "1-2 sentence Arabic summary of the news",
  "action_hint": "1 short Arabic suggestion (e.g. 'راقب BTC' or 'لا حاجة للقلق')"
}}

Rules:
- IMPACT high = could move price 5%+ within 24h (regulations, ETFs, hacks, major adoption)
- IMPACT medium = notable but limited price impact (partnerships, tech updates)
- IMPACT low = minor news (small projects, opinions, predictions)
- SENTIMENT relative to crypto market: bullish=positive, bearish=negative
- All Arabic text should be clear and concise
- DO NOT include markdown code fences or any text outside the JSON"""

    url = f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }
    body = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 500,
            "responseMimeType": "application/json",
        }
    }

    response = safe_request("POST", url, headers=headers, json_body=body,
                            timeout=(10, GEMINI_TIMEOUT), retries=1)
    if not response:
        return None
    if isinstance(response, dict) and "_auth_error" in response:
        log.warning(f"[GEMINI] auth error {response['_auth_error']}")
        return None
    if not isinstance(response, dict):
        return None

    try:
        candidates = response.get("candidates", [])
        if not candidates:
            return None
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return None
        text = parts[0].get("text", "").strip()

        # Strip code fences if present
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        result = json.loads(text)

        # Validate required fields
        if "sentiment" not in result or "impact" not in result:
            return None

        return {
            "sentiment":     result.get("sentiment", "neutral").lower(),
            "impact":        result.get("impact", "low").lower(),
            "reasoning_ar":  result.get("reasoning_ar", ""),
            "summary_ar":    result.get("summary_ar", ""),
            "action_hint":   result.get("action_hint", ""),
        }
    except json.JSONDecodeError as e:
        log.warning(f"[GEMINI] JSON parse failed: {e}")
        return None
    except Exception as e:
        log.warning(f"[GEMINI] error: {e}")
        return None


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
                    max_to_analyze: int = 8) -> List[Dict]:
    """Run AI analysis on top N relevant articles."""
    candidates = [a for a in articles if should_analyze(a)]
    candidates = candidates[:max_to_analyze]

    log.info(f"[AI] analyzing {len(candidates)} articles...")

    for a in candidates:
        try:
            ai = gemini_analyze(a)
            if ai:
                a["ai"] = ai
            time.sleep(0.3)  # gentle rate limit
        except Exception as e:
            log.warning(f"[AI] {a.get('title','?')[:40]}: {e}")

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
        "📰 *NEWS CRYPTO BOT v1.0*\n"
        "_Smart Crypto News + AI Analysis_\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "*المصادر (5):*\n"
        "📡 CoinDesk + The Block + CoinTelegraph\n"
        "📡 CoinGecko News + CryptoPanic\n\n"
        "*الميزات:*\n"
        "🤖 تحليل AI بـ Gemini (sentiment + impact)\n"
        "💼 ربط مع محفظتك من DCA BOT\n"
        "🔔 تنبيهات تلقائية للأخبار المهمة\n"
        "📊 Sentiment overview لكل عملة\n"
        "📅 ملخص يومي تلقائي\n\n"
        "*الأوامر:*\n"
        "`/start`           القائمة\n"
        "`/test`            فحص المصادر + Gemini\n"
        "`/news`            آخر الأخبار المهمة\n"
        "`/news BTC`        أخبار عملة معينة\n"
        "`/breaking`        أخبار عاجلة (high impact)\n"
        "`/sentiment`       sentiment لكل العملات\n"
        "`/sentiment BTC`   sentiment عملة معينة\n"
        "`/digest`          ملخص يومي الآن\n"
        "`/sources`         حالة المصادر\n"
        "`/monitor`         تشغيل/إيقاف التنبيهات التلقائية\n\n"
        "*أنواع التنبيهات:*\n"
        "🚨 خبر عاجل (high impact)\n"
        "💼 خبر يخص محفظتك\n"
        "📅 ملخص يومي (8 صباحاً)\n\n"
        "⚠️ _تحليل آلي — ليس نصيحة مالية_"
    )
    await u.message.reply_text(msg, parse_mode="Markdown")


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
    lines.append("*الذكاء الاصطناعي:*")
    g = results.get("Gemini", {})
    if g.get("ok"):
        lines.append(f"✅ Gemini ({g.get('model','?')}): "
                     f"{g.get('elapsed_ms', 0)}ms")
        if "sample_sentiment" in g:
            lines.append(f"   نموذج التحليل: `{g['sample_sentiment']}`")
    else:
        lines.append(f"❌ Gemini: _{g.get('error','?')[:60]}_")

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
    ai_ok = results.get("Gemini", {}).get("ok", False)
    lines.append("")
    if ok_sources == 5 and ai_ok:
        lines.append("🎯 *الحالة:* ممتاز (5/5 + AI)")
    elif ok_sources >= 3 and ai_ok:
        lines.append(f"✅ *الحالة:* جيد ({ok_sources}/5 + AI)")
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

    if not articles:
        loop = asyncio.get_event_loop()
        articles = await loop.run_in_executor(None, run_news_pipeline, True)

    breaking = [a for a in articles
                if a.get("ai", {}).get("impact") == "high"]

    await msg.delete()

    if not breaking:
        await u.message.reply_text(
            "⚪ *لا توجد أخبار عاجلة الآن*\n\n"
            "البوت لم يكتشف أي خبر عالي التأثير في آخر 4 ساعات.\n"
            "هذا عادة *خبر جيد* — السوق هادئ.",
            parse_mode="Markdown"
        )
        return

    lines = [f"🚨 *أخبار عاجلة* ({len(breaking)})",
             f"🕐 {now_str()}",
             "━━━━━━━━━━━━━━━━━━━━",
             ""]
    for a in breaking[:5]:
        lines.append(format_article_brief(a))
        lines.append("")

    await u.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


async def cmd_sentiment(u: Update, c: ContextTypes.DEFAULT_TYPE):
    args = c.args
    coin = args[0].upper() if args else None

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
    gem_status = "✅ مفعّل" if GEMINI_API_KEY else "⚪ معطّل (سيعمل بدون AI)"
    cp_status = "✅" if CRYPTOPANIC_KEY else "⚪ public mode"

    print("=" * 70)
    print("  📰 NEWS_CRYPTO_BOT v1.0 — Smart News + AI Analysis ✅")
    print("=" * 70)
    print(f"  AI Engine        :")
    print(f"    🤖 Gemini      : {gem_status}")
    print(f"    Model          : {GEMINI_MODEL}")
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
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("breaking", cmd_breaking))
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
