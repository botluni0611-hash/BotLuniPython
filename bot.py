import os
import time
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

# Cargar variables del .env
load_dotenv()

COC_TOKEN = os.getenv("COC_TOKEN")
TAG_CLAN = os.getenv("TAG_CLAN", "2R2PJUJ9C").replace("#", "")
ID_INSTANCE = os.getenv("ID_INSTANCE")
API_TOKEN = os.getenv("API_TOKEN")
GREEN_API_URL = os.getenv("GREEN_API_URL", "https://7107.api.greenapi.com/waInstance")
CHAT_ID_GRUPO = os.getenv("CHAT_ID_GRUPO", "") # Se usa para los mensajes autónomos

HEADERS = {
    "Authorization": f"Bearer {COC_TOKEN}",
    "Accept": "application/json"
}

# ==========================================
# 🧠 MEMORIA DEL VIGILANTE
# ==========================================
ESTADO_GUERRA_ANTERIOR = "desconocido"
ATAQUES_REGISTRADOS = {}
RECORDATORIO_ENVIADO = False
PERFECTA_ANUNCIADA = False
ULTIMA_REVISION = 0
INTERVALO_REVISION = 5 * 60  # Revisa cada 5 minutos

# ==========================================
# 🛠️ FUNCIONES DE SUPERCELL
# ==========================================

def consultar_api_coc(endpoint):
    url = f"https://api.clashofclans.com/v1/{endpoint}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        return res
    except:
        return None

def obtener_datos_guerra():
    clan_tag_hash = f"#{TAG_CLAN}"
    
    # 1. Buscar en Guerra Normal
    res_normal = consultar_api_coc(f"clans/%23{TAG_CLAN}/currentwar")
    if res_normal and res_normal.status_code == 200:
        datos = res_normal.json()
        if datos.get("state") != "notInWar":
            return normalizar_guerra(datos, clan_tag_hash)

    # 2. Buscar en Liga de Guerra (CWL)
    res_liga = consultar_api_coc(f"clans/%23{TAG_CLAN}/currentwar/leaguegroup")
    if res_liga and res_liga.status_code == 200:
        datos_liga = res_liga.json()
        guerra_preparacion, guerra_terminada = None, None

        for ronda in datos_liga.get("rounds", []):
            for war_tag in ronda.get("warTags", []):
                if war_tag == "#0": continue
                res_war = consultar_api_coc(f"clanwarleagues/wars/%23{war_tag.replace('#', '')}")
                if res_war and res_war.status_code == 200:
                    guerra = res_war.json()
                    c_tag, o_tag = guerra.get("clan", {}).get("tag"), guerra.get("opponent", {}).get("tag")

                    if c_tag == clan_tag_hash or o_tag == clan_tag_hash:
                        guerra = normalizar_guerra(guerra, clan_tag_hash)
                        estado = guerra.get("state")
                        if estado == "inWar": return guerra
                        elif estado == "preparation" and not guerra_preparacion: guerra_preparacion = guerra
                        elif estado == "warEnded": guerra_terminada = guerra

        if guerra_preparacion: return guerra_preparacion
        if guerra_terminada: return guerra_terminada

    return {"state": "notInWar"}

def normalizar_guerra(guerra, mi_clan_tag):
    if guerra.get("opponent", {}).get("tag") == mi_clan_tag:
        guerra["clan"], guerra["opponent"] = guerra["opponent"], guerra["clan"]
    return guerra

def calcular_tiempo(fecha_coc):
    try:
        fecha_obj = datetime.strptime(fecha_coc, "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=timezone.utc)
        restante = fecha_obj - datetime.now(timezone.utc)
        if restante.total_seconds() < 0: return "0h 0m"
        horas, resto = divmod(restante.total_seconds(), 3600)
        return f"{int(horas)}h {int(resto // 60)}m"
    except: return "Desconocido"

# ==========================================
# 📊 FUNCIONES DE FORMATO ESTELAR Y REPORTES
# ==========================================

def generar_analisis_th(mi_clan, rival):
    ths_luni = {}
    ths_rival = {}

    for m in mi_clan.get("members", []):
        th = m.get("townhallLevel", 0)
        ths_luni[th] = ths_luni.get(th, 0) + 1

    for m in rival.get("members", []):
        th = m.get("townhallLevel", 0)
        ths_rival[th] = ths_rival.get(th, 0) + 1

    todos_ths = sorted(list(set(list(ths_luni.keys()) + list(ths_rival.keys()))), reverse=True)

    lineas = []
    for th in todos_ths:
        c_luni = ths_luni.get(th, 0)
        c_rival = ths_rival.get(th, 0)
        emoji = "🌕" if c_luni >= c_rival else "🌑"
        lineas.append(f"TH{th}: {c_luni} vs {c_rival} {emoji}")

    return "\n".join(lineas)

def generar_resultados_finales(mi_clan, rival, guerra):
    e_luni = mi_clan.get('stars', 0)
    e_rival = rival.get('stars', 0)
    d_luni = mi_clan.get('destructionPercentage', 0)
    d_rival = rival.get('destructionPercentage', 0)
    
    ganador = "Empate 🤝"
    if e_luni > e_rival or (e_luni == e_rival and d_luni > d_rival): 
        ganador = "🎉 Luni"
    elif e_rival > e_luni or (e_rival == e_luni and d_rival > d_luni): 
        ganador = f"💀 {rival.get('name')}"

    dif_estrellas = abs(e_luni - e_rival)

    msg = f"🏁 *¡LA GUERRA HA TERMINADO!* 🏁\n\n"
    msg += f"📊 RESULTADOS DE GUERRA 📊\n"
    msg += f"{mi_clan.get('name')} vs {rival.get('name')}\n\n"
    msg += f"🏆 GANADOR: {ganador}\n"
    msg += f"⭐ Diferencia: {dif_estrellas} estrellas\n\n"
    msg += "⚔️ DETALLE DE ATAQUES:\n\n"

    ataques_permitidos = guerra.get("attacksPerMember", 2)
    membros = sorted(mi_clan.get("members", []), key=lambda x: x.get("mapPosition", 999))
    rival_map = {r.get("tag"): r.get("mapPosition") for r in rival.get("members", [])}

    for m in membros:
        msg += f"#{m.get('mapPosition')} {m.get('name')}:\n"
        ataques_hechos = m.get("attacks", [])
        
        for i in range(ataques_permitidos):
            if i < len(ataques_hechos):
                atk = ataques_hechos[i]
                def_pos = rival_map.get(atk.get("defenderTag"), "?")
                msg += f" ↳ Atacó al #{def_pos}: {atk.get('stars', 0)}⭐\n"
            else:
                msg += f" ↳ No utilizó este ataque\n"
        msg += "\n"

    return msg.strip()

def generar_mensaje_pendientes(guerra, es_automatico=True):
    mi_clan = guerra.get("clan", {})
    rival = guerra.get("opponent", {})
    
    titulo = "⏰ *¡ATENCIÓN! ÚLTIMAS 5 HORAS DE GUERRA* ⏰" if es_automatico else "📋 *REPORTE DE ATAQUES PENDIENTES* 📋"
    estrellas_luni = mi_clan.get("stars", 0)
    estrellas_rival = rival.get("stars", 0)
    tiempo = calcular_tiempo(guerra.get("endTime"))
    ataques_permitidos = guerra.get("attacksPerMember", 2)
    tipo_guerra = "Liga de Guerras de Clanes" if ataques_permitidos == 1 else "Guerra de Clanes"
    
    msg = f"{titulo}\n\n"
    msg += f"🏆 Ataques pendientes\n"
    msg += f"🏟️ {tipo_guerra}\n\n"
    msg += f"⭐ Equipo: {estrellas_luni} | Rival: {estrellas_rival}\n"
    msg += f"⏰ Tiempo: {tiempo}\n\n"
    msg += "⚔️ Pendientes\n\n"
    
    membros = sorted(mi_clan.get("members", []), key=lambda x: x.get("mapPosition", 999))
    todos_atacaron = True
    
    for m in membros:
        faltan = ataques_permitidos - len(m.get("attacks", []))
        if faltan > 0:
            todos_atacaron = False
            # Asignamos las lunas visuales
            emoji = "🌕" if faltan == 2 else "🌗"
            if ataques_permitidos == 1: emoji = "🌕" # Para liga 1 ataque vale luna llena
            
            msg += f"#{m.get('mapPosition')} {m.get('name')} | {faltan}{emoji}\n"
            
    if todos_atacaron:
        msg += "¡Todo el clan ha hecho sus ataques! 🎉\n"
        
    return msg.strip()

# ==========================================
# 📱 FUNCIONES DE WHATSAPP
# ==========================================

def enviar_whatsapp(chat_id, mensaje):
    url = f"{GREEN_API_URL}{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    requests.post(url, json={"chatId": chat_id, "message": mensaje})

def borrar_notificacion(receipt_id):
    requests.delete(f"{GREEN_API_URL}{ID_INSTANCE}/deleteNotification/{API_TOKEN}/{receipt_id}")

def enviar_autonomo(mensaje):
    if CHAT_ID_GRUPO:
        enviar_whatsapp(CHAT_ID_GRUPO, mensaje)
    else:
        print("⚠️ No hay CHAT_ID_GRUPO configurado.")

# ==========================================
# 🤖 EL VIGILANTE (MENSAJES AUTÓNOMOS)
# ==========================================

def verificar_cambios_guerra():
    global ESTADO_GUERRA_ANTERIOR, ATAQUES_REGISTRADOS, RECORDATORIO_ENVIADO, PERFECTA_ANUNCIADA
    
    guerra = obtener_datos_guerra()
    estado_actual = guerra.get("state")
    if not estado_actual: return

    mi_clan = guerra.get("clan", {})
    rival = guerra.get("opponent", {})

    if ESTADO_GUERRA_ANTERIOR == "desconocido":
        ESTADO_GUERRA_ANTERIOR = estado_actual
        if estado_actual == "inWar":
            for m in mi_clan.get("members", []):
                ATAQUES_REGISTRADOS[m.get("tag")] = len(m.get("attacks", []))
        return

    if ESTADO_GUERRA_ANTERIOR != "preparation" and estado_actual == "preparation":
        enviar_autonomo(f"🔎 *¡NUEVA GUERRA ENCONTRADA!*\nLuni ha entrado en fase de preparación contra {rival.get('name')}.")
        ATAQUES_REGISTRADOS.clear()
        RECORDATORIO_ENVIADO, PERFECTA_ANUNCIADA = False

    elif ESTADO_GUERRA_ANTERIOR != "inWar" and estado_actual == "inWar":
        tiempo_restante = calcular_tiempo(guerra.get("endTime"))
        analisis_th = generar_analisis_th(mi_clan, rival)
        
        msg_inicio = (
            f"🔥 *¡LA GUERRA HA COMENZADO!* 🔥\n\n"
            f"🌙 ¡La noche de guerra ha comenzado!\n\n"
            f"🌕 {mi_clan.get('name')}\n"
            f"🌑 vs {rival.get('name')}\n\n"
            f"⏱️ La guerra termina en: {tiempo_restante}\n"
            f"────────────────\n"
            f"✨ Análisis Estelar (Balance por TH)\n\n"
            f"{analisis_th}\n\n"
            f"🌙 ¡Que la Luna guíe sus ataques!"
        )
        enviar_autonomo(msg_inicio)
        
        ATAQUES_REGISTRADOS.clear()
        RECORDATORIO_ENVIADO, PERFECTA_ANUNCIADA = False, False
        for m in mi_clan.get("members", []):
            ATAQUES_REGISTRADOS[m.get("tag")] = len(m.get("attacks", []))

    elif ESTADO_GUERRA_ANTERIOR == "inWar" and estado_actual in ["warEnded", "notInWar"]:
        msg_fin = generar_resultados_finales(mi_clan, rival, guerra)
        enviar_autonomo(msg_fin)
        ATAQUES_REGISTRADOS.clear()

    ESTADO_GUERRA_ANTERIOR = estado_actual

    if estado_actual == "inWar":
        for m in mi_clan.get("members", []):
            tag = m.get("tag")
            ataques = m.get("attacks", [])
            act_len = len(ataques)
            ant_len = ATAQUES_REGISTRADOS.get(tag, -1)

            if ant_len != -1 and act_len > ant_len:
                ultimo = ataques[-1]
                defensor = next((r for r in rival.get("members", []) if r.get("tag") == ultimo.get("defenderTag")), {})
                mins, segs = divmod(ultimo.get("duration", 0), 60)
                
                msg_atk = (f"⚔️ *¡NUEVO ATAQUE DE LUNI!*\n\n"
                           f"🗡️ Atacante: #{m.get('mapPosition')} {m.get('name')}\n"
                           f"🛡️ Defensor: #{defensor.get('mapPosition', '?')} {defensor.get('name', 'Desconocido')}\n\n"
                           f"⭐ Estrellas: {ultimo.get('stars', 0)}\n"
                           f"💥 Destrucción: {ultimo.get('destructionPercentage', 0)}%\n"
                           f"⏱️ Duración: {mins}m {segs}s")
                enviar_autonomo(msg_atk)
            
            ATAQUES_REGISTRADOS[tag] = act_len

        max_estrellas = guerra.get("teamSize", 0) * 3
        if mi_clan.get('stars', 0) == max_estrellas and max_estrellas > 0 and not PERFECTA_ANUNCIADA:
            enviar_autonomo("🌟 *¡GUERRA PERFECTA ALCANZADA!* 🌟\nEl clan logró todas las estrellas posibles.")
            PERFECTA_ANUNCIADA = True

        if guerra.get("endTime") and not RECORDATORIO_ENVIADO:
            try:
                f_obj = datetime.strptime(guerra["endTime"], "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=timezone.utc)
                restante = (f_obj - datetime.now(timezone.utc)).total_seconds()
                
                # Se envía el mensaje automático de 5 horas SOLO si no es guerra perfecta
                if 0 < restante <= 18000:
                    if mi_clan.get('stars', 0) < max_estrellas:
                        enviar_autonomo(generar_mensaje_pendientes(guerra, es_automatico=True))
                    RECORDATORIO_ENVIADO = True
            except: pass

# ==========================================
# 🎮 COMANDOS
# ==========================================

def cmd_time():
    guerra = obtener_datos_guerra()
    if guerra.get("state") == "notInWar": return "🌙 Luni no está en guerra."
    if guerra.get("state") == "warEnded": return "🌙 La guerra terminó."

    mi_clan, rival = guerra.get("clan", {}), guerra.get("opponent", {})
    fase = "⏳ La guerra *COMIENZA* en:" if guerra.get("state") == "preparation" else "⏰ La guerra *TERMINA* en:"
    tiempo = calcular_tiempo(guerra.get("startTime" if guerra.get("state") == "preparation" else "endTime"))

    return f"⏳ *REPORTE DE TIEMPO* ⏳\n\n⚔️ *{mi_clan.get('name')}* vs *{rival.get('name')}*\n\n{fase} {tiempo}"

def cmd_guerra():
    guerra = obtener_datos_guerra()
    estado = guerra.get("state")
    
    if estado == "notInWar": return "🌙 No hay guerra activa."
    
    mi_clan, rival = guerra.get("clan", {}), guerra.get("opponent", {})
    
    if estado == "preparation":
        tiempo = calcular_tiempo(guerra.get("startTime"))
        return f"⏳ *FASE DE PREPARACIÓN* ⏳\n\n⚔️ *{mi_clan.get('name')}* vs *{rival.get('name')}*\n\n⏳ La batalla *COMIENZA* en: *{tiempo}*\n\n¡Preparen sus aldeas!"
    
    msg = f"🔥 *ESTADO DE LA GUERRA* 🔥\n\n🏰 *{mi_clan.get('name')}*: {mi_clan.get('stars', 0)} ⭐ ({mi_clan.get('destructionPercentage', 0):.2f}%)\n🆚\n🏰 *{rival.get('name')}*: {rival.get('stars', 0)} ⭐ ({rival.get('destructionPercentage', 0):.2f}%)\n\n⚔️ Usa !resultados para ver los detalles."
    return msg

def cmd_resultados():
    guerra = obtener_datos_guerra()
    estado = guerra.get("state")
    if estado == "notInWar": return "🌙 No hay guerra activa."
    if estado == "preparation": return "🌙 La guerra está en fase de *Preparación*. Aún no hay ataques."
    return generar_resultados_finales(guerra.get("clan", {}), guerra.get("opponent", {}), guerra)

def cmd_ataques():
    guerra = obtener_datos_guerra()
    estado = guerra.get("state")
    if estado == "notInWar": return "🌙 No hay guerra activa."
    if estado == "preparation": return "🌙 La guerra está en fase de *Preparación*. Todos los ataques están pendientes."
    
    # Genera el reporte de pendientes forzando el formato de respuesta manual
    return generar_mensaje_pendientes(guerra, es_automatico=False)

# ==========================================
# 🚀 BUCLE PRINCIPAL
# ==========================================

def procesar_mensajes():
    global ULTIMA_REVISION
    print("🤖 Bot Luni (Python) operando limpio y en local/nube...")
    while True:
        ahora = time.time()
        if ahora - ULTIMA_REVISION > INTERVALO_REVISION:
            verificar_cambios_guerra()
            ULTIMA_REVISION = ahora

        url = f"{GREEN_API_URL}{ID_INSTANCE}/receiveNotification/{API_TOKEN}"
        try:
            res = requests.get(url, timeout=20)
            if res.status_code == 200 and res.json():
                datos = res.json()
                receipt_id = datos.get("receiptId")
                body = datos.get("body", {})

                if body.get("typeWebhook") in ["incomingMessageReceived", "outgoingMessageReceived"]:
                    chat_id = body.get("senderData", {}).get("chatId")
                    msg_data = body.get("messageData", {})
                    tipo_msg = msg_data.get("typeMessage", "")
                    
                    texto = ""
                    if tipo_msg == "textMessage": texto = msg_data.get("textMessageData", {}).get("textMessage", "")
                    elif tipo_msg == "extendedTextMessage": texto = msg_data.get("extendedTextMessageData", {}).get("text", "")

                    comando = texto.strip().lower()
                    if comando:
                        print(f"➤ Comando leído: {comando}")
                        if comando in ["!time", "!tiempo"]: enviar_whatsapp(chat_id, cmd_time())
                        elif comando == "!guerra": enviar_whatsapp(chat_id, cmd_guerra())
                        elif comando == "!resultados": enviar_whatsapp(chat_id, cmd_resultados())
                        elif comando == "!ataques": enviar_whatsapp(chat_id, cmd_ataques())
                        elif comando == "!ip": enviar_whatsapp(chat_id, f"🌐 Mi IP local es: {requests.get('https://api.ipify.org').text}")

                borrar_notificacion(receipt_id)

        except requests.exceptions.RequestException: pass 
        except Exception as e: print(f"⚠️ Error general: {e}")
        
        time.sleep(3) 

if __name__ == "__main__":
    procesar_mensajes()