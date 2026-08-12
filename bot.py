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
# ✅ CONFIGURAÇÕES DO AMBIENTE
# ==============================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN")
DONO_ID = int(os.environ.get("DONO_ID", 7711945457))
CANAL_ALVO_ID = int(os.environ.get("CANAL_ALVO_ID", -1004399892914))
MONGO_URI = os.environ.get("MONGO_URI")

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
    print(f"❌ Erro ao conectar MongoDB: {e}")

FUSO_RJ = timezone(timedelta(hours=-3)) # Horário Rio de Janeiro
pagamentos_notificados = set()

# ==============================================
# ⚙️ FUNÇÕES AUXILIARES
# ==============================================
def formatar_tempo_restante(segundos):
    if segundos <= 0:
        return "Expirado"
    if segundos >= 315360000: # 10 anos = Vitalício
        return "PERMANENTE/VITALÍCIO"
    dias = int(segundos // 86400)
    horas = int((segundos % 86400) // 3600)
    minutos = int((segundos % 3600) // 60)
    partes = []
    if dias > 0: partes.append(f"{dias}d")
    if horas > 0: partes.append(f"{horas}h")
    if minutos > 0: partes.append(f"{minutos}m")
    return " ".join(partes) if partes else "Menos de 1 minuto"

def formatar_data_rj(timestamp):
    return datetime.fromtimestamp(timestamp, tz=FUSO_RJ).strftime("%d/%m/%Y às %H:%M")

# ==============================================
# 📋 COMANDOS
# ==============================================
async def pegarid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID:
        return
    video = None
    if update.message.reply_to_message and update.message.reply_to_message.video:
        video = update.message.reply_to_message.video
    elif update.message.video:
        video = update.message.video
    if video:
        await update.message.reply_text(
            f"✅ FILE_ID DO VÍDEO:\n\n{video.file_id}\n\nDuração: {video.duration} segundos\n\nColoque na lista LISTA_VIDEOS_START!"
        )
    else:
        await update.message.reply_text("⚠️ Responda a um vídeo ou envie um vídeo com /pegarid")

async def clientes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID:
        return
    agora = time.time()
    clientes = list(collection_clientes.find({}))
    if not clientes:
        return await update.message.reply_text("📭 Nenhum cliente cadastrado!")
    texto = f"📋 LISTA DE CLIENTES ATIVOS ({len(clientes)}):\n\n"
    for i, cli in enumerate(clientes, 1):
        username = cli.get('username', 'Não informado')
        if username == "@None": username = "Não informado"
        texto += (
            f"🔹 {i}. {cli.get('nome', 'Desconhecido')}\n"
            f"🆔 ID: {cli.get('user_id', '?')}\n"
            f"👤 @: {username}\n"
            f"💰 Valor Pago: R$ {cli.get('valor_pago', 'Não registrado')}\n"
            f"📅 Pagamento: {formatar_data_rj(cli.get('data_compra', 0)) if cli.get('data_compra') else 'Não registrada'}\n"
            f"⏳ Expira em: {formatar_tempo_restante(cli.get('expira_em', 0) - agora)}\n\n"
        )
    await update.message.reply_text(texto)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
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
    try:
        await update.message.reply_video(
            video=random.choice(LISTA_VIDEOS_START),
            caption=texto,
            reply_markup=InlineKeyboardMarkup(botoes),
            protect_content=True
        )
    except Exception as e:
        print(f"Erro ao enviar vídeo: {e}")
        await update.message.reply_text(texto, reply_markup=InlineKeyboardMarkup(botoes))

async def suporte_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 Suporte:\nContate diretamente: @Lyhhxv")

async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID:
        return
    await update.message.reply_text(f"📌 ID do Chat: {update.effective_chat.id}\n👤 Seu ID: {update.effective_user.id}")

async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DONO_ID:
        return
    inicio = time.time()
    msg = await update.message.reply_text("🏓 Calculando...")
    latencia = int((time.time() - inicio)*1000)
    await msg.edit_text(f"🏓 PONG!\n⏱️ Latência: {latencia}ms\n✅ Funcionando perfeitamente!")

# ==============================================
# 🔒 ANTI-FLOOD / BLOQUEIO DE COMANDOS EXTRAS
# ==============================================
async def interceptador_universal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usuario = update.effective_user
    if not usuario or usuario.id == DONO_ID:
        return
    if update.message and update.message.text and update.message.text.startswith('/'):
        cmd = update.message.text.split()[0].split('@')[0].lower()
        if cmd not in ['/start', '/suporte', '/suport']:
            raise ApplicationHandlerStop

async def verificar_saida_canal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.my_chat_member.chat.id == CANAL_ALVO_ID:
        if update.my_chat_member.new_chat_member.status in ["left", "kicked"]:
            collection_clientes.delete_one({"user_id": update.my_chat_member.from_user.id})

# ==============================================
# 💳 PAGAMENTOS MERCADO PAGO
# ==============================================
async def gerar_pagamento(valor):
    url = "https://api.mercadopago.com/v1/payments"
    headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "transaction_amount": valor,
        "description": f"Acesso VIP - R${valor:.2f}",
        "payment_method_id": "pix",
        "payer": {"email": "cliente@botvip.com"}
    }
    try:
        resposta = requests.post(url, json=payload, headers=headers, timeout=15)
        if resposta.status_code == 201:
            dados = resposta.json()
            return True, dados["id"], dados["point_of_interaction"]["transaction_data"]["qr_code"]
        return False, None, f"Erro {resposta.status_code}"
    except Exception as e:
        return False, None, str(e)

async def verificar_pagamento(pagamento_id):
    try:
        url = f"https://api.mercadopago.com/v1/payments/{pagamento_id}"
        resposta = requests.get(url, headers={"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}, timeout=10)
        if resposta.status_code == 200:
            dados = resposta.json()
            return dados.get("status") == "approved", dados.get("transaction_amount", 0)
        return False, 0
    except Exception:
        return False, 0

async def botoes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    dados = query.data

    if dados.startswith("comprar_"):
        valor = float(dados.split("_")[1])
        await query.edit_message_caption("🔄 Gerando seu código PIX... aguarde!", reply_markup=None)
        ok, pid, pix = await gerar_pagamento(valor)
        if ok:
            await query.message.reply_text(
                f"✅ PIX GERADO COM SUCESSO!\n💸 Valor: R${valor:.2f}\n\n📋 Copie e cole no app do banco:\n{pix}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Verificar Pagamento", callback_data=f"check_{pid}")]])
            )
        else:
            await query.message.reply_text(f"❌ Erro ao gerar PIX: {pix}")

    elif dados.startswith("check_"):
        ok, valor_pago = await verificar_pagamento(dados.split("_")[1])
        if ok:
            await query.answer("✅ PAGAMENTO APROVADO! 🎉", show_alert=True)
            # Define duração do plano com valores atualizados
            if abs(valor_pago - 1.00) < 0.01:
                segundos = 3600; nome_plano = "1 Hora"
            elif abs(valor_pago - 5.00) < 0.01:
                segundos = 86400; nome_plano = "1 Dia"
            elif abs(valor_pago - 10.00) < 0.01:
                segundos = 86400 * 7; nome_plano = "1 Semana"
            elif abs(valor_pago - 30.00) < 0.01:
                segundos = 86400 * 30; nome_plano = "1 Mês"
            elif abs(valor_pago - 55.00) < 0.01:
                segundos = 86400 * 365 * 10; nome_plano = "PERMANENTE/VITALÍCIO"
            else:
                segundos = int(valor_pago * 86400); nome_plano = f"R${valor_pago:.2f}"

            # Salva no banco de dados
            usuario_id = update.effective_user.id
            data_expira = time.time() + segundos
            collection_clientes.update_one(
                {"user_id": usuario_id},
                {"$set": {
                    "nome": update.effective_user.first_name,
                    "username": f"@{update.effective_user.username}" if update.effective_user.username else "Não informado",
                    "valor_pago": f"{valor_pago:.2f}",
                    "expira_em": data_expira,
                    "data_compra": time.time(),
                    "aviso1": False,
                    "aviso2": False
                }},
                upsert=True
            )

            # Envia link de convite para o usuário
            try:
                link_convite = await context.bot.create_chat_invite_link(CANAL_ALVO_ID, expire_date=int(time.time())+86400, member_limit=1)
                await query.message.reply_text(
                    f"🎉 ACESSO LIBERADO!\n📦 Plano: {nome_plano}\n\n🔗 Link do Grupo: {link_convite.invite_link}\n\nAproveite muito o conteúdo 🩷🤭"
                )
            except Exception:
                await query.message.reply_text("🎉 APROVADO! Contate o suporte para receber o link do grupo 🩷")

            # AVISO DE NOVA ASSINATURA — APENAS PARA VOCÊ (DONO)
            if dados.split("_")[1] not in pagamentos_notificados:
                pagamentos_notificados.add(dados.split("_")[1])
                await context.bot.send_message(
                    chat_id=DONO_ID,
                    text=(
                        "✅ NOVA ASSINATURA CONFIRMADA!\n"
                        f"Cliente: {update.effective_user.first_name}\n"
                        f"ID: {usuario_id}\n"
                        f"Valor Pago: R${valor_pago:.2f}\n"
                        f"Plano: {nome_plano}\n"
                        f"Pago em: {formatar_data_rj(time.time())}\n"
                        f"Expira em: {'PERMANENTE/VITALÍCIO' if nome_plano=='PERMANENTE/VITALÍCIO' else formatar_data_rj(data_expira)}"
                    )
                )
        else:
            await query.answer("⏳ Aguardando confirmação do pagamento...", show_alert=True)

# ==============================================
# ⏰ GERENCIADOR DE EXPIRAÇÕES DE PLANOS
# ==============================================
async def gerenciador_assinaturas(app):
    await asyncio.sleep(10)
    while True:
        agora = time.time()
        for cliente in collection_clientes.find({}):
            restante = cliente.get("expira_em", 0) - agora
            uid = cliente["user_id"]
            # Aviso 1 dia antes
            if 82800 <= restante <= 86400 and not cliente.get("aviso1"):
                try:
                    await app.bot.send_message(uid, "⚠️ SEU PLANO VENCE AMANHÃ! Garanta renovar agora para não perder o acesso!")
                    collection_clientes.update_one({"user_id":uid}, {"$set":{"aviso1":True}})
                except Exception: pass
            # Aviso 20 minutos antes
            elif 0 < restante <= 1200 and not cliente.get("aviso2"):
                try:
                    await app.bot.send_message(uid, "🚨 ALERTA: SEU PLANO EXPIRA EM POUCOS MINUTOS! Renove AGORA!")
                    collection_clientes.update_one({"user_id":uid}, {"$set":{"aviso2":True}})
                except Exception: pass
            # Expirou → remover do grupo e do banco
            elif restante <= 0:
                try:
                    await app.bot.kick_chat_member(CANAL_ALVO_ID, uid)
                    await app.bot.unban_chat_member(CANAL_ALVO_ID, uid)
                except Exception: pass
                collection_clientes.delete_one({"user_id":uid})
        await asyncio.sleep(60)

# ✅ FUNÇÃO DE INICIALIZAÇÃO SEGURA
async def inicializar_tarefas(app):
    asyncio.create_task(gerenciador_assinaturas(app))

# ==============================================
# 🚀 INICIO FINAL SEM ERROS
# ==============================================
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Registra todos os handlers na ordem correta
    app.add_handler(TypeHandler(Update, interceptador_universal), group=-1)
    app.add_handler(ChatMemberHandler(verificar_saida_canal, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("suporte", suporte_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("ping", ping_cmd))
    app.add_handler(CommandHandler("pegarid", pegarid_cmd))
    app.add_handler(CommandHandler("clientes", clientes_cmd))
    app.add_handler(CallbackQueryHandler(botoes_callback))

    app.post_init = inicializar_tarefas

    print("✅ BOT ONLINE SEM ERROS DE LOOP! 🚀")
    # Estável para Render
    app.run_polling(
        drop_pending_updates=True,
        read_timeout=30,
        write_timeout=30,
        connect_timeout=30,
        pool_timeout=30
    )
