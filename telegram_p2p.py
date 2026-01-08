import logging
import asyncio
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

# ==========================================
# 🔐 TOKEN DEL BOT
# ==========================================
TOKEN = "8373034080:AAEtFdns3wnNXLiTdpO_7f-toddCeFaThyw"

# --- CONFIGURACIÓN ---
BANCO = "BANESCO"
TIEMPO_REVISION = 60 
COMISION_BINANCE = 0.0014 

# Base de datos en memoria
# Estructura: { chat_id: { 'capital': 6500, 'meta': 85, 'f_venta': '4000000', 'f_compra': '500000' } }
usuarios_db = {}

# Valores por defecto si no se configuran manual
DEF_FILTRO_VENTA = "4000000" # Buscamos en tabla Verde (Tu Venta)
DEF_FILTRO_COMPRA = "500000" # Buscamos en tabla Roja (Tu Compra)

# --- LÓGICA DE BINANCE (FILTROS MANUALES) ---
def obtener_precio_competencia(estrategia, monto_filtro_usuario):
    """
    Ahora esta función es 'obediente': Busca exactamente con el monto
    que el usuario configuró en Telegram.
    """
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    
    trade_type_api = ""
    
    # ESTRATEGIA: TU VENTA (Miras la Tabla Verde / 'Comprar')
    if estrategia == "TU_VENTA":
        trade_type_api = "BUY" 

    # ESTRATEGIA: TU COMPRA (Miras la Tabla Roja / 'Vender')
    elif estrategia == "TU_COMPRA":
        trade_type_api = "SELL"

    payload = {
        "asset": "USDT",
        "fiat": "VES",
        "merchantCheck": True, 
        "page": 1,
        "rows": 5, 
        "payTypes": [BANCO],
        "publisherType": "merchant", 
        "tradeType": trade_type_api,
        "transAmount": str(monto_filtro_usuario) # <--- AQUI ENTRA TU VALOR MANUAL
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        data = response.json()
        
        if data["data"]:
            return float(data["data"][0]["adv"]["price"])

    except Exception as e:
        print(f"Error API ({estrategia}): {e}")
        pass
        
    return 0.0

# --- COMANDOS TELEGRAM ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **Monitor P2P Manual**\n\n"
        "1️⃣ Configura Capital y Meta:\n"
        "`/config [CAPITAL] [GANANCIA]`\n"
        "   Ej: `/config 6500 85`\n\n"
        "2️⃣ Configura los Filtros de Monto (VES):\n"
        "`/filtros [MONTO_TU_VENTA] [MONTO_TU_COMPRA]`\n"
        "   Ej: `/filtros 4000000 500000`\n"
        "   _(Esto buscará precios en la tabla verde por 4M y en la roja por 500k)_",
        parse_mode="Markdown"
    )

async def config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    try:
        capital = float(context.args[0])
        meta = float(context.args[1])
        
        # Si ya existe el usuario, conservamos sus filtros, si no, ponemos default
        if chat_id not in usuarios_db:
            usuarios_db[chat_id] = {
                'capital': capital, 'meta': meta, 
                'f_venta': DEF_FILTRO_VENTA, 'f_compra': DEF_FILTRO_COMPRA
            }
        else:
            usuarios_db[chat_id]['capital'] = capital
            usuarios_db[chat_id]['meta'] = meta
            
        await update.message.reply_text(f"✅ Capital: {capital} USDT | Meta: {meta} USDT")
    except:
        await update.message.reply_text("❌ Error. Ej: `/config 6500 85`")

async def filtros(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in usuarios_db:
         await update.message.reply_text("⚠️ Primero usa /config")
         return

    try:
        # El usuario envía: /filtros 4000000 500000
        f_venta = context.args[0] # Monto para la tabla verde
        f_compra = context.args[1] # Monto para la tabla roja
        
        usuarios_db[chat_id]['f_venta'] = f_venta
        usuarios_db[chat_id]['f_compra'] = f_compra
        
        await update.message.reply_text(
            f"✅ **Filtros Actualizados**\n"
            f"🟢 Tu Venta (Tabla Verde): `{f_venta}` VES\n"
            f"🔴 Tu Compra (Tabla Roja): `{f_compra}` VES",
            parse_mode="Markdown"
        )
    except:
        await update.message.reply_text("❌ Error. Ej: `/filtros 4000000 500000`")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in usuarios_db:
        datos = usuarios_db[chat_id]
        
        # Usamos los filtros guardados del usuario
        p_venta = obtener_precio_competencia("TU_VENTA", datos['f_venta']) 
        p_compra = obtener_precio_competencia("TU_COMPRA", datos['f_compra']) 
        
        if p_venta > 0 and p_compra > 0:
            cap = datos['capital']
            bruto_ves = cap * p_venta
            neto_ves = bruto_ves * (1 - COMISION_BINANCE)
            bruto_usdt_recuperados = neto_ves / p_compra
            neto_usdt_final = bruto_usdt_recuperados * (1 - COMISION_BINANCE)
            ganancia = neto_usdt_final - cap
            
            await update.message.reply_text(
                f"📊 **Estado (Filtros: {datos['f_venta']} / {datos['f_compra']})**\n"
                f"📈 Tu Venta: {p_venta:.2f}\n"
                f"📉 Tu Compra: {p_compra:.2f}\n"
                f"💰 Ganancia Neta: {ganancia:.2f} USDT", parse_mode="Markdown")
        else:
            await update.message.reply_text("🔎 Buscando precios...")
    else:
        await update.message.reply_text("⚠️ Usa /start para configurar.")

async def vigilar_mercado(context: ContextTypes.DEFAULT_TYPE):
    if not usuarios_db:
        return

    # Iteramos por cada usuario porque cada uno puede tener filtros distintos
    for chat_id, datos in usuarios_db.items():
        p_venta = obtener_precio_competencia("TU_VENTA", datos['f_venta'])
        p_compra = obtener_precio_competencia("TU_COMPRA", datos['f_compra'])
        
        if p_venta > 0 and p_compra > 0:
            print(f"User {chat_id} | V({datos['f_venta']}):{p_venta} - C({datos['f_compra']}):{p_compra}")
            
            cap = datos['capital']
            bruto_ves = cap * p_venta
            neto_ves = bruto_ves * (1 - COMISION_BINANCE)
            bruto_usdt_recuperados = neto_ves / p_compra
            neto_usdt_final = bruto_usdt_recuperados * (1 - COMISION_BINANCE)
            ganancia = neto_usdt_final - cap
            
            if ganancia >= datos['meta']:
                await context.bot.send_message(chat_id, 
                    f"🚨 **¡META ALCANZADA!** 🚨\n"
                    f"Ganancia: {ganancia:.2f} USDT\n"
                    f"Venta (F:{datos['f_venta']}): {p_venta}\n"
                    f"Compra (F:{datos['f_compra']}): {p_compra}", 
                    parse_mode="Markdown")

if __name__ == '__main__':
    
    from keep_alive import keep_alive
    
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("config", config))
    app.add_handler(CommandHandler("filtros", filtros)) # <--- NUEVO COMANDO
    app.add_handler(CommandHandler("status", status))
    app.job_queue.run_repeating(vigilar_mercado, interval=TIEMPO_REVISION, first=10)
    print("🤖 Bot Manual Corriendo...")
    app.run_polling()
    