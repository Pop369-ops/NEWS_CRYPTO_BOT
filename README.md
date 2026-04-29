# 📰 NEWS_CRYPTO_BOT v2.2 — News + Council + Massive Market Data

**Smart Crypto News with 3 AI Experts + Institutional Market Data**

## 🤝 Council of AI Experts

| AI | الشخصية | التخصص |
|---|---|---|
| 🟢 **Gemini 2.5 Flash** | العين السريعة | Sentiment + Impact للجميع |
| 🟣 **Claude Opus 4.5** | المحلل الاستراتيجي | Risk + سياق تاريخي |
| 🔵 **GPT-4o** | صوت السوق | توصيات تنفيذية + Levels |

## 💎 Market Data Layer (جديد في v2.2)

**Massive.com** (rebranded من Polygon.io في أكتوبر 2025) كمصدر بيانات احترافي:

- ✅ **أسعار cross-exchange aggregated** (أدق من أي بورصة وحدها)
- ✅ **Top movers** عبر السوق كله (gainers/losers)
- ✅ **OHLCV aggregates** على أي timeframe (1m/5m/1h/1d...)
- ✅ **Crypto Trades** الفورية (whale detection)
- ✅ **Unlimited API calls** على خطة Currencies Starter ($49/mo)
- ✅ **Auto fallback** إلى Binance لو Massive failed أو لو المفتاح غير موجود

## 🎯 Smart Routing

```
كل خبر يمر بـ Tier ذكي:

⚡ Fast (Gemini فقط) → كل الأخبار
📊 Deep (+Claude) → high impact OR portfolio match
🤝 Council (+OpenAI) → high impact + portfolio match
```

## 🔑 Environment Variables

### إلزامية
```
BOT_TOKEN              من BotFather
GEMINI_API_KEY         من Google AI Studio
```

### للـ Council (موصى به)
```
CLAUDE_API_KEY         من console.anthropic.com
OPENAI_API_KEY         من platform.openai.com
```

### لبيانات السوق (موصى به ⭐)
```
POLYGON_API_KEY        من massive.com/dashboard/keys
                       (الاسم القديم محتفظ به للتوافق)
                       اشتراك: Currencies Starter $49/mo
```

### اختيارية
```
CRYPTOPANIC_KEY        ⚪ ليس ضرورياً
COINGECKO_KEY          ⚪ ليس ضرورياً
DCA_DATA_DIR=/data     لربط محفظة DCA_BOT
```

## 📝 الأوامر

### أوامر الأخبار

| الأمر | الوظيفة |
|---|---|
| `/start` | القائمة |
| `/test` | فحص شامل + Council + Massive |
| `/news` | آخر 10 أخبار |
| `/news BTC` | أخبار عملة معينة |
| `/breaking` | الأخبار العاجلة |
| `/council` | 🤝 تحليل بـ 3 خبراء ⭐ |
| `/council BTC` | Council لخبر عن عملة |
| `/sentiment` | sentiment لكل العملات |
| `/digest` | ملخص يومي |
| `/sources` | حالة المصادر |
| `/monitor` | تشغيل/إيقاف التنبيهات |
| `/gemdebug` | تشخيص Gemini |

### 💎 أوامر السوق (Massive — جديدة في v2.2)

| الأمر | الوظيفة |
|---|---|
| `/price BTC` | سعر فوري لعملة |
| `/price BTC ETH SOL` | أسعار متعددة دفعة واحدة |
| `/movers` | 🔥 أكبر 10 صاعدين + 10 هابطين |
| `/scan BTC` | 🎯 مسح كامل: سعر + شموع + حيتان + أخبار |

**أوامر عربية مكافئة:**
- `سعر BTC` ↔ `/price BTC`
- `مسح BTC` ↔ `/scan BTC`
- `متحركين` / `صاعدين` / `هابطين` ↔ `/movers`

## 🔔 أنواع التنبيهات

- 🚨🚨 **Council Alert**: high impact + portfolio (3 خبراء)
- 🚨 **Breaking**: high impact (Gemini)
- 💼 **Portfolio**: medium impact + يخص محفظتك
- 📅 **Daily Digest**: 8 صباحاً يومياً

## 💰 التكلفة المتوقعة

```
Gemini (1M tokens/يوم مجاني):     $0
Claude (~10 خبر مهم/يوم):         ~$2/شهر
OpenAI (~3 خبر عاجل/يوم):          ~$1/شهر
Massive Currencies Starter:        $49/شهر
─────────────────────────────────────────
الإجمالي:                          ~$52/شهر
```

> 💡 **توفير:** نفس مفتاح Massive يخدم بوت Forex/Gold و بوت HYPE — مفيش رسوم إضافية.

## 🔄 Migration من v2.1 إلى v2.2

**صفر breaking changes.** البوت القديم يستمر في العمل بالضبط:
- لو `POLYGON_API_KEY` غير موجود → يستخدم Binance زي قبل
- لو موجود → يستخدم Massive كأساس + Binance كـ fallback

**خطوات التفعيل:**
1. اشترك في `https://massive.com/dashboard/subscriptions` (Currencies Starter)
2. انسخ المفتاح من `https://massive.com/dashboard/keys`
3. أضف في Railway → Variables: `POLYGON_API_KEY = your_key`
4. Redeploy → الأوامر الجديدة تشتغل تلقائياً

## ⚠️ Disclaimer

- 🔐 Read-Only — لا تنفذ أوامر تداول
- ⚠️ تحليل AI — تحقق دائماً قبل التنفيذ
- 📚 تعليمي فقط — ليس نصيحة مالية
