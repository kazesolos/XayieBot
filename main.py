import logging
from datetime import datetime, timedelta
import os

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
BOT_TOKEN = os.getenv("8532502485:AAFhLAVAAjr33QXc70g4ojmLrqqlGQuHJGI")          # your Telegram bot token
GROQ_API_KEY = os.getenv("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")    # your Groq API key
GROQ_MODEL = "llama-3.1-8b-instant"

OWNER = "@k4_ze"
OWNER_ID = 7423100284            # your Telegram numeric ID
BOT_NAME = "XayieBot"
BOT_USERNAME = "xayiebot"        # lowercase username without @

# Bot ON/OFF global switch
BOT_ENABLED = True

# ------------- LOGGING -------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(BOT_NAME)

# ------------- CONSTANTS -------------

DM_INFO_TEXT = (
    "Owner: {owner}\n\n"
    "I can do two things:\n"
    "- Work as a smart AI assistant in this chat.\n"
    "- Manage groups (warn/mute/ban/kick, anti-link, etc.).\n\n"
    "Add me to a group and make me admin to use moderation.\n"
    "In groups, tag me (@XayieBot) or reply to my message to talk to my AI.\n"
).format(owner=OWNER)

BLOCKED_WORDS = [
    "free nitro",
    "join my group",
    "crypto scam",
]

MAX_HISTORY_MESSAGES = 20   # number of user/bot messages to remember (per chat)


# ------------ HELPERS ------------

def is_private_chat(update: Update) -> bool:
    chat = update.effective_chat
    return chat.type == "private"


def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def bot_blocked_for(user_id: int) -> bool:
    """
    Returns True if bot is OFF and this user is NOT owner.
    """
    return (not BOT_ENABLED) and (not is_owner(user_id))


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


def update_history(chat_data, user_text: str, bot_reply: str):
    """
    Store last MAX_HISTORY_MESSAGES user+bot messages per chat for AI memory.
    """
    history = chat_data.get("history", [])

    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": bot_reply})

    # keep only last 2 * MAX_HISTORY_MESSAGES entries
    history = history[-2 * MAX_HISTORY_MESSAGES:]
    chat_data["history"] = history


def get_history(chat_data):
    return chat_data.get("history", [])


def maybe_store_name(user_text: str, user_data: dict):
    """
    Detect patterns like 'my name is X', 'mera naam X hai'
    and store in user_data['known_name'].
    Very simple pattern-based.
    """
    text = user_text.strip()
    low = text.lower()

    name = None
    trigger_phrases = [
        "my name is",
        "i am",
        "i'm",
        "mera naam",
        "mera name",
        "meraa naam",
        "mela naam",
        "call me",
    ]

    for phrase in trigger_phrases:
        if phrase in low:
            idx = low.find(phrase) + len(phrase)
            # part after the phrase in original text (to keep case)
            name_raw = text[idx:].strip(" .,:-!?\n\t")
            if not name_raw:
                continue

            # split and remove trailing 'hai/hu/hoon' etc
            tokens = name_raw.split()
            if tokens and tokens[-1].lower() in ["hai", "hu", "hoon", "h"]:
                tokens = tokens[:-1]
            name = " ".join(tokens).strip()
            break

    if name and 0 < len(name) <= 32:
        user_data["known_name"] = name
        logger.info("Stored name for user: %s", name)


def is_identity_question(text: str) -> bool:
    low = text.lower()
    patterns = [
        "who am i",
        "who i am",
        "what is my name",
        "what's my name",
        "mera naam kya hai",
        "mera name kya hai",
    ]
    return any(p in low for p in patterns)


# ------------ GROQ AI CALL ------------

def call_groq(messages):
    """
    Send conversation (history + current message) to Groq Chat Completions API
    and return reply text.
    `messages` = list of {"role": "...", "content": "..."}
    """

    if not GROQ_API_KEY:
        return "AI key is not configured on the server."

    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    system_prompt = (
        "You are Xayie Ai, a friendly, helpful assistant created by Kaze. "
        "Reply in English only. Be clear, concise and a bit playful, "
        "but never rude, toxic, NSFW or harmful. "
        "If the user seems to be the owner 'Kaze', treat them with extra warmth."
    )

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            *messages,
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
            return "API error: " + err

        return data["choices"][0]["message"]["content"]

    except Exception as e:
        logger.error("Groq request failed: %s", e)
        return "Network or API error happened. Please try again."


# ------------ SHARED AI HANDLER ------------

async def handle_ai_interaction(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str):
    """
    Core AI flow used by both DM and GC triggers.
    Includes:
    - owner identity handling
    - per-user name memory
    - per-chat conversation history (20 messages)
    """
    msg = update.effective_message
    user = update.effective_user
    chat_data = context.chat_data
    user_data = context.user_data

    text = prompt.strip()
    if not text:
        return await msg.reply_text("Say something and I will reply.")

    # Owner identity questions
    if is_owner(user.id) and is_identity_question(text):
        return await msg.reply_text("You are Kaze, my owner.")

    known_name = user_data.get("known_name")
    if known_name and is_identity_question(text):
        return await msg.reply_text("You are " + known_name + ".")

    # Maybe store name
    maybe_store_name(text, user_data)

    # Build history
    history = get_history(chat_data)
    messages = history + [{"role": "user", "content": text}]

    reply = call_groq(messages)
    await msg.reply_text(reply)

    update_history(chat_data, text, reply)


# ------------ BASIC COMMANDS / INFO ------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if is_private_chat(update):
        text = (
            "**{name}** online.\n\n"
            "I am a group management plus AI assistant bot.\n\n"
            "In this private chat:\n"
            "- Just type anything and I will reply using AI.\n\n"
            "In groups:\n"
            "- Tag me (@XayieBot) or reply to my message to talk with my AI.\n"
            "- Admins can use moderation commands like /warn, /mute, /ban, etc.\n\n"
            "Owner: {owner}"
        ).format(name=BOT_NAME, owner=OWNER)
        return await update.message.reply_text(text, parse_mode="Markdown")

    if bot_blocked_for(user.id):
        return

    text = (
        "{name} is online here.\n\n"
        "- Tag me or reply to my messages to use my AI.\n"
        "- Use /help to see moderation commands."
    ).format(name=BOT_NAME)
    await update.message.reply_text(text)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if is_private_chat(update):
        return await update.message.reply_text(DM_INFO_TEXT)

    if bot_blocked_for(user.id):
        return

    text = (
        "**{name} - Group Management plus AI**\n\n"
        "__AI Mode__\n"
        "- Tag me (@XayieBot) or reply to my message to talk with AI.\n"
        "- /ai <text> - Ask the AI (or reply /ai to a message)\n\n"
        "__Warn System__\n"
        "/warn (reply) - Warn a user (3 warns = auto ban)\n"
        "/warns (reply) - Check a user's warns\n"
        "/clearwarns (reply) - Reset warns\n\n"
        "__Moderation__\n"
        "/mute (reply) [minutes] - Mute a user (no time = forever)\n"
        "/unmute (reply) - Unmute user\n"
        "/ban (reply) - Ban user\n"
        "/kick (reply) - Kick user (ban plus unban)\n"
        "/del (reply) - Delete the replied message\n\n"
        "__Other__\n"
        "/ping - Check if I am responsive\n"
        "/owner - Show my owner\n"
        "/list - Info about this bot\n"
        "/whoami - Tell you who you are (owner plus saved names)\n"
        "/off - Owner only, turn bot OFF\n"
        "/on - Owner only, turn bot ON\n\n"
        "_Only group admins with proper permissions can use moderation commands._"
    ).format(name=BOT_NAME)
    await update.message.reply_text(text, parse_mode="Markdown")


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if is_private_chat(update):
        return await update.message.reply_text(DM_INFO_TEXT)

    if bot_blocked_for(user.id):
        return

    await update.message.reply_text("Pong!")


async def owner_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("{owner} is my owner.".format(owner=OWNER))


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "I am a combined AI plus group management bot.\n"
        "Add me to a group and promote me to admin to use moderation features.\n"
        "In DMs, you can chat with my AI.\n\n"
        "Owner: {owner}"
    ).format(owner=OWNER)
    await update.message.reply_text(text)


async def whoami_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = context.user_data

    if is_owner(user.id):
        return await update.message.reply_text("You are Kaze, my owner.")

    known_name = user_data.get("known_name")
    if known_name:
        return await update.message.reply_text("You are " + known_name + ".")

    if user.username:
        return await update.message.reply_text(
            "You are @{u} (id: {i}).".format(u=user.username, i=user.id)
        )
    else:
        return await update.message.reply_text(
            "You are {n} (id: {i}).".format(n=user.first_name, i=user.id)
        )


async def bot_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global BOT_ENABLED
    user = update.effective_user

    if not is_owner(user.id):
        return await update.message.reply_text("Only my owner can turn me off.")

    BOT_ENABLED = False
    await update.message.reply_text(
        "Bot is now OFF. I will ignore most commands and AI "
        "until my owner turns me ON again."
    )


async def bot_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global BOT_ENABLED
    user = update.effective_user

    if not is_owner(user.id):
        return await update.message.reply_text("Only my owner can turn me on.")

    BOT_ENABLED = True
    await update.message.reply_text("Bot is now ON. Ready to work again.")


# ------------ AI COMMAND (/ai) ------------

async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /ai command - works in DM and groups as a manual trigger.
    /ai <text> or reply with /ai
    """
    msg = update.effective_message
    user = update.effective_user

    if bot_blocked_for(user.id):
        return

    if context.args:
        prompt = " ".join(context.args)
    elif msg.reply_to_message and (msg.reply_to_message.text or msg.reply_to_message.caption):
        prompt = msg.reply_to_message.text or msg.reply_to_message.caption
    else:
        prompt = "What do you want to talk about?"

    await handle_ai_interaction(update, context, prompt)


# ------------ TEXT ROUTER (DM AI + GC tag/reply AI) ------------

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    - In DM: every text -> AI
    - In groups:
        - if message contains @XayieBot -> AI
        - OR if it is a reply to a message from this bot -> AI
    """
    msg = update.message
    user = update.effective_user

    if not msg:
        return

    if is_private_chat(update):
        if bot_blocked_for(user.id):
            return
        prompt = msg.text or ""
        await handle_ai_interaction(update, context, prompt)
        return

    # Group chat logic
    if bot_blocked_for(user.id):
        return

    text = (msg.text or "").lower()

    # Check mention
    mentioned = "@{u}".format(u=BOT_USERNAME.lower()) in text

    # Check reply-to-bot
    reply_to_bot = (
        msg.reply_to_message
        and msg.reply_to_message.from_user
        and msg.reply_to_message.from_user.id == context.bot.id
    )

    if not (mentioned or reply_to_bot):
        return  # ignore normal messages in group

    # Clean prompt: remove @XayieBot from text if present
    prompt = msg.text or ""
    prompt = prompt.replace("@{u}".format(u=BOT_USERNAME), "").replace(
        "@{u}".format(u=BOT_USERNAME.lower()), ""
    ).strip()
    if not prompt and msg.text:
        prompt = msg.text.strip()

    if not prompt and msg.reply_to_message:
        if msg.reply_to_message.text or msg.reply_to_message.caption:
            prompt = msg.reply_to_message.text or msg.reply_to_message.caption

    if not prompt:
        prompt = "What do you want to talk about?"

    await handle_ai_interaction(update, context, prompt)


# ------------ WARN SYSTEM ------------

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if is_private_chat(update):
        return await msg.reply_text(DM_INFO_TEXT)

    if bot_blocked_for(user.id):
        return

    from_user = user

    if not await is_admin(update, from_user.id):
        return await msg.reply_text("Only admins can use /warn.")

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
            return await msg.reply_text("You lack permissions to ban members.")

        try:
            await chat.ban_member(target_user.id)
            warns[target_user.id] = 0
            await msg.reply_text(
                "{u} reached 3 warns and has been banned.".format(
                    u=target_user.mention_html()
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(e)
            await msg.reply_text("Error while trying to ban. Am I an admin?")
    else:
        await msg.reply_text(
            "{u} has been warned. Warns: {w}/3".format(
                u=target_user.mention_html(), w=user_warns
            ),
            parse_mode="HTML",
        )


async def warns_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user

    if is_private_chat(update):
        return await msg.reply_text(DM_INFO_TEXT)

    if bot_blocked_for(user.id):
        return

    chat_data = context.chat_data

    target_user, _ = get_target_from_reply(update)
    if not target_user:
        return await msg.reply_text("Reply to a user and use /warns.")

    warns = chat_data.get("warns", {})
    user_warns = warns.get(target_user.id, 0)
    await msg.reply_text(
        "{u} currently has {w}/3 warns.".format(
            u=target_user.mention_html(), w=user_warns
        ),
        parse_mode="HTML",
    )


async def clear_warns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user

    if is_private_chat(update):
        return await msg.reply_text(DM_INFO_TEXT)

    if bot_blocked_for(user.id):
        return

    from_user = user

    if not await is_admin(update, from_user.id):
        return await msg.reply_text("Only admins can use /clearwarns.")

    target_user, _ = get_target_from_reply(update)
    if not target_user:
        return await msg.reply_text("Reply to a user and use /clearwarns.")

    warns = context.chat_data.setdefault("warns", {})
    warns[target_user.id] = 0
    await msg.reply_text(
        "All warns for {u} have been cleared.".format(
            u=target_user.mention_html()
        ),
        parse_mode="HTML",
    )


# ------------ MUTE / UNMUTE / BAN / KICK / DELETE ------------

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if is_private_chat(update):
        return await msg.reply_text(DM_INFO_TEXT)

    if bot_blocked_for(user.id):
        return

    from_user = user

    if not await has_restrict_permission(update, from_user.id):
        return await msg.reply_text("You lack permissions to mute members.")

    target_user, _ = get_target_from_reply(update)
    if not target_user:
        return await msg.reply_text("Reply to a user and use /mute [minutes(optional)].")

    if is_self(context, target_user.id):
        return await msg.reply_text(
            "You tried to mute me. I am the one who mutes other people here."
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
        await chat.restrict_member(
            target_user.id, permissions=permissions, until_date=until
        )
        if minutes:
            await msg.reply_text(
                "{u} has been muted for {m} minutes.".format(
                    u=target_user.mention_html(), m=minutes
                ),
                parse_mode="HTML",
            )
        else:
            await msg.reply_text(
                "{u} has been muted.".format(
                    u=target_user.mention_html()
                ),
                parse_mode="HTML",
            )
    except Exception as e:
        logger.error(e)
        await msg.reply_text("Failed to mute. Am I admin with restrict rights?")


async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if is_private_chat(update):
        return await msg.reply_text(DM_INFO_TEXT)

    if bot_blocked_for(user.id):
        return

    from_user = user
    if not await has_restrict_permission(update, from_user.id):
        return await msg.reply_text("You lack permissions to unmute members.")

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
            "{u} has been unmuted.".format(u=target_user.mention_html()),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(e)
        await msg.reply_text("Failed to unmute. Am I admin with restrict rights?")


async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if is_private_chat(update):
        return await msg.reply_text(DM_INFO_TEXT)

    if bot_blocked_for(user.id):
        return

    from_user = user
    if not await has_restrict_permission(update, from_user.id):
        return await msg.reply_text("You lack permissions to ban members.")

    target_user, _ = get_target_from_reply(update)
    if not target_user:
        return await msg.reply_text("Reply to a user and use /ban.")

    if await is_admin(update, target_user.id):
        return await msg.reply_text("I cannot ban an admin.")

    try:
        await chat.ban_member(target_user.id)
        await msg.reply_text(
            "{u} has been banned.".format(u=target_user.mention_html()),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(e)
        await msg.reply_text("Failed to ban. Am I admin with ban rights?")


async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if is_private_chat(update):
        return await msg.reply_text(DM_INFO_TEXT)

    if bot_blocked_for(user.id):
        return

    from_user = user
    if not await has_restrict_permission(update, from_user.id):
        return await msg.reply_text("You lack permissions to kick members.")

    target_user, _ = get_target_from_reply(update)
    if not target_user:
        return await msg.reply_text("Reply to a user and use /kick.")

    if await is_admin(update, target_user.id):
        return await msg.reply_text("I cannot kick an admin.")

    try:
        await chat.ban_member(target_user.id)
        await chat.unban_member(target_user.id)
        await msg.reply_text(
            "{u} has been kicked.".format(u=target_user.mention_html()),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(e)
        await msg.reply_text("Failed to kick. Am I admin with ban rights?")


async def delete_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user

    if is_private_chat(update):
        return await msg.reply_text(DM_INFO_TEXT)

    if bot_blocked_for(user.id):
        return

    if not await has_delete_permission(update, user.id):
        return await msg.reply_text("You lack permissions to delete messages.")

    if not msg.reply_to_message:
        return await msg.reply_text("Reply to a message and use /del.")

    try:
        await msg.reply_to_message.delete()
        await msg.delete()
    except Exception as e:
        logger.error(e)
        await msg.reply_text("Failed to delete message. Am I admin with delete rights?")


# ------------ ANTI-SPAM / ANTI-LINK (simple) ------------

async def anti_spam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user

    if is_private_chat(update):
        return

    if bot_blocked_for(user.id):
        return

    text = (msg.text or "").lower()

    if any(word in text for word in BLOCKED_WORDS):
        if await has_delete_permission(update, context.bot.id):
            try:
                await msg.delete()
            except Exception as e:
                logger.error(e)
        return


# ------------ MAIN ------------

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN env var is missing. Set it on Render.")

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(CommandHandler("owner", owner_cmd))
    application.add_handler(CommandHandler("list", list_cmd))
    application.add_handler(CommandHandler("whoami", whoami_cmd))
    application.add_handler(CommandHandler("off", bot_off))
    application.add_handler(CommandHandler("on", bot_on))
    application.add_handler(CommandHandler("ai", ai_command))
    application.add_handler(CommandHandler("warn", warn))
    application.add_handler(CommandHandler("warns", warns_cmd))
    application.add_handler(CommandHandler("clearwarns", clear_warns))
    application.add_handler(CommandHandler("mute", mute))
    application.add_handler(CommandHandler("unmute", unmute))
    application.add_handler(CommandHandler("ban", ban))
    application.add_handler(CommandHandler("kick", kick))
    application.add_handler(CommandHandler("del", delete_msg))

    # Text handler (for AI in DM + mentions in groups)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    # Anti-spam (simple)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, anti_spam))

    logger.info("XayieBot starting polling...")
    application.run_polling()


if __name__ == "__main__":
    main()