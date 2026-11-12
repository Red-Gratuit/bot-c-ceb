import asyncio
import logging
import os
import sqlite3
from pathlib import Path

from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ---------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------
# Le token est lu dans la variable d'environnement BOT_TOKEN
# (à définir sur Railway, ou dans un fichier .env en local).
def _load_dotenv() -> None:
    """Charge les variables d'un fichier .env local (jamais commité)."""
    env_file = Path(__file__).with_name(".env")
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

BANNER_IMAGE = Path(__file__).with_name("banner.png")

WELCOME_TEXT = (
    "Bienvenue sur la boutique de Sponge Exotic !\n"
    "🥳\n\n"
    "Accédez à notre shop,\n"
    "Rejoignez notre canal telegram ou notre\n"
    "snapchat 👻\n\n"
    "Nous vous proposons un large choix de produit\n"
    "afin de vous satisfaire,\n"
    "En cas de problème, n'oubliez de rejoindre tout\n"
    "nos réseaux pour toujours nous retrouver !"
)

SNAPCHAT_URL = "https://snapchat.com/add/m_mara59"
BOUTIQUE_URL = "https://nocturne-neon-boutique.lovable.app"

# Chemin de la base de données SQLite qui stocke les chat_id des utilisateurs.
# Sur Railway, on utilise /data (volume persistant). En local, bot.db à côté du script.
if os.environ.get("RAILWAY_PUBLIC_DOMAIN"):
    DB_PATH = Path(os.environ.get("DATABASE_PATH", "/data/bot.db"))
else:
    DB_PATH = Path(os.environ.get("DATABASE_PATH", str(Path(__file__).with_name("bot.db"))))

# ---------------------------------------------------------------
# JOURNALISATION
# ---------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------
# BASE DE DONNÉES (stockage des utilisateurs pour /broadcast)
# ---------------------------------------------------------------
_db_lock = asyncio.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        " chat_id INTEGER PRIMARY KEY,"
        " username TEXT,"
        " first_name TEXT"
        ")"
    )
    conn.commit()
    return conn


def _add_user_sync(chat_id: int, username: str | None, first_name: str | None) -> None:
    conn = _connect()
    conn.execute(
        "INSERT INTO users (chat_id, username, first_name) VALUES (?, ?, ?) "
        "ON CONFLICT(chat_id) DO UPDATE SET "
        "username = excluded.username, first_name = excluded.first_name",
        (chat_id, username, first_name),
    )
    conn.commit()
    conn.close()


def _get_all_chat_ids_sync() -> list[int]:
    conn = _connect()
    rows = conn.execute("SELECT chat_id FROM users").fetchall()
    conn.close()
    return [row[0] for row in rows]


async def add_user(chat_id: int, username: str | None, first_name: str | None) -> None:
    async with _db_lock:
        await asyncio.to_thread(_add_user_sync, chat_id, username, first_name)


async def get_all_chat_ids() -> list[int]:
    async with _db_lock:
        return await asyncio.to_thread(_get_all_chat_ids_sync)


# ---------------------------------------------------------------
# BOUTONS
# ---------------------------------------------------------------
def _welcome_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("👻 Snapchat", url=SNAPCHAT_URL)],
        [InlineKeyboardButton("🛍️ Boutique", url=BOUTIQUE_URL)],
    ]
    return InlineKeyboardMarkup(keyboard)


# ---------------------------------------------------------------
# COMMANDES
# ---------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is not None:
        await add_user(chat.id, chat.username, chat.first_name)
    logger.info("/start reçu de %s", update.effective_chat.id)

    if BANNER_IMAGE.exists():
        with open(BANNER_IMAGE, "rb") as photo:
            await update.effective_message.reply_photo(
                photo=photo,
                caption=WELCOME_TEXT,
                reply_markup=_welcome_keyboard(),
            )
    else:
        await update.effective_message.reply_text(
            WELCOME_TEXT,
            reply_markup=_welcome_keyboard(),
        )


async def any_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is not None:
        await add_user(chat.id, chat.username, chat.first_name)

    if BANNER_IMAGE.exists():
        with open(BANNER_IMAGE, "rb") as photo:
            await update.effective_message.reply_photo(
                photo=photo,
                caption=WELCOME_TEXT,
                reply_markup=_welcome_keyboard(),
            )
    else:
        await update.effective_message.reply_text(
            WELCOME_TEXT,
            reply_markup=_welcome_keyboard(),
        )


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envoie un message à tous les utilisateurs qui ont déjà parlé au bot.

    Accessible à n'importe qui, comme demandé.
    """
    if not context.args:
        await update.effective_message.reply_text(
            "Utilisation : /broadcast <ton message>"
        )
        return

    text = " ".join(context.args)
    chat_ids = await get_all_chat_ids()
    if not chat_ids:
        await update.effective_message.reply_text(
            "Aucun utilisateur enregistré pour le moment."
        )
        return

    sent = 0
    failed = 0
    for chat_id in chat_ids:
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
            sent += 1
        except Exception as exc:  # noqa: BLE001 — on continue malgré les échecs
            logger.warning("Échec d'envoi à %s : %s", chat_id, exc)
            failed += 1
        # petite pause pour ne pas dépasser les limites de l'API
        await asyncio.sleep(0.05)

    await update.effective_message.reply_text(
        f"✅ Diffusion terminée : {sent} envoyé(s), {failed} échec(s)."
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Erreur pendant le traitement d'une mise à jour :", exc_info=context.error)


# ---------------------------------------------------------------
# POINT D'ENTRÉE
# ---------------------------------------------------------------
_application: Application | None = None


async def _webhook_handler(request: web.Request) -> web.Response:
    data = await request.json()
    update = Update.de_json(data, _application.bot)
    await _application.update_queue.put(update)
    return web.Response(status=200)


async def _health_handler(request: web.Request) -> web.Response:
    return web.Response(status=200, text="OK")


async def _run_webhook(application: Application, webhook_url: str) -> None:
    port = int(os.environ.get("PORT", "8443"))

    await application.initialize()
    await application.bot.set_webhook(url=webhook_url)
    await application.start()

    web_app = web.Application()
    web_app.router.add_get("/health", _health_handler)
    web_app.router.add_post("/webhook", _webhook_handler)

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logger.info("Webhook actif sur le port %s (URL : %s)", port, webhook_url)
    await asyncio.Event().wait()


def _build_application(token: str) -> Application:
    global _application
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, any_message))
    application.add_error_handler(error_handler)
    _application = application
    return application


def main() -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit(
            "BOT_TOKEN manquant. Définis la variable d'environnement BOT_TOKEN "
            "(sur Railway) ou crée un fichier .env contenant BOT_TOKEN=..."
        )
    application = _build_application(token)

    # Sur Railway, RAILWAY_PUBLIC_DOMAIN est défini automatiquement → mode webhook.
    webhook_url = os.environ.get("WEBHOOK_URL")
    if not webhook_url and os.environ.get("RAILWAY_PUBLIC_DOMAIN"):
        webhook_url = f"https://{os.environ['RAILWAY_PUBLIC_DOMAIN']}/webhook"

    logger.info("Démarrage du bot Sponge Exotic...")

    if webhook_url:
        asyncio.run(_run_webhook(application, webhook_url))
    else:
        logger.info("Mode polling local (Ctrl+C pour arrêter).")
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )


if __name__ == "__main__":
    main()
