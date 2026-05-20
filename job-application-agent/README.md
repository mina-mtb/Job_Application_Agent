# Mina Job Application Agent

یک سیستم هوشمند جمع‌آوری، امتیازدهی و تولید CV برای جستجوی شغل.

---

## ساختار پروژه

```
job-application-agent/
│
├── agents/
│   ├── apify_collector.py   ← جمع‌آوری job از LinkedIn/Indeed
│   ├── job_collector.py     ← collector (mock + apify-mock)
│   ├── job_cleaner.py       ← حذف duplicate و نرمال‌سازی
│   ├── job_matcher.py       ← امتیازدهی 0-100
│   ├── cv_tailor.py         ← تولید CV اختصاصی با Claude API
│   └── tracker_updater.py   ← آپدیت tracker.csv
│
├── integrations/
│   ├── obsidian_sync.py     ← sync با Obsidian Vault
│   └── google_drive.py      ← آپلود به Google Drive
│
├── scheduler/
│   └── daily_runner.py      ← اجرای خودکار روزانه
│
├── config/
│   └── config.yaml          ← تمام تنظیمات
│
├── profile/
│   ├── mina_profile.yaml    ← پروفایل و skills
│   └── base_cv.md           ← CV پایه
│
├── data/
│   ├── raw/                 ← jobهای خام
│   ├── cleaned/             ← jobهای تمیز شده
│   └── scored/              ← jobهای امتیازدهی شده
│
├── cvs/tailored/            ← CVهای اختصاصی تولید شده
├── outputs/tracker.csv      ← tracker اصلی
├── logs/                    ← لاگ‌های روزانه
└── main.py                  ← اجرای دستی pipeline
```

---

## نصب و راه‌اندازی

### ۱. نصب Python packages

```bash
pip install pyyaml anthropic
```

برای Google Drive (اختیاری):
```bash
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

### ۲. تنظیم Apify (برای jobهای واقعی)

1. ثبت‌نام در [apify.com](https://apify.com)
2. از [console.apify.com/account/integrations](https://console.apify.com/account/integrations) توکن بگیر
3. در `config/config.yaml` مقدار `apify.token` را تنظیم کن

### ۳. تنظیم Google Drive (اختیاری)

1. در [console.cloud.google.com](https://console.cloud.google.com) یک پروژه بساز
2. Google Drive API را فعال کن
3. یک OAuth 2.0 credential بساز و به عنوان `config/credentials.json` ذخیره کن
4. احراز هویت اولیه را انجام بده:
```bash
python integrations/google_drive.py --auth
```
5. در `config/config.yaml` مقدار `google_drive.enabled` را `true` کن

---

## اجرای دستی

```bash
# اجرای کامل pipeline
python main.py

# فقط یک مرحله
python main.py --phase collect
python main.py --phase clean
python main.py --phase match
python main.py --phase cv
python main.py --phase track

# تولید CV فقط برای jobهای عالی (90+)
python main.py --phase cv --min-score 90

# حداکثر 3 CV تولید کن
python main.py --phase cv --max-cvs 3
```

---

## اجرای خودکار روزانه

```bash
python scheduler/daily_runner.py
```

### تنظیم cron (Linux/Mac)

```bash
crontab -e
```

این خط را اضافه کن (هر روز ساعت 8 صبح):
```
0 8 * * * cd /path/to/job-application-agent && python scheduler/daily_runner.py >> logs/cron.log 2>&1
```

### تنظیم Task Scheduler (Windows)

1. Task Scheduler را باز کن
2. Create Basic Task → Daily → 08:00
3. Action: Start a program
   - Program: `python`
   - Arguments: `scheduler/daily_runner.py`
   - Start in: `C:\path\to\job-application-agent`

---

## سیستم امتیازدهی

| بعد | وزن | توضیح |
|-----|-----|--------|
| Skill Match | 35 | مطابقت skillها با jobهای هدف |
| Experience Fit | 20 | سطح سابقه مناسب |
| Location Fit | 20 | گوتنبرگ / سوئد / Remote |
| Language Fit | 10 | انگلیسی / سوئدی |
| AI/Cloud Bonus | 10 | مرتبط با AI/ML/Cloud |
| Career Value | 5 | ارزش رشد شغلی |

| امتیاز | اولویت |
|--------|--------|
| 90+ | 🌟 Excellent — فوری CV بساز |
| 85-89 | ✅ High — CV بساز |
| 75-84 | 🔵 Medium — بررسی دستی |
| < 75 | ❌ Reject |

---

## قوانین مهم CV

- ❌ هیچ تجربه‌ای جعل نمی‌شود
- ❌ هیچ skill ای که مینا ندارد اضافه نمی‌شود
- ✅ کلمات بهتر و قوی‌تر
- ✅ کلیدواژه‌های job در bullet‌های موجود
- ✅ ترتیب‌بندی بهتر برای ATS

---

## فازهای توسعه

| فاز | وضعیت | محتوا |
|-----|--------|--------|
| Phase 1 | ✅ کامل | ساختار، پروفایل، Job Matcher، Tracker |
| Phase 2 | ✅ کامل | Job Cleaner، Collector، Obsidian Vault |
| Phase 3 | ✅ کامل | CV Tailor با Claude API، Dashboard |
| Phase 4 | ✅ کامل | Apify Live، Daily Scheduler، Drive، Obsidian Sync |
