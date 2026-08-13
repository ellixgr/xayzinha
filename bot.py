ACESSO os
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

app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "SanizinhaBot está online!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN")
DONO_ID = int(os.environ.get("DONO_ID", 7711945457))
CANAL_ALVO_ID = int(os.environ.get("CANAL_ALVO_ID", -1004399892914))
MONGO_URI = os.environ.get("MONGO_URI")


LISTA_VIDEOS_START = [
    "BAACAgEAAxkBAAMKanvd-2rf4BeJhsokFDuwcFwXK2EAAj0IAALXHuFH56allQhe6Sg9BA",  # 11s
    "BAACAgEAAxkBAAMJanvd6TMFHbXOJhMDQKA7nmbqu9EAAjsIAALXHuFHYw1Bd358q9Y9BA",  # 12s
    "BAACAgEAAxkBAAMIanvd6EgEPC10v73Qllv3LkpF3kAAAjoIAALXHuFHrLFcoPgzJqs9BA",  # 5s
    "BAACAgEAAxkBAAMHanvd57NHGzfWMAABD6oVHA1uAAGumQACOQgAAtce4UcPaNBTIBJ3vD0E", # 18s
    "BAACAgEAAxkBAAMGanvd59XTyesvUYRMqV59VF9YuXoAAjgIAALXHuFH9gutMcKA3JI9BA",  # 7s
    "BAACAgEAAxkBAAMFanvd3OOwk5fjRbquOF46iNkqNtkAAjcIAALXHuFHzx8KK4f6mfA9BA"   # 15s
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
    print(f"Erro crítico ao conectar no MongoDB: {e}")

TEMPO_INICIAL = time.time()
FUSO_RJ = timezone(timedelta(hours=-3))

ULTIMO_COMANDO = {}
CONTADOR_AVISOS_FLOD = {}
BLOQUEIO_FLOD = {}
TEMPO_LIMITE_COMANDO = 2
MAX_AVISOS_FLOD = 5
TEMPO_BLOQUEIO_FLOD = 600

pagamentos_notificados = set()

def formatar_tempo_restante(segundos):
    if segundos <= 0:
        return "Expirado"
    if segundos >= 315360000:
        return "Permanente"
    dias = int(segundos // 86400)
    horas = int((segundos % 86400) // 3600)
    minutos = int((segundos % 3600) // 60)
    partes = []
    if dias > 0:
        partes.append(f"{dias}d")
    if horas > 0:
        partes.append(f"{horas}h")
    if minutos > 0:
        partes.append(f"{minutos}m")
    return " ".join(partes) if partes else "Menos de 1m"

def formatar_data_rj(timestamp):
    return datetime.fromtimestamp(timestamp, tz=FUSO_RJ).strftime("%d/%m/%Y as %H:%M")

async def pegarid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID:
        return
    mensagem = update.message
    if mensagem.reply_to_message and mensagem.reply_to_message.video:
        video = mensagem.reply_to_message.video
        file_id = video.file_id
        duracao = video.duration
        texto = (
            "✅ FILE_ID DO VIDEO:\n\n"
            f"{file_id}\n\n"
            f"Duração: {duracao}s\n\n"
            "Coloque esse codigo na lista LISTA_VIDEOS_START!"
        )
        await mensagem.reply_text(texto)
        return
    if mensagem.video:
        file_id = mensagem.video.file_id
        duracao = mensagem.video.duration
        texto = (
            "✅ FILE_ID DO VIDEO:\n\n"
            f"{file_id}\n\n"
            f"Duração: {duracao}s\n\n"
            "Coloque esse codigo na lista LISTA_VIDEOS_START!"
        )
        await mensagem.reply_text(texto)
        return
    await mensagem.reply_text(
        "⚠️ RESPONDA um vídeo com /pegarid ou mande o vídeo junto com o comando!"
    )

async def clientes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID:
        return
    try:
        agora = time.time()
        clientes = list(collection_clientes.find({}))
        if not clientes:
            await update.message.reply_text("Nenhum cliente cadastrado no momento.")
            return
        texto = f"LISTA DE CLIENTES ATIVOS ({len(clientes)}):\n\n"
        for idx, cli in enumerate(clientes, 1):
            user_id = cli.get("user_id", "?")
            nome = cli.get("nome", "Nao informado")
            expira_em = cli.get("expira_em", 0)
            tempo_restante = expira_em - agora
            tempo_str = formatar_tempo_restante(tempo_restante)
            if tempo_str == "Permanente":
                data_limite = "Permanente"
            else:
                data_limite = formatar_data_rj(expira_em)
            valor_pago = cli.get("valor_pago", "Sem registro")
            data_compra_ts = cli.get("data_compra")
            data_compra = formatar_data_rj(data_compra_ts) if data_compra_ts else "Sem registro"
            username = cli.get("username", "Sem registro")
            texto += (
                f"{idx}. {nome}\n"
                f"ID: {user_id}\n"
                f"@: {username}\n"
                f"Valor Pago: R$ {valor_pago}\n"
                f"Pagamento: {data_compra}\n"
                f"Expira em: {tempo_str}\n"
                f"Limite: {data_limite}\n\n"
            )
        await update.message.reply_text(texto)
    except Exception as e:
        await update.message.reply_text(f"Erro ao listar clientes: {e}")

async def interceptador_universal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    user_id = user.id
    agora = time.time()
    if user_id == DONO_ID:
        return
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
                        try:
                            await context.bot.send_message(
                                chat_id=update.effective_chat.id,
                                text="Bloqueado por floodar! Tente novamente em 10 minutos."
                            )
                        except:
                            pass
                else:
                    if update.effective_chat.type == "private":
                        try:
                            await context.bot.send_message(
                                chat_id=update.effective_chat.id,
                                text="Cuidado! Nao envie muitos comandos seguidos."
                            )
                        except:
                            pass
                raise ApplicationHandlerStop
            ULTIMO_COMANDO[user_id][cmd] = agora
            return
        else:
            raise ApplicationHandlerStop

async def verificar_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if not result:
        return
    chat = result.chat
    new_status = result.new_chat_member.status
    if chat.type in ["group", "supergroup", "channel"]:
        try:
            if new_status in ["member", "administrator"]:
                collection_chats.update_one(
                    {"chat_id": chat.id},
                    {"$set": {"chat_id": chat.id, "title": chat.title, "type": chat.type}},
                    upsert=True
                )
            elif new_status in ["left", "kicked"]:
                collection_chats.delete_one({"chat_id": chat.id})
        except Exception as e:
            print(f"Erro ao atualizar chat no DB: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    texto_boas_vindas = (
        "𝗧𝗢𝗗𝗢𝗦 𝗢𝗦 𝗖𝗢𝗡𝗧𝗘𝗨𝗗𝗢𝗦 𝗩𝗔𝗭𝗔𝗗0𝗦🤫 𝗗𝗢 𝗠𝗢𝗠𝗘𝗡𝗧𝗢🥵\n\n"
        "Tenha acesso completo a todo o nosso conteudo atualizado em um so lugar:\n\n"
        "Mais de 20mil midias disponiveis (videos e fotos)\n"
        "𝗘𝘀𝗰𝗼𝗹𝗵𝗮 𝘀𝗲𝘂 𝗽𝗹𝗮𝗻𝗼 𝗲 𝗲𝗻𝘁𝗿𝗲 𝗻𝗼 𝘃𝗶𝗽:\n\n"
        "suporte: @Lyhhxv"
    )
    keyboard = [
        [InlineKeyboardButton("1 𝗛𝗢𝗥𝗔 -> R$ 1,00🔥", callback_data="comprar_1.00")],
        [InlineKeyboardButton("ACESSO POR 1 DIA -> R$ 5,00", callback_data="comprar_5.00")],
        [InlineKeyboardButton("ACESSO POR 1 SEMANA -> R$ 10,00", callback_data="comprar_10.00")],
        [InlineKeyboardButton("ACESSO POR 1 MES -> R$ 30,00", callback_data="comprar_30.00")],
        [InlineKeyboardButton("💎PERMANENTE PERMANENTE -> R$ 55,00", callback_data="comprar_55.00")],
        [InlineKeyboardButton("𝑷𝑹𝑬𝑽𝑰𝑨𝑺 𝑮𝑹𝑨𝑻𝑰𝑺🔥", url="https://t.me/+Qmozi6YQ5dE1MDYx")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    video_escolhido = random.choice(LISTA_VIDEOS_START)
    try:
        await update.message.reply_video(
            video=video_escolhido,
            caption=texto_boas_vindas,
            reply_markup=reply_markup,
            protect_content=True
        )
    except Exception as e:
        print(f"Video nao enviado: {e}")
        await update.message.reply_text(texto_boas_vindas, reply_markup=reply_markup)


async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID:
        return
    chat = update.effective_chat
    user = update.effective_user
    resposta = (
        "INFORMACOES DE ID:\n\n"
        f"Nome do Chat: {chat.title if chat.title else 'Privado'}\n"
        f"ID deste Chat/Grupo: {chat.id}\n"
        f"Seu ID de Usuario: {user.id}"
    )
    await update.message.reply_text(resposta)

async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID:
        return
    inicio = time.time()
    msg = await update.message.reply_text("pong...")
    latencia = int((time.time() - inicio) * 1000)
    uptime = int(time.time() - TEMPO_INICIAL)
    resposta = (
        "PONG! Informacoes do Sistema:\n\n"
        f"Latencia: {latencia}ms\n"
        f"Tempo online: {uptime // 3600}h {(uptime % 3600) // 60}m {uptime % 60}s\n"
        "RAM: 512 MB"
    )
    await msg.edit_text(resposta)

async def suporte_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Central de Suporte\n\n"
        "Contate: @Lyhhxv"
    )

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

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    dados = query.data

    if dados.startswith("comprar_"):
        valor = float(dados.split("_")[1])
        try:
            await query.edit_message_caption(caption="Gerando seu PIX, aguarde...", reply_markup=None)
        except:
            try:
                await query.edit_message_text("Gerando seu PIX, aguarde...")
            except:
                pass
        user = update.effective_user
        ok, pag_id, qr = await gerar_pagamento(valor, user, context.bot)
        if ok:
            msg_completa = (
                "PIX Gerado com Sucesso!\n\n"
                f"Valor: R$ {valor:.2f}\n\n"
                f"Codigo Pix Copia e Cola:\n{qr}"
            )
            keyboard_final = [
                [InlineKeyboardButton("Copiar Codigo Pix", copy_text=dict(text=qr))],
                [InlineKeyboardButton("Verificar Pagamento", callback_data=f"check_{pag_id}")]
            ]
            await query.message.reply_text(msg_completa, reply_markup=InlineKeyboardMarkup(keyboard_final))
        else:
            await query.message.reply_text(f"Erro ao gerar o Pix:\n{qr}")

    elif dados.startswith("check_"):
        payment_id = dados.split("_")[1]
        aprovado, valor_pago = await verificar_pagamento(payment_id)
        if aprovado:
            await query.answer("Pagamento Aprovado!", show_alert=True)
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
            await query.message.reply_text(
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
            await query.answer("Pagamento ainda nao identificado!", show_alert=True)
            await query.message.reply_text(
                "Pagamento ainda nao identificado! Pague e aguarde, ou clique novamente."
            )

    elif dados == "renovar_5.00":
        query.data = "comprar_5.00"
        await button_handler(update, context)
    elif dados == "ver_outros_precos":
        keyboard = [
            [InlineKeyboardButton("1 HORA -> R$ 1,00", callback_data="comprar_1.00")],
            [InlineKeyboardButton("1 Dia -> R$ 5,00", callback_data="comprar_5.00")],
            [InlineKeyboardButton("1 Semana -> R$ 10,00", callback_data="comprar_10.00")],
            [InlineKeyboardButton("1 Mes -> R$ 30,00", callback_data="comprar_30.00")],
            [InlineKeyboardButton("Permanente -> R$ 55,00", callback_data="comprar_55.00")]
        ]
        await query.message.reply_text("Escolha outro plano:", reply_markup=InlineKeyboardMarkup(keyboard))

async def gerenciador_assinaturas(application):
    await asyncio.sleep(10)
    while True:
        try:
            agora = time.time()
            clientes = collection_clientes.find({})
            for cliente in clientes:
                user_id = cliente["user_id"]
                expira_em = cliente["expira_em"]
                tempo_restante = expira_em - agora
                if 82800 <= tempo_restante <= 86400 and not cliente.get("aviso_1dia_enviado", False):
                    try:
                        msg = "SEU PLANO VENCE AMANHA! Renove agora!"
                        keyboard = [
                            [InlineKeyboardButton("Renovar 1H R$1,00", callback_data="comprar_1.00")],
                            [InlineKeyboardButton("Renovar 1Dia R$5,00", callback_data="renovar_5.00")],
                            [InlineKeyboardButton("Outros Planos", callback_data="ver_outros_precos")]
                        ]
                        await application.bot.send_message(chat_id=user_id, text=msg, reply_markup=InlineKeyboardMarkup(keyboard))
                        collection_clientes.update_one({"user_id": user_id}, {"$set": {"aviso_1dia_enviado": True}})
                    except:
                        pass
                elif 0 < tempo_restante <= 1200 and not cliente.get("aviso_20min_enviado", False):
                    try:
                        msg = "SEU PLANO EXPIRA EM MINUTOS! Renove AGORA!"
                        keyboard = [
                            [InlineKeyboardButton("Renovar 1H R$1,00", callback_data="comprar_1.00")],
                            [InlineKeyboardButton("Renovar 1Dia R$5,00", callback_data="renovar_5.00")],
                            [InlineKeyboardButton("Outros Planos", callback_data="ver_outros_precos")]
                        ]
                        await application.bot.send_message(chat_id=user_id, text=msg, reply_markup=InlineKeyboardMarkup(keyboard))
                        collection_clientes.update_one({"user_id": user_id}, {"$set": {"aviso_20min_enviado": True}})
                    except:
                        pass
                elif tempo_restante <= 0 and CANAL_ALVO_ID != 0:
                    try:
                        await application.bot.ban_chat_member(chat_id=CANAL_ALVO_ID, user_id=user_id)
                        await application.bot.unban_chat_member(chat_id=CANAL_ALVO_ID, user_id=user_id)
                        await application.bot.send_message(
                            chat_id=user_id,
                            text="Seu plano expirou! Use /start e compre um novo."
                        )
                    except:
                        pass
                    collection_clientes.delete_one({"user_id": user_id})
        except Exception as e:
            print(f"Erro gerenciador: {e}")
        await asyncio.sleep(60)

def run_background_loop(application):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(gerenciador_assinaturas(application))

def main():
    threading.Thread(target=run_web, daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    threading.Thread(target=run_background_loop, args=(app,), daemon=True).start()
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
    print("BOT ONLINE — VALORES ATUALIZADOS!")
    app.run_polling(drop_pending_updates=False)

if __name__ == "__main__":
    asyncio.run(main())
