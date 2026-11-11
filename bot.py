#!/usr/bin/env python3
"""یادآور قرص نیایش.

هر اجرا تمام می‌شود و خاموش می‌گردد. گیت‌هاب اکشنز این فایل را با زمان‌بندی
بیدار می‌کند. توکن فقط از متغیر محیطی BOT_TOKEN خوانده می‌شود.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

TZ = ZoneInfo("Asia/Tehran")
ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data.json"
WINDOW = timedelta(minutes=30)
FOLLOWUP_AFTER = timedelta(minutes=15)
SNOOZE_FOR = timedelta(minutes=10)
MAX_FOLLOWUPS = 2
MAX_SNOOZES = 8
MAX_REMINDERS = 30
HISTORY_DAYS = 7
NAME_LIMIT = 40

FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
EN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

MONTHS = [
    "",
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
]

# فقط دستهٔ کلی دارو، نه نام تجاری. ریپوی عمومی نباید اسم دقیق دارو را در کد داشته باشد.
SYMBOL_RULES = [
    (("فشار",), "❤️", "یعنی مراقب فشار و قلبت است"),
    (("قلب",), "💓", "یعنی برای قلبت است"),
    (("قند", "دیابت"), "🩸", "یعنی یادآور قند است"),
    (("ویتامین",), "🌟", "یعنی ویتامین است؛ یک نور کوچک برای بدنت"),
    (("آنتی", "چرک"), "🛡️", "یعنی محافظ بدنت است"),
    (("مسکن",), "🌿", "یعنی برای آرام شدن درد است"),
    (("درد",), "🌿", "یعنی برای آرام شدن درد است"),
    (("خواب", "آرامبخش"), "🌙", "یعنی برای خواب آرام است"),
    (("تیروئید",), "🦋", "یعنی مربوط به تیروئید است"),
    (("کلسیم", "استخوان"), "🦴", "یعنی برای استخوان‌هاست"),
    (("آهن",), "🔩", "یعنی برای آهن بدن است"),
    (("معده", "گوارش"), "🫖", "یعنی برای معده است"),
    (("چشم",), "👁️", "یعنی برای چشم‌هاست"),
    (("حساسیت", "آلرژی"), "🌸", "یعنی برای حساسیت است"),
]
DEFAULT_SYMBOL = ("💊", "یعنی یک یادآور دارو است")

INITIAL_LINES = [
    "نیایشم، زودتر خوب شو. یاسین خیلی خیلی دوستت داره.",
    "نیایش جانم، این یکی را بخور. یاسین کنارت است و هوات را دارد.",
    "یک قدم کوچک تا حالِ بهتر. یاسین خیلی خیلی دوستت داره.",
    "نیایش عزیزم، سلامتی‌ات برای یاسین از همه‌چیز مهم‌تر است.",
    "خوب شدن تو، آرامِ دل یاسین است.",
    "نیایشم، هر بار که این را می‌خوری به خودت لطف می‌کنی. یاسین بهت افتخار می‌کند.",
]
FOLLOWUP_LINES = [
    "اگر خوردی بگو، اگر نه همین حالا بخور. یاسین نگران توست و خیلی دوستت دارد.",
    "این آخرین یادآوری این نوبت است. نیایشم، زودتر خوب شو؛ یاسین خیلی خیلی دوستت داره.",
]
SNOOZE_LINES = [
    "نیایشم، همان ده دقیقه تمام شد. یاسین هنوز اینجاست کنارت.",
    "برگشتم نیایش جانم. حالا وقتش است. یاسین خیلی خیلی دوستت داره.",
]
TAKEN_LINES = [
    "نیایشم، زودتر خوب شو. یاسین خیلی خیلی دوستت داره.",
    "ثبت شد قشنگم. یاسین هوات را دارد و کنارت است.",
    "آرامِ دل یاسین همین سلامتی توست.",
]

ADD_RE = re.compile(
    r"^([0-9۰-۹٠-٩]{1,2})\s*[:：]\s*([0-9۰-۹٠-٩]{2})\s+(.+)$"
)
INTERVAL_RE = re.compile(
    r"^([0-9۰-۹٠-٩]{1,2})\s*[:：]\s*([0-9۰-۹٠-٩]{2})\s+([0-9۰-۹٠-٩]{1,2})\s+(.+)$"
)
DEL_RE = re.compile(r"^([0-9۰-۹٠-٩]+)$")
TOKEN_LIKE_RE = re.compile(r"\d{6,}\s*:\s*[A-Za-z0-9_-]{20,}")
GREETINGS = {"سلام", "سلم", "درود", "هی", "hello", "hi"}

COMMANDS = [
    {"command": "start", "description": "خوش‌آمد و راهنما"},
    {"command": "add", "description": "آخرین ساعت و فاصله: /add 19:30 8 اسم"},
    {"command": "list", "description": "فهرست یادآورها"},
    {"command": "del", "description": "حذف با شماره: /del 1"},
    {"command": "history", "description": "دفعاتی که خوردم زده شده"},
    {"command": "test", "description": "امتحان صدای اعلان گوشی"},
]


class FatalTokenError(Exception):
    """توکن را تلگرام نپذیرفت. متن خطا عمداً خالی است تا توکن در لاگ نیاید."""


class TelegramError(Exception):
    def __init__(self, method: str, description: str, status: int = 0):
        super().__init__(description)
        self.method = method
        self.description = description
        self.status = status


def fa_digits(value: object) -> str:
    return str(value).translate(FA_DIGITS)


def en_digits(value: object) -> str:
    return str(value).translate(EN_DIGITS)


def norm_text(value: str) -> str:
    text = en_digits(value)
    text = (
        text.replace("ي", "ی")
        .replace("ك", "ک")
        .replace("ۀ", "ه")
        .replace("ة", "ه")
        .replace("\u200c", "")
    )
    return re.sub(r"\s+", " ", text).strip().lower()


def html_escape(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def fa_clock(hhmm: str) -> str:
    hour, minute = hhmm.split(":")
    return fa_digits(f"{int(hour):02d}:{int(minute):02d}")


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_days_in_month = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        365 * gy
        + (gy2 + 3) // 4
        - (gy2 + 99) // 100
        + (gy2 + 399) // 400
        - 80
        + gd
        + g_days_in_month[gm - 1]
    )
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        j_month = 1 + days // 31
        j_day = 1 + (days % 31)
    else:
        j_month = 7 + (days - 186) // 30
        j_day = 1 + ((days - 186) % 30)
    return jy, j_month, j_day


def fa_day(day: date) -> str:
    jy, jm, jd = gregorian_to_jalali(day.year, day.month, day.day)
    return f"{fa_digits(jd)} {MONTHS[jm]} {fa_digits(jy)}"


def pick_line(lines: list[str], *parts: object) -> str:
    key = "|".join(str(part) for part in parts).encode("utf-8")
    return lines[sum(key) % len(lines)]


def match_symbol(name: str) -> tuple[str, str]:
    folded = norm_text(name)
    for words, emoji, note in SYMBOL_RULES:
        if any(word in folded for word in words):
            return emoji, note
    return DEFAULT_SYMBOL


def blank_data() -> dict:
    return {
        "intake_log": [],
        "last_update_id": 0,
        "reminders": [],
        "sent_log": {},
    }


def blank_entry() -> dict:
    return {
        "acked": False,
        "followups": 0,
        "initial_sent": False,
        "last_sent_at": None,
        "snooze_until": None,
        "snoozes": 0,
    }


def dump_data(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_data(path: Path) -> dict:
    if not path.exists():
        return blank_data()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("data.json is not valid JSON", file=sys.stderr)
        sys.exit(1)
    if not isinstance(raw, dict):
        print("data.json has an unexpected shape", file=sys.stderr)
        sys.exit(1)
    data = blank_data()
    for key in ("reminders", "sent_log", "intake_log"):
        if not isinstance(raw.get(key), type(data[key])):
            print("data.json has an unexpected shape", file=sys.stderr)
            sys.exit(1)
        data[key] = raw[key]
    last = raw.get("last_update_id", 0)
    if isinstance(last, int) and not isinstance(last, bool):
        data["last_update_id"] = last
    return data


def save_data(path: Path, text: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def prune(data: dict, today: date) -> None:
    keep_sent = today - timedelta(days=14)
    keep_intake = today - timedelta(days=60)
    sent_clean = {}
    for key, entry in data["sent_log"].items():
        slot_text = str(key).split(":", 1)[-1]
        try:
            day = date.fromisoformat(slot_text[:10])
        except ValueError:
            continue
        if day >= keep_sent and isinstance(entry, dict):
            sent_clean[key] = entry
    data["sent_log"] = sent_clean
    intake_clean = []
    for item in data["intake_log"]:
        if not isinstance(item, dict):
            continue
        try:
            day = date.fromisoformat(str(item.get("day")))
        except ValueError:
            continue
        if day >= keep_intake:
            intake_clean.append(item)
    data["intake_log"] = intake_clean


def parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ)
    return parsed.astimezone(TZ)


def scheduled_dt(day: date, hhmm: str) -> datetime:
    hour, minute = (int(part) for part in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ)


def valid_clock(value: object) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}:\d{2}", value):
        return False
    hour, minute = (int(part) for part in value.split(":"))
    return hour <= 23 and minute <= 59


def valid_reminder(reminder: object) -> bool:
    if not isinstance(reminder, dict):
        return False
    if isinstance(reminder.get("id"), bool) or isinstance(reminder.get("chat_id"), bool):
        return False
    return (
        isinstance(reminder.get("id"), int)
        and isinstance(reminder.get("chat_id"), int)
        and valid_clock(reminder.get("time"))
        and isinstance(reminder.get("name"), str)
        and isinstance(reminder.get("emoji"), str)
    )


def chat_reminders(data: dict, chat_id: int) -> list[dict]:
    items = [
        reminder
        for reminder in data["reminders"]
        if valid_reminder(reminder) and reminder["chat_id"] == chat_id
    ]
    items.sort(key=lambda reminder: (reminder["time"], reminder["id"]))
    return items


def find_reminder(data: dict, chat_id: int, reminder_id: int) -> dict | None:
    for reminder in data["reminders"]:
        if (
            valid_reminder(reminder)
            and reminder["chat_id"] == chat_id
            and reminder["id"] == reminder_id
        ):
            return reminder
    return None


def entry_key(reminder_id: int, day: date) -> str:
    return f"{reminder_id}:{day.isoformat()}"


def ensure_slot(data: dict, reminder_id: int, slot: str) -> dict:
    key = f"{reminder_id}:{slot}"
    entry = data["sent_log"].get(key)
    if not isinstance(entry, dict):
        entry = blank_entry()
        data["sent_log"][key] = entry
    return entry


def ensure_entry(data: dict, reminder_id: int, day: date) -> dict:
    return ensure_slot(data, reminder_id, day.isoformat())


def slot_stamp(slot: date | str) -> str:
    if isinstance(slot, date):
        return slot.strftime("%Y%m%d")
    return str(slot).replace("-", "").replace("T", "").replace(":", "")


def keyboard(reminder_id: int, slot: date | str) -> dict:
    stamp = slot_stamp(slot)
    return {
        "inline_keyboard": [[
            {"text": "خوردم ✅", "callback_data": f"t:{reminder_id}:{stamp}"},
            {"text": "۱۰ دقیقه بعد ⏰", "callback_data": f"z:{reminder_id}:{stamp}"},
        ]]
    }


def interval_hours(reminder: dict) -> int | None:
    value = reminder.get("every_hours")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if 1 <= value <= 24:
        return value
    return None


def anchor_dt(reminder: dict) -> datetime | None:
    raw = reminder.get("last_taken_at")
    if not isinstance(raw, str):
        return None
    try:
        return parse_dt(raw)
    except ValueError:
        return None


def upcoming_slot(reminder: dict, now: datetime) -> datetime | None:
    hours = interval_hours(reminder)
    anchor = anchor_dt(reminder)
    if hours is None or anchor is None:
        return None
    step = timedelta(hours=hours)
    slot = anchor + step
    for _ in range(60):
        if slot + WINDOW >= now:
            return slot
        slot += step
    return slot


def slot_label(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M")


def describe_reminder(reminder: dict, now: datetime) -> str:
    name = f"{reminder['emoji']} {html_escape(reminder['name'])}"
    hours = interval_hours(reminder)
    anchor = anchor_dt(reminder)
    if hours and anchor:
        nxt = upcoming_slot(reminder, now)
        last = fa_digits(anchor.strftime("%H:%M"))
        if nxt is None:
            nxt_text = "—"
        else:
            nxt_text = fa_digits(nxt.strftime("%H:%M"))
            if nxt.date() != now.date():
                nxt_text += f" {fa_day(nxt.date())}"
        return (
            f"{name}\n"
            f"هر {fa_digits(hours)} ساعت — آخرین بار {last} — نوبت بعدی {nxt_text}"
        )
    return f"{name} — هر روز ساعت {fa_clock(reminder['time'])}"


def reminder_message(reminder: dict, kind: str, now: datetime, followup_no: int = 1) -> str:
    title = {
        "initial": "⏰ وقت دارو شد نیایش جانم",
        "followup": "🔔 نیایش جانم، هنوز این دارو مانده",
        "snooze": "⏰ نیایش جانم، ده دقیقه‌ات تمام شد",
    }[kind]
    if kind == "initial":
        love = pick_line(INITIAL_LINES, reminder["id"], now.date().isoformat(), kind)
    elif kind == "snooze":
        love = pick_line(SNOOZE_LINES, reminder["id"], now.date().isoformat(), kind)
    else:
        love = FOLLOWUP_LINES[0 if followup_no <= 1 else 1]
    return (
        f"{title}\n"
        f"{describe_reminder(reminder, now)}\n\n"
        f"{html_escape(love)}\n\n"
        "دکمهٔ «خوردم» را بزن تا خیالم راحت شود."
    )


def schedule_sentence(now: datetime, hhmm: str) -> str:
    scheduled = scheduled_dt(now.date(), hhmm)
    delta = now - scheduled
    clock = fa_clock(hhmm)
    if timedelta(0) <= delta <= WINDOW:
        return (
            f"ساعتش همین حوالی است. چند لحظهٔ دیگر امروز هم می‌گویم، "
            f"و بعد هر روز ساعت {clock}."
        )
    if now < scheduled:
        return f"از امروز، هر روز ساعت {clock} می‌گویم."
    return f"ساعت امروز گذشته است. از فردا هر روز ساعت {clock} می‌گویم."


def help_text() -> str:
    legend = [
        "❤️ فشار و قلب",
        "🩸 قند",
        "🌟 ویتامین",
        "🛡️ آنتی‌بیوتیک",
        "🌿 درد و مسکن",
        "🌙 خواب",
        "🦋 تیروئید",
        "🦴 کلسیم",
        "🔩 آهن",
        "🫖 معده",
        "👁️ چشم",
        "🌸 حساسیت",
        "💊 بقیهٔ داروها",
    ]
    lines = [
        "سلام نیایش جانم 💛",
        "من اینجام که وقت دارو یادت نرود. یاسین خیلی خیلی دوستت داره و می‌خواهد زودتر خوب شوی.",
        "",
        "برای دارویی که هر چند ساعت یک بار است، ساعت آخرین مصرف و فاصله را بفرست.",
        "من نوبت بعدی را حساب می‌کنم و سر همان وقت یادت می‌اندازم.",
        "",
        "دستورها:",
        "/add 19:30 8 آموکسی",
        "یعنی آخرین بار ۱۹:۳۰ خورده و هر ۸ ساعت دوباره.",
        "/add 08:00 قرص صبح",
        "یعنی هر روز همان ساعت.",
        "/list",
        "فهرست، با دکمهٔ پاک کردن",
        "/history",
        "/test",
        "",
        "وقتی یادآوری برسد دو دکمه می‌آید: «خوردم ✅» و «۱۰ دقیقه بعد ⏰».",
        "اگر تا ۱۵ دقیقه «خوردم» را نزنی، آرام دوباره می‌گویم؛ حداکثر دو بار.",
        "",
        "نماد داروها:",
        *legend,
        "",
        "برای زنگ روی آیفون، اعلان تلگرام و صدا و «حساس به زمان» را روشن کن و یک بار /test بزن.",
        "کلید سایلنت کنار گوشی اگر نارنجی باشد، آیفون فقط می‌لرزد و صدای اعلان را قطع می‌کند.",
        "من نمی‌توانم داخل برنامهٔ ساعت آیفون آلارم بسازم؛ زنگ از خودِ اعلان تلگرام می‌آید.",
        "",
        "یاسین کنارت است. زودتر خوب شو نیایشم.",
    ]
    return "\n".join(lines)


def usage_text() -> str:
    return (
        "این را درست نفهمیدم نیایش جانم.\n"
        "برای داروی ساعتی این را بفرست:\n"
        "/add 19:30 8 آموکسی\n"
        "اول ساعت آخرین مصرف، بعد هر چند ساعت، بعد اسم.\n"
        "اگر هر روز یک ساعت ثابت است:\n"
        "/add 08:00 قرص صبح\n"
        "/list دارو را با دکمه پاک می‌کند.\n"
        "عدد فارسی هم اشکالی ندارد."
    )


def parse_command(text: str) -> tuple[str, str]:
    stripped = text.strip()
    if not stripped:
        return "", ""
    head, _, rest = stripped.partition(" ")
    if not head.startswith("/"):
        return "", stripped
    name = head[1:].split("@", 1)[0].lower()
    return name, rest.strip()


def parse_clock(hour_text: str, minute_text: str) -> str | None:
    try:
        hour = int(en_digits(hour_text))
        minute = int(en_digits(minute_text))
    except ValueError:
        return None
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def clean_name(name: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", name).strip()
    if not cleaned or TOKEN_LIKE_RE.search(cleaned) or len(cleaned) > NAME_LIMIT:
        return None
    return cleaned


def next_reminder_id(data: dict) -> int:
    ids = [
        reminder["id"]
        for reminder in data["reminders"]
        if valid_reminder(reminder)
    ]
    return max(ids, default=0) + 1


def already_logged(data: dict, chat_id: int, reminder_id: int, day_iso: str) -> bool:
    for item in data["intake_log"]:
        if not isinstance(item, dict):
            continue
        if (
            item.get("chat_id") == chat_id
            and item.get("reminder_id") == reminder_id
            and item.get("day") == day_iso
        ):
            return True
    return False


def handle_message(data: dict, chat_id: int, text: str, now: datetime) -> dict:
    command, rest = parse_command(text)
    if command in {"start", "help"}:
        return {"text": help_text()}
    if command == "":
        folded = norm_text(text)
        if folded in GREETINGS or folded.startswith("سلام"):
            return {
                "text": (
                    "سلام نیایش جانم 💛\n"
                    "یاسین خیلی خیلی دوستت داره و می‌خواهد زودتر خوب شوی.\n"
                    "برای راهنما /start را بزن."
                )
            }
        if INTERVAL_RE.match(text.strip()) or ADD_RE.match(text.strip()):
            command, rest = "add", text.strip()
        else:
            return {"text": usage_text()}
    if command == "add":
        return add_reminder(data, chat_id, rest, now)
    if command == "list":
        return list_reply(data, chat_id, now)
    if command == "del":
        return delete_reminder(data, chat_id, rest)
    if command == "history":
        return {"text": history_text(data, chat_id, now.date())}
    if command == "test":
        return {
            "text": (
                "🔔 این یک زنگ آزمایشی است نیایش جانم\n\n"
                "اگر صدای گوشی را شنیدی، اعلان‌ها درست است.\n"
                "نیایشم، زودتر خوب شو. یاسین خیلی خیلی دوستت داره.\n\n"
                "دکمه‌ها را هم می‌توانی امتحان کنی. این آزمایش در فهرست داروها ثبت نمی‌شود."
            ),
            "markup": keyboard(0, now.date()),
        }
    return {"text": usage_text()}


def reject_name(raw_name: str) -> str | None:
    if TOKEN_LIKE_RE.search(raw_name):
        return (
            "این نوشته را ذخیره نمی‌کنم نیایش جانم.\n"
            "فقط ساعت و یک اسم کوتاه بفرست. مثلاً:\n"
            "/add 19:30 8 آموکسی"
        )
    name = clean_name(raw_name)
    if name is None:
        return (
            "یک اسم کوتاه برای دارو بگذار نیایش جانم. مثلاً «آموکسی».\n"
            "اسم خیلی طولانی را ذخیره نمی‌کنم."
        )
    return None


def remembered_clock(now: datetime, hhmm: str) -> datetime:
    candidate = scheduled_dt(now.date(), hhmm)
    if candidate > now + timedelta(minutes=1):
        candidate = scheduled_dt(now.date() - timedelta(days=1), hhmm)
    return candidate


def add_reminder(data: dict, chat_id: int, rest: str, now: datetime) -> dict:
    interval_match = INTERVAL_RE.match(rest.strip())
    if interval_match is not None:
        return add_interval(data, chat_id, interval_match, now)
    match = ADD_RE.match(rest.strip())
    if match is None:
        return {
            "text": (
                "نیایش جانم، یکی از این دو را بفرست:\n"
                "/add 19:30 8 آموکسی\n"
                "آخرین بار ۱۹:۳۰ خورده و هر ۸ ساعت یادت می‌اندازم.\n\n"
                "/add 08:00 قرص صبح\n"
                "هر روز همان ساعت. عدد فارسی هم قبول است."
            )
        }
    hhmm = parse_clock(match.group(1), match.group(2))
    if hhmm is None:
        return {
            "text": (
                "این ساعت درست نیست نیایش جانم.\n"
                "ساعت را از ۰۰:۰۰ تا ۲۳:۵۹ بنویس. مثلاً:\n"
                "/add 19:30 8 آموکسی"
            )
        }
    problem = reject_name(match.group(3))
    if problem:
        return {"text": problem}
    name = clean_name(match.group(3))
    assert name is not None
    owned = chat_reminders(data, chat_id)
    for reminder in owned:
        if (
            not interval_hours(reminder)
            and reminder["time"] == hhmm
            and norm_text(reminder["name"]) == norm_text(name)
        ):
            return {
                "text": (
                    f"این را قبلاً داری نیایش جانم.\n"
                    f"{describe_reminder(reminder, now)}"
                )
            }
    if len(owned) >= MAX_REMINDERS:
        return {
            "text": (
                "به سقف یادآورها رسیدیم نیایش جانم.\n"
                "/list را بزن و با دکمه یکی را پاک کن."
            )
        }
    emoji, note = match_symbol(name)
    data["reminders"].append(
        {
            "chat_id": chat_id,
            "emoji": emoji,
            "id": next_reminder_id(data),
            "name": name,
            "time": hhmm,
        }
    )
    return {
        "text": (
            "ثبت شد نیایش جانم ✅\n\n"
            f"{emoji} {html_escape(name)}\n"
            f"{note}.\n"
            f"{schedule_sentence(now, hhmm)}\n\n"
            "نیایشم، زودتر خوب شو. یاسین خیلی خیلی دوستت داره 💛"
        )
    }


def add_interval(data: dict, chat_id: int, match: re.Match[str], now: datetime) -> dict:
    hhmm = parse_clock(match.group(1), match.group(2))
    if hhmm is None:
        return {
            "text": (
                "این ساعت درست نیست نیایش جانم.\n"
                "مثلاً: /add 19:30 8 آموکسی"
            )
        }
    try:
        hours = int(en_digits(match.group(3)))
    except ValueError:
        hours = 0
    if hours < 1 or hours > 24:
        return {
            "text": (
                "فاصله را از ۱ تا ۲۴ ساعت بنویس نیایش جانم.\n"
                "مثلاً هر ۸ ساعت: /add 19:30 8 آموکسی"
            )
        }
    problem = reject_name(match.group(4))
    if problem:
        return {"text": problem}
    name = clean_name(match.group(4))
    assert name is not None
    anchor = remembered_clock(now, hhmm)
    owned = chat_reminders(data, chat_id)
    for reminder in owned:
        if norm_text(reminder["name"]) == norm_text(name) and interval_hours(reminder):
            reminder["every_hours"] = hours
            reminder["last_taken_at"] = anchor.isoformat()
            reminder["time"] = hhmm
            return {
                "text": (
                    "به‌روز شد نیایش جانم ✅\n\n"
                    f"{describe_reminder(reminder, now)}\n\n"
                    "از همین آخرین بار، هر "
                    f"{fa_digits(hours)} ساعت یادت می‌اندازم."
                )
            }
    if len(owned) >= MAX_REMINDERS:
        return {
            "text": (
                "به سقف یادآورها رسیدیم نیایش جانم.\n"
                "/list را بزن و با دکمه یکی را پاک کن."
            )
        }
    emoji, note = match_symbol(name)
    reminder = {
        "chat_id": chat_id,
        "emoji": emoji,
        "every_hours": hours,
        "id": next_reminder_id(data),
        "last_taken_at": anchor.isoformat(),
        "name": name,
        "time": hhmm,
    }
    data["reminders"].append(reminder)
    return {
        "text": (
            "ثبت شد نیایش جانم ✅\n\n"
            f"{describe_reminder(reminder, now)}\n"
            f"{note}.\n\n"
            "هر بار که خوردی دکمهٔ «خوردم» را بزن تا آخرین ساعت عوض شود.\n"
            "نیایشم، زودتر خوب شو. یاسین خیلی خیلی دوستت داره 💛"
        )
    }


def list_reply(data: dict, chat_id: int, now: datetime) -> dict:
    items = chat_reminders(data, chat_id)
    if not items:
        return {
            "text": (
                "هنوز یادآوری نداری نیایش جانم.\n"
                "مثلاً:\n"
                "/add 19:30 8 آموکسی\n\n"
                "ساعت، آخرین بار است. عدد بعدی، هر چند ساعت یک بار."
            )
        }
    lines = ["داروهایت، نیایش جانم 💛", ""]
    rows = []
    for index, reminder in enumerate(items, start=1):
        lines.append(f"{fa_digits(index)}. {describe_reminder(reminder, now)}")
        lines.append("")
        rows.append([{
            "text": f"پاک کردن {fa_digits(index)}",
            "callback_data": f"d:{reminder['id']}",
        }])
    lines.append("برای پاک کردن، همان دکمهٔ زیر را بزن.")
    return {"text": "\n".join(lines).strip(), "markup": {"inline_keyboard": rows}}


def delete_reminder(data: dict, chat_id: int, rest: str) -> dict:
    match = DEL_RE.match(rest.strip())
    items = chat_reminders(data, chat_id)
    if match is None or not items:
        if not items:
            return {"text": "چیزی برای حذف نیست نیایش جانم. با /add یکی بساز."}
        return {
            "text": (
                "شماره را درست ننوشته‌ای عزیزم.\n"
                "/list را بزن و بعد مثلاً /del 1 را بفرست."
            )
        }
    index = int(en_digits(match.group(1)))
    if index < 1 or index > len(items):
        return {
            "text": (
                "این شماره در فهرست تو نیست نیایش جانم.\n"
                "/list را بزن تا شماره‌ها را ببینی."
            )
        }
    target = items[index - 1]
    data["reminders"] = [
        reminder
        for reminder in data["reminders"]
        if not (valid_reminder(reminder) and reminder["id"] == target["id"])
    ]
    return {
        "text": (
            "حذف شد.\n"
            f"{target['emoji']} {html_escape(target['name'])} دیگر هر روز نمی‌آید.\n\n"
            "اگر پشیمان شدی دوباره با /add اضافه‌اش کن. یاسین کنارت است."
        )
    }


def history_text(data: dict, chat_id: int, today: date) -> str:
    start = today - timedelta(days=HISTORY_DAYS - 1)
    rows = []
    for item in data["intake_log"]:
        if not isinstance(item, dict) or item.get("chat_id") != chat_id:
            continue
        try:
            day = date.fromisoformat(str(item.get("day")))
        except ValueError:
            continue
        if day >= start:
            rows.append(item)
    if not rows:
        return (
            "در ۷ روز اخیر هنوز «خوردم» ثبت نشده نیایش جانم.\n"
            "هر وقت خوردی همان دکمه را بزن تا اینجا بماند.\n"
            "یاسین خیلی خیلی دوستت داره."
        )
    rows.sort(key=lambda item: (str(item.get("day")), str(item.get("at"))))
    grouped: dict[str, list[dict]] = {}
    for item in rows:
        grouped.setdefault(str(item["day"]), []).append(item)
    lines = ["۷ روز اخیر، وقت‌هایی که گفتی خوردم 🌷", ""]
    for day_iso in sorted(grouped, reverse=True):
        lines.append(fa_day(date.fromisoformat(day_iso)))
        for item in grouped[day_iso]:
            try:
                clock = fa_digits(parse_dt(str(item["at"])).strftime("%H:%M"))
            except (KeyError, TypeError, ValueError):
                clock = "—"
            emoji = item.get("emoji") or "💊"
            name = html_escape(item.get("name") or "دارو")
            lines.append(f"• {clock} {emoji} {name}")
        lines.append("")
    lines.append("آفرین به تو. نیایشم، زودتر خوب شو. یاسین خیلی خیلی دوستت داره.")
    return "\n".join(lines).strip()


def collect_due(data: dict, now: datetime) -> list[dict]:
    """پیام‌های سررسید را برمی‌گرداند.

    ارسال اول فقط ۰ تا ۳۰ دقیقه بعد از ساعت مقرر است.
    تعویق و یادآوری مجدد هم اگر اجرا دیر شد، بیشتر از ۳۰ دقیقه بعد از موعدشان نمی‌آیند
    تا ساعت‌ها بعد ناگهان زنگ نزنند.
    """
    plans = []
    today = now.date()
    yesterday = today - timedelta(days=1)
    for reminder in data["reminders"]:
        if not valid_reminder(reminder):
            continue
        if interval_hours(reminder):
            plans.extend(collect_interval(data, reminder, now))
            continue
        snooze_plan = due_snooze(data, reminder, (yesterday, today), now)
        if snooze_plan is not None:
            plans.append(snooze_plan)
            if snooze_plan["day"] == today.isoformat():
                continue

        today_entry = data["sent_log"].get(entry_key(reminder["id"], today))
        if not isinstance(today_entry, dict):
            today_entry = None
        if today_entry and today_entry.get("acked"):
            continue
        if (
            today_entry
            and today_entry.get("initial_sent")
            and today_entry.get("snooze_until")
            and now < parse_dt(str(today_entry["snooze_until"]))
        ):
            continue

        if today_entry is None or not today_entry.get("initial_sent"):
            scheduled = scheduled_dt(today, reminder["time"])
            delta = now - scheduled
            if timedelta(0) <= delta <= WINDOW:
                plans.append(make_plan(reminder, "initial", today, 1))
            continue

        followups = int(today_entry.get("followups") or 0)
        if followups >= MAX_FOLLOWUPS or not today_entry.get("last_sent_at"):
            continue
        due_at = parse_dt(str(today_entry["last_sent_at"])) + FOLLOWUP_AFTER
        if now < due_at:
            continue
        if now - due_at <= WINDOW:
            plans.append(make_plan(reminder, "followup", today, followups + 1))
        else:
            today_entry["followups"] = MAX_FOLLOWUPS
    return plans


def collect_interval(data: dict, reminder: dict, now: datetime) -> list[dict]:
    snoozed = due_slot_snooze(data, reminder, now)
    if snoozed:
        return snoozed
    slot_dt = upcoming_slot(reminder, now)
    if slot_dt is None or slot_dt > now:
        return []
    slot = slot_label(slot_dt)
    entry = data["sent_log"].get(f"{reminder['id']}:{slot}")
    if isinstance(entry, dict) and entry.get("acked"):
        return []
    if isinstance(entry, dict) and entry.get("snooze_until"):
        return []
    if not isinstance(entry, dict) or not entry.get("initial_sent"):
        if now - slot_dt <= WINDOW:
            return [make_plan(reminder, "initial", slot_dt.date(), 1, slot)]
        return []
    followups = int(entry.get("followups") or 0)
    if followups >= MAX_FOLLOWUPS or not entry.get("last_sent_at"):
        return []
    due_at = parse_dt(str(entry["last_sent_at"])) + FOLLOWUP_AFTER
    if due_at <= now <= due_at + WINDOW:
        return [make_plan(reminder, "followup", slot_dt.date(), followups + 1, slot)]
    if now > due_at + WINDOW:
        entry["followups"] = MAX_FOLLOWUPS
    return []


def due_slot_snooze(data: dict, reminder: dict, now: datetime) -> list[dict]:
    prefix = f"{reminder['id']}:"
    for key, entry in data["sent_log"].items():
        if not str(key).startswith(prefix) or not isinstance(entry, dict):
            continue
        if entry.get("acked") or not entry.get("snooze_until"):
            continue
        try:
            snooze_at = parse_dt(str(entry["snooze_until"]))
        except (TypeError, ValueError):
            entry["snooze_until"] = None
            continue
        slot = str(key).split(":", 1)[1]
        if now < snooze_at:
            continue
        if now - snooze_at <= WINDOW:
            slot_day = date.fromisoformat(slot[:10])
            return [make_plan(reminder, "snooze", slot_day, 1, slot)]
        entry["snooze_until"] = None
    return []


def due_snooze(
    data: dict,
    reminder: dict,
    days: tuple[date, date],
    now: datetime,
) -> dict | None:
    for day in days:
        entry = data["sent_log"].get(entry_key(reminder["id"], day))
        if not isinstance(entry, dict) or entry.get("acked") or not entry.get("snooze_until"):
            continue
        try:
            snooze_at = parse_dt(str(entry["snooze_until"]))
        except (TypeError, ValueError):
            entry["snooze_until"] = None
            continue
        if now < snooze_at:
            if day == now.date():
                return None
            continue
        if now - snooze_at <= WINDOW:
            return make_plan(reminder, "snooze", day, 1)
        entry["snooze_until"] = None
    return None


def make_plan(
    reminder: dict,
    kind: str,
    day: date,
    followup_no: int,
    slot: str | None = None,
) -> dict:
    slot_key = slot or day.isoformat()
    when = parse_dt(slot_key) if "T" in slot_key else scheduled_dt(day, reminder["time"])
    return {
        "chat_id": reminder["chat_id"],
        "day": day.isoformat(),
        "followup_no": followup_no,
        "id": reminder["id"],
        "kind": kind,
        "markup": keyboard(reminder["id"], slot_key),
        "slot": slot_key,
        "text": reminder_message(reminder, kind, when, followup_no),
    }


def mark_sent(data: dict, plan: dict, now: datetime) -> None:
    entry = ensure_slot(data, plan["id"], str(plan.get("slot") or plan["day"]))
    entry["last_sent_at"] = now.isoformat()
    if plan["kind"] == "initial":
        entry["initial_sent"] = True
    elif plan["kind"] == "followup":
        entry["followups"] = int(entry.get("followups") or 0) + 1
        entry["initial_sent"] = True
    elif plan["kind"] == "snooze":
        entry["snooze_until"] = None


def parse_callback(raw: str) -> tuple[str, int, str] | None:
    kind, separator, rest = raw.partition(":")
    reminder_text, separator2, day_text = rest.partition(":")
    if separator != ":" or separator2 != ":" or kind not in {"t", "z"}:
        return None
    if not reminder_text.isdigit():
        return None
    if re.fullmatch(r"\d{8}", day_text):
        slot = f"{day_text[0:4]}-{day_text[4:6]}-{day_text[6:8]}"
    elif re.fullmatch(r"\d{12}", day_text):
        slot = (
            f"{day_text[0:4]}-{day_text[4:6]}-{day_text[6:8]}"
            f"T{day_text[8:10]}:{day_text[10:12]}"
        )
    else:
        return None
    try:
        date.fromisoformat(slot[:10])
    except ValueError:
        return None
    return kind, int(reminder_text), slot


def handle_callback(token: str, data: dict, callback: dict, now: datetime) -> None:
    callback_id = str(callback.get("id") or "")
    message = callback.get("message") if isinstance(callback.get("message"), dict) else {}
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    if chat.get("type") != "private" or not isinstance(chat.get("id"), int):
        answer_callback(token, callback_id, "این دکمه را این‌جا نمی‌توانم انجام بدهم.")
        return
    chat_id = chat["id"]
    message_id = message.get("message_id")
    raw_data = str(callback.get("data") or "")
    if raw_data[:2] in {"d:", "y:", "x:"}:
        handle_delete_button(token, data, chat_id, message_id, callback_id, raw_data, now)
        return
    parsed = parse_callback(raw_data)
    if parsed is None:
        answer_callback(token, callback_id, "این دکمه قدیمی است نیایش جانم.")
        return
    kind, reminder_id, day = parsed
    if reminder_id == 0:
        handle_test_callback(token, chat_id, message_id, callback_id, kind)
        return

    reminder = find_reminder(data, chat_id, reminder_id)
    if reminder is None:
        answer_callback(token, callback_id, "این یادآور دیگر نیست عزیزم.")
        edit_message(
            token,
            chat_id,
            message_id,
            "این یادآور حذف شده نیایش جانم.\nاگر هنوز می‌خواهی، دوباره با /add اضافه‌اش کن.",
        )
        return

    if kind == "t":
        record_taken(token, data, reminder, day, now, chat_id, message_id, callback_id)
        return
    record_snooze(token, data, reminder, day, now, chat_id, message_id, callback_id)


def handle_delete_button(
    token: str,
    data: dict,
    chat_id: int,
    message_id: object,
    callback_id: str,
    raw_data: str,
    now: datetime,
) -> None:
    action, _, reminder_text = raw_data.partition(":")
    if not reminder_text.isdigit():
        answer_callback(token, callback_id, "این دکمه قدیمی است نیایش جانم.")
        return
    reminder = find_reminder(data, chat_id, int(reminder_text))
    if action == "x":
        answer_callback(token, callback_id, "ماند")
        current = list_reply(data, chat_id, now)
        edit_message(token, chat_id, message_id, current["text"], current.get("markup"))
        return
    if reminder is None:
        answer_callback(token, callback_id, "این یادآور دیگر نیست عزیزم.")
        return
    if action == "d":
        answer_callback(token, callback_id, "اگر مطمئنی تأیید کن")
        edit_message(
            token,
            chat_id,
            message_id,
            f"نیایش جانم، {reminder['emoji']} {html_escape(reminder['name'])} پاک شود؟",
            {
                "inline_keyboard": [[
                    {"text": "بله، پاک کن", "callback_data": f"y:{reminder['id']}"},
                    {"text": "نه", "callback_data": f"x:{reminder['id']}"},
                ]]
            },
        )
        return
    if action == "y":
        data["reminders"] = [
            item
            for item in data["reminders"]
            if not (valid_reminder(item) and item["id"] == reminder["id"])
        ]
        answer_callback(token, callback_id, "پاک شد")
        current = list_reply(data, chat_id, now)
        edit_message(
            token,
            chat_id,
            message_id,
            "پاک شد.\n\n" + current["text"],
            current.get("markup"),
        )


def handle_test_callback(
    token: str,
    chat_id: int,
    message_id: object,
    callback_id: str,
    kind: str,
) -> None:
    if kind == "t":
        answer_callback(token, callback_id, "رسید به گوشی، نیایش جانم")
        edit_message(
            token,
            chat_id,
            message_id,
            "✅ آفرین، ثبت شد\n\nاین فقط زنگ آزمایشی بود و در فهرست داروها نماند.\n"
            "نیایشم، زودتر خوب شو. یاسین خیلی خیلی دوستت داره.",
        )
        return
    answer_callback(token, callback_id, "این یکی آزمایشی بود")
    edit_message(
        token,
        chat_id,
        message_id,
        "زنگ آزمایشی بود نیایش جانم.\nیادآور واقعی را با /add می‌سازی و همان‌جا ده دقیقه بعد هم کار می‌کند.",
    )


def acknowledge(data: dict, reminder: dict, slot: str, now: datetime, chat_id: int) -> bool:
    entry = ensure_slot(data, reminder["id"], slot)
    first_time = not already_logged_slot(data, chat_id, reminder["id"], slot)
    entry["acked"] = True
    entry["snooze_until"] = None
    entry["initial_sent"] = True
    if interval_hours(reminder):
        reminder["last_taken_at"] = now.isoformat()
        reminder["time"] = now.strftime("%H:%M")
    if first_time:
        data["intake_log"].append(
            {
                "at": now.isoformat(),
                "chat_id": chat_id,
                "day": slot[:10],
                "emoji": reminder["emoji"],
                "name": reminder["name"],
                "reminder_id": reminder["id"],
                "slot": slot,
            }
        )
    return first_time


def already_logged_slot(data: dict, chat_id: int, reminder_id: int, slot: str) -> bool:
    for item in data["intake_log"]:
        if not isinstance(item, dict):
            continue
        if item.get("chat_id") != chat_id or item.get("reminder_id") != reminder_id:
            continue
        if item.get("slot") == slot or (not item.get("slot") and item.get("day") == slot):
            return True
    return False


def postpone(data: dict, reminder: dict, slot: str, now: datetime) -> str:
    entry = ensure_slot(data, reminder["id"], slot)
    if entry.get("acked"):
        return "acked"
    snoozes = int(entry.get("snoozes") or 0)
    if snoozes >= MAX_SNOOZES:
        return "capped"
    # دکمه فقط زیر پیامی می‌آید که قبلاً فرستاده شده، پس نوبت همان روز ارسال شده است.
    entry["initial_sent"] = True
    entry["snooze_until"] = (now + SNOOZE_FOR).isoformat()
    entry["snoozes"] = snoozes + 1
    return "ok"


def record_taken(
    token: str,
    data: dict,
    reminder: dict,
    slot: str,
    now: datetime,
    chat_id: int,
    message_id: object,
    callback_id: str,
) -> None:
    first_time = acknowledge(data, reminder, slot, now, chat_id)
    toast = "آفرین نیایش جانم، ثبت شد" if first_time else "این یکی را قبلاً ثبت کرده بودم عزیزم"
    love = pick_line(TAKEN_LINES, reminder["id"], slot)
    edit_message(
        token,
        chat_id,
        message_id,
        "✅ آفرین، ثبت شد\n\n"
        f"{reminder['emoji']} {html_escape(reminder['name'])}\n"
        f"{html_escape(love)}",
    )
    answer_callback(token, callback_id, toast)


def record_snooze(
    token: str,
    data: dict,
    reminder: dict,
    slot: str,
    now: datetime,
    chat_id: int,
    message_id: object,
    callback_id: str,
) -> None:
    state = postpone(data, reminder, slot, now)
    if state == "acked":
        answer_callback(token, callback_id, "قبلاً خوردی و ثبت شده نیایش جانم")
        return
    if state == "capped":
        answer_callback(token, callback_id, "بیشتر از این نمی‌توانم عقب بیندازم عزیزم")
        edit_message(
            token,
            chat_id,
            message_id,
            "نیایش جانم، این نوبت را بیشتر از این عقب نمی‌اندازم.\n"
            "اگر خوردی دکمهٔ «خوردم» را بزن. یاسین کنارت است.",
        )
        return
    edit_message(
        token,
        chat_id,
        message_id,
        "باشه عزیزم، ۱۰ دقیقهٔ دیگر دوباره آرام می‌گویم ⏰\n\n"
        f"{reminder['emoji']} {html_escape(reminder['name'])}\n"
        "نیایشم، زودتر خوب شو. یاسین خیلی خیلی دوستت داره.",
    )
    answer_callback(token, callback_id, "۱۰ دقیقهٔ دیگر یادت می‌اندازم")


def api(token: str, method: str, payload: dict, timeout: int = 40) -> object:
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        response = requests.post(url, json=payload, timeout=timeout)
    except requests.RequestException:
        raise TelegramError(method, "network", 0)
    status = response.status_code
    try:
        body = response.json()
    except ValueError:
        if status in (401, 404):
            raise FatalTokenError()
        raise TelegramError(method, "bad response", status)
    if status in (401, 404) or not isinstance(body, dict):
        raise FatalTokenError()
    if not body.get("ok"):
        description = str(body.get("description") or "error")
        raise TelegramError(method, description, status)
    return body.get("result")


def send_html(token: str, chat_id: int, text: str, reply_markup: dict | None = None) -> None:
    payload: dict = {
        "chat_id": chat_id,
        "disable_notification": False,
        "text": text,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    try:
        api(token, "sendMessage", {**payload, "parse_mode": "HTML"})
    except TelegramError as exc:
        if "parse" not in exc.description.lower():
            raise
        plain = re.sub(r"<[^>]+>", "", text)
        api(token, "sendMessage", {**payload, "text": plain})


def edit_message(
    token: str,
    chat_id: int,
    message_id: object,
    text: str,
    reply_markup: dict | None = None,
) -> None:
    if not isinstance(message_id, int):
        return
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "reply_markup": reply_markup if reply_markup is not None else {"inline_keyboard": []},
        "text": text,
    }
    try:
        api(token, "editMessageText", {**payload, "parse_mode": "HTML"})
    except TelegramError as exc:
        if "not modified" in exc.description.lower():
            return
        if "parse" in exc.description.lower():
            plain = re.sub(r"<[^>]+>", "", text)
            try:
                api(token, "editMessageText", {**payload, "text": plain})
            except TelegramError:
                print("editMessageText failed")
            return
        print("editMessageText failed")


def answer_callback(token: str, callback_id: str, text: str) -> None:
    if not callback_id:
        return
    try:
        api(
            token,
            "answerCallbackQuery",
            {"callback_query_id": callback_id, "text": text[:180]},
        )
    except FatalTokenError:
        raise
    except TelegramError:
        print("answerCallbackQuery failed")


def prepare_bot(token: str) -> None:
    api(token, "deleteWebhook", {"drop_pending_updates": False})
    try:
        api(token, "setMyCommands", {"commands": COMMANDS})
    except FatalTokenError:
        raise
    except TelegramError:
        print("could not refresh the command menu")


def pull_updates(token: str, offset: int, timeout: int = 0) -> list[dict]:
    collected: list[dict] = []
    for _ in range(5):
        batch = api(
            token,
            "getUpdates",
            {
                "allowed_updates": ["message", "callback_query"],
                "offset": offset,
                "timeout": timeout,
            },
            timeout=timeout + 15,
        )
        if not isinstance(batch, list) or not batch:
            break
        collected.extend(item for item in batch if isinstance(item, dict))
        offset = int(batch[-1]["update_id"]) + 1
        if len(batch) < 100:
            break
    return collected


def process_updates(
    token: str,
    data: dict,
    now: datetime,
    poll_timeout: int = 0,
) -> tuple[int, str | None]:
    try:
        updates = pull_updates(token, int(data["last_update_id"]) + 1, poll_timeout)
    except FatalTokenError:
        raise
    except TelegramError as exc:
        if exc.status == 409:
            raise
        print(f"could not read updates: {exc.method} status={exc.status}")
        return 0, exc.description

    handled = 0
    for update in updates:
        update_id = update.get("update_id")
        if not isinstance(update_id, int):
            continue
        try:
            if isinstance(update.get("callback_query"), dict):
                handle_callback(token, data, update["callback_query"], now)
            elif isinstance(update.get("message"), dict):
                deliver_message(token, data, update["message"], now)
        except FatalTokenError:
            raise
        except TelegramError as exc:
            print(f"update failed: {exc.method} status={exc.status}")
            if exc.status not in (403, 400):
                return handled, exc.description
        except Exception:
            print("could not handle one update")
        data["last_update_id"] = update_id
        handled += 1
    return handled, None


def deliver_message(token: str, data: dict, message: dict, now: datetime) -> None:
    if message.get("from", {}).get("is_bot"):
        return
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    if chat.get("type") != "private" or not isinstance(chat.get("id"), int):
        return
    text = message.get("text")
    if not isinstance(text, str) or not text.strip():
        send_html(
            token,
            chat["id"],
            "فقط نوشته را می‌فهمم نیایش جانم. مثلاً بنویس:\n/add 08:00 قرص صبح",
        )
        return
    reply = handle_message(data, chat["id"], text, now)
    send_html(token, chat["id"], reply["text"], reply.get("markup"))


def deliver_plans(token: str, data: dict, plans: list[dict], now: datetime) -> dict[str, int]:
    counts = {"initial": 0, "followup": 0, "snooze": 0}
    for plan in plans:
        try:
            send_html(token, plan["chat_id"], plan["text"], plan["markup"])
        except FatalTokenError:
            raise
        except TelegramError as exc:
            print(f"send failed: {exc.method} status={exc.status}")
            if exc.status == 403:
                mark_sent(data, plan, now)
                blocked = ensure_entry(data, plan["id"], date.fromisoformat(plan["day"]))
                blocked["followups"] = MAX_FOLLOWUPS
            continue
        mark_sent(data, plan, now)
        counts[plan["kind"]] += 1
    return counts


def publish_data() -> None:
    subprocess.run(["git", "add", "data.json"], cwd=ROOT, check=False)
    quiet = subprocess.run(["git", "diff", "--cached", "--quiet", "data.json"], cwd=ROOT)
    if quiet.returncode == 0:
        return
    committed = subprocess.run(
        ["git", "commit", "-m", "Update reminder data"],
        cwd=ROOT,
        check=False,
    )
    if committed.returncode != 0:
        return
    subprocess.run(["git", "pull", "--rebase", "--autostash"], cwd=ROOT, check=False)
    subprocess.run(["git", "push"], cwd=ROOT, check=False)


def run_once(token: str, poll_timeout: int = 0, publish: bool = False) -> int:
    data = load_data(DATA_PATH)
    original = dump_data(data)
    now = datetime.now(TZ)
    fatal = False
    update_error = None
    counts = {"initial": 0, "followup": 0, "snooze": 0}
    handled = 0
    try:
        prepare_bot(token)
        handled, update_error = process_updates(token, data, now, poll_timeout)
        plans = collect_due(data, now)
        counts = deliver_plans(token, data, plans, now)
    except FatalTokenError:
        fatal = True
        print(
            "BOT_TOKEN was rejected by Telegram. "
            "Generate a new token in BotFather and update the BOT_TOKEN secret.",
            file=sys.stderr,
        )
    except TelegramError as exc:
        if exc.status == 409:
            print("another instance is polling; skip")
            return 0
        raise

    prune(data, now.date())
    updated = dump_data(data)
    if updated != original:
        save_data(DATA_PATH, updated)
        print("data_changed=yes")
        if publish:
            publish_data()
    else:
        print("data_changed=no")
    print(
        "done "
        f"updates={handled} "
        f"sent={counts['initial']} "
        f"followups={counts['followup']} "
        f"snoozes={counts['snooze']}"
    )
    if fatal or (update_error and updated == original):
        return 1
    return 0


def main() -> None:
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        print(
            "BOT_TOKEN is not set. Add it as a GitHub Actions secret named BOT_TOKEN.",
            file=sys.stderr,
        )
        sys.exit(1)
    if "--watch" in sys.argv:
        print("watching")
        while True:
            try:
                run_once(token, poll_timeout=20, publish=True)
            except FatalTokenError:
                print(
                    "BOT_TOKEN was rejected by Telegram.",
                    file=sys.stderr,
                )
                sys.exit(1)
            except Exception as exc:
                text = f"{exc.__class__.__name__}: {exc}"
                if "api.telegram.org" in text:
                    text = exc.__class__.__name__
                print(text, file=sys.stderr)
                time.sleep(3)
        return
    sys.exit(run_once(token))


if __name__ == "__main__":
    try:
        main()
    except TelegramError as exc:
        print(f"telegram error: {exc.method} status={exc.status}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        text = f"{exc.__class__.__name__}: {exc}"
        if "api.telegram.org" in text:
            text = exc.__class__.__name__
        print(text, file=sys.stderr)
        sys.exit(1)
