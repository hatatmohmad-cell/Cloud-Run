
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بوت تيليجرام الذكي لنشر حاوية V2Ray/VLESS على Google Cloud Run (Qwiklabs / Google Skills)
يدعم:
1. التبديل الفوري لروابط .run.app داخل كونفيغ VLESS الخاص بك.
2. الدخول التلقائي لروابط المختبر (Google Skills / Qwiklabs) وتخطي شاشة الترحيب (أفهم ذلك / الشروط).
3. النشر عبر Cloud Shell (أوامر gcloud السريعة) أو عبر واجهة المتصفح (Cloud Run GUI) مع التبديل التلقائي.
4. الفحص الذكي للمناطق (Regions) المسموحة في المختبر وتجاوز قيود المنظمة تلقائياً.
5. التوافق الكامل مع المستودعات السحابية (GitHub Actions / Codespaces / Docker / VPS) ومع Termux على الهاتف.
"""

import os
import re
import json
import time
import uuid
import shutil
import platform
import threading
import urllib.parse
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==================== اكتشاف البيئة التلقائي (Termux / Linux / Cloud) ====================
IS_TERMUX = (
    os.path.exists("/data/data/com.termux")
    or "com.termux" in os.environ.get("PREFIX", "")
    or "ANDROID_ROOT" in os.environ
)

if IS_TERMUX:
    # منع خطأ Unsupported platform: android في Playwright داخل Termux
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")

# استيراد Playwright مع دعم termux-playwright إن وجد
HAS_PLAYWRIGHT = False
HAS_TERMUX_PW = False
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    pass

try:
    import termux_playwright  # noqa: F401
    HAS_TERMUX_PW = True
except ImportError:
    pass

# ==================== إعدادات البوت والكونفيغ الافتراضية ====================
CONFIG_FILE = "bot_config.json"

DEFAULT_CONFIG = {
    "bot_token": os.environ.get("BOT_TOKEN", "9200620644:AAGvAwCTrOvwr_-qUdQ5Waf6c8kp8SMSFxU"),
    "service_name": "gcp-v2ray",
    "docker_image": "docker.io/mohmghjuy/gcp-v2ray:latest",
    "preferred_region": "europe-west12",
    "deploy_method": "auto",          # "auto" (GUI ثم Cloud Shell) | "cloud_shell" (أوامر الشل مباشرة) | "gui" (واجهة المتصفح)
    "auto_pick_region": True,         # True = نشر سريع فوري (مثل الصورة) | False = عرض أزرار لاختيار السيرفر
    "port": "8080",
    "memory": "2Gi",
    "cpu": "1",
    "timeout": "3600",
    "concurrency": "1000",
    "min_instances": "0",
    "max_instances": "10",
    "uuid": "110cc6a9-ab28-4cdf-99d7-e962c639b2d4",
    "path": "%2F%40dososdrido464-vless",
    "sni": "youtube.com",
    "tag": "VLESS-WS-US",
    "vless_template": (
        "vless://110cc6a9-ab28-4cdf-99d7-e962c639b2d4@"
        "gcp-v2ray-872504818995.europe-west12.run.app:443"
        "?security=tls&encryption=none&type=ws"
        "&host=gcp-v2ray-872504818995.europe-west12.run.app"
        "&path=%2F%40dososdrido464-vless&sni=youtube.com#VLESS-WS-US"
    ),
    "headless": True                  # True دائماً للعمل على المستودعات والسيرفرات وتريمكس بدون أخطاء شاشة
}


def load_config() -> dict:
    cfg = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                cfg.update(saved)
        except Exception:
            pass
    if os.environ.get("BOT_TOKEN"):
        cfg["bot_token"] = os.environ["BOT_TOKEN"]
    return cfg


def save_config(cfg: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


CONFIG = load_config()

# قاموس أسماء وأعلام جميع سيرفرات جوجل كلاود
REGION_INFO = {
    "europe-west12": "🇮🇹 تورينو - إيطاليا (europe-west12)",
    "europe-west1": "🇧🇪 بلجيكا (europe-west1)",
    "europe-west4": "🇳🇱 هولندا (europe-west4)",
    "europe-west8": "🇮🇹 ميلانو - إيطاليا (europe-west8)",
    "europe-west3": "🇩🇪 فرانكفورت - ألمانيا (europe-west3)",
    "europe-west10": "🇩🇪 برلين - ألمانيا (europe-west10)",
    "europe-west9": "🇫🇷 باريس - فرنسا (europe-west9)",
    "europe-west2": "🇬🇧 لندن - بريطانيا (europe-west2)",
    "europe-west6": "🇨🇭 زيورخ - سويسرا (europe-west6)",
    "europe-north1": "🇫🇮 فنلندا (europe-north1)",
    "europe-central2": "🇵🇱 وارسو - بولندا (europe-central2)",
    "europe-southwest1": "🇪🇸 مدريد - إسبانيا (europe-southwest1)",
    "us-east4": "🇺🇸 فرجينيا - أمريكا (us-east4)",
    "us-east1": "🇺🇸 ساوث كارولينا - أمريكا (us-east1)",
    "us-east5": "🇺🇸 أوهايو - أمريكا (us-east5)",
    "us-central1": "🇺🇸 أيوا - أمريكا (us-central1)",
    "us-south1": "🇺🇸 دالاس - أمريكا (us-south1)",
    "us-west1": "🇺🇸 أوريغون - أمريكا (us-west1)",
    "us-west2": "🇺🇸 لوس أنجلوس - أمريكا (us-west2)",
    "us-west3": "🇺🇸 يوتا - أمريكا (us-west3)",
    "us-west4": "🇺🇸 لاس فيغاس - أمريكا (us-west4)",
    "northamerica-northeast1": "🇨🇦 مونتريال - كندا (northamerica-northeast1)",
    "northamerica-northeast2": "🇨🇦 تورونتو - كندا (northamerica-northeast2)",
    "asia-east1": "🇹🇼 تايوان (asia-east1)",
    "asia-northeast1": "🇯🇵 طوكيو (asia-northeast1)",
    "asia-southeast1": "🇸🇬 سنغافورة (asia-southeast1)",
    "me-west1": "🌍 الشرق الأوسط (me-west1)",
    "me-central1": "🇶🇦 الدوحة - قطر (me-central1)",
    "me-central2": "🇸🇦 الدمام - السعودية (me-central2)",
}

PRIORITY_ORDER = [
    "europe-west12", "europe-west1", "europe-west4", "europe-west3",
    "europe-west9", "europe-west2", "europe-west8", "europe-west6",
    "europe-north1", "europe-southwest1", "europe-central2",
    "us-east4", "us-central1", "us-east1", "us-west1", "us-west2", "us-south1"
]

PENDING_CHOICES = {}

bot = telebot.TeleBot(CONFIG["bot_token"], parse_mode="HTML")


# ==================== دوال بناء وتحديث الكونفيغ ====================
def get_region_display(region_code: str) -> str:
    return REGION_INFO.get(region_code, f"🌐 {region_code}")


def extract_domain_from_url(run_url: str) -> str:
    cleaned = run_url.strip()
    if "://" not in cleaned:
        cleaned = "https://" + cleaned
    parsed = urllib.parse.urlparse(cleaned)
    domain = parsed.netloc if parsed.netloc else cleaned.split("/")[0]
    return domain.split(":")[0].strip()


def build_vless_uri(run_url: str) -> str:
    """
    يأخذ رابط Cloud Run الجديد (مثل https://gcp-v2ray-387961488464.europe-west12.run.app)
    ويستبدل الدومين والـ host داخل كونفيغ VLESS الخاص بالمستخدم بدقة تامة.
    """
    domain = extract_domain_from_url(run_url)
    template = CONFIG.get("vless_template", "").strip()

    if template.startswith("vless://"):
        # استبدال الدومين بعد @ وقبل :443
        updated = re.sub(r"@[^:?/#]+", f"@{domain}", template, count=1)
        # استبدال قيمة host= في الرابط
        if "host=" in updated:
            updated = re.sub(r"([?&]host=)[^&#]+", rf"\g<1>{domain}", updated)
        return updated

    return (
        f"vless://{CONFIG['uuid']}@{domain}:443"
        f"?security=tls&encryption=none&type=ws"
        f"&host={domain}"
        f"&path={CONFIG['path']}"
        f"&sni={CONFIG['sni']}"
        f"#{CONFIG['tag']}"
    )


def update_vless_template_from_uri(vless_uri: str) -> bool:
    """حفظ قالب VLESS جديد إذا أرسله المستخدم للبوت"""
    vless_uri = vless_uri.strip()
    if not vless_uri.startswith("vless://"):
        return False
    CONFIG["vless_template"] = vless_uri
    m_uuid = re.search(r"vless://([^@]+)@", vless_uri)
    if m_uuid:
        CONFIG["uuid"] = m_uuid.group(1)
    m_path = re.search(r"[?&]path=([^&#]+)", vless_uri)
    if m_path:
        CONFIG["path"] = m_path.group(1)
    m_sni = re.search(r"[?&]sni=([^&#]+)", vless_uri)
    if m_sni:
        CONFIG["sni"] = m_sni.group(1)
    if "#" in vless_uri:
        CONFIG["tag"] = vless_uri.split("#", 1)[1]
    save_config(CONFIG)
    return True


def extract_project_id(text_or_url: str) -> str:
    if not text_or_url:
        return ""
    decoded = urllib.parse.unquote(urllib.parse.unquote(text_or_url))
    match = re.search(r"(qwiklabs-gcp-[a-zA-Z0-9-]+)", decoded)
    return match.group(1) if match else ""


def pick_best_available_region(available_codes: list) -> str:
    if not available_codes:
        return CONFIG["preferred_region"]
    if CONFIG["preferred_region"] in available_codes:
        return CONFIG["preferred_region"]
    for code in PRIORITY_ORDER:
        if code in available_codes:
            return code
    return available_codes[0]


# ==================== إعداد المتصفح المتوافق مع Termux والسيرفرات ====================
def find_chromium_executable() -> str:
    """البحث عن مسار متصفح Chromium المثبت على النظام أو Termux"""
    env_path = os.environ.get("CHROMIUM_PATH") or os.environ.get("CHROME_BIN")
    if env_path and os.path.exists(env_path):
        return env_path

    candidates = [
        "/data/data/com.termux/files/usr/bin/chromium-browser",
        "/data/data/com.termux/files/usr/bin/chromium",
        "/data/data/com.termux/files/usr/bin/chrome",
        shutil.which("chromium-browser"),
        shutil.which("chromium"),
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def launch_browser_compatible(p):
    """تشغيل Chromium بإعدادات متوافقة مع كل من السيرفرات السحابية و Termux Android"""
    args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
    ]

    if IS_TERMUX or platform.machine().startswith(("aarch64", "arm")):
        # أعلام ضرورية لنظام أندرويد لتجنب الإغلاق المفاجئ (SELinux W^X & Phantom Killer)
        args.extend([
            "--single-process",
            "--js-flags=--jitless",
            "--disable-features=VizDisplayCompositor",
        ])

    launch_kwargs = {
        "headless": CONFIG.get("headless", True),
        "args": args,
    }

    exe_path = find_chromium_executable()
    if IS_TERMUX and exe_path:
        launch_kwargs["executable_path"] = exe_path

    try:
        return p.chromium.launch(**launch_kwargs)
    except Exception:
        if exe_path and "executable_path" not in launch_kwargs:
            launch_kwargs["executable_path"] = exe_path
            return p.chromium.launch(**launch_kwargs)
        raise


# ==================== تخطي النوافذ المنبثقة وشروط جوجل ====================
def handle_google_popups_and_speedbump(page):
    """تخطي شاشة 'أفهم ذلك' وشروط الخدمة وتفويض Cloud Shell تلقائياً"""
    # 1. زر أفهم ذلك / I understand (Speedbump)
    speedbump_selectors = [
        'button:has-text("أفهم ذلك")',
        'button:has-text("I understand")',
        'input[value="أفهم ذلك"]',
        'input[value="I understand"]',
        '#confirm',
        'button[name="confirm"]',
    ]
    for sel in speedbump_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=500):
                btn.click(timeout=2000)
                time.sleep(1.5)
        except Exception:
            pass

    # 2. مربع الموافقة على شروط الخدمة (Terms of Service)
    try:
        terms_cb = page.locator(
            'mat-checkbox:has-text("I agree"), '
            'mat-checkbox:has-text("أوافق"), '
            'mdc-checkbox: near(:text("I agree")), '
            'input[type="checkbox"]:visible'
        ).first
        if terms_cb.is_visible(timeout=500):
            classes = terms_cb.get_attribute("class") or ""
            if "checked" not in classes and "selected" not in classes:
                terms_cb.click(timeout=1500)
                time.sleep(0.5)
    except Exception:
        pass

    # 3. أزرار الموافقة والمتابعة وتفويض Cloud Shell
    popup_buttons = [
        'button:has-text("Agree and continue")',
        'button:has-text("موافقة ومتابعة")',
        'button:has-text("I agree")',
        'button:has-text("Authorize")',
        'button:has-text("تفويض")',
        'button:has-text("Continue")',
        'button:has-text("متابعة")',
        'button:has-text("Got it")',
        'button:has-text("Dismiss")',
        'button:has-text("Close")',
    ]
    for sel in popup_buttons:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=500):
                btn.click(timeout=1500)
                time.sleep(0.5)
        except Exception:
            pass


# ==================== فحص السيرفرات المتاحة داخل المختبر ====================
def scan_available_lab_regions(page) -> list:
    available_regions = []
    default_selected_code = None

    try:
        # انتظار انتهاء Fetching regions...
        for _ in range(10):
            content = page.content()
            if "Fetching regions" not in content:
                break
            time.sleep(1)

        region_select = page.locator(
            'mat-form-field:has-text("Region") mat-select, '
            '[aria-label*="Region"]'
        ).first

        if region_select.is_visible(timeout=3000):
            current_text = region_select.inner_text().strip()
            m_def = re.search(r"([a-z]+-[a-z]+[0-9]+)", current_text)
            if m_def:
                default_selected_code = m_def.group(1)

            region_select.click(timeout=4000)
            time.sleep(1.2)

            extracted = page.evaluate("""() => {
                const options = Array.from(document.querySelectorAll('mat-option, [role="option"]'));
                const results = [];
                for (const opt of options) {
                    const isDisabled = opt.getAttribute('aria-disabled') === 'true' ||
                                       opt.classList.contains('mat-option-disabled') ||
                                       opt.classList.contains('mdc-list-item--disabled') ||
                                       opt.hasAttribute('disabled');
                    const optGroup = opt.closest('mat-optgroup, [role="group"]');
                    const groupLabel = optGroup ? (optGroup.innerText || optGroup.getAttribute('label') || '').toLowerCase() : '';
                    const isRestrictedGroup = groupLabel.includes('restricted') ||
                                              groupLabel.includes('unavailable') ||
                                              groupLabel.includes('مقيد') ||
                                              groupLabel.includes('غير متاح');
                    if (!isDisabled && !isRestrictedGroup) {
                        const rawText = (opt.innerText || '').trim();
                        const match = rawText.match(/([a-z]+-[a-z]+[0-9]+)/);
                        if (match) {
                            results.push(match[1]);
                        }
                    }
                }
                return [...new Set(results)];
            }""")

            if extracted:
                available_regions = extracted

            page.keyboard.press("Escape")
            time.sleep(0.6)
    except Exception:
        pass

    if not available_regions and default_selected_code:
        available_regions = [default_selected_code]

    return available_regions


def select_region_on_page(page, chosen_region: str):
    try:
        region_select = page.locator(
            'mat-form-field:has-text("Region") mat-select, '
            '[aria-label*="Region"]'
        ).first
        if region_select.is_visible(timeout=2000):
            current_text = region_select.inner_text().strip()
            if chosen_region in current_text:
                return
            region_select.click(timeout=4000)
            time.sleep(1)
            opt = page.locator(
                f'mat-option:has-text("{chosen_region}"), '
                f'[role="option"]:has-text("{chosen_region}")'
            ).first
            if opt.is_visible(timeout=2000):
                opt.click(timeout=3000)
                time.sleep(0.8)
            else:
                page.keyboard.press("Escape")
    except Exception:
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass


# ==================== الطريقة 1: النشر السريع عبر Cloud Shell (أوامر gcloud) ====================
def deploy_via_cloud_shell(page, project_id: str, chosen_region: str, fallback_regions: list = None) -> tuple:
    """
    يفتح Cloud Shell في وضع الترمينال المباشر، يتخطى Continue و Authorize،
    وينفذ أمر gcloud run deploy مع تجربة المناطق البديلة تلقائياً إذا كانت المنطقة مقيدة.
    يرجع: (deployed_url, actual_region)
    """
    shell_url = f"https://console.cloud.google.com/cloudshell/editor?shellonly=true&project={project_id}"
    page.goto(shell_url, wait_until="domcontentloaded", timeout=60000)

    terminal_ready = False
    for _ in range(45):
        handle_google_popups_and_speedbump(page)
        # إذا ظهر زر Close Editor للانتقال إلى الترمينال
        try:
            close_ed = page.locator('button[aria-label*="Close Editor"], button:has-text("Open Terminal")').first
            if close_ed.is_visible(timeout=400):
                close_ed.click()
        except Exception:
            pass

        for frame in page.frames:
            try:
                if frame.locator(".xterm-helper-textarea").count() > 0:
                    terminal_ready = True
                    break
            except Exception:
                pass
        if terminal_ready:
            break
        time.sleep(2)

    if not terminal_ready:
        return None, chosen_region

    time.sleep(5)
    handle_google_popups_and_speedbump(page)

    regions_to_try = [chosen_region]
    if fallback_regions:
        for r in fallback_regions:
            if r not in regions_to_try:
                regions_to_try.append(r)
    for r in ["europe-west12", "europe-west1", "europe-west4", "us-east4", "us-central1", "us-east1", "us-west1"]:
        if r not in regions_to_try:
            regions_to_try.append(r)

    regions_str = " ".join(regions_to_try[:7])

    # أمر باش متكامل يفعل الخدمة ويجرب المناطق بالترتيب حتى ينجح النشر ويطبع الرابط النهائي
    cmd = (
        f"gcloud config set project {project_id} --quiet; "
        f"gcloud services enable run.googleapis.com --project={project_id} --quiet; "
        f"for REG in {regions_str}; do "
        f"echo \"__TRYING_REGION__:${{REG}}\"; "
        f"if gcloud run deploy {CONFIG['service_name']} "
        f"--image={CONFIG['docker_image']} "
        f"--region=${{REG}} "
        f"--platform=managed "
        f"--allow-unauthenticated "
        f"--no-cpu-throttling "
        f"--memory={CONFIG['memory']} "
        f"--cpu={CONFIG['cpu']} "
        f"--timeout={CONFIG['timeout']} "
        f"--concurrency={CONFIG['concurrency']} "
        f"--execution-environment=gen2 "
        f"--min-instances={CONFIG['min_instances']} "
        f"--max-instances={CONFIG['max_instances']} "
        f"--no-cpu-boost "
        f"--port={CONFIG['port']} "
        f"--project={project_id} --quiet; then "
        f"URL=$(gcloud run services describe {CONFIG['service_name']} "
        f"--region=${{REG}} --project={project_id} --format='value(status.url)'); "
        f"echo \"__RUN_RESULT__|${{REG}}|${{URL}}|\"; "
        f"break; "
        f"fi; "
        f"done"
    )

    target_frame = page
    for frame in page.frames:
        try:
            if frame.locator(".xterm-helper-textarea").count() > 0:
                target_frame = frame
                break
        except Exception:
            pass

    target_frame.locator(".xterm-helper-textarea").first.focus()
    page.keyboard.type(cmd, delay=8)
    page.keyboard.press("Enter")

    start_wait = time.time()
    while time.time() - start_wait < 220:
        handle_google_popups_and_speedbump(page)
        for frame in page.frames:
            try:
                text = frame.content()
                m = re.search(r"__RUN_RESULT__\|([a-z0-9-]+)\|(https://[a-zA-Z0-9.-]+\.run\.app)\|", text)
                if m:
                    return m.group(2), m.group(1)
                m2 = re.search(r"Service URL:\s*(https://[a-zA-Z0-9.-]+\.run\.app)", text)
                if m2:
                    url_found = m2.group(1)
                    reg_m = re.search(r"\.([a-z]+-[a-z]+[0-9]+)\.run\.app", url_found)
                    return url_found, (reg_m.group(1) if reg_m else chosen_region)
            except Exception:
                pass
        time.sleep(3)

    return None, chosen_region


# ==================== الطريقة 2: النشر عبر واجهة Cloud Run GUI (مطابق للفيديو 1) ====================
def fill_and_create_service_gui(page, chosen_region: str) -> tuple:
    """
    يملأ نموذج إنشاء خدمة Cloud Run كما في الفيديو التوضيحي الأول تماماً:
    - Container image URL: docker.io/mohmghjuy/gcp-v2ray:latest
    - Service name: gcp-v2ray
    - Authentication: Allow public access
    - Billing: Instance-based
    - Memory: 2 GiB | CPU: 1
    - Request timeout: 3600 | Maximum concurrent requests: 1000
    - Execution environment: Second generation
    - Revision scaling: Min 0 | Max 10 | Startup CPU boost: OFF
    """
    handle_google_popups_and_speedbump(page)

    # 1. إدخال صورة الحاوية Container image URL
    img_input = page.locator(
        'input[aria-label*="Container image"], '
        'input[placeholder*="us-docker.pkg.dev"], '
        'mat-form-field:has-text("Container image URL") input'
    ).first
    img_input.click(timeout=10000)
    img_input.fill(CONFIG["docker_image"])
    page.keyboard.press("Tab")
    time.sleep(1.2)

    # 2. إدخال اسم الخدمة Service name
    try:
        svc_input = page.locator(
            'input[aria-label*="Service name"], '
            'mat-form-field:has-text("Service name") input'
        ).first
        if svc_input.is_visible(timeout=2000):
            svc_input.fill(CONFIG["service_name"])
    except Exception:
        pass

    # 3. اختيار المنطقة (Region)
    select_region_on_page(page, chosen_region)

    # قراءة المنطقة المختارة فعلياً في الصفحة
    actual_region = chosen_region
    try:
        reg_text = page.locator('mat-form-field:has-text("Region") mat-select, [aria-label*="Region"]').first.inner_text()
        m_reg = re.search(r"([a-z]+-[a-z]+[0-9]+)", reg_text)
        if m_reg:
            actual_region = m_reg.group(1)
    except Exception:
        pass

    # 4. Authentication -> Allow public access
    try:
        pub_radio = page.locator(
            'mat-radio-button:has-text("Allow public access"), '
            'mat-radio-button:has-text("Allow unauthenticated")'
        ).first
        if pub_radio.is_visible(timeout=2000):
            pub_radio.click()
    except Exception:
        pass

    # 5. Billing -> Instance-based
    try:
        billing_radio = page.locator(
            'mat-radio-button:has-text("Instance-based"), '
            'mat-radio-button:has-text("CPU is always allocated")'
        ).first
        if billing_radio.is_visible(timeout=2000):
            billing_radio.click()
    except Exception:
        pass

    # فتح قسم Containers, Networking, Security إن كان مطوياً
    try:
        accordion = page.locator(
            'mat-expansion-panel-header:has-text("Containers"), '
            ':text("Containers, Networking, Security")'
        ).first
        if accordion.is_visible(timeout=2000):
            if accordion.get_attribute("aria-expanded") == "false":
                accordion.click()
                time.sleep(1)
    except Exception:
        pass

    # 6. Resources -> Memory = 2 GiB, CPU = 1
    try:
        mem_select = page.locator('mat-form-field:has-text("Memory") mat-select').first
        if mem_select.is_visible(timeout=2000):
            mem_select.scroll_into_view_if_needed()
            mem_select.click()
            time.sleep(0.8)
            mem_opt = page.locator('mat-option:has-text("2 GiB"), mat-option:has-text("2 GB")').first
            if mem_opt.is_visible(timeout=2000):
                mem_opt.click()
                time.sleep(0.6)
            else:
                page.keyboard.press("Escape")
    except Exception:
        pass

    try:
        cpu_select = page.locator('mat-form-field:has-text("CPU") mat-select').first
        if cpu_select.is_visible(timeout=2000):
            cpu_select.click()
            time.sleep(0.6)
            cpu_opt = page.locator('mat-option:has-text("1")').first
            if cpu_opt.is_visible(timeout=2000):
                cpu_opt.click()
                time.sleep(0.6)
            else:
                page.keyboard.press("Escape")
    except Exception:
        pass

    # 7. Requests -> Request timeout = 3600, Maximum concurrent requests = 1000
    try:
        timeout_input = page.locator(
            'mat-form-field:has-text("Request timeout") input, '
            'input[aria-label*="Request timeout"]'
        ).first
        if timeout_input.is_visible(timeout=2000):
            timeout_input.scroll_into_view_if_needed()
            timeout_input.fill(CONFIG["timeout"])
    except Exception:
        pass

    try:
        conc_input = page.locator(
            'mat-form-field:has-text("Maximum concurrent") input, '
            'input[aria-label*="Maximum concurrent"]'
        ).first
        if conc_input.is_visible(timeout=2000):
            conc_input.scroll_into_view_if_needed()
            conc_input.fill(CONFIG["concurrency"])
    except Exception:
        pass

    # 8. Execution environment -> Second generation
    try:
        gen2_radio = page.locator('mat-radio-button:has-text("Second generation")').first
        if gen2_radio.is_visible(timeout=2000):
            gen2_radio.scroll_into_view_if_needed()
            gen2_radio.click()
    except Exception:
        pass

    # 9. Revision scaling -> Min = 0, Max = 10, Startup CPU boost = OFF
    try:
        min_inputs = page.locator('mat-form-field:has-text("Minimum number of") input')
        for i in range(min_inputs.count()):
            inp = min_inputs.nth(i)
            if inp.is_visible():
                inp.fill(CONFIG["min_instances"])
    except Exception:
        pass

    try:
        max_inputs = page.locator('mat-form-field:has-text("Maximum number of") input')
        for i in range(max_inputs.count()):
            inp = max_inputs.nth(i)
            if inp.is_visible():
                inp.fill(CONFIG["max_instances"])
    except Exception:
        pass

    try:
        boost_cb = page.locator('mat-checkbox:has-text("Startup CPU boost")').first
        if boost_cb.is_visible(timeout=2000):
            boost_cb.scroll_into_view_if_needed()
            classes = boost_cb.get_attribute("class") or ""
            is_checked = (
                "mat-checkbox-checked" in classes
                or "mdc-checkbox--selected" in classes
                or boost_cb.locator("input:checked").count() > 0
            )
            if is_checked:
                boost_cb.click()
    except Exception:
        pass

    # التقاط الرابط المتوقع من Endpoint URL Preview في الصفحة
    preview_url = None
    html_before = page.content()
    preview_match = re.search(r"https://[a-zA-Z0-9-]+-[0-9]+\.[a-z0-9-]+\.run\.app", html_before)
    if preview_match:
        preview_url = preview_match.group(0)

    # 10. الضغط على زر Create
    create_btn = page.locator('button:has-text("Create"), button[type="submit"]:has-text("Create")').first
    create_btn.scroll_into_view_if_needed()
    create_btn.click()

    # انتظار اكتمال النشر وظهور الرابط النهائي
    deployed_url = None
    start_wait = time.time()
    while time.time() - start_wait < 200:
        handle_google_popups_and_speedbump(page)
        content = page.content()

        if "violates constraint" in content or "resourceLocations" in content:
            return None, actual_region

        url_match = re.search(r"https://[a-zA-Z0-9-]+-[a-zA-Z0-9]+\.[a-z0-9-]+\.run\.app", content)
        if url_match:
            deployed_url = url_match.group(0)
            reg_in_url = re.search(r"\.([a-z]+-[a-z]+[0-9]+)\.run\.app", deployed_url)
            if reg_in_url:
                actual_region = reg_in_url.group(1)

        # في الفيديو الأول يكتمل النشر عند ظهور علامات الصح أو 100%
        if deployed_url and ("100%" in content or "Routing traffic" in content or "Manage traffic" in content):
            if "100%" in content or time.time() - start_wait > 45:
                break

        time.sleep(3)

    return (deployed_url or preview_url), actual_region


# ==================== المسار الرئيسي الكامل للنشر ====================
def run_deployment_pipeline(chat_id: int, status_msg_id: int, sso_url: str):
    start_time = time.time()
    project_id = extract_project_id(sso_url)
    image_short = CONFIG["docker_image"].split("/")[-1].split(":")[0]

    if not HAS_PLAYWRIGHT:
        bot.edit_message_text(
            "❌ <b>مكتبة Playwright غير مثبتة!</b>\n"
            "شغّل سكربت التثبيت <code>bash setup_termux.sh</code> أو <code>pip install playwright</code>.",
            chat_id=chat_id,
            message_id=status_msg_id
        )
        return

    try:
        with sync_playwright() as p:
            browser = launch_browser_compatible(p)
            context = browser.new_context(viewport={"width": 1366, "height": 900})
            page = context.new_page()

            # رسالة بدء النشر السريع المطابقة للصورة المرفقة
            bot.edit_message_text(
                f"🚀 <b>بدء النشر السريع...</b>\n\n"
                f"📦 <b>الصورة:</b> <code>{image_short}</code>\n"
                f"🏷 <b>الخدمة:</b> <code>{CONFIG['service_name']}</code>\n"
                f"📍 <b>المنطقة:</b> <code>{CONFIG['preferred_region']}</code>\n"
                f"⚡️ <b>الحد الأقصى:</b> <code>220s</code>",
                chat_id=chat_id,
                message_id=status_msg_id
            )

            # 1. فتح رابط Google Skills وتخطي شاشة الترحيب (أفهم ذلك) وشروط الخدمة
            page.goto(sso_url, wait_until="domcontentloaded", timeout=60000)
            for _ in range(20):
                time.sleep(2)
                handle_google_popups_and_speedbump(page)
                if not project_id:
                    project_id = extract_project_id(page.url) or extract_project_id(page.content())
                if "console.cloud.google.com" in page.url and project_id:
                    break

            for _ in range(5):
                time.sleep(1.5)
                handle_google_popups_and_speedbump(page)
                if not project_id:
                    project_id = extract_project_id(page.url) or extract_project_id(page.content())

            if not project_id:
                browser.close()
                bot.edit_message_text(
                    "❌ <b>تعذر استخراج Project ID من الرابط.</b>\n"
                    "تأكد من أن رابط المختبر جديد وصالح ولم تنتهِ مدته.",
                    chat_id=chat_id,
                    message_id=status_msg_id
                )
                return

            deployed_url = None
            chosen_region = CONFIG["preferred_region"]
            available_regions = []

            # إذا كان وضع النشر هو Cloud Shell المباشر
            if CONFIG.get("deploy_method") == "cloud_shell":
                bot.edit_message_text(
                    f"🚀 <b>بدء النشر السريع عبر Cloud Shell...</b>\n\n"
                    f"🆔 <b>المشروع:</b> <code>{project_id}</code>\n"
                    f"📦 <b>الصورة:</b> <code>{image_short}</code>\n"
                    f"🏷 <b>الخدمة:</b> <code>{CONFIG['service_name']}</code>\n"
                    f"📍 <b>المنطقة:</b> <code>{chosen_region}</code>\n"
                    f"⚡️ <b>الحد الأقصى:</b> <code>220s</code>",
                    chat_id=chat_id,
                    message_id=status_msg_id
                )
                deployed_url, chosen_region = deploy_via_cloud_shell(page, project_id, chosen_region)

            else:
                # فتح صفحة إنشاء خدمة Cloud Run وتفعيل الـ API تلقائياً (كما في الفيديو الأول)
                create_url = f"https://console.cloud.google.com/run/create?enableApi=true&project={project_id}"
                page.goto(create_url, wait_until="domcontentloaded", timeout=60000)

                for _ in range(30):
                    handle_google_popups_and_speedbump(page)
                    if page.locator('input[aria-label*="Container image"], mat-form-field:has-text("Region")').count() > 0:
                        break
                    time.sleep(2)

                time.sleep(2.5)
                handle_google_popups_and_speedbump(page)

                available_regions = scan_available_lab_regions(page)
                if not available_regions:
                    available_regions = [CONFIG["preferred_region"], "europe-west12", "europe-west1", "us-east4", "us-central1"]

                chosen_region = pick_best_available_region(available_regions)

                # إذا كان المستخدم مفعلاً لوضع الأزرار التفاعلية وهناك أكثر من منطقة
                if not CONFIG.get("auto_pick_region", True) and len(available_regions) > 1:
                    session_id = str(uuid.uuid4())[:8]
                    event = threading.Event()
                    PENDING_CHOICES[session_id] = {
                        "event": event,
                        "chosen": None,
                    }

                    markup = InlineKeyboardMarkup(row_width=1)
                    for reg_code in available_regions[:10]:
                        markup.add(
                            InlineKeyboardButton(
                                text=f"{get_region_display(reg_code)}",
                                callback_data=f"pick_{session_id}_{reg_code}"
                            )
                        )
                    markup.add(
                        InlineKeyboardButton(
                            text=f"⚡️ اختيار تلقائي ({get_region_display(chosen_region)})",
                            callback_data=f"pick_{session_id}_{chosen_region}"
                        )
                    )

                    bot.edit_message_text(
                        f"🔍 <b>السيرفرات المفتوحة في هذا المختبر ({len(available_regions)}):</b>\n"
                        f"اختر السيرفر خلال 20 ثانية أو سيتم الاختيار تلقائياً:",
                        chat_id=chat_id,
                        message_id=status_msg_id,
                        reply_markup=markup
                    )
                    event.wait(timeout=20)
                    user_pick = PENDING_CHOICES.pop(session_id, {}).get("chosen")
                    if user_pick:
                        chosen_region = user_pick

                bot.edit_message_text(
                    f"🚀 <b>بدء النشر السريع...</b>\n\n"
                    f"📦 <b>الصورة:</b> <code>{image_short}</code>\n"
                    f"🏷 <b>الخدمة:</b> <code>{CONFIG['service_name']}</code>\n"
                    f"📍 <b>المنطقة:</b> <code>{chosen_region}</code>\n"
                    f"⚡️ <b>الحد الأقصى:</b> <code>220s</code>",
                    chat_id=chat_id,
                    message_id=status_msg_id
                )

                deployed_url, chosen_region = fill_and_create_service_gui(page, chosen_region)

                # خطة بديلة تلقائية عبر Cloud Shell إذا لم يظهر الرابط من الواجهة
                if not deployed_url and CONFIG.get("deploy_method") == "auto":
                    deployed_url, chosen_region = deploy_via_cloud_shell(
                        page, project_id, chosen_region, available_regions
                    )

            browser.close()

            if not deployed_url:
                bot.edit_message_text(
                    "⚠️ <b>تعذر استخراج رابط الخدمة تلقائياً.</b>\n"
                    "تأكد من أن المختبر شغال ولم تنتهِ مدته، أو جرب التبديل إلى وضع Cloud Shell بالأمر <code>/mode</code>.",
                    chat_id=chat_id,
                    message_id=status_msg_id
                )
                return

            elapsed = int(time.time() - start_time)
            new_vless = build_vless_uri(deployed_url)

            # رسالة النجاح المطابقة للصورة + كونفيغ VLESS الجاهز للنسخ
            success_msg = (
                "🎉 <b>تم النشر بنجاح!</b>\n\n"
                f"🏷 <b>الخدمة:</b> <code>{CONFIG['service_name']}</code>\n"
                f"📦 <b>الصورة:</b> <code>{image_short}</code>\n"
                f"🚀 <b>الرابط:</b>\n{deployed_url}\n\n"
                f"📍 <b>المنطقة:</b> <code>{chosen_region}</code> ({get_region_display(chosen_region)})\n"
                f"⚡️ <b>الوقت:</b> {elapsed} ثانية\n\n"
                f"🔗 <b>كونفيغ VLESS الجديد (اضغط للنسخ):</b>\n"
                f"<code>{new_vless}</code>"
            )

            bot.edit_message_text(
                success_msg,
                chat_id=chat_id,
                message_id=status_msg_id,
                disable_web_page_preview=True
            )

    except Exception as e:
        bot.edit_message_text(
            f"❌ <b>حدث خطأ أثناء العملية:</b>\n<code>{str(e)}</code>",
            chat_id=chat_id,
            message_id=status_msg_id
        )


# ==================== معالج أزرار اختيار السيرفر ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("pick_"))
def on_region_button_click(call):
    try:
        _, session_id, reg_code = call.data.split("_", 2)
        session = PENDING_CHOICES.get(session_id)
        if not session:
            bot.answer_callback_query(call.id, "⏰ انتهت مهلة الاختيار وتم البدء تلقائياً!")
            return
        session["chosen"] = reg_code
        session["event"].set()
        bot.answer_callback_query(call.id, f"✅ تم اختيار {get_region_display(reg_code)}!")
    except Exception:
        pass


# ==================== أوامر البوت في تيليجرام ====================
@bot.message_handler(commands=["start", "help"])
def welcome(message):
    text = (
        "👋 <b>أهلاً بك في بوت النشر السريع على Google Cloud Run وتوليد كونفيغ VLESS!</b>\n\n"
        "🚀 <b>طريقة الاستخدام:</b>\n"
        "1️⃣ <b>نشر سيرفر جديد:</b> أرسل رابط مختبر <b>Google Skills / Qwiklabs</b> وسيقوم البوت بفتح المتصفح وتفعيل Cloud Run ونشر الحاوية <code>docker.io/mohmghjuy/gcp-v2ray:latest</code> وإرسال الرابط والكونفيغ الجديد تلقائياً.\n"
        "2️⃣ <b>تبديل رابط كونفيغ جاهز:</b> أرسل أي رابط <code>https://...run.app</code> وسيرسل لك البوت فوراً كونفيغ VLESS الخاص بك بعد تحديث الدومين والـ host.\n"
        "3️⃣ <b>تحديث قالب الكونفيغ:</b> أرسل أي رابط يبدأ بـ <code>vless://</code> لحفظه كقالب أساسي لك.\n\n"
        "🛠 <b>الأوامر المتاحة:</b>\n"
        "• <code>/status</code> — عرض الإعدادات الحالية والقالب المحفوظ\n"
        "• <code>/mode</code> — التبديل بين وضع النشر (تلقائي GUI+Shell / Cloud Shell فقط / GUI فقط)\n"
        "• <code>/auto_select</code> — التبديل بين النشر السريع الفوري أو عرض أزرار اختيار المنطقة\n"
        "• <code>/set_region europe-west12</code> — تغيير المنطقة المفضلة\n"
        "• <code>/set_image docker.io/mohmghjuy/gcp-v2ray:latest</code> — تغيير الحاوية\n"
        "• <code>/set_service gcp-v2ray</code> — تغيير اسم الخدمة"
    )
    bot.reply_to(message, text)


@bot.message_handler(commands=["status"])
def status_cmd(message):
    text = (
        "⚙️ <b>الإعدادات الحالية للبوت:</b>\n\n"
        f"🏷 <b>الخدمة:</b> <code>{CONFIG['service_name']}</code>\n"
        f"📦 <b>الحاوية:</b> <code>{CONFIG['docker_image']}</code>\n"
        f"📍 <b>المنطقة المفضلة:</b> <code>{CONFIG['preferred_region']}</code> ({get_region_display(CONFIG['preferred_region'])})\n"
        f"🖥 <b>طريقة النشر:</b> <code>{CONFIG.get('deploy_method', 'auto')}</code>\n"
        f"⚡ <b>اختيار المنطقة:</b> <code>{'نشر سريع تلقائي' if CONFIG.get('auto_pick_region', True) else 'أزرار تفاعلية'}</code>\n"
        f"🧠 <b>الموارد:</b> <code>{CONFIG['memory']} RAM | {CONFIG['cpu']} CPU | Gen2 | Boost OFF</code>\n"
        f"⏱ <b>المهلة والتزامن:</b> <code>{CONFIG['timeout']}s | {CONFIG['concurrency']} req | Max {CONFIG['max_instances']}</code>\n\n"
        f"🔗 <b>قالب VLESS المحفوظ حالياً:</b>\n<code>{CONFIG['vless_template']}</code>"
    )
    bot.reply_to(message, text)


@bot.message_handler(commands=["mode"])
def switch_mode(message):
    modes = ["auto", "cloud_shell", "gui"]
    current = CONFIG.get("deploy_method", "auto")
    nxt = modes[(modes.index(current) + 1) % len(modes)] if current in modes else "auto"
    CONFIG["deploy_method"] = nxt
    save_config(CONFIG)

    desc = {
        "auto": "🤖 <b>تلقائي ذكي (GUI + Cloud Shell احتياطي)</b>",
        "cloud_shell": "💻 <b>أوامر Cloud Shell المباشرة (gcloud run deploy)</b>",
        "gui": "🌐 <b>واجهة المتصفح فقط (Cloud Run Create Service GUI)</b>",
    }[nxt]
    bot.reply_to(message, f"✅ تم تغيير طريقة النشر إلى:\n{desc}")


@bot.message_handler(commands=["auto_select"])
def toggle_auto_select(message):
    CONFIG["auto_pick_region"] = not CONFIG.get("auto_pick_region", True)
    save_config(CONFIG)
    if CONFIG["auto_pick_region"]:
        bot.reply_to(message, "⚡️ <b>تم تفعيل النشر السريع التلقائي!</b>")
    else:
        bot.reply_to(message, "🔘 <b>تم تفعيل عرض أزرار اختيار السيرفر!</b>")


@bot.message_handler(commands=["set_region"])
def change_region(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ مثال:\n<code>/set_region europe-west12</code>")
        return
    CONFIG["preferred_region"] = parts[1].strip()
    save_config(CONFIG)
    bot.reply_to(message, f"✅ تم ضبط المنطقة المفضلة إلى:\n<b>{get_region_display(CONFIG['preferred_region'])}</b>")


@bot.message_handler(commands=["set_image"])
def change_image(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ مثال:\n<code>/set_image docker.io/mohmghjuy/gcp-v2ray:latest</code>")
        return
    CONFIG["docker_image"] = parts[1].strip()
    save_config(CONFIG)
    bot.reply_to(message, f"✅ تم تحديث الحاوية إلى:\n<code>{CONFIG['docker_image']}</code>")


@bot.message_handler(commands=["set_service"])
def change_service(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ مثال:\n<code>/set_service gcp-v2ray</code>")
        return
    CONFIG["service_name"] = parts[1].strip()
    save_config(CONFIG)
    bot.reply_to(message, f"✅ تم تحديث اسم الخدمة إلى:\n<code>{CONFIG['service_name']}</code>")


@bot.message_handler(func=lambda m: True)
def handle_all_messages(message):
    text = (message.text or "").strip()

    # 1. إذا أرسل المستخدم كونفيغ vless:// جديد لتحديث القالب المحفوظ
    if text.startswith("vless://"):
        update_vless_template_from_uri(text)
        bot.reply_to(
            message,
            f"✅ <b>تم حفظ قالب VLESS الجديد بنجاح!</b>\n\n"
            f"🔗 <b>القالب الحالي:</b>\n<code>{CONFIG['vless_template']}</code>"
        )
        return

    # 2. إذا أرسل المستخدم رابط .run.app جاهز لتغيير الدومين في الكونفيغ فوراً
    run_match = re.search(r"https?://([a-zA-Z0-9.-]+\.run\.app)", text)
    if run_match and "skills.google" not in text and "console.cloud.google" not in text:
        run_url = run_match.group(0)
        vless_uri = build_vless_uri(run_url)
        bot.reply_to(
            message,
            f"✅ <b>تم تركيب الرابط الجديد في الكونفيغ بنجاح!</b>\n\n"
            f"🚀 <b>الرابط الجديد:</b>\n{run_url}\n\n"
            f"🔗 <b>كونفيغ VLESS الجاهز (اضغط للنسخ):</b>\n<code>{vless_uri}</code>",
            disable_web_page_preview=True
        )
        return

    # 3. إذا أرسل المستخدم رابط مختبر Google Skills / Qwiklabs
    if any(k in text for k in ("skills.google", "qwiklabs", "console.cloud.google", "accounts.google")):
        url_match = re.search(r"https?://[^\s]+", text)
        if not url_match:
            bot.reply_to(message, "⚠️ لم يتم العثور على رابط صالح في الرسالة.")
            return

        sso_url = url_match.group(0)
        wait_msg = bot.reply_to(
            message,
            "⏳ <b>تم استلام رابط المختبر! جاري بدء النشر السريع...</b>"
        )
        t = threading.Thread(
            target=run_deployment_pipeline,
            args=(message.chat.id, wait_msg.message_id, sso_url),
            daemon=True
        )
        t.start()
        return

    bot.reply_to(
        message,
        "⚠️ أرسل رابط <b>Google Skills</b> لنشر السيرفر تلقائياً، أو أرسل رابط <b>https://...run.app</b> لتحديث كونفيغ VLESS فوراً."
    )


if __name__ == "__main__":
    print("🤖 البوت يعمل الآن بنجاح! جاهز لاستقبال روابط المختبر وروابط Cloud Run...")
    bot.infinity_polling(timeout=60, long_polling_timeout=30)
