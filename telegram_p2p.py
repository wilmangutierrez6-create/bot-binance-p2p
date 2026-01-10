import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import requests
from keep_alive import keep_alive

# --- CONFIGURACIÓN PRINCIPAL ---
TOKEN = "7658418390:AAETeKF0VhNY1PhgC5QF-iyg9oLWfbsgZbg"  # <--- ¡PEGA TU TOKEN AQUÍ!

# Configuración de Mercado
TIEMPO_REVISION = 60  # Segundos entre revisiones
COMISION_BINANCE = 0.001  # 0.1% Taker

# --- BASE DE DATOS EN MEMORIA (DICCIONARIO) ---
# Estructura: { user_id: { 'capital': 0, 'meta': 0, 'f_venta': 0, 'f_compra': 0, 'activo': False } }
USERS_DB = {} 

# Configuración de Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def obtener_precio_competencia(tipo, filtro_monto):
    """
    Consulta a Binance P2P.
    tipo: "BUY" (para ver competencia de venta) o "SELL" (para ver competencia de compra)
    """
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json"
    }
    data = {
        "asset": "USDT",
        "fiat": "VES",
        "merchantCheck": False,
        "page": 1,
        "publisherType": None,
        "rows": 10,
        "tradeType": tipo,
        "transAmount": filtro_monto
    }
    
    try:
        response = requests.post(url, json=data, headers=headers, timeout=5)
        resultados = response.json()['data']
        
        if resultados:
            # Tomamos el primer precio (el mejor del mercado)
            precio = float(resultados[0]['adv']['price'])
            return precio
        else:
            return None
    except Exception as e:
        print(f"Error conexión Binance: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # Registramos al usuario si no existe
    if user_id not in USERS_DB:
        USERS_DB[user_id] = {
            'capital': 0, 
            'meta': 0, 
            'f_venta': 4000000,   # Filtro por defecto
            'f_compra': 500000,   # Filtro por defecto
            'activo': False
        }
        await update.message.reply_text(
            f"👋 ¡Hola {user.first_name}! Bienvenido al Monitor P2P Comunitario.\n\n"
            "Este bot es INDIVIDUAL. Tu configuración es privada.\n\n"
            "⚙️ **Paso 1:** Configura tu capital y meta:\n"
            "`/config [CAPITAL] [GANANCIA]`\n"
            "Ej: `/config 1000 20`\n\n"
            "⚙️ **Paso 2:** (Opcional) Filtros de monto:\n"
            "`/filtros [MONTO_VENTA] [MONTO_COMPRA]`",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"👋 ¡Hola de nuevo {user.first_name}! Ya estás registrado. Usa /status para ver tus datos.")

async def config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        args = context.args
        if len(args) != 2:
            await update.message.reply_text("⚠️ Error. Usa: `/config [CAPITAL] [META]`", parse_mode="Markdown")
            return

        capital = float(args[0])
        meta = float(args[1])
        
        # Guardamos en la "carpeta" de este usuario específico
        if user_id not in USERS_DB: USERS_DB[user_id] = {'f_venta': 4000000, 'f_compra': 500000}
        
        USERS_DB[user_id]['capital'] = capital
        USERS_DB[user_id]['meta'] = meta
        USERS_DB[user_id]['activo'] = True  # Activamos al usuario
        
        await update.message.reply_text(
            f"✅ **Configuración Personal Guardada**\n"
            f"💰 Capital: {capital} USDT\n"
            f"🎯 Meta: {meta} USDT\n\n"
            f"🚀 ¡Ahora recibirás alertas cuando cumplas TU meta!",
            parse_mode="Markdown"
        )
        
    except ValueError:
        await update.message.reply_text("⚠️ Los valores deben ser números.")

async def filtros(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        args = context.args
        if len(args) != 2:
            await update.message.reply_text("⚠️ Usa: `/filtros [MONTO_VENTA] [MONTO_COMPRA]`")
            return

        f_venta = float(args[0])
        f_compra = float(args[1])
        
        if user_id not in USERS_DB: 
            await update.message.reply_text("⚠️ Primero usa /start")
            return

        USERS_DB[user_id]['f_venta'] = f_venta
        USERS_DB[user_id]['f_compra'] = f_compra
        
        await update.message.reply_text(
            f"✅ **Filtros Personales Actualizados**\n"
            f"🟢 Tu Venta (Tabla Verde): {f_venta:.0f} VES\n"
            f"🔴 Tu Compra (Tabla Roja): {f_compra:.0f} VES",
            parse_mode="Markdown"
        )
    except ValueError:
        await update.message.reply_text("⚠️ Usa números enteros sin puntos ni comas.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in USERS_DB and USERS_DB[user_id].get('activo'):
        data = USERS_DB[user_id]
        await update.message.reply_text(
            f"📊 **TU ESTADO ACTUAL**\n"
            f"👤 Usuario: {update.effective_user.first_name}\n"
            f"💰 Capital: {data['capital']} USDT\n"
            f"🎯 Meta: {data['meta']} USDT\n"
            f"🔍 Filtros: {data['f_venta']} / {data['f_compra']} VES\n"
            f"✅ **Monitoreo: ACTIVO**",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ No tienes configuración activa. Usa `/config`.")

async def vigilar_mercado(context: ContextTypes.DEFAULT_TYPE):
    """
    Esta función corre cada 60 segundos.
    1. Obtiene precios generales de Binance.
    2. Recorre la lista de usuarios y calcula la ganancia para CADA UNO.
    """
    if not USERS_DB:
        print("💤 Nadie configurado todavía...")
        return

    print(f"🔎 Revisando mercado para {len(USERS_DB)} usuarios...")

    # --- PASO 1: OBTENER PRECIOS (Optimizamos haciendo solo 2 llamadas para todos) ---
    # Para hacerlo simple, usaremos un promedio de filtros o un filtro estándar para obtener el precio base
    # NOTA: En un bot avanzado, agruparíamos usuarios por filtros similares. 
    # Aquí usaremos un filtro genérico de 1.000.000 VES para obtener una referencia de precio rápida.
    # Si quieres exactitud total por usuario, habría que mover esto dentro del loop (pero es más lento).
    
    # Estrategia: Usaremos los filtros del primer usuario activo como referencia (para el prototipo)
    # O mejor, hacemos la llamada dentro del loop SOLO si el usuario está activo.
    
    # Vamos a hacerlo dentro del loop por seguridad de datos, aunque sea un poco más lento.
    # Binance permite bastantes llamadas, con pocos usuarios no hay problema.
    
    for user_id, data in USERS_DB.items():
        if not data.get('activo'):
            continue # Si el usuario no configuró capital, lo saltamos
            
        cap = data['capital']
        meta = data['meta']
        f_venta = data['f_venta']
        f_compra = data['f_compra']
        
        # 1. Obtener precios según LOS FILTROS DE ESTE USUARIO
        p_venta = await obtener_precio_competencia("BUY", f_venta)  # A cómo vende la competencia (donde yo quiero vender)
        p_compra = await obtener_precio_competencia("SELL", f_compra) # A cómo compra la competencia (donde yo quiero comprar)

        if p_venta and p_compra:
            # 2. Calcular Matemática P2P
            bruto_ves = cap * p_venta
            neto_ves = bruto_ves * (1 - COMISION_BINANCE)
            
            bruto_usdt_recuperados = neto_ves / p_compra
            neto_usdt_final = bruto_usdt_recuperados * (1 - COMISION_BINANCE)
            
            ganancia = neto_usdt_final - cap
            
            # 3. Verificar si cumple LA META DE ESTE USUARIO
            if ganancia >= meta:
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"🚨 **¡ALERTA PARA TI!** 🚨\n\n"
                             f"💰 **Ganancia:** {ganancia:.2f} USDT (Meta: {meta})\n"
                             f"🟢 Vende a: {p_venta}\n"
                             f"🔴 Compra a: {p_compra}\n"
                             f"📊 Capital: {cap}",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"No se pudo enviar mensaje a {user_id}: {e}")

if __name__ == '__main__':
    from keep_alive import keep_alive
    keep_alive()
    
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("config", config))
    app.add_handler(CommandHandler("filtros", filtros))
    app.add_handler(CommandHandler("status", status))
    
    # Revisamos cada 60 segundos
    app.job_queue.run_repeating(vigilar_mercado, interval=TIEMPO_REVISION, first=10)
    
    print("🤖 Bot Comunitario Corriendo...")
    app.run_polling()
