import os
import uuid
import time
import asyncio
import requests
import threading
import random
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
# 🚀 FLASK PARA RENDER NÃO MATAR O PROCESSO
# ==============================================
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "SanizinhaBot está online!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)

# ==============================================
# ✅ VARIÁVEIS
# ==============================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN")
DONO_ID = int(os.environ.get("DONO_ID", 7711945457))
CANAL_ALVO_ID = int(os.environ.get("CANAL_ALVO_ID", -1004399892914))
MONGO_URI = os.environ.get("MONGO_URI")

if not TELEGRAM_TOKEN or not MONGO_URI:
    raise SystemExit("❌ ERRO: Defina TELEGRAM_TOKEN e MONGO_URI!")

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

async def gerar_pagamento(valor, user, bot):
    url = "https://api.mercadopago.com/v1/payments"
    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "X-Idempotency-Key": str(uuid.uuid4())
    }
    payload = {
        "transaction_amount": valor,
        "description": f"Acesso VIP - R$ {valor:.2f}",
        "payment_method_id": "pix",
        "payer": {
            "email": f"user_{user.id}@telegrambot.com",
            "first_name": user.first_name or "Cliente",
            "last_name": user.last_name or "Telegram"
        }
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code == 201:
            dados = resp.json()
            qr = dados.get("point_of_interaction", {}).get("transaction_data", {}).get("qr_code", "")
            return True, dados["id"], qr
        else:
            print(f"ERRO MP: {resp.status_code} | {resp.text[:300]}")
            return False, None, f"Erro API: {resp.status_code}"
    except Exception as e:
        print(f"ERRO CONEXAO MP: {e}")
        return False, None, f"Erro de conexao: {str(e)}"

async def verificar_pagamento(pag_id):
    url = f"https://api.mercadopago.com/v1/payments/{pag_id}"
    headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            dados = resp.json()
            return dados.get("status") == "approved", dados.get("transaction_amount", 0)
        return False, 0
    except Exception as e:
        print(f"Erro verificar pagamento: {e}")
        return False, 0

async def botoes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    dados = q.data

    if dados.startswith("comprar_"):
        valor = float(dados.split("_")[1])
        try:
            await q.edit_message_caption(caption="Gerando seu PIX, aguarde...", reply_markup=None)
        except:
            try:
                await q.edit_message_text("Gerando seu PIX, aguarde...")
            except:
                pass
        user = update.effective_user
        ok, pid, pix = await gerar_pagamento(valor, user, context.bot)
        if ok:
            msg_completa = (
                "PIX Gerado com Sucesso!\n\n"
                f"Valor: R$ {valor:.2f}\n\n"
                f"Codigo Pix Copia e Cola:\n{pix}"
            )
            keyboard_final = [
                [InlineKeyboardButton("Copiar Codigo Pix", copy_text=dict(text=pix))],
                [InlineKeyboardButton("Verificar Pagamento", callback_data=f"check_{pid}")]
            ]
            await q.message.reply_text(msg_completa, reply_markup=InlineKeyboardMarkup(keyboard_final))
        else:
            await q.message.reply_text(f"Erro ao gerar o Pix:\n{pix}")

    elif dados.startswith("check_"):
        payment_id = dados.split("_")[1]
        aprovado, valor_pago = await verificar_pagamento(payment_id)
        if aprovado:
            await q.answer("Pagamento Aprovado!", show_alert=True)
            if abs(valor_pago - 1.00) < 0.01:
                duracao_segundos = 3600
                nome_plano = "1 Hora"
            elif abs(valor_pago - 5.00) < 0.01:
                duracao_segundos = 86400
                nome_plano = "1 Dia"
            elif abs(valor_pago - 10.00) < 0.01:
                duracao_segundos = 86400 * 7
                nome_plano = "1 Semana"
            elif abs(valor_pago - 30.00) < 0.01:
                duracao_segundos = 86400 * 30
                nome_plano = "1 Mes"
            elif abs(valor_pago - 55.00) < 0.01:
                duracao_segundos = 86400 * 365 * 10
                nome_plano = "Permanente"
            else:
                duracao_segundos = int(valor_pago) * 86400
                nome_plano = f"R$ {valor_pago:.2f}"

            user_id = update.effective_user.id
            tempo_expiracao = time.time() + duracao_segundos
            user_obj = update.effective_user
            username = f"@{user_obj.username}" if user_obj.username else "Sem @"
            data_compra = time.time()

            collection_clientes.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "user_id": user_id,
                        "nome": user_obj.first_name or "Cliente",
                        "username": username,
                        "expira_em": tempo_expiracao,
                        "valor_pago": f"{valor_pago:.2f}",
                        "data_compra": data_compra,
                        "aviso_1dia_enviado": False,
                        "aviso_20min_enviado": False
                    }
                },
                upsert=True
            )

            link_convite = None
            if CANAL_ALVO_ID != 0:
                try:
                    convite = await context.bot.create_chat_invite_link(
                        chat_id=CANAL_ALVO_ID,
                        member_limit=1,
                        expire_date=int(time.time()) + 86400
                    )
                    link_convite = convite.invite_link
                except Exception as e:
                    print(f"Erro ao gerar link: {e}")

            texto_link = f"Aqui esta o seu link:\n{link_convite}" if link_convite else "Contate o suporte @Lyhhxv"
            data_compra_rj = formatar_data_rj(data_compra)
            data_expira_rj = "Permanente" if nome_plano == "Permanente" else formatar_data_rj(tempo_expiracao)

            await q.message.reply_text(
                f"Pagamento Aprovado!\n\n"
                f"Plano: {nome_plano}\n"
                f"Valor: R$ {valor_pago:.2f}\n\n{texto_link}\n\n"
                f"Aproveite o grupo🤭🩷"
            )

            if payment_id not in pagamentos_notificados:
                pagamentos_notificados.add(payment_id)
                comprador = update.effective_user
                relatorio = (
                    "NOVA ASSINATURA CONFIRMADA!\n\n"
                    f"Cliente: {comprador.first_name or 'Sem nome'}\n"
                    f"Usuario: @{comprador.username if comprador.username else 'Sem @'}\n"
                    f"ID: {comprador.id}\n"
                    f"Valor: R$ {valor_pago:.2f}\n"
                    f"Plano: {nome_plano}\n"
                    f"Pagamento em: {data_compra_rj}\n"
                    f"Expira em: {data_expira_rj}"
                )
                try:
                    await context.bot.send_message(chat_id=DONO_ID, text=relatorio)
                except:
                    pass
        else:
            await q.answer("Pagamento ainda nao identificado!", show_alert=True)
            await q.message.reply_text("Pagamento ainda nao identificado! Pague e aguarde, ou clique novamente.")

# ==============================================
# 🔒 ANTI-FLOOD + GERENCIADOR
# ==============================================
ULTIMO_COMANDO = {}
CONTADOR_AVISOS_FLOD = {}
BLOQUEIO_FLOD = {}
TEMPO_LIMITE_COMANDO = 2
MAX_AVISOS_FLOD = 5
TEMPO_BLOQUEIO_FLOD = 600

async def interceptador_universal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user: return
    user_id = user.id
    agora = time.time()
    if user_id == DONO_ID: return
    if user_id in BLOQUEIO_FLOD:
        if BLOQUEIO_FLOD[user_id] > agora:
            raise ApplicationHandlerStop
        else:
            del BLOQUEIO_FLOD[user_id]
            CONTADOR_AVISOS_FLOD.pop(user_id, None)
    COMANDOS_LIBERADOS = ['/start', '/suporte', '/suport']
    if update.message and update.message.text and update.message.text.startswith('/'):
        cmd = update.message.text.split()[0].split('@')[0].lower()
        if cmd in COMANDOS_LIBERADOS:
            if user_id not in ULTIMO_COMANDO:
                ULTIMO_COMANDO[user_id] = {}
            ultimo = ULTIMO_COMANDO[user_id].get(cmd, 0)
            if agora - ultimo < TEMPO_LIMITE_COMANDO:
                CONTADOR_AVISOS_FLOD[user_id] = CONTADOR_AVISOS_FLOD.get(user_id, 0) + 1
                avisos = CONTADOR_AVISOS_FLOD[user_id]
                if avisos >= MAX_AVISOS_FLOD:
                    BLOQUEIO_FLOD[user_id] = agora + TEMPO_BLOQUEIO_FLOD
                    CONTADOR_AVISOS_FLOD[user_id] = 0
                    if update.effective_chat.type == "private":
                        try: await context.bot.send_message(chat_id=update.effective_chat.id, text="Bloqueado por floodar! Tente novamente em 10 minutos.")
                        except: pass
                else:
                    if update.effective_chat.type == "private":
                        try: await context.bot.send_message(chat_id=update.effective_chat.id, text="Cuidado! Nao envie muitos comandos seguidos.")
                        except: pass
                raise ApplicationHandlerStop
            ULTIMO_COMANDO[user_id][cmd] = agora
            return
        else:
            raise ApplicationHandlerStop

async def verificar_saida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.my_chat_member.chat.id == CANAL_ALVO_ID and update.my_chat_member.new_chat_member.status in ["left","kicked"]:
        collection_clientes.delete_one({"user_id": update.my_chat_member.from_user.id})

async def gerenciar_expiracoes(app):
    await asyncio.sleep(10)
    while True:
        try:
            agora = time.time()
            for cli in collection_clientes.find({}):
                restante = cli.get("expira_em", 0) - agora
                uid = cli["user_id"]
                if 82800 <= restante <= 86400 and not cli.get("aviso_1dia_enviado", False):
                    try:
                        msg = "SEU PLANO VENCE AMANHA! Renove agora!"
                        keyboard = [
                            [InlineKeyboardButton("Renovar 1H R$1,00", callback_data="comprar_1")],
                            [InlineKeyboardButton("Renovar 1Dia R$5,00", callback_data="comprar_5")],
                            [InlineKeyboardButton("Outros Planos", callback_data="ver_outros")]
                        ]
                        await app.bot.send_message(chat_id=uid, text=msg, reply_markup=InlineKeyboardMarkup(keyboard))
                        collection_clientes.update_one({"user_id": uid}, {"$set": {"aviso_1dia_enviado": True}})
                    except: pass
                elif 0 < restante <= 1200 and not cli.get("aviso_20min_enviado", False):
                    try:
                        msg = "SEU PLANO EXPIRA EM MINUTOS! Renove AGORA!"
                        keyboard = [
                            [InlineKeyboardButton("Renovar 1H R$1,00", callback_data="comprar_1")],
                            [InlineKeyboardButton("Renovar 1Dia R$5,00", callback_data="comprar_5")],
                            [InlineKeyboardButton("Outros Planos", callback_data="ver_outros")]
                        ]
                        await app.bot.send_message(chat_id=uid, text=msg, reply_markup=InlineKeyboardMarkup(keyboard))
                        collection_clientes.update_one({"user_id": uid}, {"$set": {"aviso_20min_enviado": True}})
                    except: pass
                elif restante <= 0 and CANAL_ALVO_ID != 0:
                    try:
                        await app.bot.ban_chat_member(chat_id=CANAL_ALVO_ID, user_id=uid)
                        await app.bot.unban_chat_member(chat_id=CANAL_ALVO_ID, user_id=uid)
                        await app.bot.send_message(chat_id=uid, text="Seu plano expirou! Use /start e compre um novo.")
                    except: pass
                    collection_clientes.delete_one({"user_id": uid})
        except Exception as e:
            print(f"Erro gerenciador: {e}")
        await asyncio.sleep(60)

def run_background_loop(application):
    asyncio.run(gerenciar_expiracoes(application))

# ==============================================
# 🚀 INICIO — IGUAL SEU OUTRO BOT, RODA NO RENDER WEB SERVICE DE GRAÇA!
# ==============================================
def main():
    threading.Thread(target=run_web, daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    threading.Thread(target=run_background_loop, args=(app,), daemon=True).start()

    app.add_handler(TypeHandler(Update, interceptador_universal), group=-1)
    app.add_handler(ChatMemberHandler(verificar_saida, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("suporte", suporte_cmd))
    app.add_handler(CommandHandler("suport", suporte_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("ping", ping_cmd))
    app.add_handler(CommandHandler("pegarid", pegarid_cmd))
    app.add_handler(CommandHandler("clientes", clientes_cmd))
    app.add_handler(CallbackQueryHandler(botoes_callback))

    print("✅ BOT ONLINE E FUNCIONANDO NO RENDER DE GRAÇA! 🚀")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
