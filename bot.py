import os
import time
import asyncio
import requests
import threading
import random
import re
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    TypeHandler,
    ContextTypes,
    ApplicationHandlerStop,
    ChatMemberHandler
)

# ==============================================
# ✅ CONFIGURAÇÕES
# ==============================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN")
DONO_ID = int(os.environ.get("DONO_ID", 7711945457))
CANAL_ALVO_ID = int(os.environ.get("CANAL_ALVO_ID", -1004399892914))
MONGO_URI = os.environ.get("MONGO_URI")

LISTA_VIDEOS_START = [
    "BAACAgEAAxkBAAIEaGpypkNQUJJljEnJb7HL6E8_jI9wAAKFBgACCyKZR-8RZtV8X4rJPQQ",
    "BAACAgQAAxkDAAICGmpoPJTXgCHfxtZabyU-4BF-LQ2aAAIyCgACN9NMU1DMn3zufwakPQQ",
    "BAACAgQAAxkDAAICHGpoPQABSIsmMhqbhyOF5T3dTtOPMQAC2AoAAsGPRVP2U4U5hzZfgD0E",
    "BAACAgEAAxkBAAIEiGpyriREGTmCsDEL-K7HP20Lu4anAAKIBgACCyKZR-NXEURfyoGWPQQ",
    "BAACAgEAAxkBAAIEi2pyrrUAAXpOCWe8aG_nf_8n0X927wACiQYAAgsimUdIi2LyBhmPoz0E",
    "BAACAgEAAxkBAAIEjmpyrxiNAfhRdTuM-gL2QlzUVjRzAAKKBgACCyKZR5GXizEzidIiPQQ",
    "BAACAgEAAxkBAAIElGpysAVDwH-LYNh9sODcX3lBl7O-AAKMBgACCyKZR3ERh8tK65nkPQQ"
]

try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, tlsAllowInvalidCertificates=True)
    db = mongo_client["sanizinhabot_db"]
    collection_clientes = db["clientes"]
except Exception as e:
    print(f"❌ MongoDB: {e}")

TEMPO_INICIAL = time.time()
FUSO_RJ = timezone(timedelta(hours=-3))
pagamentos_notificados = set()

# ==============================================
# ⚙️ FUNÇÕES AUXILIARES
# ==============================================
def formatar_tempo_restante(segundos):
    if segundos <= 0: return "Expirado"
    if segundos >= 315360000: return "Permanente"
    dias = int(segundos // 86400); horas = int((segundos % 86400) // 3600); minutos = int((segundos % 3600) // 60)
    partes = []
    if dias>0: partes.append(f"{dias}d")
    if horas>0: partes.append(f"{horas}h")
    if minutos>0: partes.append(f"{minutos}m")
    return " ".join(partes) if partes else "Menos de 1m"

def formatar_data_rj(timestamp):
    return datetime.fromtimestamp(timestamp, tz=FUSO_RJ).strftime("%d/%m/%Y às %H:%M")

# ==============================================
# 📋 COMANDOS
# ==============================================
async def pegarid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID: return
    v = update.message.reply_to_message.video if (update.message.reply_to_message and update.message.reply_to_message.video) else update.message.video
    if v: await update.message.reply_text(f"✅ FILE_ID:\n{v.file_id}\nDuração: {v.duration}s")
    else: await update.message.reply_text("⚠️ Responda/envie um vídeo com /pegarid")

async def clientes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID: return
    agora = time.time(); clientes = list(collection_clientes.find({}))
    if not clientes: return await update.message.reply_text("Nenhum cliente!")
    texto = f"📋 CLIENTES ({len(clientes)}):\n\n"
    for i,cli in enumerate(clientes,1):
        texto += f"{i}. {cli.get('nome','?')}\nID: {cli['user_id']}\nValor: R${cli.get('valor_pago','0')}\nExpira: {formatar_tempo_restante(cli.get('expira_em',0)-agora)}\n\n"
    await update.message.reply_text(texto)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": return
    texto = "Escolha seu plano VIP:\nSuporte: @Lyhhxv"
    botoes = [
        [InlineKeyboardButton("1H → R$1", callback_data="comprar_1")],
        [InlineKeyboardButton("1DIA → R$5", callback_data="comprar_5")],
        [InlineKeyboardButton("1SEMANA → R$10", callback_data="comprar_10")],
        [InlineKeyboardButton("1MES → R$30", callback_data="comprar_30")],
        [InlineKeyboardButton("PERMANENTE → R$55", callback_data="comprar_55")]
    ]
    try: await update.message.reply_video(random.choice(LISTA_VIDEOS_START), caption=texto, reply_markup=InlineKeyboardMarkup(botoes))
    except: await update.message.reply_text(texto, reply_markup=InlineKeyboardMarkup(botoes))

async def suporte_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Suporte: @Lyhhxv")

async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID: return
    await update.message.reply_text(f"Chat: {update.effective_chat.id}\nSeu ID: {update.effective_user.id}")

async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID: return
    ini=time.time(); msg=await update.message.reply_text("Pong..."); lat=int((time.time()-ini)*1000)
    await msg.edit_text(f"Latência: {lat}ms")

# ==============================================
# 🔒 ANTI-FLOOD
# ==============================================
async def interceptador(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u or u.id == DONO_ID: return
    if update.message and update.message.text and update.message.text.startswith('/'):
        cmd = update.message.text.split()[0].split('@')[0].lower()
        if cmd not in ['/start','/suporte']: raise ApplicationHandlerStop

async def saiu_canal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.my_chat_member.chat.id == CANAL_ALVO_ID and update.my_chat_member.new_chat_member.status in ["left","kicked"]:
        collection_clientes.delete_one({"user_id": update.my_chat_member.from_user.id})

# ==============================================
# 💳 PAGAMENTOS
# ==============================================
async def gerar_pix(valor):
    url = "https://api.mercadopago.com/v1/payments"
    h = {"Authorization":f"Bearer {MP_ACCESS_TOKEN}","Content-Type":"application/json"}
    p = {"transaction_amount":valor,"description":"Acesso VIP","payment_method_id":"pix","payer":{"email":"user@bot.com"}}
    try: r=requests.post(url,json=p,headers=h,timeout=15)
    except: return False,None,"Erro"
    if r.status_code==201: d=r.json(); return True,d["id"],d["point_of_interaction"]["transaction_data"]["qr_code"]
    return False,None,f"Erro {r.status_code}"

async def verificar_pix(pid):
    try: r=requests.get(f"https://api.mercadopago.com/v1/payments/{pid}",headers={"Authorization":f"Bearer {MP_ACCESS_TOKEN}"},timeout=10)
    except: return False,0
    if r.status_code==200: d=r.json(); return d.get("status")=="approved",d.get("transaction_amount",0)
    return False,0

async def botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); d = q.data
    if d.startswith("comprar_"):
        v = float(d.split("_")[1])
        ok,pid,pix = await gerar_pix(v)
        if ok: await q.edit_message_text(f"PIX R${v}:\n{pix}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Verificar", callback_data=f"check_{pid}")]]))
        else: await q.edit_message_text(f"Erro: {pix}")
    elif d.startswith("check_"):
        ok,valor = await verificar_pix(d.split("_")[1])
        if ok:
            await q.answer("✅ APROVADO!", show_alert=True)
            if abs(valor-1)<0.01: seg=3600; nome="1H"
            elif abs(valor-5)<0.01: seg=86400; nome="1Dia"
            elif abs(valor-10)<0.01: seg=86400*7; nome="1Semana"
            elif abs(valor-30)<0.01: seg=86400*30; nome="1Mes"
            elif abs(valor-55)<0.01: seg=86400*365*10; nome="PERMANENTE"
            else: seg=int(valor*86400); nome=f"R${valor}"
            uid=update.effective_user.id; exp=time.time()+seg
            collection_clientes.update_one({"user_id":uid},{"$set":{"nome":update.effective_user.first_name,"valor_pago":f"{valor:.2f}","expira_em":exp,"data_compra":time.time()}},upsert=True)
            try: link=await context.bot.create_chat_invite_link(CANAL_ALVO_ID,member_limit=1); await q.message.reply_text(f"Aprovado! Acesse: {link.invite_link}\nAproveite 🩷")
            except: await q.message.reply_text("Aprovado! Contate suporte 🩷")
            if d.split("_")[1] not in pagamentos_notificados:
                pagamentos_notificados.add(d.split("_")[1])
                await context.bot.send_message(DONO_ID,f"NOVO PAGAMENTO:\nCliente: {update.effective_user.first_name}\nValor: R${valor:.2f}\nPlano: {nome}\nExpira: {formatar_data_rj(exp)}")
        else: await q.answer("⏳ Aguardando", show_alert=True)

# ==============================================
# ⏰ GERENCIADOR
# ==============================================
async def gerenciar(app):
    await asyncio.sleep(10)
    while True:
        agora=time.time()
        for cli in collection_clientes.find({}):
            r = cli.get("expira_em",0)-agora; uid=cli["user_id"]
            if 82800<=r<=86400 and not cli.get("aviso1"):
                try: await app.bot.send_message(uid,"⚠️ Vence AMANHÃ!"); collection_clientes.update_one({"user_id":uid},{"$set":{"aviso1":True}})
                except: pass
            elif 0<r<=1200 and not cli.get("aviso2"):
                try: await app.bot.send_message(uid,"🚨 Vence EM MINUTOS!"); collection_clientes.update_one({"user_id":uid},{"$set":{"aviso2":True}})
                except: pass
            elif r<=0:
                try: await app.bot.kick_chat_member(CANAL_ALVO_ID,uid); await app.bot.unban_chat_member(CANAL_ALVO_ID,uid)
                except: pass
                collection_clientes.delete_one({"user_id":uid})
        await asyncio.sleep(60)

# ==============================================
# 🚀 INICIO SEM CONFLITO
# ==============================================
if __name__ == "__main__":
    # Inicia Flask em thread SEPARADA e DEPOIS do bot
    def iniciar_flask():
        import web
        web.app_web.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)), use_reloader=False)
    threading.Thread(target=iniciar_flask, daemon=True).start()

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(TypeHandler(Update, interceptador), group=-1)
    app.add_handler(ChatMemberHandler(saiu_canal, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("suporte", suporte_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("ping", ping_cmd))
    app.add_handler(CommandHandler("pegarid", pegarid_cmd))
    app.add_handler(CommandHandler("clientes", clientes_cmd))
    app.add_handler(CallbackQueryHandler(botoes))
    asyncio.create_task(gerenciar(app))

    print("✅ BOT ONLINE SEM ERROS!")
    # ✅ NÃO USE close_loop=False AQUI! O bot gerencia sozinho
    app.run_polling(drop_pending_updates=True)
