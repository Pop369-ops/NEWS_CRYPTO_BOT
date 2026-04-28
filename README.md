# 📰 NEWS_CRYPTO_BOT v2.1 — Council of AI Experts

**Smart Crypto News with 3 AI Experts Analysis**

## 🤝 Council of AI Experts

| AI | الشخصية | التخصص |
|---|---|---|
| 🟢 **Gemini 2.5 Flash** | العين السريعة | Sentiment + Impact للجميع |
| 🟣 **Claude Opus 4.5** | المحلل الاستراتيجي | Risk + سياق تاريخي |
| 🔵 **GPT-4o** | صوت السوق | توصيات تنفيذية + Levels |

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

### اختيارية
```
CRYPTOPANIC_KEY        ⚪ ليس ضرورياً
COINGECKO_KEY          ⚪ ليس ضرورياً
DCA_DATA_DIR=/data     لربط محفظة DCA_BOT
```

## 📝 الأوامر

| الأمر | الوظيفة |
|---|---|
| `/start` | القائمة |
| `/test` | فحص شامل + Council |
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
─────────────────────────────────────
الإجمالي:                          ~$3/شهر
```

## ⚠️ Disclaimer

- 🔐 Read-Only — لا تنفذ أوامر تداول
- ⚠️ تحليل AI — تحقق دائماً قبل التنفيذ
- 📚 تعليمي فقط — ليس نصيحة مالية
