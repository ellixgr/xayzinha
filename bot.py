import os
import uuid
import time
import asyncio
import requests
import threading
import random
import re
from datetime import datetime, timezone, timedelta
from flask import Flask
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
# 🚫 REMOVA QUALQUER nest_asyncio — vamos usar método mais estável!
# ==============================================

app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "SanizinhaBot está online!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)

# ==============================================
# ✅ CONFIGURAÇÕES DO AMBIENTE
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
    mongo_client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        tlsAllowInvalidCertificates=True
    )
    db = mongo_client["sanizinhabot_db"]
    collection_clientes = db["clientes"]
    collection_chats = db["chats_autorizados"]
except Exception as e:
    print(f"❌ Erro ao conectar MongoDB: {e}")

TEMPO_INICIAL = time.time()
FUSO_RJ = timezone(timedelta(hours=-3))
ULTIMO_COMANDO = {}
CONTADOR_AVISOS_FLOD = {}
BLOQUEIO_FLOD = {}
TEMPO_LIMITE_COMANDO = 2
MAX_AVISOS_FLOD = 5
TEMPO_BLOQUEIO_FLOD = 600
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
# 📋 COMANDOS DO BOT
# ==============================================
async def pegarid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID: return
    v = None
    if update.message.reply_to_message and update.message.reply_to_message.video:
        v = update.message.reply_to_message.video
    elif update.message.video:
        v = update.message.video
    if v:
        await update.message.reply_text(f"✅ FILE_ID:\n{v.file_id}\nDuração: {v.duration}s")
    else:
        await update.message.reply_text("⚠️ Responda/envie um vídeo com /pegarid")

async def clientes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID: return
    agora = time.time(); clientes = list(collection_clientes.find({}))
    if not clientes: return await update.message.reply_text("Nenhum cliente cadastrado!")
    texto = f"📋 CLIENTES ATIVOS ({len(clientes)}):\n\n"
    for i,cli in enumerate(clientes,1):
        texto += (
            f"{i}. {cli.get('nome','?')}\n🆔 ID: {cli['user_id']}\n👤 @: {cli.get('username','Não informado')}\n"
            f"💰 Valor Pago: R$ {cli.get('valor_pago','Não registrado')}\n📅 Pagamento: {formatar_data_rj(cli.get('data_compra',0)) if cli.get('data_compra') else 'Não registrada'}\n"
            f"⏳ Expira em: {formatar_tempo_restante(cli.get('expira_em',0)-agora)}\n\n"
        )
    await update.message.reply_text(texto)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": return
    texto = (
        "𝗧𝗢𝗗𝗢𝗦 𝗢𝗦 𝗖𝗢𝗡𝗧𝗘𝗨𝗗𝗢𝗦 𝗩𝗔𝗭𝗔𝗗0𝗦🤫 𝗗𝗢 𝗠𝗢𝗠𝗘𝗡𝗧𝗢🥵\n\n"
        "Tenha acesso completo a todo o nosso conteúdo atualizado:\n"
        "+20mil mídias (vídeos/fotos)\n\nEscolha seu plano VIP:\nSuporte: @Lyhhxv"
    )
    botoes = [
        [InlineKeyboardButton("1 HORA → R$ 1,00🔥", callback_data="comprar_1.00")],
        [InlineKeyboardButton("1 DIA → R$ 5,00", callback_data="comprar_5.00")],
        [InlineKeyboardButton("1 SEMANA → R$ 10,00", callback_data="comprar_10.00")],
        [InlineKeyboardButton("1 MÊS → R$ 30,00", callback_data="comprar_30.00")],
        [InlineKeyboardButton("PERMANENTE → R$ 55,00", callback_data="comprar_55.00")]
    ]
    try: await update.message.reply_video(random.choice(LISTA_VIDEOS_START), caption=texto, reply_markup=InlineKeyboardMarkup(botoes), protect_content=True)
    except: await update.message.reply_text(texto, reply_markup=InlineKeyboardMarkup(botoes))

async def suporte_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Suporte:\nContate: @Lyhhxv")

async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID: return
    await update.message.reply_text(f"📌 ID Chat: {update.effective_chat.id}\n👤 Seu ID: {update.effective_user.id}")

async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID: return
    ini=time.time(); msg=await update.message.reply_text("Pong..."); lat=int((time.time()-ini)*1000)
    await msg.edit_text(f"🏓 PONG!\n⏱️ Latência: {lat}ms")

# ==============================================
# 🔒 ANTI-FLOOD / INTERCEPTOR
# ==============================================
async def interceptador_universal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u or u.id == DONO_ID: return
    if update.message and update.message.text and update.message.text.startswith('/'):
        cmd = update.message.text.split()[0].split('@')[0].lower()
        if cmd not in ['/start','/suporte','/suport']: raise ApplicationHandlerStop

async def verificar_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.my_chat_member.chat.id == CANAL_ALVO_ID and update.my_chat_member.new_chat_member.status in ["left","kicked"]:
        collection_clientes.delete_one({"user_id": update.my_chat_member.from_user.id})

# ==============================================
# 💳 PAGAMENTOS MERCADO PAGO
# ==============================================
async def gerar_pagamento(valor, usuario):
    url = "https://api.mercadopago.com/v1/payments"
    headers = {"Authorization":f"Bearer {MP_ACCESS_TOKEN}","Content-Type":"application/json"}
    payload = {
        "transaction_amount":valor, "description":f"Acesso VIP - R${valor:.2f}",
        "payment_method_id":"pix", "payer":{"email":f"user{usuario.id}@bot.com"}
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        if r.status_code==201:
            d=r.json()
            return True, d["id"], d["point_of_interaction"]["transaction_data"]["qr_code"]
        return False, None, f"Erro {r.status_code}"
    except Exception as e:
        return False, None, str(e)

async def verificar_pagamento(pid):
    try:
        r = requests.get(f"https://api.mercadopago.com/v1/payments/{pid}", headers={"Authorization":f"Bearer {MP_ACCESS_TOKEN}"}, timeout=10)
        if r.status_code==200:
            d=r.json()
            return d.get("status")=="approved", d.get("transaction_amount",0)
        return False,0
    except:
        return False,0

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); d = q.data

    if d.startswith("comprar_"):
        valor = float(d.split("_")[1])
        await q.edit_message_caption("🔄 Gerando PIX...", reply_markup=None)
        ok,pid,pix = await gerar_pagamento(valor, update.effective_user)
        if ok:
            await q.message.reply_text(
                f"✅ PIX Gerado com Sucesso!\nValor: R${valor:.2f}\n\nCódigo Copia e Cola:\n{pix}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Verificar Pagamento", callback_data=f"check_{pid}")]])
            )
        else:
            await q.message.reply_text(f"❌ Erro ao gerar Pix:\n{pix}")

    elif d.startswith("check_"):
        ok,valor = await verificar_pagamento(d.split("_")[1])
        if ok:
            await q.answer("✅ Pagamento Aprovado!", show_alert=True)
            if abs(valor-1.00)<0.01: seg=3600; nome="1 Hora"
            elif abs(valor-5.00)<0.01: seg=86400; nome="1 Dia"
            elif abs(valor-10.00)<0.01: seg=86400*7; nome="1 Semana"
            elif abs(valor-30.00)<0.01: seg=86400*30; nome="1 Mês"
            elif abs(valor-55.00)<0.01: seg=86400*365*10; nome="PERMANENTE"
            else: seg=int(valor*86400); nome=f"R${valor:.2f}"

            uid=update.effective_user.id; exp=time.time()+seg
            collection_clientes.update_one(
                {"user_id":uid},
                {"$set":{"nome":update.effective_user.first_name,"username":f"@{update.effective_user.username}","valor_pago":f"{valor:.2f}","expira_em":exp,"data_compra":time.time()}},
                upsert=True
            )
            try:
                link=await context.bot.create_chat_invite_link(CANAL_ALVO_ID, expire_date=int(time.time())+86400, member_limit=1)
                await q.message.reply_text(f"🎉 Aprovado!\nPlano: {nome}\nAcesse: {link.invite_link}\n\nAproveite o grupo🤭🩷")
            except:
                await q.message.reply_text("🎉 Aprovado! Contate o suporte para entrar 🩷")

            if d.split("_")[1] not in pagamentos_notificados:
                pagamentos_notificados.add(d.split("_")[1])
                await context.bot.send_message(
                    chat_id=DONO_ID,
                    text=(
                        "✅ NOVA ASSINATURA CONFIRMADA!\n"
                        f"Cliente: {update.effective_user.first_name}\nID: {uid}\nValor: R${valor:.2f}\nPlano: {nome}\n"
                        f"Pago em: {formatar_data_rj(time.time())}\nExpira em: {'Permanente' if nome=='PERMANENTE' else formatar_data_rj(exp)}"
                    )
                )
        else:
            await q.answer("⏳ Ainda não confirmado!", show_alert=True)

# ==============================================
# ⏰ GERENCIADOR DE ASSINATURAS
# ==============================================
async def gerenciador_assinaturas(app):
    await asyncio.sleep(10)
    while True:
        agora=time.time()
        for cli in collection_clientes.find({}):
            restante = cli.get("expira_em",0)-agora; uid=cli["user_id"]
            if 82800 <= restante <= 86400 and not cli.get("aviso_1d"):
                try: await app.bot.send_message(uid,"⚠️ SEU PLANO VENCE AMANHÃ! Renove agora!"); collection_clientes.update_one({"user_id":uid},{"$set":{"aviso_1d":True}})
                except: pass
            elif 0 < restante <=1200 and not cli.get("aviso_20m"):
                try: await app.bot.send_message(uid,"🚨 SEU PLANO EXPIRA EM MINUTOS! Renove AGORA!"); collection_clientes.update_one({"user_id":uid},{"$set":{"aviso_20m":True}})
                except: pass
            elif restante <=0:
                try: await app.bot.kick_chat_member(CANAL_ALVO_ID,uid); await app.bot.unban_chat_member(CANAL_ALVO_ID,uid)
                except: pass
                collection_clientes.delete_one({"user_id":uid})
        await asyncio.sleep(60)

# ==============================================
# 🚀 INICIALIZAÇÃO QUE RESOLVE O ERRO DE VEZ!
# ==============================================
def run_flask():
    run_web()

async def main():
    # Flask roda em thread separada
    threading.Thread(target=run_flask, daemon=True).start()

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Registra todos os handlers
    app.add_handler(TypeHandler(Update, interceptador_universal), group=-1)
    app.add_handler(ChatMemberHandler(verificar_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("suporte", suporte_cmd))
    app.add_handler(CommandHandler("suport", suporte_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("ping", ping_cmd))
    app.add_handler(CommandHandler("pegarid", pegarid_cmd))
    app.add_handler(CommandHandler("clientes", clientes_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))

    asyncio.create_task(gerenciador_assinaturas(app))

    print("✅ BOT ONLINE — SEM ERROS DE LOOP!")
    # ✅ CHAVE: close_loop=False + não usar asyncio.run() de forma conflitante
    await app.run_polling(drop_pending_updates=True, close_loop=False)

if __name__ == "__main__":
    # ✅ MÉTODO ESTÁVEL PARA RENDER/PYTHON3.14
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()
