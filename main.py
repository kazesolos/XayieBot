import logging
from datetime import datetime, timedelta

from telegram import Update, ChatPermissions
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ------------- CONFIG -------------
BOT_TOKEN = "8532502485:AAEFHx_gZhDvbgoGg8jK9o8ugT3BX8vOvas"  # <-- paste your token here safely
OWNER = "@k4_ze"
BOT_NAME = "XayieBot"

# ------------- LOGGING -------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(BOT_NAME)


# ------------ HELPERS ------------

async def is_admin(update: Update, user_id: int) -> bool:
    """Check if given user is admin in this chat."""
    chat = update.effective_chat
    member = await chat.get_member(user_id)
    return member.status in ("administrator", "creator")


def get_target_from_reply(update: Update):
    """Return (user, message) from replied message, else (None, None)."""
    msg = update.effective_message
    if not msg.reply_to_message:
        return None, None
    return msg.reply_to_message.from_user, msg.reply_to_message


# ------------ BASIC COMMANDS ------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat

    if chat.type == "private":
        text = (
            f"⚔️ **{BOT_NAME} is online**\n\n"
            f"Owner: {OWNER}\n\n"
            "I am a lightweight **group management bot**.\n\n"
            "__How to use:__\n"
            "1. Add me to your group\n"
            "2. Promote me as admin (can delete, restrict, ban)\n"
            "3. Disable privacy mode in BotFather\n\n"
            "Use /help to see my commands."
        )
    else:
        text = f"{BOT_NAME} is alive here ✅ Use /help in private chat for full commands."

    await update.message.reply_text(text, parse_mode="Markdown")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"**{BOT_NAME} – Group Management Commands**\n\n"
        "__Warn System__\n"
        "/warn (reply) – Warn a user (3 warns = auto ban)\n"
        "/warns (reply) – Check a user's warns\n"
        "/clearwarns (reply) – Reset warns\n\n"
        "__Moderation__\n"
        "/mute (reply) [minutes] – Mute a user (no time = forever)\n"
        "/unmute (reply) – Unmute user\n"
        "/ban (reply) – Ban user\n"
        "/kick (reply) – Kick user (ban + unban)\n"
        "/del (reply) – Delete the replied message\n\n"
        "__Other__\n"
        "/ping – Check if I am responsive\n\n"
        "_Only group admins can use moderation commands._"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Pong! 🏓")


# ------------ WARN SYSTEM ------------

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    from_user = update.effective_user

    # Only admins can warn
    if not await is_admin(update, from_user.id):
        return await msg.reply_text("❌ Only admins can use /warn.")

    target_user, _ = get_target_from_reply(update)
    if not target_user:
        return await msg.reply_text("Reply to a user's message and use /warn.")

    if await is_admin(update, target_user.id):
        return await msg.reply_text("I will not warn an admin.")

    chat_data = context.chat_data
    warns = chat_data.setdefault("warns", {})
    user_warns = warns.get(target_user.id, 0) + 1
    warns[target_user.id] = user_warns

    if user_warns >= 3:
        # Ban user
        try:
            await chat.ban_member(target_user.id)
            warns[target_user.id] = 0  # reset after ban
            await msg.reply_text(
                f"🚫 {target_user.mention_html()} reached 3 warns and has been **banned**.",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(e)
            await msg.reply_text("Error while trying to ban. Am I an admin?")
    else:
        await msg.reply_text(
            f"⚠️ {target_user.mention_html()} has been warned. "
            f"Warns: {user_warns}/3",
            parse_mode="HTML",
        )


async def warns_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat_data = context.chat_data

    target_user, _ = get_target_from_reply(update)
    if not target_user:
        return await msg.reply_text("Reply to a user and use /warns.")

    warns = chat_data.get("warns", {})
    user_warns = warns.get(target_user.id, 0)
    await msg.reply_text(
        f"📊 {target_user.mention_html()} currently has {user_warns}/3 warns.",
        parse_mode="HTML",
    )


async def clear_warns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    from_user = update.effective_user

    if not await is_admin(update, from_user.id):
        return await msg.reply_text("❌ Only admins can use /clearwarns.")

    target_user, _ = get_target_from_reply(update)
    if not target_user:
        return await msg.reply_text("Reply to a user and use /clearwarns.")

    warns = context.chat_data.setdefault("warns", {})
    warns[target_user.id] = 0
    await msg.reply_text(
        f"✅ All warns for {target_user.mention_html()} have been cleared.",
        parse_mode="HTML",
    )


# ------------ MUTE / UNMUTE / BAN / KICK / DELETE ------------

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    from_user = update.effective_user

    if not await is_admin(update, from_user.id):
        return await msg.reply_text("❌ Only admins can use /mute.")

    target_user, _ = get_target_from_reply(update)
    if not target_user:
        return await msg.reply_text("Reply to a user and use /mute [minutes(optional)].")

    if await is_admin(update, target_user.id):
        return await msg.reply_text("I cannot mute an admin.")

    until = None
    minutes = None
    if context.args:
        try:
            minutes = int(context.args[0])
            until = datetime.utcnow() + timedelta(minutes=minutes)
        except ValueError:
            return await msg.reply_text("Invalid time. Example: /mute 10")

    permissions = ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
    )

    try:
        await chat.restrict_member(target_user.id, permissions=permissions, until_date=until)
        if minutes:
            await msg.reply_text(
                f"🔇 {target_user.mention_html()} has been muted for {minutes} minutes.",
                parse_mode="HTML",
            )
        else:
            await msg.reply_text(
                f"🔇 {target_user.mention_html()} has been muted indefinitely.",
                parse_mode="HTML",
            )
    except Exception as e:
        logger.error(e)
        await msg.reply_text("Failed to mute. Check my admin permissions.")


async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    from_user = update.effective_user

    if not await is_admin(update, from_user.id):
        return await msg.reply_text("❌ Only admins can use /unmute.")

    target_user, _ = get_target_from_reply(update)
    if not target_user:
        return await msg.reply_text("Reply to a user and use /unmute.")

    permissions = ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
    )

    try:
        await chat.restrict_member(target_user.id, permissions=permissions)
        await msg.reply_text(
            f"🔊 {target_user.mention_html()} has been unmuted.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(e)
        await msg.reply_text("Failed to unmute. Check my admin permissions.")


async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    from_user = update.effective_user

    if not await is_admin(update, from_user.id):
        return await msg.reply_text("❌ Only admins can use /ban.")

    target_user, _ = get_target_from_reply(update)
    if not target_user:
        return await msg.reply_text("Reply to a user and use /ban.")

    if await is_admin(update, target_user.id):
        return await msg.reply_text("I will not ban an admin.")

    try:
        await chat.ban_member(target_user.id)
        await msg.reply_text(
            f"🚫 {target_user.mention_html()} has been banned.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(e)
        await msg.reply_text("Failed to ban. Check my admin permissions.")


async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    from_user = update.effective_user

    if not await is_admin(update, from_user.id):
        return await msg.reply_text("❌ Only admins can use /kick.")

    target_user, _ = get_target_from_reply(update)
    if not target_user:
        return await msg.reply_text("Reply to a user and use /kick.")

    if await is_admin(update, target_user.id):
        return await msg.reply_text("I will not kick an admin.")

    try:
        await chat.ban_member(target_user.id)
        await chat.unban_member(target_user.id)
        await msg.reply_text(
            f"👢 {target_user.mention_html()} has been kicked.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(e)
        await msg.reply_text("Failed to kick. Check my admin permissions.")


async def delete_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    from_user = update.effective_user

    if not await is_admin(update, from_user.id):
        return await msg.reply_text("❌ Only admins can use /del.")

    if not msg.reply_to_message:
        return await msg.reply_text("Reply to the message you want to delete and use /del.")

    try:
        await msg.reply_to_message.delete()
        await msg.delete()
    except Exception as e:
        logger.error(e)


# ------------ WELCOME NEW MEMBERS ------------

async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    for member in update.message.new_chat_members:
        await update.message.reply_text(
            f"👋 Welcome {member.mention_html()} to {chat.title}!\n"
            "Follow the rules and enjoy your stay.",
            parse_mode="HTML",
        )


# ------------ ANTI-SPAM / ANTI-LINK ------------

BLOCKED_WORDS = [
    "free nitro",
    "join my group",
    "crypto scam",
]

async def anti_spam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        return

    # Ignore admins
    if await is_admin(update, user.id):
        return

    text = (msg.text or msg.caption or "").lower()

    has_link = "t.me/" in text or "http://" in text or "https://" in text
    blocked = any(word in text for word in BLOCKED_WORDS)

    if has_link or blocked:
        try:
            await msg.delete()
            await chat.send_message(
                f"🚫 {user.mention_html()}, links and promotions are not allowed.",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(e)


# ------------ MAIN APP ------------

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ping", ping))

    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("warns", warns_cmd))
    app.add_handler(CommandHandler("clearwarns", clear_warns))

    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("kick", kick))
    app.add_handler(CommandHandler("del", delete_msg))

    # Welcome new members
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))

    # Anti-spam/anti-link
    app.add_handler(
        MessageHandler(
            filters.TEXT | filters.CAPTION,
            anti_spam,
        )
    )

    logger.info(f"{BOT_NAME} is starting...")
    await app.run_polling()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())