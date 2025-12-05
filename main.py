import logging
from datetime import datetime, timedelta

import requests
from telegram import Update, ChatPermissions
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ------------- CONFIG -------------
BOT_TOKEN = "8532502485:AAEk1ZzS12mxm5D1g3laehbjAzitgKkNVsg"   # <-- your Telegram bot token
GROQ_API_KEY = "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"      # <-- your Groq API key
GROQ_MODEL = "llama-3.1-8b-instant"

OWNER = "@k4_ze"
BOT_NAME = "XayieBot"

# ------------- LOGGING -------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(BOT_NAME)

# ------------- CONSTANTS -------------

DM_INFO_TEXT = (
    f"Owner: {OWNER}\n\n"
    "I can do two things:\n"
    "• Work as a smart AI assistant in this chat.\n"
    "• Manage groups (warn/mute/ban/kick, anti-link, etc.).\n\n"
    "Add me to a group and make me admin to use moderation.\n"
    "In groups, use /ai to ask me anything.\n"
)

BLOCKED_WORDS = [
    "free nitro",
    "join my group",
    "crypto scam",
]


# ------------ HELPERS ------------

def is_private_chat(update: Update) -> bool:
    chat = update.effective_chat
    return chat.type == "private"


async def is_admin(update: Update, user_id: int) -> bool:
    """Check if given user is admin in this chat."""
    chat = update.effective_chat
    member = await chat.get_member(user_id)
    return member.status in ("administrator", "creator")


async def has_restrict_permission(update: Update, user_id: int) -> bool:
    """Check if user can restrict/ban/mute members."""
    chat = update.effective_chat
    member = await chat.get_member(user_id)

    if member.status == "creator":
        return True
    if member.status != "administrator":
        return False

    return bool(getattr(member, "can_restrict_members", False))


async def has_delete_permission(update: Update, user_id: int) -> bool:
    """Check if user can delete messages."""
    chat = update.effective_chat
    member = await chat.get_member(user_id)

    if member.status == "creator":
        return True
    if member.status != "administrator":
        return False

    return bool(getattr(member, "can_delete_messages", False))


def get_target_from_reply(update: Update):
    """Return (user, message) from replied message, else (None, None)."""
    msg = update.effective_message
    if not msg.reply_to_message:
        return None, None
    return msg.reply_to_message.from_user, msg.reply_to_message


def is_self(context: ContextTypes.DEFAULT_TYPE, target_id: int) -> bool:
    """Check if the target user is the bot itself."""
    return context.bot.id == target_id


# ------------ GROQ AI CALL ------------

def call_groq(prompt: str) -> str:
    """
    Send user text to Groq Chat Completions API and return reply text.
    """

    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    system_prompt = (
        "You are Xayie Ai, a friendly, helpful assistant created by Kaze. "
        "Reply in English only. Be clear, concise and a bit playful, "
        "but never rude, toxic, NSFW or harmful."
    )

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 512,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        data = response.json()

        if "error" in data:
            err = data["error"].get("message", "Unknown API error")
            logger.error("Groq API error: %s", err)
            return f"API error: {err}"

        return data["choices"][0]["message"]["content"]

    except Exception as e:
        logger.error("Groq request failed: %s", e)
        return "Network or API error happened. Please try again."


# ------------ BASIC COMMANDS / AI ------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat

    if is_private_chat(update):
        text = (
            f"⚔️ **{BOT_NAME}** online.\n\n"
            "I am a **group management + AI assistant** bot.\n\n"
            "In this private chat:\n"
            "• Just type anything and I will reply using AI.\n\n"
            "In groups:\n"
            "• Use /ai to ask me something.\n"
            "• Admins can use moderation commands like /warn, /mute, /ban, etc.\n\n"
            f"Owner: {OWNER}"
        )
        return await update.message.reply_text(text, parse_mode="Markdown")

    # In groups
    text = (
        f"⚔️ {BOT_NAME} is online here.\n\n"
        "• Use /ai to talk with my AI mode.\n"
        "• Use /help to see moderation commands."
    )
    await update.message.reply_text(text)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_private_chat(update):
        return await update.message.reply_text(DM_INFO_TEXT)

    text = (
        f"**{BOT_NAME} – Group Management + AI**\n\n"
        "__AI Mode__\n"
        "/ai <text> – Ask the AI (or reply /ai to a message)\n\n"
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
        "/ping – Check if I am responsive\n"
        "/owner – Show my owner\n"
        "/list – Info about this bot\n\n"
        "_Only group admins with proper permissions can use moderation commands._"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_private_chat(update):
        return await update.message.reply_text(DM_INFO_TEXT)
    await update.message.reply_text("Pong! 🏓")


async def owner_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"{OWNER} is my owner.")


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "I am a combined **AI + group management** bot.\n"
        "Add me to a group and promote me to admin to use moderation features.\n"
        "In DMs, you can chat with my AI.\n\n"
        f"Owner: {OWNER}"
    )
    await update.message.reply_text(text)


# ------------ AI HANDLERS ------------

async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /ai command – works mainly in groups.
    /ai <text> or reply with /ai
    """
    msg = update.effective_message
    chat = update.effective_chat

    if is_private_chat(update):
        # In DM, just tell user to send normal text (since all goes to AI)
        return await msg.reply_text(
            "You’re already in my DM. Just send a normal message, I’ll reply with AI 🙂"
        )

    # Group usage
    if context.args:
        prompt = " ".join(context.args)
    elif msg.reply_to_message and (msg.reply_to_message.text or msg.reply_to_message.caption):
        prompt = msg.reply_to_message.text or msg.reply_to_message.caption
    else:
        return await msg.reply_text(
            "Use `/ai <text>` or reply to a message with `/ai`.",
            parse_mode="Markdown",
        )

    reply = call_groq(prompt)
    await msg.reply_text(reply)


async def ai_chat_dm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Normal text in DM -> AI chat.
    In groups this handler does nothing.
    """
    if not is_private_chat(update):
        return

    msg = update.message
    user_text = msg.text

    reply = call_groq(user_text)
    await msg.reply_text(reply)


# ------------ WARN SYSTEM ------------

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat

    if is_private_chat(update):
        return await msg.reply_text(DM_INFO_TEXT)

    from_user = update.effective_user

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
        if not await has_restrict_permission(update, from_user.id):
            return await msg.reply_text("❌ You lack permissions to ban members.")

        try:
            await chat.ban_member(target_user.id)
            warns[target_user.id] = 0
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

    if is_private_chat(update):
        return await msg.reply_text(DM_INFO_TEXT)

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

    if is_private_chat(update):
        return await msg.reply_text(DM_INFO_TEXT)

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

    if is_private_chat(update):
        return await msg.reply_text(DM_INFO_TEXT)

    from_user = update.effective_user

    if not await has_restrict_permission(update, from_user.id):
        return await msg.reply_text("❌ You lack permissions to mute members.")

    target_user, _ = get_target_from_reply(update)
    if not target_user:
        return await msg.reply_text("Reply to a user and use /mute [minutes(optional)].")

    if is_self(context, target_user.id):
        return await msg.reply_text(
            "You tried to mute *me*? 😂\n"
            "I’m the one who does the muting here."
        )

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

    if is_private_chat(update):
        return await msg.reply_text(DM_INFO_TEXT)

    from_user = update.effective_user

    if not await has_restrict_permission(update, from_user.id):
        return await msg.reply_text("❌ You lack permissions to unmute members.")

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

    if is_private_chat(update):
        return await msg.reply_text(DM_INFO_TEXT)

    from_user = update.effective_user

    if not await has_restrict_permission(update, from_user.id):
        return await msg.reply_text("❌ You lack permissions to ban members.")

    target_user, _ = get_target_from_reply(update)
    if not target_user:
        return await msg.reply_text("Reply to a user and use /ban.")

    if is_self(context, target_user.id):
        return await msg.reply_text(
            "Trying to ban *me*? 💀\n"
            "Nice joke, but I’m not going anywhere."
        )

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

    if is_private_chat(update):
        return await msg.reply_text(DM_INFO_TEXT)

    from_user = update.effective_user

    if not await has_restrict_permission(update, from_user.id):
        return await msg.reply_text("❌ You lack permissions to kick members.")

    target_user, _ = get_target_from_reply(update)
    if not target_user:
        return await msg.reply_text("Reply to a user and use /kick.")

    if is_self(context, target_user.id):
        return await msg.reply_text(
            "You tried to kick *me* out of the chat I protect? 😭\n"
            "Bold move, but impossible."
        )

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

    if is_private_chat(update):
        return await msg.reply_text(DM_INFO_TEXT)

    from_user = update.effective_user

    if not await has_delete_permission(update, from_user.id):
        return await msg.reply_text("❌ You lack permissions to delete messages.")

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

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Core commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("owner", owner_cmd))
    app.add_handler(CommandHandler("list", list_cmd))

    # AI
    app.add_handler(CommandHandler("ai", ai_command))
    app.add_handler(
        MessageHandler(
            filters.TEXT & (~filters.COMMAND),
            ai_chat_dm,   # only works in DM; in group it returns immediately
        )
    )

    # Warn system
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("warns", warns_cmd))
    app.add_handler(CommandHandler("clearwarns", clear_warns))

    # Moderation
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("kick", kick))
    app.add_handler(CommandHandler("del", delete_msg))

    # Welcome & anti-spam
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    app.add_handler(
        MessageHandler(
            filters.TEXT | filters.CAPTION,
            anti_spam,
        )
    )

    logger.info("%s is starting...", BOT_NAME)
    app.run_polling()


if __name__ == "__main__":
    main()