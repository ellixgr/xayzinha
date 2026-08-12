import os
import time
import asyncio
import requests
import random
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
# ✅ VARIÁVEIS DE AMBIENTE NO RENDER
# ==============================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN")
DONO_ID = int(os.environ.get("DONO_ID", 7711945457))
CANAL_ALVO_ID = int(os.environ.get("CANAL_ALVO_ID", -1004399892914))
MONGO_URI = os.environ.get("MONGO_URI")

if not TELEGRAM_TOKEN or not MONGO_URI:
    raise SystemExit("❌ ERRO: Adicione TELEGRAM_TOKEN e MONGO_URI nas variáveis!")

# Seus vídeos
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
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = mongo_client["sanizinhabot_db"]
    collection_clientes = db["clientes"]
    print("✅ Conectado ao MongoDB!")
except Exception as e:
    raise SystemExit(f"❌ Erro Mongo: {e}")

FUSO_RJ = timezone(timedelta(hours=-3))
pagamentos_notificados = set()

# ==============================================
# ⚙️ FUNÇÕES AUXILIARES
# ==============================================
def formatar_tempo_restante(segundos):
    if segundos <= 0: return "Expirado"
    if segundos >= 315360000: return "PERMANENTE/VITALÍCIO"
    dias = int(segundos // 86400); horas = int((segundos % 86400) // 3600)
    return f"{dias}d {horas}h".strip()

def formatar_data_rj(timestamp):
    return datetime.fromtimestamp(timestamp, tz=FUSO_RJ).strftime("%d/%m/%Y às %H:%M")

# ==============================================
# 📋 COMANDOS ADMIN
# ==============================================
async def pegarid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID: return
    video = None
    if update.message.reply_to_message and update.message.reply_to_message.video:
        video = update.message.reply_to_message.video
    elif update.message.video:
        video = update.message.video
    if video:
        await update.message.reply_text(f"✅ FILE_ID:\n\n{video.file_id}\nDuração: {video.duration} segundos")
    else:
        await update.message.reply_text("⚠️ Responda/envie um vídeo com /pegarid")

async def clientes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID: return
    agora = time.time()
    lista = list(collection_clientes.find({}))
    texto = f"📋 LISTA CLIENTES ({len(lista)}):\n\n"
    for i, cli in enumerate(lista, 1):
        texto += (
            f"{i}. {cli.get('nome', 'Desconhecido')}\n"
            f"🆔 ID: {cli['user_id']}\n"
            f"👤 Usuário: {cli.get('username', 'Não informado')}\n"
            f"💰 Valor Pago: R${cli.get('valor_pago', 'Não registrado')}\n"
            f"📅 Compra: {formatar_data_rj(cli.get('data_compra', agora))}\n"
            f"⏳ Expira: {formatar_tempo_restante(cli.get('expira_em',0)-agora)}\n\n"
        )
    await update.message.reply_text(texto)

async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID: return
    await update.message.reply_text(f"👤 Seu ID: {update.effective_user.id}\n💬 Chat ID: {update.effective_chat.id}")

async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID: return
    inicio = time.time()
    msg = await update.message.reply_text("🏓 Calculando...")
    lat = int((time.time() - inicio)*1000)
    await msg.edit_text(f"🏓 PONG! Latência: {lat}ms")

# ==============================================
# 🛒 VENDAS E PAGAMENTOS
# ==============================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": return
    texto = "𝗧𝗢𝗗𝗢𝗦 𝗢𝗦 𝗖𝗢𝗡𝗧𝗘𝗨𝗗𝗢𝗦 𝗩𝗔𝗭𝗔𝗗0𝗦 🤫\nEscolha seu plano VIP:\nSuporte: @Lyhhxv"
    botoes = [
        [InlineKeyboardButton("1 HORA → R$ 1,00🔥", callback_data="comprar_1")],
        [InlineKeyboardButton("1 DIA → R$ 5,00", callback_data="comprar_5")],
        [InlineKeyboardButton("1 SEMANA → R$ 10,00", callback_data="comprar_10")],
        [InlineKeyboardButton("1 MÊS → R$ 30,00", callback_data="comprar_30")],
        [InlineKeyboardButton("PERMANENTE → R$ 55,00", callback_data="comprar_55")]
    ]
    try:
        await update.message.reply_video(random.choice(LISTA_VIDEOS_START), caption=texto, reply_markup=InlineKeyboardMarkup(botoes))
    except:
        await update.message.reply_text(texto, reply_markup=InlineKeyboardMarkup(botoes))

async def suporte_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Suporte: @Lyhhxv")

async def gerar_pagamento(valor):
    url = "https://api.mercadopago.com/v1/payments"
    headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "transaction_amount": valor,
        "description": "Acesso VIP Grupo",
        "payment_method_id": "pix",
        "payer": {"email": "cliente@botvip.com"}
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
    except Exception as e:
        return False, None, f"Erro conexão: {str(e)}"
    if r.status_code == 201:
        dados = r.json()
        return True, dados["id"], dados["point_of_interaction"]["transaction_data"]["qr_code"]
    return False, None, f"Erro {r.status_code}"

async def verificar_pagamento(pid):
    try:
        r = requests.get(f"https://api.mercadopago.com/v1/payments/{pid}", headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}, timeout=10)
    except:
        return False, 0
    if r.status_code == 200:
        dados = r.json()
        return dados.get("status") == "approved", dados.get("transaction_amount", 0)
    return False, 0

async def botoes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    dados = q.data

    if dados.startswith("comprar_"):
        valor = float(dados.split("_")[1])
        ok, pid, pix = await gerar_pagamento(valor)
        if ok:
            await q.edit_message_text(
                f"✅ PIX GERADO COM SUCESSO!\n💸 Valor: R$ {valor:.2f}\n\n{pix}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Verificar Pagamento", callback_data=f"check_{pid}")]])
            )
        else:
            await q.edit_message_text(f"❌ Erro ao gerar: {pix}")

    elif dados.startswith("check_"):
        ok, valor_pago = await verificar_pagamento(dados.split("_")[1])
        if ok:
            await q.answer("✅ PAGAMENTO APROVADO!", show_alert=True)
            # Define duração do plano
            if abs(valor_pago - 1) < 0.05: seg, nome = 3600, "1 Hora"
            elif abs(valor_pago - 5) < 0.05: seg, nome = 86400, "1 Dia"
            elif abs(valor_pago - 10) < 0.05: seg, nome = 86400*7, "1 Semana"
            elif abs(valor_pago - 30) < 0.05: seg, nome = 86400*30, "1 Mês"
            elif abs(valor_pago - 55) < 0.05: seg, nome = 3153600000, "PERMANENTE/VITALÍCIO"
            else: seg, nome = int(valor_pago*86400), f"R${valor_pago:.2f}"

            uid = update.effective_user.id
            expira = time.time() + seg

            # Salva no banco
            collection_clientes.update_one(
                {"user_id": uid},
                {"$set": {
                    "nome": update.effective_user.first_name,
                    "username": f"@{update.effective_user.username}" if update.effective_user.username else "Não informado",
                    "valor_pago": f"{valor_pago:.2f}",
                    "expira_em": expira,
                    "data_compra": time.time()
                }},
                upsert=True
            )

            # Envia link do grupo
            try:
                link = await context.bot.create_chat_invite_link(CANAL_ALVO_ID, expire_date=int(time.time())+86400, member_limit=1)
                await q.message.reply_text(f"🎉 ACESSO LIBERADO!\n✅ Plano: {nome}\n🔗 Link: {link.invite_link}\nAproveite muito 🩷🤭")
            except:
                await q.message.reply_text("🎉 Aprovado! Contate o suporte para receber o link 🩷")

            # Avisa você (dono)
            if dados.split("_")[1] not in pagamentos_notificados:
                pagamentos_notificados.add(dados.split("_")[1])
                await context.bot.send_message(
                    DONO_ID,
                    f"✅ NOVA VENDA CONFIRMADA!\n"
                    f"👤 Cliente: {update.effective_user.first_name}\n"
                    f"🆔 ID: {uid}\n"
                    f"💸 Valor: R${valor_pago:.2f}\n"
                    f"📦 Plano: {nome}\n"
                    f"📅 Pago em: {formatar_data_rj(time.time())}\n"
                    f"⏳ Expira em: {'PERMANENTE' if seg>315360000 else formatar_data_rj(expira)}"
                )
        else:
            await q.answer("⏳ Aguardando confirmação do pagamento...", show_alert=True)

# ==============================================
# 🔒 ANTI-FLOOD + GERENCIADOR DE EXPIRAÇÕES
# ==============================================
async def interceptador(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u or u.id == DONO_ID: return
    if update.message and update.message.text and update.message.text.startswith('/'):
        cmd = update.message.text.split()[0].lower()
        if cmd not in ['/start','/suporte']: raise ApplicationHandlerStop

async def verificar_saida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.my_chat_member.chat.id == CANAL_ALVO_ID and update.my_chat_member.new_chat_member.status in ["left","kicked"]:
        collection_clientes.delete_one({"user_id": update.my_chat_member.from_user.id})

async def gerenciar_expiracoes(app):
    await asyncio.sleep(10)
    while True:
        agora = time.time()
        for cli in collection_clientes.find({}):
            restante = cli.get("expira_em", 0) - agora
            uid = cli["user_id"]
            if restante <= 0:
                try: await app.bot.kick_chat_member(CANAL_ALVO_ID, uid); await app.bot.unban_chat_member(CANAL_ALVO_ID, uid)
                except: pass
                collection_clientes.delete_one({"user_id": uid})
        await asyncio.sleep(60)

async def inicializar(app):
    asyncio.create_task(gerenciar_expiracoes(app))

# ==============================================
# 🚀 INICIO SEM ERRO DE LOOP! RESOLVIDO DE VEZ!
# ==============================================
if __name__ == "__main__":
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Registra todos os handlers
    app.add_handler(TypeHandler(Update, interceptador), group=-1)
    app.add_handler(ChatMemberHandler(verificar_saida, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("suporte", suporte_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("ping", ping_cmd))
    app.add_handler(CommandHandler("pegarid", pegarid_cmd))
    app.add_handler(CommandHandler("clientes", clientes_cmd))
    app.add_handler(CallbackQueryHandler(botoes_callback))

    app.post_init = inicializar

    print("✅ BOT 100% ONLINE, SEM ERROS, SEM CONFLITOS! 🚀")
    app.run_polling(drop_pending_updates=True)
