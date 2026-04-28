# 📰 NEWS_CRYPTO_BOT v1.0

**Smart Crypto News + AI Analysis Bot**

## 🎯 الميزات

| # | الميزة | الوصف |
|---|---|---|
| 1 | 📡 5 مصادر | CoinDesk + The Block + CoinTelegraph + CoinGecko + CryptoPanic |
| 2 | 🤖 Gemini AI | تحليل sentiment + impact + reasoning |
| 3 | 💼 Portfolio Link | يقرأ DCA_BOT portfolio لربط الأخبار بعملاتك |
| 4 | 🔔 تنبيهات تلقائية | كل 30 دقيقة + ملخص يومي |
| 5 | 📊 Sentiment Overview | تتبع لكل عملة (% bullish) |

## 🔑 Environment Variables

```
BOT_TOKEN              (إلزامي - من BotFather)
GEMINI_API_KEY         (إلزامي - من Google AI Studio)
CRYPTOPANIC_KEY        (اختياري - حدود أعلى)
COINGECKO_KEY          (اختياري - demo key)
DATA_DIR=/data         (auto-set)
DCA_DATA_DIR=/data     (لربط DCA_BOT portfolio)
```

## 🌐 Railway Setup

1. Region: `europe-west4`
2. Volume: mount at `/data`
3. Variables: BOT_TOKEN + GEMINI_API_KEY (إلزاميين)

### للربط مع DCA_BOT:
شارك نفس الـ Volume بين البوتين، أو ضع DCA_DATA_DIR لمسار portfolio_latest.json

## 📝 الأوامر

| الأمر | الوظيفة |
|---|---|
| `/start` | القائمة |
| `/test` | فحص المصادر + Gemini + Storage |
| `/news` | آخر 10 أخبار |
| `/news BTC` | أخبار عملة معينة |
| `/breaking` | الأخبار العاجلة (high impact) |
| `/sentiment` | sentiment لكل العملات |
| `/sentiment BTC` | sentiment عملة معينة |
| `/digest` | ملخص يومي الآن |
| `/sources` | حالة المصادر |
| `/monitor` | تشغيل/إيقاف التنبيهات التلقائية |
| `/monitor off` | إيقاف فقط |

## 🤖 AI Logic

```
كل خبر يمر بـ:
1. Coin Detection (regex match)
2. Portfolio Match (DCA_BOT data)
3. Gemini Analysis (sentiment + impact + reasoning)
4. Decision:
   - high impact → 🚨 breaking alert
   - medium + portfolio match → 💼 personal alert
   - low → خفي عن التنبيهات
```

## 🔔 أنواع التنبيهات

- 🚨 **Breaking**: high impact (5%+ price move expected)
- 💼 **Portfolio**: medium impact + يخص عملة في محفظتك
- 📅 **Daily Digest**: 8 صباحاً يومياً

**Cooldown**: 4 ساعات لكل خبر | حد أقصى 3 تنبيهات لكل scan

## ⚠️ Disclaimer

- 🔐 Read-Only — لا تنفذ أوامر تداول
- ⚠️ تحليل AI — تحقق دائماً قبل التنفيذ
- 📚 تعليمي فقط — ليس نصيحة مالية
