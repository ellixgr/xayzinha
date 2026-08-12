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

# --------------------------
# CONFIGS
# --------------------------
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "SanizinhaBot está ONLINE! ✅"

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

# Conexão MongoDB
mongo_client = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    tlsAllowInvalidCertificates=True,
    maxPoolSize=10
)
db = mongo_client["sanizinhabot_db"]
collection_clientes = db["clientes"]
collection_chats = db["chats_autorizados"]

TEMPO_INICIAL = time.time()
FUSO_RJ = timezone(timedelta(hours=-3))

ULTIMO_COMANDO = {}
CONTADOR_AVISOS_FLOD = {}
BLOQUEIO_FLOD = {}
TEMPO_LIMITE_COMANDO = 2
MAX_AVISOS_FLOD = 5
TEMPO_BLOQUEIO_FLOD = 600

pagamentos_notificados = set()

# --------------------------
# FUNÇÕES AUXILIARES
# --------------------------
def formatar_tempo_restante(segundos):
    if segundos <= 0: return "Expirado"
    if segundos >= 315360000: return "Permanente"
    dias = int(segundos // 86400)
    horas = int((segundos % 86400) // 3600)
    minutos = int((segundos % 3600) // 60)
    partes = []
    if dias: partes.append(f"{dias}d")
    if horas: partes.append(f"{horas}h")
    if minutos: partes.append(f"{minutos}m")
    return " ".join(partes) if partes else "Menos de 1m"

def formatar_data_rj(timestamp):
    return datetime.fromtimestamp(timestamp, tz=FUSO_RJ).strftime("%d/%m/%Y às %H:%M")

# --------------------------
# COMANDOS DO DONO
# --------------------------
async def pegarid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID: return
    mensagem = update.message
    video = mensagem.reply_to_message.video if mensagem.reply_to_message and mensagem.reply_to_message.video else mensagem.video
    if not video:
        return await mensagem.reply_text("⚠️ Responda um vídeo com /pegarid ou envie o vídeo junto do comando!")
    await mensagem.reply_text(f"✅ FILE_ID:\n\n{video.file_id}\n\nDuração: {video.duration}s\nColoque na LISTA_VIDEOS_START!")

async def clientes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID: return
    agora = time.time()
    clientes = list(collection_clientes.find({}))
    if not clientes: return await update.message.reply_text("📋 Nenhum cliente cadastrado no momento.")
    texto = f"📋 LISTA DE CLIENTES ATIVOS ({len(clientes)}):\n\n"
    for idx, cli in enumerate(clientes,1):
        tempo_rest = cli.get("expira_em",0) - agora
        texto += (
            f"{idx}. {cli.get('nome','?')}\n"
            f"🆔 ID: {cli.get('user_id')}\n"
            f"👤 @: {cli.get('username','Não informado')}\n"
            f"💰 Valor Pago: R$ {cli.get('valor_pago','Não registrado')}\n"
            f"📅 Pagamento: {formatar_data_rj(cli.get('data_compra',0)) if cli.get('data_compra') else 'Não registrada'}\n"
            f"⏳ Expira em: {formatar_tempo_restante(tempo_rest)}\n"
            f"📆 Limite: {'Permanente' if tempo_rest>=315360000 else formatar_data_rj(cli.get('expira_em',0))}\n\n"
        )
    await update.message.reply_text(texto)

async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID: return
    await update.message.reply_text(f"📌 ID Chat: {update.effective_chat.id}\n👤 Seu ID: {update.effective_user.id}")

async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID: return
    ini = time.time()
    msg = await update.message.reply_text("🏓 Pong...")
    lat = int((time.time()-ini)*1000)
    up = int(time.time()-TEMPO_INICIAL)
    await msg.edit_text(f"🏓 PONG!\nLatência: {lat}ms\nOnline: {up//3600}h {(up%3600)//60}m {up%60}s")

async def suporte_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Central de Suporte\n\nContate: @Lyhhxv")

# --------------------------
# REMOÇÃO AUTOMÁTICA QUANDO SAI
# --------------------------
async def verificar_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    res = update.my_chat_member
    if not res: return
    chat, status = res.chat, res.new_chat_member.status
    if chat.id == CANAL_ALVO_ID:
        usuario_id = res.from_user.id
        if status in ("left", "kicked", "restricted"):
            collection_clientes.delete_one({"user_id": usuario_id})
    if chat.type in ("group","supergroup","channel"):
        if status in ("member","administrator"):
            collection_chats.update_one({"chat_id":chat.id}, {"$set":{"chat_id":chat.id,"title":chat.title,"type":chat.type}}, upsert=True)
        elif status in ("left","kicked"):
            collection_chats.delete_one({"chat_id":chat.id})

# --------------------------
# BLOQUEIO DE FLOOD
# --------------------------
async def interceptador_universal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or user.id == DONO_ID: return
    agora = time.time()
    if user.id in BLOQUEIO_FLOD:
        if BLOQUEIO_FLOD[user.id] > agora: raise ApplicationHandlerStop
        else: del BLOQUEIO_FLOD[user.id]; CONTADOR_AVISOS_FLOD.pop(user.id, None)
    if update.message and update.message.text and update.message.text.startswith('/'):
        cmd = update.message.text.split()[0].split('@')[0].lower()
        if cmd in ['/start','/suporte','/suport']:
            ult = ULTIMO_COMANDO.get(user.id, {}).get(cmd,0)
            if agora - ult < TEMPO_LIMITE_COMANDO:
                CONTADOR_AVISOS_FLOD[user.id] = CONTADOR_AVISOS_FLOD.get(user.id,0)+1
                if CONTADOR_AVISOS_FLOD[user.id] >= MAX_AVISOS_FLOD:
                    BLOQUEIO_FLOD[user.id] = agora + TEMPO_BLOQUEIO_FLOD
                    CONTADOR_AVISOS_FLOD[user.id]=0
                    await context.bot.send_message(user.id, "⚠️ Bloqueado por floodar! Tente novamente em 10 minutos.")
                else: await context.bot.send_message(user.id, "⚠️ Cuidado! Não envie comandos seguidos.")
                raise ApplicationHandlerStop
            ULTIMO_COMANDO.setdefault(user.id, {})[cmd] = agora
        else: raise ApplicationHandlerStop

# --------------------------
# INICIO
# --------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": return
    texto = (
        "𝗧𝗢𝗗𝗢𝗦 𝗢𝗦 𝗖𝗢𝗡𝗧𝗘𝗨𝗗𝗢𝗦 𝗩𝗔𝗭𝗔𝗗𝗢𝗦🤫 𝗗𝗢 𝗠𝗢𝗠𝗘𝗡𝗧𝗢🥵\n\n"
        "Tenha acesso completo a todo conteúdo atualizado:\nMais de 20mil mídias disponíveis!\n\nEscolha seu plano VIP:"
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

# --------------------------
# PAGAMENTO MERCADO PAGO
# --------------------------
async def gerar_pagamento(valor, user):
    url = "https://api.mercadopago.com/v1/payments"
    headers = {"Authorization":f"Bearer {MP_ACCESS_TOKEN}","Content-Type":"application/json","X-Idempotency-Key":str(uuid.uuid4())}
    try:
        r = requests.post(url, json={"transaction_amount":valor,"description":f"Acesso VIP R${valor:.2f}","payment_method_id":"pix","payer":{"email":f"user_{user.id}@bot.com","first_name":user.first_name or "Cliente"}}, headers=headers, timeout=15)
        if r.status_code==201: return True, r.json()["id"], r.json()["point_of_interaction"]["transaction_data"]["qr_code"]
        return False, None, f"Erro API: {r.status_code}"
    except Exception as e: return False, None, str(e)

async def verificar_pagamento(pag_id):
    try:
        r = requests.get(f"https://api.mercadopago.com/v1/payments/{pag_id}", headers={"Authorization":f"Bearer {MP_ACCESS_TOKEN}"}, timeout=10)
        return r.status_code==200 and r.json()["status"]=="approved", r.json().get("transaction_amount",0)
    except: return False,0

# --------------------------
# BOTÕES
# --------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    dados = query.data

    if dados.startswith("comprar_"):
        valor = float(dados.split("_")[1])
        await query.edit_message_caption("🔄 Gerando seu código PIX, aguarde...", reply_markup=None) if query.message.caption else await query.edit_message_text("🔄 Gerando seu código PIX, aguarde...")
        ok, pag_id, qr = await gerar_pagamento(valor, update.effective_user)
        if ok:
            await query.message.reply_text(
                f"✅ PIX GERADO COM SUCESSO!\n\nValor: R$ {valor:.2f}\n\nCopie e pague:\n{qr}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 Copiar Código", copy_text={"text":qr})],
                    [InlineKeyboardButton("✅ Verificar Pagamento", callback_data=f"check_{pag_id}")]
                ])
            )
        else: await query.message.reply_text(f"❌ Erro ao gerar PIX: {qr}")

    elif dados.startswith("check_"):
        aprovado, val_pago = await verificar_pagamento(dados.split("_")[1])
        if aprovado:
            await query.answer("✅ PAGAMENTO APROVADO!", show_alert=True)
            if abs(val_pago-1)<0.01: seg, nome = 3600, "1 Hora"
            elif abs(val_pago-5)<0.01: seg, nome = 86400, "1 Dia"
            elif abs(val_pago-10)<0.01: seg, nome = 86400*7, "1 Semana"
            elif abs(val_pago-30)<0.01: seg, nome = 86400*30, "1 Mês"
            elif abs(val_pago-55)<0.01: seg, nome = 3153600000, "Permanente"
            else: seg, nome = int(val_pago)*86400, f"R${val_pago:.2f}"

            user = update.effective_user
            expira = time.time() + seg
            collection_clientes.update_one(
                {"user_id":user.id},
                {"$set":{"user_id":user.id,"nome":user.first_name or "Cliente","username":f"@{user.username}"if user.username else"Sem @","expira_em":expira,"valor_pago":f"{val_pago:.2f}","data_compra":time.time(),"aviso_1dia_enviado":False,"aviso_20min_enviado":False}},
                upsert=True
            )
            try: link = await context.bot.create_chat_invite_link(CANAL_ALVO_ID, expire_date=int(time.time())+86400, member_limit=1)
            except: link = None
            await query.message.reply_text(
                f"🎉 ACESSO LIBERADO!\n\nPlano: {nome}\nValor Pago: R$ {val_pago:.2f}\n\nSeu link: {link.invite_link if link else 'Contate o suporte @Lyhhxv'}\n\nAproveite muito 🩷"
            )
            if dados.split("_")[1] not in pagamentos_notificados:
                pagamentos_notificados.add(dados.split("_")[1])
                await context.bot.send_message(
                    chat_id=DONO_ID,
                    text=f"🔔 NOVA VENDA CONFIRMADA!\n\nCliente: {user.first_name}\nID: {user.id}\nUsuário: @{user.username if user.username else 'Sem @'}\nValor: R$ {val_pago:.2f}\nPlano: {nome}\nPagamento: {formatar_data_rj(time.time())}\nExpira: {'Permanente' if seg>=3153600000 else formatar_data_rj(expira)}"
                )
        else: await query.answer("⏳ Ainda não aprovado! Pague e clique novamente.", show_alert=True)

    elif dados == "ver_outros_precos":
        await query.message.reply_text("Escolha outro plano:", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("1 HORA → R$ 1,00", callback_data="comprar_1.00")],
            [InlineKeyboardButton("1 DIA → R$ 5,00", callback_data="comprar_5.00")],
            [InlineKeyboardButton("1 SEMANA → R$ 10,00", callback_data="comprar_10.00")],
            [InlineKeyboardButton("1 MÊS → R$ 30,00", callback_data="comprar_30.00")],
            [InlineKeyboardButton("PERMANENTE → R$ 55,00", callback_data="comprar_55.00")]
        ]))

# --------------------------
# GERENCIADOR DE ASSINATURAS (REMOÇÃO AUTOMÁTICA AO EXPIRAR)
# --------------------------
async def gerenciador_assinaturas(app):
    await asyncio.sleep(10)
    while True:
        agora = time.time()
        for cli in collection_clientes.find({}):
            rest = cli.get("expira_em",0) - agora
            if 82800 <= rest <= 86400 and not cli.get("aviso_1dia_enviado"):
                try: await app.bot.send_message(cli["user_id"], "⚠️ SEU PLANO VENCE AMANHÃ! Renove agora!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Renovar R$1",callback_data="comprar_1.00")],[InlineKeyboardButton("Renovar R$5",callback_data="comprar_5.00")]]))
                except: pass
                collection_clientes.update_one({"user_id":cli["user_id"]},{"$set":{"aviso_1dia_enviado":True}})
            elif 0 < rest <= 1200 and not cli.get("aviso_20min_enviado"):
                try: await app.bot.send_message(cli["user_id"], "🚨 ACABANDO EM MINUTOS! RENOVE AGORA!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Renovar R$1",callback_data="comprar_1.00")]]))
                except: pass
                collection_clientes.update_one({"user_id":cli["user_id"]},{"$set":{"aviso_20min_enviado":True}})
            elif rest <=0:
                try: await app.bot.kick_chat_member(CANAL_ALVO_ID, cli["user_id"]); await app.bot.unban_chat_member(CANAL_ALVO_ID, cli["user_id"])
                except: pass
                collection_clientes.delete_one({"user_id":cli["user_id"]})
        await asyncio.sleep(60)

# --------------------------
# INICIALIZAÇÃO
# --------------------------
def run_bot():
    async def bot_loop():
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        app.add_handler(TypeHandler(Update, interceptador_universal), group=-1)
        app.add_handler(ChatMemberHandler(verificar_my_chat_member))
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("suporte", suporte_cmd))
        app.add_handler(CommandHandler("suport", suporte_cmd))
        app.add_handler(CommandHandler("id", id_cmd))
        app.add_handler(CommandHandler("ping", ping_cmd))
        app.add_handler(CommandHandler("pegarid", pegarid_cmd))
        app.add_handler(CommandHandler("clientes", clientes_cmd))
        app.add_handler(CallbackQueryHandler(button_handler))
        asyncio.create_task(gerenciador_assinaturas(app))
        await app.run_polling(drop_pending_updates=True)
    asyncio.run(bot_loop())

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    print("✅ BOT ONLINE COM python-telegram-bot 22.8!")
    app_web.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
