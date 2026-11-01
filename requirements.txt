```bash
#!/data/data/com.termux/files/usr/bin/bash
set -e

echo "===================================================="
echo "🚀 جاري تثبيت متطلبات البوت على Termux بدون أخطاء..."
echo "===================================================="

# 1. تحديث الحزم وتفعيل مستودع X11 لتحميل Chromium الأصلي
pkg update -y && pkg upgrade -y
pkg install -y x11-repo tur-repo
pkg install -y python nodejs chromium python-greenlet procps termux-api git

# 2. تثبيت مكتبات البوت وحل مشكلة توافق Playwright مع أندرويد
pip install --upgrade pip setuptools wheel
pip install pyTelegramBotAPI pyee typing-extensions termux-playwright

# 3. حقن عجلة Playwright وتفعيل باتش أندرويد تلقائياً
termux-playwright-install || true

# 4. ضبط متغيرات البيئة لمتصفح Chromium على Termux
export PLAYWRIGHT_BROWSERS_PATH=0
export CHROMIUM_PATH=$(which chromium-browser 2>/dev/null || which chromium)

echo "✅ اكتمل التثبيت بنجاح! لتشغيل البوت الآن نفذ الأمر:"
echo "python3 bot.py"
```
