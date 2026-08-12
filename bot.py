import os
import time
import asyncio
import requests
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
# ✅ VALIDAÇÃO DAS VARIÁVEIS DE AMBIENTE
# ==============================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN")
DONO_ID = int(os.environ.get("DONO_ID", 7711945457))
CANAL_ALVO_ID = int(os.environ.get("CANAL_ALVO_ID", -1004399892914))
MONGO_URI = os.environ.get("MONGO_URI")

if not TELEGRAM_TOKEN:
    raise SystemExit("❌ ERRO: Variável TELEGRAM_TOKEN não definida!")
if not MONGO_URI:
    raise SystemExit("❌ ERRO: Variável MONGO_URI não definida!")

# File IDs dos seus vídeos
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
try:
    mongo_client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        tlsAllowInvalidCertificates=True
    )
    db = mongo_client["sanizinhabot_db"]
    collection_clientes = db["clientes"]
    print("✅ Conectado ao MongoDB!")
except Exception as e:
    raise SystemExit(f"❌ Erro ao conectar MongoDB: {e}")

FUSO_RJ = timezone(timedelta(hours=-3))
pagamentos_notificados = set()

# ==============================================
# ⚙️ FUNÇÕES AUXILIARES
# ==============================================
def formatar_tempo_restante(segundos):
    if segundos <= 0: return "Expirado"
    if segundos >= 315360000: return "PERMANENTE/VITALÍCIO"
    dias = int(segundos // 86400); horas = int((segundos % 86400) // 3600); minutos = int((segundos % 3600) // 60)
    partes = []
    if dias>0: partes.append(f"{dias}d")
    if horas>0: partes.append(f"{horas}h")
    if minutos>0: partes.append(f"{minutos}m")
    return " ".join(partes) if partes else "Menos de 1 minuto"

def formatar_data_rj(timestamp):
    return datetime.fromtimestamp(timestamp, tz=FUSO_RJ).strftime("%d/%m/%Y às %H:%M")

# ==============================================
# 📋 COMANDOS
# ==============================================
async def pegarid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID: return
    video = None
    if update.message.reply_to_message and update.message.reply_to_message.video:
        video = update.message.reply_to_message.video
    elif update.message.video:
        video = update.message.video
    if video:
        await update.message.reply_text(f"✅ FILE_ID DO VÍDEO:\n\n{video.file_id}\n\nDuração: {video.duration} segundos")
    else:
        await update.message.reply_text("⚠️ Responda/envie um vídeo com /pegarid")

async def clientes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID: return
    agora = time.time(); clientes = list(collection_clientes.find({}))
    if not clientes: return await update.message.reply_text("📭 Nenhum cliente cadastrado!")
    texto = f"📋 LISTA DE CLIENTES ATIVOS ({len(clientes)}):\n\n"
    for i,cli in enumerate(clientes,1):
        username = cli.get('username', 'Não informado')
        if username == "@None": username = "Não informado"
        texto += (
            f"🔹 {i}. {cli.get('nome','Desconhecido')}\n"
            f"🆔 ID: {cli.get('user_id','?')}\n"
            f"👤 @: {username}\n"
            f"💰 Valor Pago: R$ {cli.get('valor_pago','Não registrado')}\n"
            f"📅 Pagamento: {formatar_data_rj(cli.get('data_compra',0)) if cli.get('data_compra') else 'Não registrada'}\n"
            f"⏳ Expira em: {formatar_tempo_restante(cli.get('expira_em',0)-agora)}\n\n"
        )
    await update.message.reply_text(texto)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": return
    texto = "𝗧𝗢𝗗𝗢𝗦 𝗢𝗦 𝗖𝗢𝗡𝗧𝗘𝗨𝗗𝗢𝗦 𝗩𝗔𝗭𝗔𝗗0𝗦🤫 𝗗𝗢 𝗠𝗢𝗠𝗘𝗡𝗧𝗢🥵\n\nEscolha seu plano VIP:\nSuporte: @Lyhhxv"
    botoes = [
        [InlineKeyboardButton("1 HORA → R$ 1,00🔥", callback_data="comprar_1.00")],
        [InlineKeyboardButton("1 DIA → R$ 5,00", callback_data="comprar_5.00")],
        [InlineKeyboardButton("1 SEMANA → R$ 10,00", callback_data="comprar_10.00")],
        [InlineKeyboardButton("1 MÊS → R$ 30,00", callback_data="comprar_30.00")],
        [InlineKeyboardButton("PERMANENTE → R$ 55,00", callback_data="comprar_55.00")]
    ]
    try:
        await update.message.reply_video(random.choice(LISTA_VIDEOS_START), caption=texto, reply_markup=InlineKeyboardMarkup(botoes))
    except Exception as e:
        print(f"Erro vídeo: {e}")
        await update.message.reply_text(texto, reply_markup=InlineKeyboardMarkup(botoes))

async def suporte_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Suporte: @Lyhhxv")

async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID: return
    await update.message.reply_text(f"📌 Chat: {update.effective_chat.id}\n👤 Seu ID: {update.effective_user.id}")

async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID: return
    ini=time.time(); msg=await update.message.reply_text("🏓 Calculando..."); lat=int((time.time()-ini)*1000)
    await msg.edit_text(f"🏓 PONG!\n⏱️ Latência: {lat}ms")

# ==============================================
# 🔒 ANTI-FLOOD
# ==============================================
async def interceptador_universal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u or u.id == DONO_ID: return
    if update.message and update.message.text and update.message.text.startswith('/'):
        cmd = update.message.text.split()[0].split('@')[0].lower()
        if cmd not in ['/start','/suporte','/suport']: raise ApplicationHandlerStop

async def verificar_saida_canal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.my_chat_member.chat.id == CANAL_ALVO_ID and update.my_chat_member.new_chat_member.status in ["left","kicked"]:
        collection_clientes.delete_one({"user_id": update.my_chat_member.from_user.id})

# ==============================================
# 💳 PAGAMENTOS MERCADO PAGO
# ==============================================
async def gerar_pagamento(valor):
    url = "https://api.mercadopago.com/v1/payments"
    headers = {"Authorization":f"Bearer {MP_ACCESS_TOKEN}","Content-Type":"application/json"}
    payload = {"transaction_amount":valor,"description":"Acesso VIP","payment_method_id":"pix","payer":{"email":"cliente@botvip.com"}}
    try: r=requests.post(url,json=payload,headers=headers,timeout=15)
    except Exception as e: return False,None,f"Erro conexão: {e}"
    if r.status_code==201: d=r.json(); return True,d["id"],d["point_of_interaction"]["transaction_data"]["qr_code"]
    return False,None,f"Erro {r.status_code}"

async def verificar_pagamento(pid):
    try: r=requests.get(f"https://api.mercadopago.com/v1/payments/{pid}",headers={"Authorization":f"Bearer {MP_ACCESS_TOKEN}"},timeout=10)
    except: return False,0
    if r.status_code==200: d=r.json(); return d.get("status")=="approved",d.get("transaction_amount",0)
    return False,0

async def botoes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); d = q.data
    if d.startswith("comprar_"):
        v = float(d.split("_")[1])
        ok,pid,pix = await gerar_pagamento(v)
        if ok: await q.edit_message_text(f"✅ PIX GERADO!\nValor: R${v:.2f}\n\n{pix}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Verificar Pagamento", callback_data=f"check_{pid}")]]))
        else: await q.edit_message_text(f"❌ Erro: {pix}")
    elif d.startswith("check_"):
        ok,valor = await verificar_pagamento(d.split("_")[1])
        if ok:
            await q.answer("✅ PAGAMENTO APROVADO!", show_alert=True)
            if abs(valor-1.00)<0.01: seg=3600; nome="1 Hora"
            elif abs(valor-5.00)<0.01: seg=86400; nome="1 Dia"
            elif abs(valor-10.00)<0.01: seg=86400*7; nome="1 Semana"
            elif abs(valor-30.00)<0.01: seg=86400*30; nome="1 Mês"
            elif abs(valor-55.00)<0.01: seg=86400*365*10; nome="PERMANENTE/VITALÍCIO"
            else: seg=int(valor*86400); nome=f"R${valor:.2f}"
            uid=update.effective_user.id; exp=time.time()+seg
            collection_clientes.update_one({"user_id":uid},{"$set":{"nome":update.effective_user.first_name,"username":f"@{update.effective_user.username}" if update.effective_user.username else "Não informado","valor_pago":f"{valor:.2f}","expira_em":exp,"data_compra":time.time(),"aviso1":False,"aviso2":False}},upsert=True)
            try: link=await context.bot.create_chat_invite_link(CANAL_ALVO_ID, expire_date=int(time.time())+86400, member_limit=1); await q.message.reply_text(f"🎉 ACESSO LIBERADO!\nPlano: {nome}\nLink: {link.invite_link}\nAproveite 🩷🤭")
            except Exception as e: await q.message.reply_text(f"🎉 Aprovado! Contate suporte 🩷")
            if d.split("_")[1] not in pagamentos_notificados:
                pagamentos_notificados.add(d.split("_")[1])
                await context.bot.send_message(DONO_ID,f"✅ NOVA ASSINATURA CONFIRMADA!\nCliente: {update.effective_user.first_name}\nID: {uid}\nValor: R${valor:.2f}\nPlano: {nome}\nPago em: {formatar_data_rj(time.time())}\nExpira em: {'PERMANENTE/VITALÍCIO' if nome.startswith('PERM') else formatar_data_rj(exp)}")
        else: await q.answer("⏳ Aguardando confirmação...", show_alert=True)

# ==============================================
# ⏰ GERENCIADOR DE EXPIRAÇÕES
# ==============================================
async def gerenciador_assinaturas(app):
    await asyncio.sleep(10)
    while True:
        agora=time.time()
        for cli in collection_clientes.find({}):
            r = cli.get("expira_em",0)-agora; uid=cli["user_id"]
            if 82800<=r<=86400 and not cli.get("aviso1"):
                try: await app.bot.send_message(uid,"⚠️ SEU PLANO VENCE AMANHÃ!"); collection_clientes.update_one({"user_id":uid},{"$set":{"aviso1":True}})
                except: pass
            elif 0<r<=1200 and not cli.get("aviso2"):
                try: await app.bot.send_message(uid,"🚨 ALERTA: Expira em minutos!"); collection_clientes.update_one({"user_id":uid},{"$set":{"aviso2":True}})
                except: pass
            elif r<=0:
                try: await app.bot.kick_chat_member(CANAL_ALVO_ID,uid); await app.bot.unban_chat_member(CANAL_ALVO_ID,uid)
                except: pass
                collection_clientes.delete_one({"user_id":uid})
        await asyncio.sleep(60)

# ✅ FUNÇÃO DE INICIALIZAÇÃO CORRETA (executa DEPOIS do loop estar ativo)
async def inicializar_tarefas(app):
    asyncio.create_task(gerenciador_assinaturas(app))

# ==============================================
# 🚀 INICIO SEM ERRO DE LOOP
# ==============================================
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(TypeHandler(Update, interceptador_universal), group=-1)
    app.add_handler(ChatMemberHandler(verificar_saida_canal, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("suporte", suporte_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("ping", ping_cmd))
    app.add_handler(CommandHandler("pegarid", pegarid_cmd))
    app.add_handler(CommandHandler("clientes", clientes_cmd))
    app.add_handler(CallbackQueryHandler(botoes_callback))

    # ✅ AQUI É O LUGAR CERTO! O loop já está rodando quando executa
    app.post_init = inicializar_tarefas

    print("✅ BOT ONLINE SEM ERROS DE LOOP! 🚀")
    app.run_polling(drop_pending_updates=True)
