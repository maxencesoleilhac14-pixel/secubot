import asyncio
from copy import deepcopy
import json
import logging
import os
import random
import traceback
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
try:
    from telegram.constants import ChatMember
except ImportError:
    from telegram import ChatMember
from dotenv import load_dotenv
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
DEFAULT_DATA_DIR = Path(os.getenv("RAILWAY_VOLUME_MOUNT_PATH", str(BASE_DIR)))
DATA_FILE = Path(
    os.getenv("WELCOME_BOT_DATA_FILE", str(DEFAULT_DATA_DIR / "welcome_bot_data.json"))
).expanduser()
SEED_DATA_FILE = BASE_DIR / "welcome_bot_data.json"
DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
TOKEN = os.getenv("BOT_TOKEN", "")
WELCOME_MESSAGE = os.getenv(
    "WELCOME_MESSAGE",
    "👋 Bienvenue sur BonPlav by HumaineFC 🔥\nAvant d'acceder au bot, il faut passer une verification rapide.",
)
APPROVED_MESSAGE = os.getenv(
    "APPROVED_MESSAGE",
    "✅ Acces valide. Tu peux maintenant utiliser les boutons ci-dessous.",
)
APPROVED_POST_TEXT = os.getenv(
    "APPROVED_POST_TEXT",
    "🚨 BONPLAV — ACCUEIL OFFICIEL 🚨\n\n"
    "Bienvenue sur BonPlav by HumaineFC 🔥\n\n"
    "🤖 Retrouvez ici l'ensemble de nos services et de nos différents serveurs, accessibles directement via les boutons ci-dessous.\n\n"
    "📌 COMMENT ÇA MARCHE ?\n"
    "• Sélectionne le serveur que tu souhaites rejoindre\n"
    "• Consulte les informations et services disponibles\n"
    "• Rejoins directement le serveur correspondant\n\n"
    "⚡ Simple. Rapide. Accessible.\n\n"
    "👇 Retrouve tous nos serveurs ci-dessous 👇\n\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "🔥 BONPLAV BY HUMAINEFC\n"
    "━━━━━━━━━━━━━━━━━━",
)
APPROVED_PHOTO_FILE_ID = os.getenv("APPROVED_PHOTO_FILE_ID", "").strip()
PENDING_MESSAGE = os.getenv(
    "PENDING_MESSAGE",
    "⏳ Ta demande a bien ete envoyee. Un admin doit maintenant l'approuver.",
)
REJECTED_MESSAGE = os.getenv(
    "REJECTED_MESSAGE",
    "❌ Ta demande a ete refusee. Tu peux relancer /start plus tard si besoin.",
)
MIN_INTRO_LENGTH = int(os.getenv("MIN_INTRO_LENGTH", "1"))
REQUIRE_INTRO = os.getenv("REQUIRE_INTRO", "true").lower() in {"1", "true", "yes", "on"}
REQUIRE_USERNAME = os.getenv("REQUIRE_USERNAME", "false").lower() in {"1", "true", "yes", "on"}

DEFAULT_MENU_BUTTONS = [
    {"text": "🔥 SERVEUR PRINCIPAL", "url": "https://t.me/+AMh0k16img9hYzZk"},
    {"text": "💬 LE CHAT", "url": "https://t.me/+dt0f_U1yHb4wNDk0"},
    {"text": "🛒 O'MARKET", "url": "https://t.me/Omarketbotbot_bot"},
    {"text": "🔐 BACKUP", "url": "https://t.me/+oOZ75UdUR6JjYjU8"},
]
BUTTON_SLOT_COUNT = 7
SETTINGS_VERSION = 2
BACKUP_INVITE_DEFAULT = "https://t.me/+oOZ75UdUR6JjYjU8"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
LOGGER = logging.getLogger("welcome_broadcast_bot")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_admin_ids() -> set[int]:
    admin_ids: set[int] = set()

    for key in ("ADMIN_ID_1", "ADMIN_ID_2"):
        raw_value = os.getenv(key, "").strip()
        if raw_value:
            admin_ids.add(int(raw_value))

    raw_single = os.getenv("ADMIN_ID", "").strip()
    if raw_single:
        admin_ids.add(int(raw_single))

    raw_list = os.getenv("ADMIN_IDS", "").strip()
    if raw_list:
        for item in raw_list.split(","):
            item = item.strip()
            if item:
                admin_ids.add(int(item))

    return admin_ids


ADMIN_IDS = parse_admin_ids()


def parse_menu_buttons() -> list[dict[str, str]]:
    raw_value = os.getenv("MENU_BUTTONS_JSON", "").strip()
    if not raw_value:
        return deepcopy(DEFAULT_MENU_BUTTONS)

    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        LOGGER.warning("MENU_BUTTONS_JSON invalide, utilisation des boutons par defaut.")
        return deepcopy(DEFAULT_MENU_BUTTONS)

    buttons: list[dict[str, str]] = []
    if not isinstance(parsed, list):
        return deepcopy(DEFAULT_MENU_BUTTONS)

    for item in parsed:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        url = str(item.get("url", "")).strip()
        buttons.append({"text": text, "url": url})

    while len(buttons) < BUTTON_SLOT_COUNT:
        buttons.append({"text": "", "url": ""})

    return buttons[:BUTTON_SLOT_COUNT] or deepcopy(DEFAULT_MENU_BUTTONS)


MENU_BUTTONS = parse_menu_buttons()


def default_settings() -> dict:
    return {
        "approved_post": {
            "caption": APPROVED_POST_TEXT,
            "photo_file_id": APPROVED_PHOTO_FILE_ID,
            "buttons": deepcopy(MENU_BUTTONS),
        }
    }


def load_data() -> dict:
    if not DATA_FILE.exists():
        if DATA_FILE != SEED_DATA_FILE and SEED_DATA_FILE.exists():
            try:
                seed_text = SEED_DATA_FILE.read_text(encoding="utf-8")
                DATA_FILE.write_text(seed_text, encoding="utf-8")
                return json.loads(seed_text)
            except json.JSONDecodeError:
                LOGGER.warning("Le fichier seed JSON est invalide, creation d'une base vide.")
        return {"users": {}}

    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        LOGGER.warning("Fichier JSON corrompu, recreation d'une base vide.")
        return {"users": {}}


DATA = load_data()


def save_data() -> None:
    DATA_FILE.write_text(json.dumps(DATA, ensure_ascii=True, indent=2), encoding="utf-8")


def ensure_data() -> None:
    if "users" not in DATA or not isinstance(DATA["users"], dict):
        DATA["users"] = {}
    if "settings" not in DATA or not isinstance(DATA["settings"], dict):
        DATA["settings"] = default_settings()
    else:
        ensure_settings()


def ensure_settings() -> None:
    settings = DATA.setdefault("settings", {})

    if settings.get("version") != SETTINGS_VERSION:
        settings["approved_post"] = {
            "caption": APPROVED_POST_TEXT,
            "photo_file_id": "",
            "buttons": deepcopy(MENU_BUTTONS),
        }
        settings["version"] = SETTINGS_VERSION
        return

    approved_post = settings.setdefault("approved_post", {})

    if not isinstance(approved_post.get("caption"), str):
        approved_post["caption"] = APPROVED_POST_TEXT

    if not isinstance(approved_post.get("photo_file_id"), str):
        approved_post["photo_file_id"] = APPROVED_PHOTO_FILE_ID

    buttons = approved_post.get("buttons")
    if not isinstance(buttons, list):
        approved_post["buttons"] = deepcopy(MENU_BUTTONS)
    else:
        normalized: list[dict[str, str]] = []
        for item in buttons:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            url = str(item.get("url", "")).strip()
            normalized.append({"text": text, "url": url})
        while len(normalized) < BUTTON_SLOT_COUNT:
            normalized.append({"text": "", "url": ""})
        approved_post["buttons"] = normalized[:BUTTON_SLOT_COUNT] or deepcopy(MENU_BUTTONS)


def linked_groups() -> list[int]:
    ensure_data()
    groups = DATA["settings"].get("groups")
    if not isinstance(groups, list):
        return []
    return [group for group in groups if isinstance(group, int)]


def group_title(chat_id: int) -> str:
    ensure_data()
    titles = DATA["settings"].get("group_titles")
    if isinstance(titles, dict):
        return str(titles.get(str(chat_id)) or "").strip()
    return ""


def set_group_title(chat_id: int, title: str) -> None:
    ensure_data()
    titles = DATA["settings"].setdefault("group_titles", {})
    clean = str(title or "").strip()
    if clean:
        titles[str(chat_id)] = clean
    else:
        titles.pop(str(chat_id), None)
    save_data()


def add_linked_group(chat_id: int, title: str = "") -> None:
    ensure_data()
    groups = DATA["settings"].setdefault("groups", [])
    changed = False
    if chat_id not in groups:
        groups.append(chat_id)
        changed = True
    clean_title = str(title or "").strip()
    if clean_title:
        titles = DATA["settings"].setdefault("group_titles", {})
        if str(titles.get(str(chat_id))) != clean_title:
            titles[str(chat_id)] = clean_title
            changed = True
    if changed:
        save_data()


def remove_linked_group(chat_id: int) -> None:
    ensure_data()
    groups = DATA["settings"].setdefault("groups", [])
    if chat_id in groups:
        groups.remove(chat_id)
        save_data()


def get_backup_chat_id() -> int | None:
    ensure_data()
    backup = DATA["settings"].get("backup_chat_id")
    return backup if isinstance(backup, int) else None


def set_backup_chat_id(chat_id: int) -> None:
    ensure_data()
    DATA["settings"]["backup_chat_id"] = int(chat_id)
    save_data()


def get_backup_invite() -> str:
    ensure_data()
    invite = str(DATA["settings"].get("backup_invite") or os.getenv("BACKUP_INVITE", "") or "").strip()
    return invite or BACKUP_INVITE_DEFAULT


def set_backup_invite(invite: str) -> None:
    ensure_data()
    DATA["settings"]["backup_invite"] = invite
    save_data()


async def is_chat_member(context, chat_id: int, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return member.status in (ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER)
    except Exception:
        return False


async def ban_everywhere(context, user_id: int) -> dict[int, bool]:
    results: dict[int, bool] = {}
    for chat_id in linked_groups():
        try:
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            results[chat_id] = True
        except Exception as exc:
            LOGGER.warning("Ban de %s dans %s impossible: %s", user_id, chat_id, exc)
            results[chat_id] = False
    return results


async def unban_everywhere(context, user_id: int) -> dict[int, bool]:
    results: dict[int, bool] = {}
    for chat_id in linked_groups():
        try:
            await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
            results[chat_id] = True
        except Exception as exc:
            LOGGER.warning("Unban de %s dans %s impossible: %s", user_id, chat_id, exc)
            results[chat_id] = False
    return results


def format_group_results(results: dict[int, bool]) -> str:
    if not results:
        return ""
    ok = sum(1 for accepted in results.values() if accepted)
    return f"🔨 Serveurs: {ok}/{len(results)}"


def backup_join_markup() -> InlineKeyboardMarkup:
    rows = []
    invite = get_backup_invite()
    if invite:
        rows.append([InlineKeyboardButton("🔗 Rejoindre le serveur BACKUP", url=invite)])
    rows.append([InlineKeyboardButton("✅ J'ai rejoint", callback_data="gate:backup:check")])
    return InlineKeyboardMarkup(rows)


def backup_join_text() -> str:
    return (
        "📌 Derniere etape: rejoins le serveur BACKUP.\n\n"
        "1. Clique sur le bouton ci-dessous pour rejoindre le serveur.\n"
        "2. Une fois dedans, appuie sur « J'ai rejoint ».\n\n"
        "Tant que tu n'es pas dans le BACKUP, tu ne peux pas acceder aux serveurs."
    )


async def proceed_after_verification(
    user: dict,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    reply_target=None,
    is_callback: bool,
) -> None:
    backup_chat_id = get_backup_chat_id()
    if backup_chat_id and not await is_chat_member(context, backup_chat_id, user["id"]):
        set_status(user, "pending_backup")
        save_data()
        text = backup_join_text()
        markup = backup_join_markup()
        if is_callback and reply_target is not None:
            try:
                await reply_target.edit_message_text(text=text, reply_markup=markup)
                return
            except Exception:
                pass
        await context.bot.send_message(chat_id=user["id"], text=text, reply_markup=markup)
        return

    await queue_for_approval(user, context)
    if is_callback and reply_target is not None:
        try:
            await reply_target.edit_message_text(text=PENDING_MESSAGE)
            return
        except Exception:
            pass
    await context.bot.send_message(chat_id=user["id"], text=PENDING_MESSAGE)


def approved_post_settings() -> dict:
    ensure_data()
    return DATA["settings"]["approved_post"]


def visible_buttons(buttons: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        button
        for button in buttons
        if (button.get("text") or "").strip() and (button.get("url") or "").strip()
    ]


def build_risk_flags(user_payload: dict) -> list[str]:
    flags: list[str] = []
    username = (user_payload.get("username") or "").strip()
    first_name = (user_payload.get("first_name") or "").strip()

    if not username:
        flags.append("pas de username")
    elif sum(char.isdigit() for char in username) >= 4:
        flags.append("username charge en chiffres")

    if len(first_name) <= 2:
        flags.append("prenom tres court")

    if not user_payload.get("intro_text"):
        flags.append("pas de presentation")

    return flags


def ensure_user(telegram_user) -> dict:
    ensure_data()
    key = str(telegram_user.id)
    existing = DATA["users"].get(key, {})
    created_at = existing.get("created_at", utc_now())

    payload = {
        "id": telegram_user.id,
        "username": telegram_user.username or "",
        "first_name": telegram_user.first_name or "",
        "last_name": telegram_user.last_name or "",
        "full_name": telegram_user.full_name or telegram_user.first_name or str(telegram_user.id),
        "status": existing.get("status", "new"),
        "subscribed": existing.get("subscribed", True),
        "human_verified": existing.get("human_verified", False),
        "intro_text": existing.get("intro_text", ""),
        "created_at": created_at,
        "updated_at": utc_now(),
        "approved_at": existing.get("approved_at"),
        "rejected_at": existing.get("rejected_at"),
        "banned_at": existing.get("banned_at"),
        "review_requested_at": existing.get("review_requested_at"),
        "last_challenge": existing.get("last_challenge", {}),
        "admin_note": existing.get("admin_note", ""),
    }
    payload["risk_flags"] = build_risk_flags(payload)
    DATA["users"][key] = payload
    return payload


def get_user(user_id: int) -> dict | None:
    ensure_data()
    return DATA["users"].get(str(user_id))


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_private_chat(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type == "private")


def build_main_menu() -> InlineKeyboardMarkup:
    buttons = visible_buttons(approved_post_settings().get("buttons", []))
    rows = [[InlineKeyboardButton(button["text"], url=button["url"])] for button in buttons]
    rows.append([InlineKeyboardButton("🔄 Rafraichir", callback_data="menu:refresh")])
    return InlineKeyboardMarkup(rows)


def build_menu_preview_markup() -> InlineKeyboardMarkup:
    buttons = visible_buttons(approved_post_settings().get("buttons", []))
    rows = [[InlineKeyboardButton(button["text"], url=button["url"])] for button in buttons]
    rows.append([InlineKeyboardButton("⬅️ Retour admin", callback_data="admin:home")])
    return InlineKeyboardMarkup(rows)


def build_admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📥 Demandes en attente", callback_data="admin:pending")],
            [InlineKeyboardButton("🖼️ Accueil approuve", callback_data="admin:welcome")],
            [InlineKeyboardButton("📢 Nouvelle annonce", callback_data="admin:broadcast")],
            [InlineKeyboardButton("📊 Statistiques", callback_data="admin:stats")],
            [InlineKeyboardButton("👥 Gestion acces", callback_data="admin:access")],
            [InlineKeyboardButton("👀 Voir menu utilisateur", callback_data="admin:usermenu")],
            [InlineKeyboardButton("🔗 Serveurs lies", callback_data="admin:servers")],
        ]
    )


def build_servers_admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Ajouter un serveur lie", callback_data="admin:servers:add")],
            [InlineKeyboardButton("🎯 Choisir le serveur BACKUP", callback_data="admin:servers:backup")],
            [InlineKeyboardButton("🔗 Modifier le lien BACKUP", callback_data="admin:servers:link")],
            [InlineKeyboardButton("🗑️ Retirer un serveur lie", callback_data="admin:servers:remove")],
            [InlineKeyboardButton("⬅️ Retour", callback_data="admin:home")],
        ]
    )


def build_welcome_admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📝 Modifier le texte", callback_data="admin:welcome:text")],
            [InlineKeyboardButton("🖼️ Modifier l'image", callback_data="admin:welcome:photo")],
            [InlineKeyboardButton("🗑️ Retirer l'image", callback_data="admin:welcome:clearphoto")],
            [InlineKeyboardButton("🔘 Gerer les boutons", callback_data="admin:welcome:buttons")],
            [InlineKeyboardButton("👀 Previsualiser", callback_data="admin:welcome:preview")],
            [InlineKeyboardButton("⬅️ Retour", callback_data="admin:home")],
        ]
    )


def build_buttons_admin_menu() -> InlineKeyboardMarkup:
    buttons = approved_post_settings().get("buttons", [])
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton("➕ Ajouter un bouton", callback_data="admin:button:add")]
    ]

    for index, button in enumerate(buttons):
        label = f"{index + 1}. {button['text']}" if button.get("text") else f"{index + 1}. [VIDE]"
        rows.append([InlineKeyboardButton(label[:55], callback_data=f"admin:button:view:{index}")])

    rows.append([InlineKeyboardButton("⬅️ Retour", callback_data="admin:welcome")])
    return InlineKeyboardMarkup(rows)


def build_button_edit_menu(index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📝 Modifier le nom", callback_data=f"admin:button:edittext:{index}")],
            [InlineKeyboardButton("🔗 Modifier le lien", callback_data=f"admin:button:editurl:{index}")],
            [InlineKeyboardButton("🗑️ Supprimer", callback_data=f"admin:button:delete:{index}")],
            [InlineKeyboardButton("⬅️ Retour", callback_data="admin:welcome:buttons")],
        ]
    )


def build_access_admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Utilisateurs approuves", callback_data="admin:access:approved")],
            [InlineKeyboardButton("⛔ Utilisateurs bannis", callback_data="admin:access:banned")],
            [InlineKeyboardButton("⬅️ Retour", callback_data="admin:home")],
        ]
    )


def build_access_list_markup(status: str, limit: int = 15) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    users = users_by_status(status, limit=limit)
    for user in users:
        username = f"@{user['username']}" if user.get("username") else str(user["id"])
        label = f"{user.get('full_name') or user['id']} • {username}"
        rows.append([InlineKeyboardButton(label[:55], callback_data=f"admin:access:view:{user['id']}")])

    if not rows:
        rows.append([InlineKeyboardButton("Aucun utilisateur", callback_data="admin:noop")])

    rows.append([InlineKeyboardButton("⬅️ Retour", callback_data="admin:access")])
    return InlineKeyboardMarkup(rows)


def build_access_user_menu(user: dict) -> InlineKeyboardMarkup:
    if user.get("status") == "banned":
        action_row = [InlineKeyboardButton("✅ Debannir", callback_data=f"admin:unban:{user['id']}")]
    else:
        action_row = [InlineKeyboardButton("⛔ Bannir", callback_data=f"admin:ban:{user['id']}")]

    return InlineKeyboardMarkup(
        [
            action_row,
            [InlineKeyboardButton("⬅️ Retour", callback_data=f"admin:access:{user.get('status', 'approved')}")],
        ]
    )


def build_approval_markup(target_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Approuver", callback_data=f"admin:approve:{target_id}"),
                InlineKeyboardButton("❌ Refuser", callback_data=f"admin:reject:{target_id}"),
            ],
            [InlineKeyboardButton("⛔ Bannir", callback_data=f"admin:ban:{target_id}")],
        ]
    )


def build_pending_list_markup(limit: int = 10) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for user in pending_users()[:limit]:
        label = user.get("full_name") or str(user["id"])
        rows.append([InlineKeyboardButton(label[:50], callback_data=f"admin:review:{user['id']}")])

    if not rows:
        rows.append([InlineKeyboardButton("✅ Aucune demande en attente", callback_data="admin:noop")])

    rows.append([InlineKeyboardButton("⬅️ Retour", callback_data="admin:home")])
    return InlineKeyboardMarkup(rows)


def stats_snapshot() -> dict[str, int]:
    ensure_data()
    users = list(DATA["users"].values())
    return {
        "total": len(users),
        "approved": sum(1 for user in users if user.get("status") == "approved"),
        "pending": sum(1 for user in users if user.get("status") == "pending_approval"),
        "intro": sum(1 for user in users if user.get("status") == "pending_intro"),
        "backup": sum(1 for user in users if user.get("status") == "pending_backup"),
        "banned": sum(1 for user in users if user.get("status") == "banned"),
        "subscribed": sum(1 for user in users if user.get("subscribed")),
    }


def pending_users() -> list[dict]:
    ensure_data()
    users = [user for user in DATA["users"].values() if user.get("status") == "pending_approval"]
    return sorted(users, key=lambda item: item.get("review_requested_at") or item.get("created_at") or "")


def users_by_status(status: str, limit: int = 15) -> list[dict]:
    ensure_data()
    users = [user for user in DATA["users"].values() if user.get("status") == status]
    users.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)
    return users[:limit]


def format_user_for_admin(user: dict) -> str:
    risk_flags = user.get("risk_flags") or []
    flags_text = ", ".join(risk_flags) if risk_flags else "aucun"
    username = f"@{user['username']}" if user.get("username") else "aucun"
    intro_text = escape(user.get("intro_text") or "aucune presentation")
    return (
        "<b>Nouvelle demande d'acces</b>\n\n"
        f"<b>👤 ID:</b> <code>{user['id']}</code>\n"
        f"<b>🪪 Nom:</b> {escape(user.get('full_name') or '')}\n"
        f"<b>🔗 Username:</b> {escape(username)}\n"
        f"<b>📌 Statut:</b> {escape(user.get('status') or '')}\n"
        f"<b>⚠️ Signaux:</b> {escape(flags_text)}\n"
        f"<b>📝 Presentation:</b> {intro_text}"
    )


def format_access_user(user: dict) -> str:
    username = f"@{user['username']}" if user.get("username") else "aucun"
    return (
        "<b>Fiche utilisateur</b>\n\n"
        f"<b>👤 ID:</b> <code>{user['id']}</code>\n"
        f"<b>🪪 Nom:</b> {escape(user.get('full_name') or '')}\n"
        f"<b>🔗 Username:</b> {escape(username)}\n"
        f"<b>📌 Statut:</b> {escape(user.get('status') or '')}\n"
        f"<b>📅 Cree le:</b> {escape(user.get('created_at') or '')}\n"
        f"<b>🔔 Annonces:</b> {'oui' if user.get('subscribed') else 'non'}"
    )


def format_welcome_summary() -> str:
    approved_post = approved_post_settings()
    buttons = approved_post.get("buttons", [])
    photo_label = "configuree" if approved_post.get("photo_file_id") else "aucune"
    caption = approved_post.get("caption") or ""
    preview = caption if len(caption) <= 280 else f"{caption[:277]}..."
    return (
        "🖼️ Accueil approuve\n\n"
        f"Photo: {photo_label}\n"
        f"Boutons: {len(buttons)}\n\n"
        "Apercu du texte:\n"
        f"{preview}"
    )


def photo_caption_fits(text: str) -> bool:
    return len(text) <= 1024


async def send_approved_content(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    preview: bool = False,
) -> None:
    approved_post = approved_post_settings()
    caption = approved_post.get("caption") or APPROVED_MESSAGE
    reply_markup = build_main_menu()
    photo_file_id = approved_post.get("photo_file_id") or ""
    text = caption
    if preview and photo_file_id and not photo_caption_fits(caption):
        text = "ℹ️ Texte trop long pour une legende photo, il sera envoye juste apres l'image.\n\n" + caption

    if photo_file_id and photo_caption_fits(caption):
        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo_file_id,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
            return
        except Exception as exc:
            LOGGER.warning("Echec envoi photo+legende vers %s: %s", chat_id, exc)

    if photo_file_id:
        try:
            await context.bot.send_photo(chat_id=chat_id, photo=photo_file_id)
        except Exception as exc:
            LOGGER.warning("Echec envoi photo seule vers %s: %s", chat_id, exc)

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
        return
    except Exception as exc:
        LOGGER.warning("Echec envoi message HTML vers %s: %s", chat_id, exc)

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )


async def edit_or_send(
    query,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> None:
    try:
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as exc:
        LOGGER.warning("Impossible d'editer le message callback, envoi d'un nouveau message: %s", exc)
        target_chat_id = query.message.chat_id if query.message else query.from_user.id
        await query.get_bot().send_message(
            chat_id=target_chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )


def build_pending_user_view(target_id: int, user: dict) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        f"{format_user_for_admin(user)}\n\n"
        "<b>Actions rapides</b>\n"
        "Tu peux approuver, refuser ou bannir directement depuis cette fiche."
    )
    markup = InlineKeyboardMarkup(
        build_approval_markup(target_id).inline_keyboard
        + [[InlineKeyboardButton("⬅️ Retour", callback_data="admin:pending")]]
    )
    return text, markup


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    LOGGER.error("Erreur non geree: %s", context.error)
    LOGGER.error("%s", "".join(traceback.format_exception(None, context.error, context.error.__traceback__)))


def get_button(index: int) -> dict | None:
    buttons = approved_post_settings().get("buttons", [])
    if 0 <= index < len(buttons):
        return buttons[index]
    return None


def new_captcha() -> dict:
    left = random.randint(1, 9)
    right = random.randint(1, 9)
    answer = left + right

    options = {answer}
    while len(options) < 4:
        options.add(max(2, answer + random.randint(-4, 4)))

    choices = list(options)
    random.shuffle(choices)
    return {
        "question": f"{left} + {right} = ?",
        "answer": answer,
        "choices": choices,
        "created_at": utc_now(),
    }


def captcha_markup(challenge: dict) -> InlineKeyboardMarkup:
    rows = []
    for choice in challenge["choices"]:
        rows.append([InlineKeyboardButton(str(choice), callback_data=f"gate:captcha:{choice}")])
    return InlineKeyboardMarkup(rows)


async def send_private_only_notice(update: Update) -> None:
    target = update.effective_message
    if target:
        await target.reply_text("Passe en message prive avec le bot et utilise /start.")


def set_status(user: dict, status: str) -> None:
    user["status"] = status
    user["updated_at"] = utc_now()


async def queue_for_approval(user: dict, context: ContextTypes.DEFAULT_TYPE) -> None:
    set_status(user, "pending_approval")
    user["review_requested_at"] = utc_now()
    user["risk_flags"] = build_risk_flags(user)
    save_data()

    text = format_user_for_admin(user)
    markup = build_approval_markup(user["id"])
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=text,
                reply_markup=markup,
                parse_mode=ParseMode.HTML,
            )
        except Exception as exc:
            LOGGER.warning("Impossible d'envoyer la demande a l'admin %s: %s", admin_id, exc)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_private_chat(update):
        await send_private_only_notice(update)
        return

    telegram_user = update.effective_user
    if telegram_user is None:
        return

    user = ensure_user(telegram_user)
    user["subscribed"] = True

    if user.get("status") == "banned":
        save_data()
        await update.message.reply_text("⛔ Acces refuse.")
        return

    if is_admin(telegram_user.id):
        user["human_verified"] = True
        set_status(user, "approved")
        user["approved_at"] = user.get("approved_at") or utc_now()
        save_data()
        await send_approved_content(update.effective_chat.id, context)
        return

    if REQUIRE_USERNAME and not user.get("username"):
        save_data()
        await update.message.reply_text(
            "⚙️ Ajoute d'abord un username Telegram dans tes reglages, puis relance /start."
        )
        return

    if user.get("status") == "approved":
        save_data()
        await send_approved_content(update.effective_chat.id, context)
        return

    if user.get("status") == "pending_approval":
        save_data()
        await update.message.reply_text(PENDING_MESSAGE)
        return

    if user.get("status") == "pending_intro":
        save_data()
        await update.message.reply_text(
            "📝 Envoie une petite presentation pour terminer la demande d'acces."
        )
        return

    if user.get("status") == "pending_backup":
        save_data()
        await update.message.reply_text(backup_join_text(), reply_markup=backup_join_markup())
        return

    challenge = new_captcha()
    user["last_challenge"] = challenge
    user["human_verified"] = False
    set_status(user, "pending_captcha")
    save_data()

    await update.message.reply_text(
        f"{WELCOME_MESSAGE}\n\n🤖 Verification humaine: {challenge['question']}",
        reply_markup=captcha_markup(challenge),
    )


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_private_chat(update):
        await send_private_only_notice(update)
        return

    telegram_user = update.effective_user
    if telegram_user is None:
        return

    user = ensure_user(telegram_user)
    user["subscribed"] = False
    save_data()
    await update.message.reply_text("🔕 Tu ne recevras plus les annonces. Utilise /start pour revenir.")


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_private_chat(update):
        await send_private_only_notice(update)
        return

    telegram_user = update.effective_user
    if telegram_user is None or not is_admin(telegram_user.id):
        if update.message:
            await update.message.reply_text("🔐 Commande reservee aux admins.")
        return

    await update.message.reply_text("🛠️ Panel admin", reply_markup=build_admin_menu())


async def servers_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_private_chat(update):
        await send_private_only_notice(update)
        return

    actor = update.effective_user
    if actor is None or not is_admin(actor.id):
        if update.message:
            await update.message.reply_text("🔐 Commande reservee aux admins.")
        return

    await update.message.reply_text("🔗 Serveurs lies", reply_markup=build_servers_admin_menu())


def record_ban(user_id: int) -> None:
    ensure_data()
    record = DATA["users"].get(str(user_id))
    if record is None:
        record = {
            "id": user_id,
            "username": "",
            "first_name": "",
            "last_name": "",
            "full_name": str(user_id),
            "status": "banned",
            "subscribed": False,
            "human_verified": False,
            "intro_text": "",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "approved_at": None,
            "rejected_at": None,
            "banned_at": utc_now(),
            "review_requested_at": None,
            "last_challenge": {},
            "admin_note": "",
            "risk_flags": [],
        }
        DATA["users"][str(user_id)] = record
    else:
        set_status(record, "banned")
        record["banned_at"] = utc_now()
        record["subscribed"] = False
    save_data()


def resolve_target_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    message = update.effective_message
    if message is None:
        return None

    reply = message.reply_to_message
    if reply is not None and reply.from_user is not None:
        return reply.from_user.id

    if context.args:
        arg = context.args[0].lstrip("@")
        if arg.isdigit():
            return int(arg)

    return None


async def can_moderate(update: Update, context: ContextTypes.DEFAULT_TYPE, actor_id: int) -> bool:
    if is_admin(actor_id):
        return True

    chat = update.effective_chat
    if chat is None or chat.type not in ("group", "supergroup", "channel"):
        return False

    try:
        member = await context.bot.get_chat_member(chat_id=chat.id, user_id=actor_id)
        return member.status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER)
    except Exception:
        return False


async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    actor = update.effective_user
    message = update.effective_message
    if actor is None or message is None:
        return

    if not await can_moderate(update, context, actor.id):
        await message.reply_text("🔐 Commande reservee aux admins.")
        return

    target_id = resolve_target_id(update, context)
    if target_id is None:
        if is_private_chat(update):
            await message.reply_text("Usage: /ban 123456789")
        else:
            await message.reply_text("Usage: reponds a un message avec /ban, ou /ban 123456789")
        return

    if target_id == actor.id:
        await message.reply_text("❌ Tu ne peux pas te bannir toi-meme.")
        return

    record_ban(target_id)

    try:
        await context.bot.send_message(target_id, "⛔ Acces retire par un admin.")
    except Exception as exc:
        LOGGER.warning("Impossible de notifier l'utilisateur %s: %s", target_id, exc)

    results = await ban_everywhere(context, target_id)
    if linked_groups():
        suffix = f"\n{format_group_results(results)}"
    else:
        suffix = "\nℹ️ Aucun serveur lie (ajoute le bot en admin dans tes serveurs)."
    await message.reply_text(f"⛔ Utilisateur banni: {target_id}{suffix}")


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    actor = update.effective_user
    message = update.effective_message
    if actor is None or message is None:
        return

    if not await can_moderate(update, context, actor.id):
        await message.reply_text("🔐 Commande reservee aux admins.")
        return

    target_id = resolve_target_id(update, context)
    if target_id is None:
        if is_private_chat(update):
            await message.reply_text("Usage: /unban 123456789")
        else:
            await message.reply_text("Usage: reponds a un message avec /unban, ou /unban 123456789")
        return

    target = get_user(target_id)
    if target is not None:
        set_status(target, "approved")
        target["subscribed"] = True
        save_data()

        try:
            await send_approved_content(target_id, context)
        except Exception as exc:
            LOGGER.warning("Impossible de notifier l'utilisateur %s: %s", target_id, exc)

    results = await unban_everywhere(context, target_id)
    if linked_groups():
        suffix = f"\n{format_group_results(results)}"
    else:
        suffix = "\nℹ️ Aucun serveur lie (ajoute le bot en admin dans tes serveurs)."
    await message.reply_text(f"✅ Utilisateur debanni: {target_id}{suffix}")


def admin_state(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> dict:
    states = context.application.bot_data.setdefault("admin_states", {})
    return states.setdefault(user_id, {})


def reset_admin_state(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    states = context.application.bot_data.setdefault("admin_states", {})
    states[user_id] = {}


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()
    actor = update.effective_user
    if actor is None:
        return

    actor_record = ensure_user(actor)
    save_data()

    if query.data.startswith("gate:captcha:"):
        await handle_captcha_callback(query, actor_record, context)
        return

    if query.data == "gate:backup:check":
        await handle_backup_check(query, actor_record, context)
        return

    if query.data == "menu:refresh":
        if actor_record.get("status") != "approved":
            await query.edit_message_text("Acces en attente d'approbation.")
            return
        await send_approved_content(actor.id, context)
        return

    if not is_admin(actor.id):
        await query.answer("Reserve aux admins.", show_alert=True)
        return

    if query.data == "admin:noop":
        return

    if query.data == "admin:home":
        await query.edit_message_text("🛠️ Panel admin", reply_markup=build_admin_menu())
        return

    if query.data == "admin:pending":
        await query.edit_message_text(
            "📥 Demandes en attente",
            reply_markup=build_pending_list_markup(),
        )
        return

    if query.data == "admin:welcome":
        await query.edit_message_text(
            format_welcome_summary(),
            reply_markup=build_welcome_admin_menu(),
        )
        return

    if query.data == "admin:welcome:text":
        state = admin_state(actor.id, context)
        state.clear()
        state["mode"] = "welcome_text_edit"
        await query.edit_message_text(
            "📝 Envoie maintenant le nouveau texte d'accueil approuve.\n\n"
            "Tu peux utiliser du HTML Telegram comme <b>gras</b>, <i>italique</i> et "
            "<tg-emoji emoji-id=\"...\">🙂</tg-emoji> si ton bot peut utiliser les custom emojis.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Annuler", callback_data="admin:welcome")]]
            ),
        )
        return

    if query.data == "admin:welcome:photo":
        state = admin_state(actor.id, context)
        state.clear()
        state["mode"] = "welcome_photo_edit"
        await query.edit_message_text(
            "🖼️ Envoie maintenant la photo a utiliser pour le message d'accueil approuve.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Annuler", callback_data="admin:welcome")]]
            ),
        )
        return

    if query.data == "admin:welcome:clearphoto":
        approved_post_settings()["photo_file_id"] = ""
        save_data()
        await query.edit_message_text(
            format_welcome_summary(),
            reply_markup=build_welcome_admin_menu(),
        )
        return

    if query.data == "admin:welcome:preview":
        await send_approved_content(actor.id, context, preview=True)
        await query.answer("Previsualisation envoyee.")
        return

    if query.data == "admin:welcome:buttons":
        await query.edit_message_text(
            "🔘 Gestion des boutons",
            reply_markup=build_buttons_admin_menu(),
        )
        return

    if query.data == "admin:button:add":
        state = admin_state(actor.id, context)
        state.clear()
        state["mode"] = "button_add_text"
        await query.edit_message_text(
            "➕ Envoie le nom du nouveau bouton.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Annuler", callback_data="admin:welcome:buttons")]]
            ),
        )
        return

    if query.data.startswith("admin:button:view:"):
        index = int(query.data.split(":")[-1])
        button = get_button(index)
        if not button:
            await query.edit_message_text(
                "❌ Bouton introuvable.",
                reply_markup=build_buttons_admin_menu(),
            )
            return
        await query.edit_message_text(
            f"🔘 Bouton {index + 1}\n\nNom: {button['text']}\nLien: {button['url']}",
            reply_markup=build_button_edit_menu(index),
        )
        return

    if query.data.startswith("admin:button:edittext:"):
        index = int(query.data.split(":")[-1])
        if not get_button(index):
            await query.edit_message_text("❌ Bouton introuvable.", reply_markup=build_buttons_admin_menu())
            return
        state = admin_state(actor.id, context)
        state.clear()
        state["mode"] = "button_edit_text"
        state["button_index"] = index
        await query.edit_message_text(
            "📝 Envoie le nouveau nom du bouton.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Annuler", callback_data="admin:welcome:buttons")]]
            ),
        )
        return

    if query.data.startswith("admin:button:editurl:"):
        index = int(query.data.split(":")[-1])
        if not get_button(index):
            await query.edit_message_text("❌ Bouton introuvable.", reply_markup=build_buttons_admin_menu())
            return
        state = admin_state(actor.id, context)
        state.clear()
        state["mode"] = "button_edit_url"
        state["button_index"] = index
        await query.edit_message_text(
            "🔗 Envoie le nouveau lien du bouton.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Annuler", callback_data="admin:welcome:buttons")]]
            ),
        )
        return

    if query.data.startswith("admin:button:delete:"):
        index = int(query.data.split(":")[-1])
        buttons = approved_post_settings().get("buttons", [])
        if not (0 <= index < len(buttons)):
            await query.edit_message_text("❌ Bouton introuvable.", reply_markup=build_buttons_admin_menu())
            return
        removed = buttons.pop(index)
        save_data()
        await query.edit_message_text(
            f"🗑️ Bouton supprime: {removed['text']}",
            reply_markup=build_buttons_admin_menu(),
        )
        return

    if query.data == "admin:stats":
        snapshot = stats_snapshot()
        await query.edit_message_text(
            (
                "📊 Statistiques\n\n"
                f"👥 Total inscrits: {snapshot['total']}\n"
                f"✅ Approuves: {snapshot['approved']}\n"
                f"⏳ En attente: {snapshot['pending']}\n"
                f"📝 En presentation: {snapshot['intro']}\n"
                f"🔐 En backup: {snapshot['backup']}\n"
                f"⛔ Bannis: {snapshot['banned']}\n"
                f"📢 Abonnes annonces: {snapshot['subscribed']}"
            ),
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Retour", callback_data="admin:home")]]
            ),
        )
        return

    if query.data == "admin:usermenu":
        await query.edit_message_text(
            "Apercu du menu utilisateur",
            reply_markup=build_menu_preview_markup(),
        )
        return

    if query.data == "admin:servers":
        groups = linked_groups()
        lines = []
        for group_id in groups:
            label = group_title(group_id)
            if not label:
                try:
                    chat = await context.bot.get_chat(chat_id=group_id)
                    label = chat.title or ""
                except Exception:
                    label = ""
            lines.append(f"• {label} ({group_id})" if label else f"• {group_id}")
        text = "🔗 Serveurs lies (le bot doit etre admin)\n\n"
        text += (
            "\n".join(lines)
            if lines
            else "Aucun serveur lie pour l'instant.\n\nAjoute le bot en admin dans tes serveurs "
            "(detection automatique) ou utilise « Ajouter un serveur lie »."
        )
        backup_id = get_backup_chat_id()
        text += f"\n\n🎯 BACKUP: {backup_id}" if backup_id else "\n\n🎯 Aucun BACKUP configure."
        await query.edit_message_text(text, reply_markup=build_servers_admin_menu())
        return

    if query.data == "admin:servers:add":
        state = admin_state(actor.id, context)
        state.clear()
        state["mode"] = "add_group"
        await query.edit_message_text(
            "➕ Forwarde ici n'importe quel message depuis le serveur a lier (le bot doit y etre admin).",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Annuler", callback_data="admin:servers")]]
            ),
        )
        return

    if query.data == "admin:servers:backup":
        state = admin_state(actor.id, context)
        state.clear()
        state["mode"] = "set_backup"
        await query.edit_message_text(
            "🎯 Forwarde ici n'importe quel message depuis le serveur BACKUP.\n\n"
            "Le bot doit y etre admin pour verifier les membres.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Annuler", callback_data="admin:servers")]]
            ),
        )
        return

    if query.data == "admin:servers:link":
        state = admin_state(actor.id, context)
        state.clear()
        state["mode"] = "set_backup_link"
        await query.edit_message_text(
            "🔗 Envoie le lien d'invitation du serveur BACKUP (ex: https://t.me/+...).",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Annuler", callback_data="admin:servers")]]
            ),
        )
        return

    if query.data == "admin:servers:remove":
        state = admin_state(actor.id, context)
        state.clear()
        state["mode"] = "remove_group"
        await query.edit_message_text(
            "🗑️ Forwarde ici n'importe quel message depuis le serveur a retirer de la liste.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Annuler", callback_data="admin:servers")]]
            ),
        )
        return

    if query.data == "admin:access":
        await query.edit_message_text(
            "👥 Gestion des acces",
            reply_markup=build_access_admin_menu(),
        )
        return

    if query.data == "admin:access:approved":
        await query.edit_message_text(
            "✅ Utilisateurs approuves",
            reply_markup=build_access_list_markup("approved"),
        )
        return

    if query.data == "admin:access:banned":
        await query.edit_message_text(
            "⛔ Utilisateurs bannis",
            reply_markup=build_access_list_markup("banned"),
        )
        return

    if query.data.startswith("admin:access:view:"):
        target_id = int(query.data.split(":")[-1])
        target = get_user(target_id)
        if not target:
            await query.edit_message_text(
                "❌ Utilisateur introuvable.",
                reply_markup=build_access_admin_menu(),
            )
            return
        await query.edit_message_text(
            format_access_user(target),
            parse_mode=ParseMode.HTML,
            reply_markup=build_access_user_menu(target),
        )
        return

    if query.data.startswith("admin:review:"):
        target_id = int(query.data.split(":")[-1])
        target = get_user(target_id)
        if not target:
            await edit_or_send(
                query,
                "❌ Utilisateur introuvable.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅️ Retour", callback_data="admin:pending")]]
                ),
            )
            return

        view_text, view_markup = build_pending_user_view(target_id, target)
        await edit_or_send(query, view_text, parse_mode=ParseMode.HTML, reply_markup=view_markup)
        return

    if query.data == "admin:broadcast":
        state = admin_state(actor.id, context)
        state.clear()
        state["mode"] = "broadcast_compose"
        await query.edit_message_text(
            "📣 Envoie maintenant le texte, la photo ou le document a diffuser. Le bot te demandera ensuite confirmation.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Annuler", callback_data="admin:broadcast:cancel")]]
            ),
        )
        return

    if query.data == "admin:broadcast:cancel":
        reset_admin_state(actor.id, context)
        await query.edit_message_text(
            "❌ Annonce annulee.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Retour", callback_data="admin:home")]]
            ),
        )
        return

    if query.data == "admin:broadcast:confirm":
        await confirm_broadcast(query, actor.id, context)
        return

    if query.data == "admin:broadcast:discard":
        reset_admin_state(actor.id, context)
        await query.edit_message_text(
            "Brouillon supprime.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Retour", callback_data="admin:home")]]
            ),
        )
        return

    if query.data.startswith("admin:review:"):
        target_id = int(query.data.split(":")[-1])
        target = get_user(target_id)
        if not target:
            await query.edit_message_text(
                "❌ Utilisateur introuvable.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅️ Retour", callback_data="admin:pending")]]
                ),
            )
            return
        await query.edit_message_text(
            format_user_for_admin(target),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                build_approval_markup(target_id).inline_keyboard
                + [[InlineKeyboardButton("⬅️ Retour", callback_data="admin:pending")]]
            ),
        )
        return

    for action in ("approve", "reject", "ban", "unban"):
        prefix = f"admin:{action}:"
        if query.data.startswith(prefix):
            target_id = int(query.data.split(":")[-1])
            await handle_admin_decision(query, target_id, action, context)
            return


async def handle_captcha_callback(query, user: dict, context: ContextTypes.DEFAULT_TYPE) -> None:
    if user.get("status") == "banned":
        await query.edit_message_text("⛔ Acces refuse.")
        return

    if user.get("status") == "approved":
        await send_approved_content(query.from_user.id, context)
        return

    if user.get("status") == "pending_approval":
        await query.edit_message_text(PENDING_MESSAGE)
        return

    if user.get("status") == "pending_intro":
        await query.edit_message_text(
            "✅ Verification deja validee. Envoie maintenant ta presentation par message."
        )
        return

    if user.get("status") == "pending_backup":
        await query.edit_message_text(backup_join_text(), reply_markup=backup_join_markup())
        return

    if user.get("status") != "pending_captcha":
        await query.edit_message_text("🔁 Relance /start pour recommencer la verification.")
        return

    challenge = user.get("last_challenge") or {}
    picked = int(query.data.split(":")[-1])

    if picked != challenge.get("answer"):
        new_challenge = new_captcha()
        user["last_challenge"] = new_challenge
        save_data()
        await query.edit_message_text(
            f"❌ Mauvaise reponse. Reessaie.\n\n🤖 Verification humaine: {new_challenge['question']}",
            reply_markup=captcha_markup(new_challenge),
        )
        return

    user["human_verified"] = True
    if REQUIRE_INTRO:
        set_status(user, "pending_intro")
        save_data()
        await query.edit_message_text(
            "✅ Verification validee.\n\n📝 Envoie maintenant une petite presentation pour demander l'acces. Exemple: qui t'a invite ou pourquoi tu veux acceder au bot."
        )
        return

    await proceed_after_verification(user, context, reply_target=query, is_callback=True)


async def handle_backup_check(query, user: dict, context: ContextTypes.DEFAULT_TYPE) -> None:
    if user.get("status") == "banned":
        await query.edit_message_text("⛔ Acces refuse.")
        return

    if user.get("status") == "approved":
        await send_approved_content(query.from_user.id, context)
        return

    if user.get("status") == "pending_approval":
        await query.edit_message_text(PENDING_MESSAGE)
        return

    if user.get("status") != "pending_backup":
        await query.edit_message_text("🔁 Relance /start pour continuer la verification.")
        return

    await proceed_after_verification(user, context, reply_target=query, is_callback=True)


async def handle_admin_decision(query, target_id: int, action: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    target = get_user(target_id)
    if not target:
        await query.edit_message_text(
            "❌ Utilisateur introuvable.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Retour", callback_data="admin:home")]]
            ),
        )
        return

    previous_status = target.get("status")
    back_callback = "admin:pending"
    if action == "approve":
        set_status(target, "approved")
        target["approved_at"] = utc_now()
        target["subscribed"] = True
        text = "✅ Utilisateur approuve."
        back_callback = "admin:pending"
    elif action == "reject":
        set_status(target, "rejected")
        target["rejected_at"] = utc_now()
        text = "❌ Utilisateur refuse."
        notify_text = REJECTED_MESSAGE
        reply_markup = None
        back_callback = "admin:pending"
    elif action == "unban":
        set_status(target, "approved")
        target["subscribed"] = True
        text = "✅ Utilisateur debanni."
        back_callback = "admin:access:banned"
    else:
        set_status(target, "banned")
        target["banned_at"] = utc_now()
        target["subscribed"] = False
        text = "⛔ Utilisateur banni."
        notify_text = "⛔ Acces refuse."
        reply_markup = None
        back_callback = "admin:pending" if previous_status == "pending_approval" else "admin:access:approved"

    save_data()

    if action in ("ban", "unban"):
        sync_results = (
            await ban_everywhere(context, target_id)
            if action == "ban"
            else await unban_everywhere(context, target_id)
        )
        extra = format_group_results(sync_results)
        if extra:
            text += f"\n{extra}"
        elif not linked_groups():
            text += "\nℹ️ Aucun serveur lie."

    try:
        if action == "approve":
            await send_approved_content(target_id, context)
        elif action == "unban":
            await send_approved_content(target_id, context)
        else:
            await context.bot.send_message(chat_id=target_id, text=notify_text, reply_markup=reply_markup)
    except Exception as exc:
        LOGGER.warning("Impossible de notifier l'utilisateur %s: %s", target_id, exc)

    await edit_or_send(
        query,
        f"{text}\n\n{format_access_user(target)}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Retour", callback_data=back_callback)]]
        ),
    )
    return

    await query.edit_message_text(
        f"{text}\n\n{format_access_user(target)}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Retour", callback_data=back_callback)]]
        ),
    )


async def confirm_broadcast(query, admin_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = admin_state(admin_id, context)
    draft = state.get("broadcast_draft")
    if not draft:
        await query.edit_message_text(
            "📭 Aucun brouillon a envoyer.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Retour", callback_data="admin:home")]]
            ),
        )
        return

    recipients = [
        int(user["id"])
        for user in DATA["users"].values()
        if user.get("status") == "approved" and user.get("subscribed")
    ]

    sent = 0
    failed = 0
    for recipient in recipients:
        try:
            await context.bot.copy_message(
                chat_id=recipient,
                from_chat_id=draft["chat_id"],
                message_id=draft["message_id"],
            )
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as exc:
            failed += 1
            user = get_user(recipient)
            if user:
                user["subscribed"] = False
            LOGGER.warning("Echec diffusion vers %s: %s", recipient, exc)

    save_data()
    reset_admin_state(admin_id, context)
    await query.edit_message_text(
        f"Annonce envoyee.\n\nSucces: {sent}\nEchecs: {failed}",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Retour", callback_data="admin:home")]]
        ),
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_private_chat(update):
        return

    telegram_user = update.effective_user
    message = update.message
    if telegram_user is None or message is None:
        return

    user = ensure_user(telegram_user)

    if is_admin(telegram_user.id):
        state = admin_state(telegram_user.id, context)
        mode = state.get("mode")

        if mode == "welcome_text_edit":
            approved_post_settings()["caption"] = message.text or ""
            save_data()
            reset_admin_state(telegram_user.id, context)
            await message.reply_text(
                "✅ Texte d'accueil mis a jour.",
                reply_markup=build_welcome_admin_menu(),
            )
            return

        if mode == "button_add_text":
            button_text = (message.text or "").strip()
            if not button_text:
                await message.reply_text("❌ Envoie un nom de bouton valide.")
                return
            state["pending_button_text"] = button_text
            state["mode"] = "button_add_url"
            await message.reply_text("🔗 Envoie maintenant le lien du nouveau bouton.")
            return

        if mode == "button_add_url":
            button_url = (message.text or "").strip()
            if not button_url.startswith(("https://", "http://", "tg://")):
                await message.reply_text("❌ Envoie un lien valide qui commence par https://, http:// ou tg://")
                return
            approved_post_settings()["buttons"].append(
                {"text": state.get("pending_button_text", "Nouveau bouton"), "url": button_url}
            )
            save_data()
            reset_admin_state(telegram_user.id, context)
            await message.reply_text(
                "✅ Bouton ajoute.",
                reply_markup=build_buttons_admin_menu(),
            )
            return

        if mode == "button_edit_text":
            index = int(state.get("button_index", -1))
            button = get_button(index)
            new_text = (message.text or "").strip()
            if not button or not new_text:
                await message.reply_text("❌ Impossible de modifier ce bouton.")
                return
            button["text"] = new_text
            save_data()
            reset_admin_state(telegram_user.id, context)
            await message.reply_text(
                "✅ Nom du bouton modifie.",
                reply_markup=build_buttons_admin_menu(),
            )
            return

        if mode == "button_edit_url":
            index = int(state.get("button_index", -1))
            button = get_button(index)
            new_url = (message.text or "").strip()
            if not button:
                await message.reply_text("❌ Bouton introuvable.")
                return
            if not new_url.startswith(("https://", "http://", "tg://")):
                await message.reply_text("❌ Envoie un lien valide qui commence par https://, http:// ou tg://")
                return
            button["url"] = new_url
            save_data()
            reset_admin_state(telegram_user.id, context)
            await message.reply_text(
                "✅ Lien du bouton modifie.",
                reply_markup=build_buttons_admin_menu(),
            )
            return

        if mode == "set_backup_link":
            link = (message.text or "").strip()
            if not link.startswith(("https://t.me/", "tg://")):
                await message.reply_text("❌ Envoie un lien d'invitation valide (https://t.me/...).")
                return
            set_backup_invite(link)
            reset_admin_state(telegram_user.id, context)
            await message.reply_text(
                "✅ Lien BACKUP mis a jour.",
                reply_markup=build_servers_admin_menu(),
            )
            return

        if state.get("mode") == "broadcast_compose":
            state["broadcast_draft"] = {
                "chat_id": message.chat_id,
                "message_id": message.message_id,
            }
            state["mode"] = "broadcast_confirm"
            await message.reply_text(
                "📨 Brouillon recu. Confirme l'envoi de cette annonce.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("✅ Confirmer", callback_data="admin:broadcast:confirm")],
                        [InlineKeyboardButton("🗑️ Supprimer le brouillon", callback_data="admin:broadcast:discard")],
                    ]
                ),
            )
            return

        if not state.get("mode"):
            await message.reply_text("🔧 Utilise /admin pour ouvrir le panel admin.")
            return

    if user.get("status") == "pending_intro":
        intro_text = (message.text or "").strip()
        if not intro_text:
            await message.reply_text(
                "📝 Envoie au moins un petit message de presentation."
            )
            return

        if MIN_INTRO_LENGTH > 1 and len(intro_text) < MIN_INTRO_LENGTH:
            await message.reply_text(
                f"📝 Presentation trop courte. Envoie au moins {MIN_INTRO_LENGTH} caracteres."
            )
            return

        user["intro_text"] = intro_text
        user["risk_flags"] = build_risk_flags(user)
        await proceed_after_verification(user, context, reply_target=None, is_callback=False)
        return

    if user.get("status") == "pending_backup":
        await message.reply_text(backup_join_text(), reply_markup=backup_join_markup())
        return

    if user.get("status") == "approved":
        await send_approved_content(message.chat_id, context)
        return

    if user.get("status") == "pending_approval":
        await message.reply_text(PENDING_MESSAGE)
        return

    if user.get("status") == "banned":
        await message.reply_text("⛔ Acces refuse.")
        return

    await message.reply_text("👋 Utilise /start pour commencer.")


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_private_chat(update):
        return

    telegram_user = update.effective_user
    message = update.effective_message
    if telegram_user is None or message is None:
        return

    ensure_user(telegram_user)

    if is_admin(telegram_user.id):
        state = admin_state(telegram_user.id, context)
        if state.get("mode") == "welcome_photo_edit" and message.photo:
            approved_post_settings()["photo_file_id"] = message.photo[-1].file_id
            save_data()
            reset_admin_state(telegram_user.id, context)
            await message.reply_text(
                "✅ Image d'accueil mise a jour.",
                reply_markup=build_welcome_admin_menu(),
            )
            return

        if state.get("mode") == "broadcast_compose":
            state["broadcast_draft"] = {
                "chat_id": message.chat_id,
                "message_id": message.message_id,
            }
            state["mode"] = "broadcast_confirm"
            await message.reply_text(
                "📨 Brouillon recu. Confirme l'envoi de cette annonce.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("✅ Confirmer", callback_data="admin:broadcast:confirm")],
                        [InlineKeyboardButton("🗑️ Supprimer le brouillon", callback_data="admin:broadcast:discard")],
                    ]
                ),
            )
            return

        if not state.get("mode"):
            await message.reply_text("🔧 Utilise /admin pour ouvrir le panel admin.")
            return

    await message.reply_text("📝 Envoie du texte pour la verification, ou utilise /start.")


async def handle_forwarded(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_private_chat(update):
        return

    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return

    if not is_admin(user.id):
        await message.reply_text("ℹ️ Envoi forwarde recu.")
        return

    state = admin_state(user.id, context)
    forwarded_chat = message.forward_from_chat

    if state.get("mode") == "add_group" and forwarded_chat:
        add_linked_group(forwarded_chat.id, forwarded_chat.title or "")
        reset_admin_state(user.id, context)
        await message.reply_text(
            f"✅ Serveur lie: {forwarded_chat.title or forwarded_chat.id} ({forwarded_chat.id})",
            reply_markup=build_servers_admin_menu(),
        )
        return

    if state.get("mode") == "set_backup" and forwarded_chat:
        set_backup_chat_id(forwarded_chat.id)
        add_linked_group(forwarded_chat.id, forwarded_chat.title or "")
        reset_admin_state(user.id, context)
        await message.reply_text(
            f"✅ Serveur BACKUP defini: {forwarded_chat.title or forwarded_chat.id} ({forwarded_chat.id})",
            reply_markup=build_servers_admin_menu(),
        )
        return

    if state.get("mode") == "remove_group" and forwarded_chat:
        remove_linked_group(forwarded_chat.id)
        reset_admin_state(user.id, context)
        await message.reply_text(
            f"🗑️ Serveur retire: {forwarded_chat.title or forwarded_chat.id}",
            reply_markup=build_servers_admin_menu(),
        )
        return

    await message.reply_text("ℹ️ Envoi forwarde recu. Utilise /admin pour le menu admin.")


async def chat_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    join = update.chat_join_request
    if join is None:
        return

    chat_id = join.chat.id
    user_id = join.from_user.id
    add_linked_group(chat_id)

    record = get_user(user_id)
    status = record.get("status") if record else "unknown"
    backup_chat_id = get_backup_chat_id()

    if status == "approved" or (
        backup_chat_id and chat_id == backup_chat_id and status == "pending_backup"
    ):
        try:
            await context.bot.approve_chat_join_request(chat_id=chat_id, user_id=user_id)
            LOGGER.info("Join request accepte: user %s -> chat %s", user_id, chat_id)
        except Exception as exc:
            LOGGER.warning("Impossible d'accepter la demande %s -> %s: %s", user_id, chat_id, exc)
    else:
        try:
            await context.bot.decline_chat_join_request(chat_id=chat_id, user_id=user_id)
            LOGGER.info("Join request refuse: user %s -> chat %s (statut %s)", user_id, chat_id, status)
        except Exception as exc:
            LOGGER.warning("Impossible de refuser la demande %s -> %s: %s", user_id, chat_id, exc)


async def my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None or chat.type not in ("group", "supergroup", "channel"):
        return

    member_update = update.my_chat_member
    if member_update is None:
        return

    new_status = member_update.new_chat_member.status
    if new_status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER):
        add_linked_group(chat.id, chat.title or "")
        LOGGER.info("Bot admin dans %s (%s)", chat.id, chat.title)
    elif new_status in (ChatMember.LEFT, ChatMember.KICKED, ChatMember.RESTRICTED):
        remove_linked_group(chat.id)
        LOGGER.info("Bot retire de %s (%s)", chat.id, chat.title)


async def auto_configure_backup(application: Application) -> None:
    ensure_data()
    if get_backup_chat_id():
        return
    for group_id in linked_groups():
        try:
            chat = await application.bot.get_chat(chat_id=group_id)
        except Exception:
            continue
        title = (chat.title or "").lower()
        if "backup" in title or "secours" in title:
            set_backup_chat_id(group_id)
            set_group_title(group_id, chat.title or "")
            LOGGER.info("BACKUP auto-configure: %s (%s)", group_id, chat.title)
            return


async def verify_linked_groups(application: Application) -> None:
    for group_id in linked_groups():
        try:
            member = await application.bot.get_chat_member(
                chat_id=group_id, user_id=application.bot.id
            )
            if member.status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER):
                LOGGER.info(
                    "Admin OK dans %s (%s)", group_id, group_title(group_id)
                )
            else:
                LOGGER.warning(
                    "Plus admin dans %s (%s) status=%s",
                    group_id,
                    group_title(group_id),
                    member.status,
                )
        except Exception as exc:
            LOGGER.warning("Verif admin dans %s impossible: %s", group_id, exc)


async def post_init(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Commencer et ouvrir l'accueil"),
            BotCommand("stop", "Couper les annonces"),
            BotCommand("admin", "Ouvrir le panel admin"),
            BotCommand("ban", "Bannir un utilisateur par ID"),
            BotCommand("unban", "Debannir un utilisateur par ID"),
        ]
    )
    try:
        await auto_configure_backup(application)
        await verify_linked_groups(application)
    except Exception as exc:
        LOGGER.warning("Verification de depart impossible: %s", exc)


def ensure_event_loop() -> None:
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def main() -> None:
    if not TOKEN:
        raise RuntimeError("Configure BOT_TOKEN avant de lancer le bot.")
    if not ADMIN_IDS:
        raise RuntimeError(
            "Configure ADMIN_ID_1 et/ou ADMIN_ID_2, ou utilise ADMIN_ID / ADMIN_IDS."
        )

    ensure_event_loop()
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("servers", servers_command))
    app.add_handler(ChatMemberHandler(my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(ChatJoinRequestHandler(chat_join_request))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.FORWARDED, handle_forwarded))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_media))
    app.add_error_handler(error_handler)
    app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
