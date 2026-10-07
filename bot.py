"""Jojo Usta — zamonaviy Telegram bot.
AI/API to'lovisiz ishlaydi: aqlli kalit-so'z aniqlash,
xavfsiz diagnostika, rasm, telefon, hudud va ustaga zakaz.
Ishga tushirish: python bot.py
"""

import html
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton as Btn,
    InlineKeyboardMarkup as Markup,
    InputMediaPhoto,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# ============================================================
# 1. SOZLAMALAR
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_chat_id: int | None
    emergency_phone: str
    max_photos: int = 5


def to_int(value: str | None) -> int | None:
    try:
        return int(value) if value and value.strip() else None
    except ValueError:
        return None


def load_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN topilmadi. .env faylga BotFather tokenini yozing."
        )

    return Settings(
        bot_token=token,
        admin_chat_id=to_int(os.getenv("ADMIN_CHAT_ID")),
        emergency_phone=os.getenv(
            "EMERGENCY_PHONE", "+998 77 286 2009"
        ).strip(),
    )


settings = load_settings()

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("jojo_usta")


# ============================================================
# 2. USTALAR
# ============================================================
# chat_id — ustaning Telegram ID si.
# Usta botga /id yuborsa, bot ID ni chiqaradi.
#
# Muhim:
# Telegram bot telefon raqamga bevosita Telegram xabar yubora
# olmaydi. Usta avval botga /start yuboradi, /id orqali chat_id
# olinadi va shu yerga yoziladi.
#
# phone — ustaning telefon raqami, foydalanuvchiga ko'rsatish/
# kontakt uchun saqlanadi.
#
# service:
# appliance = maishiy texnika
# plumber   = santexnik
# electric  = elektrik
# *         = istalgan xizmat
#
# region/district:
# * = istalgan hudud
# ============================================================

MASTERS = [
    {
        "region": "Andijon",
        "district": "Asaka",
        "service": "plumber",
        "name": "Asaka santexnik",
        "phone": "+998 90 000 00 01",
        "chat_id": 0,
    },
    {
        "region": "Andijon",
        "district": "Asaka",
        "service": "appliance",
        "name": "Asaka texnika ustasi",
        "phone": "+998 90 000 00 02",
        "chat_id": 0,
    },
    {
        "region": "Andijon",
        "district": "Asaka",
        "service": "electric",
        "name": "Asaka elektrik",
        "phone": "+998 90 000 00 03",
        "chat_id": 0,
    },
    {
        "region": "Andijon",
        "district": "*",
        "service": "*",
        "name": "Andijon umumiy usta",
        "phone": "+998 90 000 00 04",
        "chat_id": 0,
    },
    {
        "region": "*",
        "district": "*",
        "service": "*",
        "name": "Umumiy navbatchi usta",
        "phone": "+998 90 000 00 05",
        "chat_id": 0,
    },
]


# ============================================================
# 3. XIZMATLAR
# ============================================================

SERVICES = {
    "appliance": {
        "label": "🔧 Maishiy texnika",
        "title": "Maishiy texnika",
    },
    "plumber": {
        "label": "🚰 Santexnik",
        "title": "Santexnik",
    },
    "electric": {
        "label": "⚡ Elektrik",
        "title": "Elektrik",
    },
}

PROBLEM_CATALOG = {
    "appliance": [
        {
            "key": "fridge",
            "label": "🧊 Muzlatgich",
            "keywords": ["muzlatgich", "xolodilnik", "sovutmayapti", "sovutmay"],
            "steps": [
                (
                    "Muzlatgich elektrga ulanganmi?",
                    "Vilka va rozetkani faqat tashqi tomondan tekshiring. Nam qo'l bilan tegmang.",
                ),
                (
                    "Eshigi mahkam yopilayaptimi?",
                    "Eshik rezinasini ko'zdan kechiring va eshik to'liq yopilayotganini tekshiring.",
                ),
                (
                    "Harorat sozlamasi to'g'rimi?",
                    "Harorat sozlamasi tasodifan o'zgarmaganini tekshiring.",
                ),
            ],
        },
        {
            "key": "washer",
            "label": "🧺 Kir yuvish mashinasi",
            "keywords": ["kir yuvish", "stiralka", "suv olmayapti", "suv olmay"],
            "steps": [
                (
                    "Mashina elektrga ulanganmi?",
                    "Vilka va rozetkani tashqi tomondan tekshiring. Nam qo'l bilan ishlamang.",
                ),
                (
                    "Suv krani ochiqmi?",
                    "Mashinaning suv kirish krani ochiqligini tekshiring.",
                ),
                (
                    "Kirish shlangi bukilmaganmi?",
                    "Shlang tashqi tomondan qattiq bukilib qolmaganini ko'ring.",
                ),
            ],
        },
        {
            "key": "vacuum",
            "label": "🧹 Changyutgich",
            "keywords": ["changyutgich", "pilesos", "plisos", "ishlamayapti"],
            "steps": [
                (
                    "Vilka rozetkaga to'g'ri ulanganmi?",
                    "Faqat tashqi ulanishni tekshiring. Shikastlangan simga tegmang.",
                ),
                (
                    "Filtri to'lib qolmaganmi?",
                    "Qurilmani elektrdan uzib, yo'riqnomasiga ko'ra filtrini tashqi qismini tekshiring.",
                ),
                (
                    "Qurilma qizib ketgan bo'lishi mumkinmi?",
                    "Elektrdan uzib, sovishini kuting. Korpusni ochmang.",
                ),
            ],
        },
        {
            "key": "other",
            "label": "📦 Boshqa texnika",
            "keywords": ["televizor", "mikroto'lqin", "pech", "duhovka", "konditsioner"],
            "steps": [
                (
                    "Qurilma elektrga ulanganmi?",
                    "Vilka/rozetkani tashqi tomondan tekshiring. Korpusni ochmang.",
                ),
                (
                    "Qurilma ekranida yoki chirog'ida xato belgisi bormi?",
                    "Ko'rinayotgan xato kodi bo'lsa, uni aynan qanday chiqayotganini yozib oling.",
                ),
                (
                    "Qurilmani qayta ishga tushirib ko'rdingizmi?",
                    "Faqat yo'riqnoma ruxsat bersa, elektrdan uzib, bir necha daqiqa kutib qayta yoqing.",
                ),
            ],
        },
    ],
    "plumber": [
        {
            "key": "faucet",
            "label": "🚰 Kran / jo'mrak",
            "keywords": ["kran", "jo'mrak", "jomrak", "krandan", "suv oqyapti"],
            "steps": [
                (
                    "Suv qayeridan chiqayotganini ko'ryapsizmi?",
                    "Suv sizayotgan joyni tashqi tomondan aniqlang va xavfsiz bo'lsa, atrofini quruq tuting.",
                ),
                (
                    "Kran tagidagi ulanishlar bo'shashmaganmi?",
                    "Faqat ko'z bilan tekshiring. Kuch bilan burab ochmang.",
                ),
                (
                    "Suvni vaqtincha to'xtatish kerakmi?",
                    "Agar oqish kuchli bo'lsa va xavfsiz yetib borilsa, asosiy suv kranini yopish mumkin.",
                ),
            ],
        },
        {
            "key": "toilet",
            "label": "🚽 Unitaz",
            "keywords": ["unitaz", "toilet", "bachok", "suv to'xtamay"],
            "steps": [
                (
                    "Suv qayeridan oqayotganini aniqlang.",
                    "Polga yoki devorga zarar bermaslik uchun oqayotgan joyni tashqi tomondan kuzating.",
                ),
                (
                    "Bachokdan suv to'xtamay oqyaptimi?",
                    "Suv kirish krani ko'rinib tursa, faqat tashqi holatini tekshiring.",
                ),
                (
                    "Oqish kuchlimi?",
                    "Kuchli oqish bo'lsa, xavfsiz yetib borilsa suvni vaqtincha to'xtating va usta chaqiring.",
                ),
            ],
        },
        {
            "key": "pipe",
            "label": "🪠 Quvur / suv sizishi",
            "keywords": ["quvur", "truba", "suv siz", "suv tosh", "yorildi"],
            "steps": [
                (
                    "Suv oqishi kuchlimi?",
                    "Katta oqish bo'lsa, xavfsiz bo'lsa asosiy suvni vaqtincha yoping.",
                ),
                (
                    "Suv qayerdan chiqayotganini aniqlash mumkinmi?",
                    "Joyini tashqi tomondan aniqlang va usta uchun rasm tayyorlang.",
                ),
            ],
        },
        {
            "key": "other",
            "label": "🔩 Boshqa santexnika muammosi",
            "keywords": ["rakovina", "dush", "vanna", "sifon"],
            "steps": [
                (
                    "Muammo qayerda ekanini aniqlang.",
                    "Suv sizayotgan yoki ishlamayotgan qismini tashqi tomondan ko'rib chiqing.",
                ),
                (
                    "Rasm yubora olasizmi?",
                    "Muammo joyini tushunarli qilib suratga oling. Keyin usta chaqirish mumkin.",
                ),
            ],
        },
    ],
    "electric": [
        {
            "key": "socket",
            "label": "🔌 Rozetka",
            "keywords": ["rozetka", "razetka", "rozetkam"],
            "steps": [
                (
                    "Rozetkada kuyish hidi, tutun yoki uchqun bormi?",
                    "Shunday belgi bo'lsa, rozetkaga yaqinlashmang va usta chaqiring.",
                ),
                (
                    "Boshqa rozetka ishlayaptimi?",
                    "Xavfsiz bo'lsa, boshqa sog'lom qurilma bilan tekshirish o'rniga muammoni ta'mirlashga urinmang; usta ko'rigini tanlang.",
                ),
            ],
        },
        {
            "key": "light",
            "label": "💡 Chiroq",
            "keywords": ["chiroq", "svet", "lampa", "yorug"],
            "steps": [
                (
                    "Boshqa xonalarda elektr bor-mi?",
                    "Boshqa chiroqlar ishlayotganini masofadan kuzating; ochiq simlarga tegmang.",
                ),
                (
                    "Avtomat o'chganini ko'ryapsizmi?",
                    "Faqat xavfsiz quruq joydan shchitdagi holatni ko'ring. Qopqoqni ochmang.",
                ),
            ],
        },
        {
            "key": "breaker",
            "label": "⚡ Avtomat / tok",
            "keywords": ["avtomat", "tok", "elektr", "svet o'chdi"],
            "steps": [
                (
                    "Tutun, kuygan hid yoki uchqun bormi?",
                    "Bo'lsa, qurilmaga yaqinlashmang va usta chaqiring.",
                ),
                (
                    "Muammo faqat bitta qurilmadami yoki butun xonadami?",
                    "Qaysi joylarda elektr bor-yo'qligini aniqlang. Simlarni ushlamang.",
                ),
            ],
        },
        {
            "key": "other",
            "label": "⚡ Boshqa elektr muammosi",
            "keywords": ["sim", "adapter", "zaryad", "elektr"],
            "steps": [
                (
                    "Kuyish hidi, tutun yoki uchqun yo'qmi?",
                    "Xavfli belgi bo'lsa, yaqinlashmang va usta chaqiring.",
                ),
                (
                    "Muammoni rasmga olish mumkinmi?",
                    "Faqat xavfsiz masofadan rasm oling. Simlarni ochmang yoki kesmang.",
                ),
            ],
        },
    ],
}

REGIONS = [
    "Andijon",
    "Buxoro",
    "Farg'ona",
    "Jizzax",
    "Xorazm",
    "Namangan",
    "Navoiy",
    "Qashqadaryo",
    "Qoraqalpog'iston",
    "Samarqand",
    "Sirdaryo",
    "Surxondaryo",
    "Toshkent viloyati",
    "Toshkent shahri",
]

APOSTROPHES = "ʻʼ’‘`´'"
DISTRICT_WORDS = {"tumani", "tuman", "shahri", "shahar", "shaxri", "shahrida"}

DANGER_WORDS = (
    "gaz hidi",
    "gaz xidi",
    "gaz sizib",
    "gaz chiq",
    "uchqun",
    "tutun",
    "kuyish hidi",
    "kuygan hid",
    "yonish hidi",
    "tok urdi",
    "tok uryapti",
    "tok urayapti",
    "yongin",
    "portla",
    "qisqa tutashuv",
    "tutashuv",
    "suv bosdi",
    "katta suv toshdi",
    "sim erib",
)

SAFETY_NOTE = (
    "⚠️ XAVFSIZLIK\n\n"
    "Bu belgida o'zingiz ta'mirlashga urinmang.\n"
    "Elektr, gaz, tutun, uchqun yoki katta suv oqishi bo'lsa "
    "qurilmaga yaqinlashmang.\n\n"
    "Zarurat bo'lsa:\n"
    "101 — o't o'chirish\n"
    "103 — tez yordam\n"
    "104 — gaz xizmati\n\n"
    "☎️ Usta: "
)


def norm(text: str) -> str:
    text = (text or "").lower()
    for ch in APOSTROPHES:
        text = text.replace(ch, "")
    text = re.sub(r"[^\w\s*]", " ", text)
    return " ".join(text.split())


def norm_district(text: str) -> str:
    return " ".join(
        w for w in norm(text).split() if w not in DISTRICT_WORDS
    )


def detect_danger(text: str) -> bool:
    value = norm(text)
    return any(word in value for word in DANGER_WORDS)


def find_master(region: str, district: str, service: str) -> dict | None:
    want_region = norm(region)
    want_district = norm_district(district)

    best = None
    best_score = -1

    for route in MASTERS:
        try:
            chat_id = int(route.get("chat_id", 0))
        except (TypeError, ValueError):
            continue

        if chat_id == 0:
            continue

        r_region = str(route.get("region", "*"))
        r_district = str(route.get("district", "*"))
        r_service = str(route.get("service", "*")).strip().lower()

        score = 0

        if r_region != "*":
            if norm(r_region) != want_region:
                continue
            score += 2

        if r_district != "*":
            if norm_district(r_district) != want_district:
                continue
            score += 4

        if r_service != "*":
            if r_service != service:
                continue
            score += 1

        if score > best_score:
            best = route
            best_score = score

    if best:
        return best

    if settings.admin_chat_id:
        return {
            "name": "Admin",
            "phone": settings.emergency_phone,
            "chat_id": settings.admin_chat_id,
            "region": "*",
            "district": "*",
            "service": "*",
        }

    return None


def match_problem(service: str, text: str) -> dict | None:
    value = norm(text)

    for problem in PROBLEM_CATALOG[service]:
        for keyword in problem["keywords"]:
            if norm(keyword) in value:
                return problem

    return None


# ============================================================
# 4. TUGMALAR
# ============================================================

MENU, PROBLEM, DIAGNOSIS, NAME, PHONE, REGION, DISTRICT, CONFIRM = range(8)

BACK_TXT = "⬅️ Orqaga"
RESTART_TXT = "🔄 Qayta boshlash"


def nav_buttons(back_to: str | None = None) -> list:
    row = []
    if back_to:
        row.append(Btn(BACK_TXT, callback_data=f"back:{back_to}"))
    row.append(Btn(RESTART_TXT, callback_data="restart"))
    return row


def main_menu() -> Markup:
    rows = [
        [Btn(SERVICES["appliance"]["label"], callback_data="svc:appliance")],
        [Btn(SERVICES["plumber"]["label"], callback_data="svc:plumber")],
        [Btn(SERVICES["electric"]["label"], callback_data="svc:electric")],
    ]
    return Markup(rows)


def problem_menu(service: str) -> Markup:
    rows = []
    for problem in PROBLEM_CATALOG[service]:
        rows.append(
            [Btn(problem["label"], callback_data=f"problem:{problem['key']}")]
        )

    rows.append([Btn("✍️ Muammoni o'zim yozaman", callback_data="problem:free")])
    rows.append(nav_buttons("menu"))
    return Markup(rows)


def diagnosis_menu(step_index: int, total: int) -> Markup:
    rows = [
        [
            Btn("✅ Tekshirdim", callback_data=f"diag:next:{step_index}"),
            Btn("❌ Yordam bermadi", callback_data=f"diag:next:{step_index}"),
        ],
        [Btn("📷 Rasm yuborish", callback_data="photo:start")],
        [Btn("🧑‍🔧 Usta chaqirish", callback_data="call_master")],
        nav_buttons("problem"),
    ]
    return Markup(rows)


def after_diagnosis_menu() -> Markup:
    return Markup(
        [
            [Btn("✅ Muammo hal bo'ldi", callback_data="solved")],
            [Btn("📷 Rasm yuborish", callback_data="photo:start")],
            [Btn("🧑‍🔧 Usta chaqirish", callback_data="call_master")],
            nav_buttons("problem"),
        ]
    )


def photo_menu() -> Markup:
    return Markup(
        [
            [Btn("➡️ Rasm yubormasdan davom etish", callback_data="photo:skip")],
            [Btn("🧑‍🔧 Usta chaqirish", callback_data="call_master")],
            nav_buttons("diagnosis"),
        ]
    )


def name_menu(first_name: str) -> Markup:
    return Markup(
        [
            [Btn(f"👤 {first_name[:30]}", callback_data="name:tg")],
            nav_buttons("diagnosis"),
        ]
    )


def phone_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📱 Raqamimni yuborish", request_contact=True)],
            [KeyboardButton(BACK_TXT), KeyboardButton(RESTART_TXT)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def region_menu() -> Markup:
    rows = []
    row = []

    for index, region in enumerate(REGIONS):
        row.append(Btn(region, callback_data=f"region:{index}"))
        if len(row) == 2:
            rows.append(row)
            row = []

    if row:
        rows.append(row)

    rows.append(nav_buttons("phone"))
    return Markup(rows)


def confirm_menu() -> Markup:
    return Markup(
        [
            [Btn("✅ Ustaga yuborish", callback_data="send_order")],
            [Btn("✏️ Ma'lumotni qayta kiritish", callback_data="back:name")],
            nav_buttons("district"),
        ]
    )


# ============================================================
# 5. YORDAMCHI FUNKSIYALAR
# ============================================================

async def send(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    markup=None,
    html_mode: bool = True,
):
    chat_id = update.effective_chat.id
    return await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=markup,
        parse_mode=ParseMode.HTML if html_mode else None,
    )


def current_problem(context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    return context.user_data.get("problem")


def reset_diagnosis(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["step_index"] = 0


# ============================================================
# 6. BOT HANDLERLARI
# ============================================================

WELCOME = (
    "👋 Salom! Men <b>Jojo Usta</b>.\n\n"
    "Maishiy texnika, santexnika va elektrika bo'yicha "
    "muammoni aniqlashga yordam beraman.\n\n"
    "Avval oddiy va xavfsiz tekshiruvlarni birgalikda ko'ramiz. "
    "Hal bo'lmasa rasm yuborib, usta chaqirishingiz mumkin.\n\n"
    "Kerakli xizmatni tanlang:"
)

HELP_TEXT = (
    "ℹ️ <b>Jojo Usta</b>\n\n"
    "/start — boshidan boshlash\n"
    "/help — yordam\n"
    "/id — Telegram chat ID ni ko'rsatish\n\n"
    "Siz muammoni yozishingiz yoki rasm yuborishingiz mumkin.\n"
    f"Jiddiy holat uchun: {html.escape(settings.emergency_phone)}"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()

    context.user_data.clear()

    await send(
        update,
        context,
        WELCOME,
        main_menu(),
    )
    return MENU


async def pick_service(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    await query.answer()

    service = query.data.split(":", 1)[1]

    if service not in SERVICES:
        return MENU

    context.user_data.clear()
    context.user_data.update(
        service=service,
        photos=[],
        first_problem=None,
        history=[],
        step_index=0,
    )

    text = (
        f"<b>{SERVICES[service]['title']}</b>\n\n"
        "Muammoni tanlang yoki o'zingiz yozing:"
    )

    await send(update, context, text, problem_menu(service))
    return PROBLEM


async def pick_problem(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    await query.answer()

    service = context.user_data["service"]
    key = query.data.split(":", 1)[1]

    problems = PROBLEM_CATALOG[service]
    problem = next((p for p in problems if p["key"] == key), None)

    if key == "free":
        await send(
            update,
            context,
            "✍️ Muammoni oddiy tilda yozing.\n\n"
            "Masalan: “muzlatgichim sovutmayapti” yoki "
            "“kranimdan suv oqyapti”.",
            nav_markup := Markup([nav_buttons("problem")]),
            html_mode=False,
        )
        return DIAGNOSIS

    if not problem:
        return PROBLEM

    context.user_data["problem"] = problem
    context.user_data["first_problem"] = problem["label"]
    reset_diagnosis(context)

    return await show_diagnosis(update, context)


async def show_diagnosis(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    problem = current_problem(context)

    if not problem:
        await send(
            update,
            context,
            "Muammoni tanlang:",
            problem_menu(context.user_data["service"]),
        )
        return PROBLEM

    index = context.user_data.get("step_index", 0)
    steps = problem["steps"]

    if index >= len(steps):
        await send(
            update,
            context,
            "🔎 Oddiy tekshiruvlar tugadi.\n\n"
            "Muammo hal bo'lmagan bo'lsa, muammo joyining "
            "rasmini yuboring yoki usta chaqiring.",
            after_diagnosis_menu(),
        )
        return DIAGNOSIS

    question, advice = steps[index]

    text = (
        f"🔎 <b>Tekshiruv {index + 1}/{len(steps)}</b>\n\n"
        f"❓ {html.escape(question)}\n\n"
        f"💡 {html.escape(advice)}"
    )

    await send(
        update,
        context,
        text,
        diagnosis_menu(index, len(steps)),
    )
    return DIAGNOSIS


async def diagnosis_next(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    await query.answer()

    context.user_data["step_index"] = context.user_data.get("step_index", 0) + 1
    return await show_diagnosis(update, context)


async def chat_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    text = update.message.text.strip()

    if detect_danger(text):
        context.user_data["first_problem"] = text[:500]

        await send(
            update,
            context,
            SAFETY_NOTE + settings.emergency_phone,
            Markup(
                [
                    [Btn("🧑‍🔧 Usta chaqirish", callback_data="call_master")],
                    nav_buttons("menu"),
                ]
            ),
            html_mode=False,
        )
        return DIAGNOSIS

    service = context.user_data.get("service")

    if not service:
        return await start(update, context)

    context.user_data["first_problem"] = text[:500]

    problem = match_problem(service, text)

    if problem:
        context.user_data["problem"] = problem
        reset_diagnosis(context)

        await send(
            update,
            context,
            f"✅ Muammoni tushundim: <b>{html.escape(problem['label'])}</b>\n\n"
            "Avval xavfsiz tekshiruvlardan o'tamiz.",
        )

        return await show_diagnosis(update, context)

    await send(
        update,
        context,
        "Tushundim 👍 Muammo nomini aniqroq tanlash uchun "
        "quyidagi bo'limlardan birini bosing. Men “topilmadi” deb to'xtab qolmayman.",
        problem_menu(service),
    )
    return PROBLEM


async def chat_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    photo = update.message.photo[-1]

    if len(context.user_data.setdefault("photos", [])) >= settings.max_photos:
        await send(
            update,
            context,
            f"📷 Maksimum {settings.max_photos} ta rasm qabul qilinadi.",
            after_diagnosis_menu(),
            html_mode=False,
        )
        return DIAGNOSIS

    context.user_data["photos"].append(photo.file_id)

    caption = (update.message.caption or "").strip()
    if caption:
        context.user_data["first_problem"] = caption[:500]

    await send(
        update,
        context,
        "📷 Rasm qabul qilindi.\n\n"
        "Bu bot rasmni ustaga yuboradi, shuning uchun usta muammoni "
        "joyida ko'rib chiqishi osonlashadi.\n\n"
        "Yana rasm yuborishingiz mumkin yoki usta chaqirishni davom ettiring.",
        after_diagnosis_menu(),
        html_mode=False,
    )
    return DIAGNOSIS


async def photo_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    await query.answer()

    await send(
        update,
        context,
        "📷 Muammo joyining rasmini yuboring.\n\n"
        "Rasmni oddiy foto ko'rinishida yuboring. "
        "Qurilmani xavfsiz masofadan suratga oling.",
        photo_menu(),
        html_mode=False,
    )
    return DIAGNOSIS


async def photo_skip(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    await query.answer()
    return await ask_name(update, context)


async def solved(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    await update.callback_query.answer()

    context.user_data.clear()

    await send(
        update,
        context,
        "🎉 Zo'r! Muammo hal bo'libdi.\n\n"
        "Yana yordam kerak bo'lsa, /start ni bosing.",
        Markup([[Btn("🔄 Yangi so'rov", callback_data="restart")]]),
        html_mode=False,
    )
    return ConversationHandler.END


async def call_master(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    await update.callback_query.answer()
    return await ask_name(update, context)


async def ask_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    user = update.effective_user
    first = user.first_name or "Ismim"

    await send(
        update,
        context,
        "🧑‍🔧 <b>Usta chaqirish</b>\n\n"
        "<b>1/4</b> — Ismingizni yozing yoki pastdagi tugmani bosing:",
        name_menu(first),
    )
    return NAME


async def got_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    name = " ".join(update.message.text.split())

    if not 2 <= len(name) <= 60:
        await send(
            update,
            context,
            "Ism 2–60 belgidan iborat bo'lsin. Qayta yozing:",
            html_mode=False,
        )
        return NAME

    context.user_data["name"] = name
    return await ask_phone(update, context)


async def tg_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    await update.callback_query.answer()

    user = update.effective_user
    context.user_data["name"] = (user.full_name or "Mijoz")[:60]

    return await ask_phone(update, context)


async def ask_phone(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    await send(
        update,
        context,
        "<b>2/4</b> — Telefon raqamingizni yuboring.\n\n"
        "“📱 Raqamimni yuborish” tugmasini bosing yoki "
        "raqamingizni yozing.",
        phone_menu(),
    )
    return PHONE


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw or "")

    if len(digits) == 9:
        return "+998" + digits

    if len(digits) == 12 and digits.startswith("998"):
        return "+" + digits

    return None


async def got_contact(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    phone = normalize_phone(update.message.contact.phone_number)

    if not phone:
        await send(
            update,
            context,
            "Telefon raqami noto'g'ri ko'rinyapti. Qayta yuboring.",
            phone_menu(),
            html_mode=False,
        )
        return PHONE

    return await phone_ok(update, context, phone)


async def got_phone_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    text = update.message.text.strip()

    if text == BACK_TXT:
        return await ask_name(update, context)

    if text == RESTART_TXT:
        return await start(update, context)

    phone = normalize_phone(text)

    if not phone:
        await send(
            update,
            context,
            "❗ Masalan: 90 123 45 67 yoki +998901234567",
            phone_menu(),
            html_mode=False,
        )
        return PHONE

    return await phone_ok(update, context, phone)


async def phone_ok(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    phone: str,
) -> int:
    context.user_data["phone"] = phone

    await send(
        update,
        context,
        f"✅ Raqam qabul qilindi: <b>{html.escape(phone)}</b>",
        ReplyKeyboardRemove(),
    )

    return await ask_region(update, context)


async def ask_region(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    await send(
        update,
        context,
        "<b>3/4</b> — Viloyatingizni tanlang:",
        region_menu(),
    )
    return REGION


async def pick_region(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    await query.answer()

    index = int(query.data.split(":", 1)[1])

    if not 0 <= index < len(REGIONS):
        return REGION

    context.user_data["region"] = REGIONS[index]
    return await ask_district(update, context)


async def ask_district(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    region = html.escape(context.user_data.get("region", ""))

    await send(
        update,
        context,
        f"<b>4/4</b> — <b>{region}</b>\n\n"
        "Tuman yoki shahar nomini yozing.\n"
        "Masalan: Asaka",
        Markup([nav_buttons("region")]),
    )
    return DISTRICT


async def got_district(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    district = " ".join(update.message.text.split())

    if not 2 <= len(district) <= 60:
        await send(
            update,
            context,
            "Tuman/shahar nomini 2–60 belgida yozing.",
            html_mode=False,
        )
        return DISTRICT

    context.user_data["district"] = district
    return await show_confirm(update, context)


async def show_confirm(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    ud = context.user_data
    service = ud.get("service", "")
    problem = ud.get("first_problem", "Ko'rsatilmagan")

    text = (
        "📋 <b>Zakazni tekshiring</b>\n\n"
        f"🛠 Xizmat: {html.escape(SERVICES[service]['title'])}\n"
        f"❗ Muammo: {html.escape(problem[:500])}\n"
        f"👤 Ism: {html.escape(ud['name'])}\n"
        f"📞 Telefon: {html.escape(ud['phone'])}\n"
        f"📍 Hudud: {html.escape(ud['region'])}, {html.escape(ud['district'])}\n"
        f"📷 Rasmlar: {len(ud.get('photos', []))} ta\n\n"
        "Tasdiqlasangiz, mos ustaga yuboriladi."
    )

    await send(update, context, text, confirm_menu())
    return CONFIRM


async def send_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    await query.answer()

    ud = context.user_data

    required = ("service", "name", "phone", "region", "district")
    if not all(key in ud for key in required):
        return await start(update, context)

    master = find_master(
        ud["region"],
        ud["district"],
        ud["service"],
    )

    if not master:
        await send(
            update,
            context,
            "😔 Bu hudud va xizmat uchun hali Telegram ustasi biriktirilmagan.\n\n"
            f"☎️ Bog'lanish: {settings.emergency_phone}",
            Markup([[Btn("🔄 Yangi so'rov", callback_data="restart")]]),
            html_mode=False,
        )
        return ConversationHandler.END

    order_id = time.strftime("%m%d-%H%M") + "-" + secrets.token_hex(1).upper()
    user = update.effective_user

    username = f"@{user.username}" if user.username else "username yo'q"

    problem_text = str(ud.get("first_problem", "Ko'rsatilmagan"))[:800]
    master_name = str(master.get("name", "Usta"))
    master_phone = str(master.get("phone", "Noma'lum"))

    order_text = (
        f"🆕 <b>Yangi zakaz #{order_id}</b>\n\n"
        f"🛠 Xizmat: <b>{html.escape(SERVICES[ud['service']]['title'])}</b>\n"
        f"❗ Muammo: {html.escape(problem_text)}\n"
        f"👤 Ism: {html.escape(ud['name'])}\n"
        f"📞 Telefon: <b>{html.escape(ud['phone'])}</b>\n"
        f"📍 Hudud: {html.escape(ud['region'])}, {html.escape(ud['district'])}\n"
        f"💬 Telegram: {html.escape(username)}\n"
        f"🆔 Mijoz ID: <code>{user.id}</code>\n"
        f"📷 Rasmlar: {len(ud.get('photos', []))} ta\n\n"
        f"🧑‍🔧 Biriktirilgan usta: {html.escape(master_name)}\n"
        f"☎️ Usta raqami: {html.escape(master_phone)}"
    )

    try:
        await context.bot.send_message(
            chat_id=int(master["chat_id"]),
            text=order_text,
            parse_mode=ParseMode.HTML,
        )

        photos = ud.get("photos", [])

        if len(photos) == 1:
            await context.bot.send_photo(
                chat_id=int(master["chat_id"]),
                photo=photos[0],
                caption=f"📷 Zakaz #{order_id}",
            )
        elif photos:
            media = [
                InputMediaPhoto(
                    media=photo_id,
                    caption=f"📷 Zakaz #{order_id}" if index == 0 else None,
                )
                for index, photo_id in enumerate(photos[: settings.max_photos])
            ]
            await context.bot.send_media_group(
                chat_id=int(master["chat_id"]),
                media=media,
            )

    except TelegramError:
        logger.exception(
            "Zakazni yuborib bo'lmadi. chat_id=%s",
            master.get("chat_id"),
        )

        await send(
            update,
            context,
            "⚠️ Zakaz yuborishda xatolik bo'ldi.\n\n"
            f"☎️ Iltimos, bog'laning: {settings.emergency_phone}",
            Markup([[Btn("🔄 Yangi so'rov", callback_data="restart")]]),
            html_mode=False,
        )
        return CONFIRM

    context.user_data.clear()

    await send(
        update,
        context,
        f"✅ <b>Zakaz #{order_id} yuborildi!</b>\n\n"
        "Usta siz bilan bog'lanadi.",
        Markup([[Btn("🔄 Yangi so'rov", callback_data="restart")]]),
    )

    return ConversationHandler.END


# ============================================================
# 7. ORQAGA / RESTART
# ============================================================

async def go_back(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    await query.answer()

    target = query.data.split(":", 1)[1]

    if target == "menu":
        return await start(update, context)

    if target == "problem":
        service = context.user_data.get("service")
        if not service:
            return await start(update, context)

        await send(
            update,
            context,
            "Muammo turini tanlang:",
            problem_menu(service),
        )
        return PROBLEM

    if target == "diagnosis":
        return await show_diagnosis(update, context)

    if target == "name":
        return await ask_name(update, context)

    if target == "phone":
        return await ask_phone(update, context)

    if target == "region":
        return await ask_region(update, context)

    if target == "district":
        return await ask_district(update, context)

    return MENU


async def help_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await send(update, context, HELP_TEXT)


async def id_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await send(
        update,
        context,
        f"Telegram Chat ID: <code>{update.effective_chat.id}</code>\n\n"
        "Agar siz usta bo'lsangiz, shu ID ni MASTERS ro'yxatiga yozish kerak.",
    )


async def on_error(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    logger.error("Kutilmagan xatolik", exc_info=context.error)

    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=(
                    "⚠️ Kutilmagan xatolik yuz berdi.\n"
                    "Iltimos, /start ni bosib qayta urinib ko'ring."
                ),
            )
        except TelegramError:
            pass


async def unexpected(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    await send(
        update,
        context,
        "Iltimos, menyudagi tugmalardan foydalaning yoki so'ralgan "
        "ma'lumotni yuboring.\n\n/start — boshidan boshlash",
        Markup([[Btn("🔄 Qayta boshlash", callback_data="restart")]]),
        html_mode=False,
    )


async def post_init(app) -> None:
    await app.bot.set_my_commands(
        [
            ("start", "Boshlash / qayta boshlash"),
            ("help", "Yordam"),
            ("id", "Chat ID"),
        ]
    )


# ============================================================
# 8. ISHGA TUSHIRISH
# ============================================================

def main() -> None:
    app = (
        ApplicationBuilder()
        .token(settings.bot_token)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .post_init(post_init)
        .build()
    )

    private = filters.ChatType.PRIVATE
    text_msg = filters.TEXT & ~filters.COMMAND & private

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start, filters=private),
            CallbackQueryHandler(start, pattern=r"^restart$"),
        ],
        states={
            MENU: [
                CallbackQueryHandler(pick_service, pattern=r"^svc:")
            ],
            PROBLEM: [
                CallbackQueryHandler(pick_problem, pattern=r"^problem:")
            ],
            DIAGNOSIS: [
                CallbackQueryHandler(diagnosis_next, pattern=r"^diag:next:"),
                CallbackQueryHandler(photo_start, pattern=r"^photo:start$"),
                CallbackQueryHandler(photo_skip, pattern=r"^photo:skip$"),
                CallbackQueryHandler(call_master, pattern=r"^call_master$"),
                CallbackQueryHandler(solved, pattern=r"^solved$"),
                MessageHandler(filters.PHOTO & private, chat_photo),
                MessageHandler(text_msg, chat_text),
            ],
            NAME: [
                CallbackQueryHandler(tg_name, pattern=r"^name:tg$"),
                MessageHandler(text_msg, got_name),
            ],
            PHONE: [
                MessageHandler(filters.CONTACT & private, got_contact),
                MessageHandler(text_msg, got_phone_text),
            ],
            REGION: [
                CallbackQueryHandler(pick_region, pattern=r"^region:\d+$")
            ],
            DISTRICT: [
                MessageHandler(text_msg, got_district)
            ],
            CONFIRM: [
                CallbackQueryHandler(send_order, pattern=r"^send_order$")
            ],
        },
        fallbacks=[
            CommandHandler(["start", "cancel"], start, filters=private),
            CallbackQueryHandler(start, pattern=r"^restart$"),
            CallbackQueryHandler(go_back, pattern=r"^back:"),
            MessageHandler(private & ~filters.COMMAND, unexpected),
        ],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("help", help_cmd, filters=private))
    app.add_handler(CommandHandler("id", id_cmd, filters=private))
    app.add_handler(conv)
    app.add_error_handler(on_error)

    logger.info("Jojo Usta ishga tushdi. To'xtatish: Ctrl+C")
    app.run_polling()


if __name__ == "__main__":
    main()

