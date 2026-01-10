import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import requests
from keep_alive import keep_alive

# --- ⚠️ PEGA TU TOKEN NUEVO AQUÍ ---
TOKEN = "7658418390:AAEVAIV5r2Sb33IV-mkig5yd8hqHXegU47E" 

# Configuración Global
TIEMPO_REVISION = 60
COMISION_BINANCE = 0.001

# Base de datos
USERS_DB = {} 

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

async def obtener_precio_competencia(tipo, filtro_monto):
    """Consulta precios a Binance P2P (SOLO BANESCO)"""
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
    data = {
        "asset": "USDT",
        "fiat": "VES",
        "merchantCheck": False,
        "page": 1,
        "rows": 1,
        "tradeType": tipo,
        "transAmount": filtro_monto,
        "payTypes": ["BANESCO"]  # <--- AQUÍ FILTRAMOS SOLO BANESCO
    }
    try:
        response = requests.post(url, json=data, headers=headers, timeout=5)
        resultados = response.json()['data']
        if resultados: return float(resultados[0]['adv']['price'])
    except Exception as e:
        print(f"Error Binance: {e}")
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in USERS_DB:
        USERS_DB[user.id] = {'capital': 0, 'meta': 0, 'f_venta': 4000000, 'f_compra': 500000, 'activo': False}
        mensaje = (
            f"👋 **¡Monitor P2P (Solo Banesco)!**\n\n"
            f"⚙️ **Paso 1: Configura**\n`/config [CAPITAL] [GANANCIA]`\n"
            f"⚙️ **Paso 2: Filtros**\n`/filtros [VENTA] [COMPRA]`"
        )
    else:
        mensaje = f"👋 Hola {user.first_name}. Sigues activo."
    await update.message.reply_text(mensaje, parse_mode="Markdown")

async def config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        if len(context.args) != 2: raise ValueError
        capital = float(context.args[0])
        meta = float(context.args[1])
        if user_id not in USERS_DB: await start(update, context)
        USERS_DB[user_id]['capital'] = capital
        USERS_DB[user_id]['meta'] = meta
        USERS_DB[user_id]['activo'] = True
        await update.message.reply_text(f"✅ **Listo:** Cap {capital} | Meta {meta}", parse_mode="Markdown")
    except:
        await update.message.reply_text("⚠️ Error. Ej: `/config 1000 20`")

async def filtros(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        if len(context.args) != 2: raise ValueError
        fv = float(context.args[0])
        fc = float(context.args[1])
        if user_id not in USERS_DB: await start(update, context)
        USERS_DB[user_id]['f_venta'] = fv
        USERS_DB[user_id]['f_compra'] = fc
        await update.message.reply_text(f"✅ **Filtros:** Venta {fv:.0f} | Compra {fc:.0f}", parse_mode="Markdown")
    except:
        await update.message.reply_text("⚠️ Error. Ej: `/filtros 4000000 500000`")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in USERS_DB and USERS_DB[user_id]['activo']:
        d = USERS_DB[user_id]
        await update.message.reply_text(f"📊 **ESTADO**\n💰 Cap: {d['capital']}\n✅ ACTIVO", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Inactivo.")

async def vigilar_mercado(context: ContextTypes.DEFAULT_TYPE):
    if not USERS_DB: return
    for uid, data in USERS_DB.items():
        if not data['activo']: continue
        
        p_venta = await obtener_precio_competencia("BUY", data['f_venta'])
        p_compra = await obtener_precio_competencia("SELL", data['f_compra'])
        
        if p_venta and p_compra:
            bruto_ves = data['capital'] * p_venta
            neto_ves = bruto_ves * (1 - COMISION_BINANCE)
            neto_usdt = (neto_ves / p_compra) * (1 - COMISION_BINANCE)
            ganancia = neto_usdt - data['capital']
            
            if ganancia >= data['meta']:
                try:
                    await context.bot.send_message(
                        chat_id=uid,
                        text=f"🚨 **¡OPORTUNIDAD BANESCO!** 🚨\n💰 Ganancia: {ganancia:.2f} USDT\n🟢 Vende a: {p_venta}\n🔴 Compra a: {p_compra}",
                        parse_mode="Markdown"
                    )
                except: pass

if __name__ == '__main__':
    from keep_alive import keep_alive
    keep_alive()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("config", config))
    app.add_handler(CommandHandler("filtros", filtros))
    app.add_handler(CommandHandler("status", status))
    app.job_queue.run_repeating(vigilar_mercado, interval=TIEMPO_REVISION, first=10)
    print("🤖 Bot Banesco Iniciado...")
    app.run_polling()
