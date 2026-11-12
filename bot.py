import asyncio
import logging
import os
import sqlite3
from pathlib import Path

from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
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
    "BIENVENUE CHEZ SpongeXotic 🧽🔌\n\n"
    "Nous vous souhaitons la bienvenue dans notre univers.\n\n"
    "Une boutique aux saveurs variées, pensée pour tous les goûts.\n\n"
    "🫟Le goût qui fait la différence.🫟\n"
    "✨ Le service qui fait l’excellence.✨\n\n"
    "━━━━━━━━━━━━━━\n\n"
    "🌐 NOS PLATEFORMES OFFICIELLES\n\n"
    "📢 Canal Telegram\n"
    "💬 Contact Telegram\n"
    "👻 Snapchat\n"
    "📲 Mini-App\n\n"
    "━━━━━━━━━━━━━━\n\n"
    "🪼 SPONGEXOTIC®\n"
    "L’exotisme dans l’ADN."
)

SNAPCHAT_URL = "https://snapchat.com/add/m_mara59"
BOUTIQUE_URL = "https://nocturne-neon-boutique.lovable.app"

# Chemin de la base de données SQLite qui stocke les chat_id des utilisateurs.
# Priorité : DATABASE_PATH > volume Railway /data s'il existe > bot.db local.
def _resolve_db_path() -> Path:
    explicit = os.environ.get("DATABASE_PATH")
    if explicit:
        return Path(explicit)
    volume = Path("/data")
    if volume.is_dir():
        return volume / "bot.db"
    return Path(__file__).with_name("bot.db")


DB_PATH = _resolve_db_path()

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
        [InlineKeyboardButton("🛍️ Boutique", web_app=WebAppInfo(url=BOUTIQUE_URL))],
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
    try:
        data = await request.json()
    except Exception:  # noqa: BLE001 — requête malformée : on répond 400
        logger.warning("Requête webhook invalide reçue")
        return web.Response(status=400)

    update = Update.de_json(data, _application.bot)
    if update is not None:
        await _application.update_queue.put(update)
    return web.Response(status=200)


async def _health_handler(request: web.Request) -> web.Response:
    return web.Response(status=200, text="OK")


async def _start_health_server(port: int, with_webhook: bool) -> web.AppRunner | None:
    """Démarre un petit serveur HTTP pour le healthcheck Railway.

    En mode webhook, il sert aussi /webhook. En mode polling, il ne sert que
    /health, ce qui suffit à Railway pour considérer le service comme sain.
    """
    web_app = web.Application()
    web_app.router.add_get("/health", _health_handler)
    if with_webhook:
        web_app.router.add_post("/webhook", _webhook_handler)

    runner = web.AppRunner(web_app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    try:
        await site.start()
    except OSError as exc:
        logger.warning("Serveur HTTP non démarré sur le port %s : %s", port, exc)
        await runner.cleanup()
        return None
    logger.info("Serveur HTTP actif sur le port %s", port)
    return runner


async def _run(application: Application, webhook_url: str | None) -> None:
    port = int(os.environ.get("PORT", "8080"))

    await application.initialize()
    runner = await _start_health_server(port, with_webhook=bool(webhook_url))

    if webhook_url:
        await application.bot.set_webhook(
            url=webhook_url,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
        logger.info("Mode webhook (URL : %s)", webhook_url)
    else:
        # Pas de domaine public : on repasse en polling.
        await application.bot.delete_webhook(drop_pending_updates=True)
        logger.info("Mode polling (Ctrl+C pour arrêter)")

    await application.start()
    if not webhook_url:
        await application.updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )

    try:
        await asyncio.Event().wait()
    finally:
        if not webhook_url:
            await application.updater.stop()
        await application.stop()
        await application.shutdown()
        if runner is not None:
            await runner.cleanup()


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
    # Sinon (ou si WEBHOOK_URL est fourni), on garde le polling.
    webhook_url = os.environ.get("WEBHOOK_URL")
    if not webhook_url and os.environ.get("RAILWAY_PUBLIC_DOMAIN"):
        webhook_url = f"https://{os.environ['RAILWAY_PUBLIC_DOMAIN']}/webhook"

    logger.info("Démarrage du bot Sponge Exotic...")
    try:
        asyncio.run(_run(application, webhook_url))
    except KeyboardInterrupt:
        logger.info("Arrêt demandé.")


if __name__ == "__main__":
    main()
