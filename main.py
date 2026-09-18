import requests
import time
import os
from datetime import datetime
import pytz
import json
import statistics
from collections import defaultdict

API_KEY   = os.getenv("API_FOOTBALL_KEY")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

BASE_URL = "https://v3.football.api-sports.io"
HEADERS  = {"x-apisports-key": API_KEY}

LIGAS = [71, 72, 39, 140, 135, 78, 61, 40]
SEASON = 2026

BET365_ID    = 8
OUTRAS_CASAS = [4, 32, 11, 7]

ARQUIVO_ENVIADOS = "jogos_enviados.json"
ARQUIVO_CACHE    = "cache_stats.json"
ARQUIVO_REQ      = "req_count.json"
ARQUIVO_BINGO    = "bingo_do_dia.json"
ARQUIVO_PLACAR   = "placar_do_dia.json"
ARQUIVO_ODD_ERR  = "odd_errada_hoje.json"

LIMITE_DIARIO = 7000
ALERTA_LIMITE = 6000

MANDANTE_MIN_FIN   = 12
MANDANTE_MIN_ESC   = 4
TAXA_MIN_ACERTO    = 0.70
MIN_JOGOS          = 5
PERNAS_MIN         = 2
PERNAS_MAX         = 4
ODD_MIN_FINAL      = 1.50
ODD_BINGO_DIA      = 5.00
ODD_ERRADA_MIN     = 1.30
ODD_ERRADA_MIN_ODD = 1.50
ODD_VALOR_MIN      = 1.30

INTERVALO_MIN = 30
BINGO_MIN_JOGOS = 3
PLACAR_MIN_JOGOS = 3
PLACAR_MAX_JOGOS = 4
ESPERA_ENTRE_MSGS = 10

# ─────────────────────────────────────────────
# CONTROLE DE REQUISIÇÕES
# ─────────────────────────────────────────────

def _hoje_str():
    return datetime.now(pytz.timezone("America/Sao_Paulo")).strftime("%Y-%m-%d")

def carregar_req():
    if os.path.exists(ARQUIVO_REQ):
        try:
            with open(ARQUIVO_REQ) as f:
                d = json.load(f)
            if d.get("data") == _hoje_str():
                return d.get("count", 0)
        except:
            pass
    return 0

def salvar_req(count):
    with open(ARQUIVO_REQ, "w") as f:
        json.dump({"data": _hoje_str(), "count": count}, f)

REQ_COUNT = carregar_req()

def pode_buscar():
    return REQ_COUNT < LIMITE_DIARIO

def atingiu_alerta():
    return REQ_COUNT >= ALERTA_LIMITE

def api_get(endpoint, params=None):
    global REQ_COUNT
    if not pode_buscar():
        print(f"[!] Limite diário atingido ({REQ_COUNT}/{LIMITE_DIARIO})")
        return None
    url = f"{BASE_URL}/{endpoint}"
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=20)
        REQ_COUNT += 1
        if REQ_COUNT % 50 == 0:
            salvar_req(REQ_COUNT)
        if r.status_code != 200:
            return None
        return r.json().get("response", [])
    except Exception as e:
        print(f"Erro API {endpoint}: {e}")
        return None

# ─────────────────────────────────────────────
# CACHE
# ─────────────────────────────────────────────

def carregar_cache():
    if os.path.exists(ARQUIVO_CACHE):
        try:
            with open(ARQUIVO_CACHE) as f:
                return json.load(f)
        except:
            return {}
    return {}

def salvar_cache(cache):
    with open(ARQUIVO_CACHE, "w") as f:
        json.dump(cache, f)

CACHE = carregar_cache()

def get_stats_fixture(fixture_id):
    fid = str(fixture_id)
    if fid in CACHE:
        return CACHE[fid]
    resp = api_get("fixtures/statistics", {"fixture": fixture_id})
    if resp is None:
        return []
    CACHE[fid] = resp
    salvar_cache(CACHE)
    return resp

def get_odds_fixture(fixture_id):
    resp = api_get("odds", {"fixture": fixture_id})
    return resp if resp else []

# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────

def enviar_mensagem(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, data=payload, timeout=15)
    except Exception as e:
        print(f"Erro Telegram: {e}")

# ─────────────────────────────────────────────
# ARQUIVOS DE CONTROLE
# ─────────────────────────────────────────────

def carregar_enviados():
    if os.path.exists(ARQUIVO_ENVIADOS):
        try:
            with open(ARQUIVO_ENVIADOS) as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def salvar_enviados(enviados):
    with open(ARQUIVO_ENVIADOS, "w") as f:
        json.dump(list(enviados), f)

def _ja_enviado_hoje(arquivo):
    if os.path.exists(arquivo):
        try:
            with open(arquivo) as f:
                d = json.load(f)
            return d.get("data") == _hoje_str()
        except:
            return False
    return False

def _marcar_enviado_hoje(arquivo):
    with open(arquivo, "w") as f:
        json.dump({"data": _hoje_str()}, f)

def bingo_ja_enviado_hoje():
    return _ja_enviado_hoje(ARQUIVO_BINGO)

def marcar_bingo_enviado():
    _marcar_enviado_hoje(ARQUIVO_BINGO)

def placar_ja_enviado_hoje():
    return _ja_enviado_hoje(ARQUIVO_PLACAR)

def marcar_placar_enviado():
    _marcar_enviado_hoje(ARQUIVO_PLACAR)

def carregar_odd_errada_hoje():
    if os.path.exists(ARQUIVO_ODD_ERR):
        try:
            with open(ARQUIVO_ODD_ERR) as f:
                d = json.load(f)
            if d.get("data") == _hoje_str():
                return set(d.get("ids", []))
        except:
            pass
    return set()

def salvar_odd_errada_hoje(ids):
    with open(ARQUIVO_ODD_ERR, "w") as f:
        json.dump({"data": _hoje_str(), "ids": list(ids)}, f)

# ─────────────────────────────────────────────
# BUSCAS
# ─────────────────────────────────────────────

def get_jogos_do_dia():
    hoje = datetime.now(pytz.timezone("America/Sao_Paulo")).strftime("%Y-%m-%d")
    jogos = []
    for liga in LIGAS:
        resp = api_get("fixtures", {"date": hoje, "league": liga, "season": SEASON})
        if resp:
            jogos.extend(resp)
        time.sleep(0.2)
    return jogos

def get_jogos_time(team_id, liga_id, casa=True):
    resp = api_get("fixtures", {"team": team_id, "league": liga_id, "season": SEASON})
    if not resp:
        return []
    filtrados = []
    for j in resp:
        status = j["fixture"]["status"]["short"]
        if status not in ["FT", "AET", "PEN"]:
            continue
        if casa and j["teams"]["home"]["id"] != team_id:
            continue
        if not casa and j["teams"]["away"]["id"] != team_id:
            continue
        filtrados.append(j)
    return filtrados

# ─────────────────────────────────────────────
# EXTRAÇÃO DE STATS
# ─────────────────────────────────────────────

def extrair_stats_jogo(stats, team_id):
    res = {"finalizacoes": 0, "chutes_gol": 0, "cartoes": 0, "escanteios": 0}
    if not stats:
        return res
    for team_stats in stats:
        if team_stats["team"]["id"] != team_id:
            continue
        for stat in team_stats["statistics"]:
            tipo = stat["type"]
            valor = stat["value"]
            if isinstance(valor, int):
                if tipo == "Total Shots":
                    res["finalizacoes"] = valor
                elif tipo == "Shots on Goal":
                    res["chutes_gol"] = valor
                elif tipo == "Yellow Cards":
                    res["cartoes"] = valor
                elif tipo == "Corner Kicks":
                    res["escanteios"] = valor
    return res

def get_gols(jogo, team_id):
    if jogo["teams"]["home"]["id"] == team_id:
        return jogo["goals"]["home"] or 0
    return jogo["goals"]["away"] or 0

def get_gols_sofridos(jogo, team_id):
    if jogo["teams"]["home"]["id"] == team_id:
        return jogo["goals"]["away"] or 0
    return jogo["goals"]["home"] or 0

# ─────────────────────────────────────────────
# ANÁLISES
# ─────────────────────────────────────────────

def analisar_mandante(jogos, team_id):
    if not jogos:
        return None
    fin, esc, cart = [], [], []
    gols_feitos, gols_sofridos = [], []
    for j in jogos:
        stats = get_stats_fixture(j["fixture"]["id"])
        s = extrair_stats_jogo(stats, team_id)
        fin.append(s["finalizacoes"])
        esc.append(s["escanteios"])
        cart.append(s["cartoes"])
        gols_feitos.append(get_gols(j, team_id))
        gols_sofridos.append(get_gols_sofridos(j, team_id))
        time.sleep(0.1)
    if not fin:
        return None
    return {
        "n_jogos": len(fin),
        "media_fin": statistics.mean(fin),
        "media_esc": statistics.mean(esc),
        "media_cart": statistics.mean(cart) if cart else 0,
        "media_gols_feitos": statistics.mean(gols_feitos),
        "media_gols_sofridos": statistics.mean(gols_sofridos),
        "lista_fin": fin,
        "lista_esc": esc,
        "lista_cart": cart,
    }

def analisar_visitante(jogos, team_id):
    if not jogos:
        return None
    fin, chutes, cart = [], [], []
    v, e, d = [], [], []
    gols_feitos, gols_sofridos = [], []
    for j in jogos:
        stats = get_stats_fixture(j["fixture"]["id"])
        s = extrair_stats_jogo(stats, team_id)
        fin.append(s["finalizacoes"])
        chutes.append(s["chutes_gol"])
        cart.append(s["cartoes"])
        gf = get_gols(j, team_id)
        gs = get_gols_sofridos(j, team_id)
        gols_feitos.append(gf)
        gols_sofridos.append(gs)
        if gf > gs:
            v.append(s["finalizacoes"])
        elif gf < gs:
            d.append(s["finalizacoes"])
        else:
            e.append(s["finalizacoes"])
        time.sleep(0.1)
    if not fin:
        return None
    media_geral = statistics.mean(fin)
    media_perdendo = statistics.mean(d) if d else 0
    reativo = media_perdendo > media_geral if d else False
    return {
        "n_jogos": len(fin),
        "media_fin": media_geral,
        "media_fin_perdendo": media_perdendo,
        "media_cart": statistics.mean(cart) if cart else 0,
        "media_gols_feitos": statistics.mean(gols_feitos),
        "media_gols_sofridos": statistics.mean(gols_sofridos),
        "reativo": reativo,
        "lista_fin": fin,
        "lista_chutes_gol": chutes,
        "lista_cartoes": cart,
    }

def taxa(lista, linha):
    if not lista:
        return 0, 0
    acertos = sum(1 for v in lista if v >= linha)
    return acertos / len(lista), acertos

# ─────────────────────────────────────────────
# ODDS
# ─────────────────────────────────────────────

def extrair_odds(odds_data):
    res = {}
    if not odds_data:
        return res
    for item in odds_data:
        for bm in item.get("bookmakers", []):
            bm_id = bm.get("id")
            if bm_id not in res:
                res[bm_id] = {}
            for bet in bm.get("bets", []):
                res[bm_id][bet["id"]] = [(v["value"], float(v["odd"])) for v in bet.get("values", [])]
    return res

def get_odd(odds, bm_id, bet_id, valor):
    if bm_id not in odds or bet_id not in odds[bm_id]:
        return None
    for v, o in odds[bm_id][bet_id]:
        if v == valor:
            return o
    return None

def media_outras(odds, bet_id, valor):
    odds_lista = []
    for bm_id in OUTRAS_CASAS:
        o = get_odd(odds, bm_id, bet_id, valor)
        if o:
            odds_lista.append(o)
    return statistics.mean(odds_lista) if odds_lista else None

def detectar_odd_errada(odds, bet_id, valor, nome):
    o365 = get_odd(odds, BET365_ID, bet_id, valor)
    if not o365 or o365 < ODD_ERRADA_MIN_ODD:
        return None
    media = media_outras(odds, bet_id, valor)
    if not media:
        return None
    if o365 / media >= ODD_ERRADA_MIN:
        return {
            "mercado": nome, "valor": valor, "bet365": o365, "media": media,
            "diff": int((o365 / media - 1) * 100)
        }
    return None

# ─────────────────────────────────────────────
# IDs DOS MERCADOS
# ─────────────────────────────────────────────

ID_GOALS      = 5
ID_BTTS       = 8
ID_EXACT      = 10
ID_CORNERS    = 45
ID_CARDS      = 80
ID_HOME_CARDS = 82
ID_AWAY_CARDS = 83
ID_HOME_CORN  = 57
ID_AWAY_CORN  = 58
ID_TOTAL_SHOT = 211
ID_TOTAL_SOG  = 87
ID_AWAY_SHOTS = 276
# ─────────────────────────────────────────────
# ENTRADA PRINCIPAL — VISITANTE REATIVO
# ─────────────────────────────────────────────

def montar_principal(mandante, visitante, odds, home_nome, away_nome):
    pernas = []

    if visitante:
        for linha in [9.5, 8.5, 7.5, 6.5]:
            t, ac = taxa(visitante["lista_fin"], linha)
            if t >= TAXA_MIN_ACERTO and visitante["n_jogos"] >= MIN_JOGOS:
                odd = get_odd(odds, BET365_ID, ID_AWAY_SHOTS, f"Over {linha}")
                pernas.append({
                    "nome": f"{away_nome} +{linha} finalizações",
                    "taxa": t, "acertos": ac, "total": visitante["n_jogos"],
                    "odd": odd, "bet_id": ID_AWAY_SHOTS, "valor": f"Over {linha}"
                })
                break

        for linha in [2.5, 1.5]:
            t, ac = taxa(visitante["lista_chutes_gol"], linha)
            if t >= TAXA_MIN_ACERTO and visitante["n_jogos"] >= MIN_JOGOS:
                pernas.append({
                    "nome": f"{away_nome} +{linha} chutes ao gol",
                    "taxa": t, "acertos": ac, "total": visitante["n_jogos"],
                    "odd": None, "bet_id": None, "valor": None
                })
                break

        for linha in [2.5, 1.5, 0.5]:
            t, ac = taxa(visitante["lista_cartoes"], linha)
            if t >= TAXA_MIN_ACERTO and visitante["n_jogos"] >= MIN_JOGOS:
                odd = get_odd(odds, BET365_ID, ID_AWAY_CARDS, f"Over {linha}")
                pernas.append({
                    "nome": f"{away_nome} +{linha} cartões",
                    "taxa": t, "acertos": ac, "total": visitante["n_jogos"],
                    "odd": odd, "bet_id": ID_AWAY_CARDS, "valor": f"Over {linha}"
                })
                break

    if mandante:
        for linha in [1.5, 0.5]:
            t, ac = taxa(mandante["lista_cart"], linha)
            if t >= TAXA_MIN_ACERTO and mandante["n_jogos"] >= MIN_JOGOS:
                odd = get_odd(odds, BET365_ID, ID_HOME_CARDS, f"Over {linha}")
                pernas.append({
                    "nome": f"{home_nome} +{linha} cartões",
                    "taxa": t, "acertos": ac, "total": mandante["n_jogos"],
                    "odd": odd, "bet_id": ID_HOME_CARDS, "valor": f"Over {linha}"
                })
                break

        for linha in [4.5, 3.5]:
            t, ac = taxa(mandante["lista_esc"], linha)
            if t >= TAXA_MIN_ACERTO and mandante["n_jogos"] >= MIN_JOGOS:
                odd = get_odd(odds, BET365_ID, ID_HOME_CORN, f"Over {linha}")
                pernas.append({
                    "nome": f"{home_nome} +{linha} escanteios",
                    "taxa": t, "acertos": ac, "total": mandante["n_jogos"],
                    "odd": odd, "bet_id": ID_HOME_CORN, "valor": f"Over {linha}"
                })
                break

    return pernas[:PERNAS_MAX]

# ─────────────────────────────────────────────
# ENTRADA NORMAL — VALOR
# ─────────────────────────────────────────────

def buscar_valor_jogo(odds):
    achados = []
    mercados = [
        (ID_GOALS, "Over 0.5", "Mais de 0,5 gols"),
        (ID_GOALS, "Over 1.5", "Mais de 1,5 gols"),
        (ID_GOALS, "Over 2.5", "Mais de 2,5 gols"),
        (ID_BTTS, "Yes", "Ambas marcam"),
        (ID_CORNERS, "Over 8.5", "Mais de 8,5 escanteios"),
        (ID_CORNERS, "Over 9.5", "Mais de 9,5 escanteios"),
        (ID_CARDS, "Over 3.5", "Mais de 3,5 cartões"),
        (ID_CARDS, "Over 4.5", "Mais de 4,5 cartões"),
        (ID_TOTAL_SHOT, "Over 25.5", "Mais de 25,5 finalizações"),
        (ID_TOTAL_SHOT, "Over 30.5", "Mais de 30,5 finalizações"),
        (ID_TOTAL_SOG, "Over 8.5", "Mais de 8,5 chutes ao gol"),
        (ID_TOTAL_SOG, "Over 9.5", "Mais de 9,5 chutes ao gol"),
    ]
    for bet_id, valor, label in mercados:
        o365 = get_odd(odds, BET365_ID, bet_id, valor)
        if not o365 or o365 < ODD_MIN_FINAL:
            continue
        media = media_outras(odds, bet_id, valor)
        if not media:
            continue
        if o365 / media >= ODD_VALOR_MIN:
            achados.append({
                "nome": label, "odd": o365, "media": media,
                "diff": int((o365 / media - 1) * 100),
                "bet_id": bet_id, "valor": valor
            })
    return achados

# ─────────────────────────────────────────────
# PLACAR MÚLTIPLO — COM CONTEXTO
# ─────────────────────────────────────────────

def escolher_placar_com_contexto(mandante, visitante, placar_odds):
    """
    Analisa o contexto e escolhe o placar mais provável.
    Retorna (placar, odd, motivo).
    """
    if not mandante or not visitante or not placar_odds:
        return None, None, None

    gols_casa = mandante.get("media_gols_feitos", 1.5)
    gols_sofridos_casa = mandante.get("media_gols_sofridos", 1.0)
    gols_fora = visitante.get("media_gols_feitos", 1.0)
    gols_sofridos_fora = visitante.get("media_gols_sofridos", 1.5)

    # Quantos gols o mandante deve fazer
    gols_mand = round((gols_casa + gols_sofridos_fora) / 2)
    gols_mand = max(0, min(4, gols_mand))

    # Quantos gols o visitante deve fazer
    gols_vis = round((gols_fora + gols_sofridos_casa) / 2)
    gols_vis = max(0, min(3, gols_vis))

    placar = f"{gols_mand}:{gols_vis}"

    # Se não tiver esse placar, tenta os próximos
    if placar not in placar_odds:
        alternativas = [
            f"{gols_mand}:{gols_vis+1}",
            f"{gols_mand+1}:{gols_vis}",
            f"{gols_mand}:{gols_vis-1}" if gols_vis > 0 else None,
            f"{gols_mand-1}:{gols_vis}" if gols_mand > 0 else None,
        ]
        placar = None
        for alt in alternativas:
            if alt and alt in placar_odds:
                placar = alt
                break

    if not placar:
        return None, None, None

    # Monta motivo
    motivo = (
        f"{mandante.get('nome', 'Mandante')} faz {gols_casa:.1f} gol/jogo em casa | "
        f"{visitante.get('nome', 'Visitante')} faz {gols_fora:.1f} gol/jogo fora"
    )

    # Checa se visitante costuma marcar fora
    if gols_fora >= 0.7 and int(placar.split(":")[1]) == 0:
        # Visitante marca, mas escolhemos placar sem gol dele → tenta ajustar
        placar_alt = f"{placar.split(':')[0]}:1"
        if placar_alt in placar_odds:
            placar = placar_alt
            motivo += " | Visitante costuma marcar fora → ajustado com gol dele"

    return placar, placar_odds[placar], motivo

def montar_placar_multipla(jogos, dados_por_jogo):
    """Agrupa jogos por horário e monta múltiplas de placar."""
    por_horario = defaultdict(list)
    for jogo in jogos:
        data_hora = jogo["fixture"]["date"][:16]
        por_horario[data_hora].append(jogo)

    for horario, lista in por_horario.items():
        if len(lista) < PLACAR_MIN_JOGOS:
            continue

        candidatos = []
        for jogo in lista:
            fid = jogo["fixture"]["id"]
            if fid not in dados_por_jogo:
                continue
            dados = dados_por_jogo[fid]
            if not dados.get("placar_odds"):
                continue

            placar, odd, motivo = escolher_placar_com_contexto(
                dados["mandante"], dados["visitante"], dados["placar_odds"]
            )
            if placar and odd and 6.00 <= odd <= 15.00:
                candidatos.append({
                    "home": jogo["teams"]["home"]["name"],
                    "away": jogo["teams"]["away"]["name"],
                    "placar": placar,
                    "odd": odd,
                    "motivo": motivo,
                    "horario": horario
                })

        if len(candidatos) >= PLACAR_MIN_JOGOS:
            candidatos.sort(key=lambda x: x["odd"])
            return candidatos[:PLACAR_MAX_JOGOS]
    return None

# ─────────────────────────────────────────────
# FORMATADORES DE MENSAGEM
# ─────────────────────────────────────────────

def fmt(v):
    return f"{v:.2f}"

def msg_aviso(liga, home, away, horario, texto="Padrão identificado. Calculando valor..."):
    return (
        f"⚽ <b>RD STATS | ANÁLISE EM ANDAMENTO</b>\n\n"
        f"🏆 {liga}\n"
        f"🆚 {home} x {away}\n"
        f"🕐 Hoje, {horario[11:16]}\n\n"
        f"🔎 {texto}"
    )

def msg_principal(liga, home, away, mandante, visitante, pernas):
    linhas = [
        "⚽ <b>RD STATS | ESTRATÉGIA VISITANTE REATIVO</b>",
        "",
        f"🏆 {liga}",
        f"🆚 {home} x {away}",
        "",
        "━━━━━━━━━━━━━━━━━━━",
        "",
        "📊 <b>CONTEXTO</b>",
        f"🏠 {home} em casa: {mandante['media_fin']:.1f} fin/jogo, {mandante['media_esc']:.1f} esc/jogo ({mandante['n_jogos']} jogos)",
        f"✈️ {away} fora: {visitante['media_fin_perdendo']:.1f} fin quando perde ({visitante['n_jogos']} jogos)",
        "✅ Visitante reativo confirmado",
        "",
        "━━━━━━━━━━━━━━━━━━━",
        "",
        "🎯 <b>ENTRADA PRINCIPAL</b>"
    ]
    for p in pernas:
        linha = f"• {p['nome']}: {int(p['taxa']*100)}% ({p['acertos']}/{p['total']})"
        if p.get("odd"):
            linha += f" — @ {fmt(p['odd'])}"
        linhas.append(linha)

    taxas = [p["taxa"] for p in pernas]
    pct = int((sum(taxas) / len(taxas)) * 100)
    nivel = "ALTA" if pct >= 90 else "MÉDIA" if pct >= 80 else "BAIXA"

    linhas += [
        "",
        "━━━━━━━━━━━━━━━━━━━",
        "",
        f"📈 <b>Confiança:</b> {pct}% ({nivel})",
        "",
        "━━━━━━━━━━━━━━━━━━━",
        "",
        "Cada um sabe o que faz com a informação. 🚀"
    ]
    return "\n".join(linhas)

def msg_valor(liga, home, away, achados):
    linhas = [
        "⚽ <b>RD STATS | ENTRADA</b>",
        "",
        f"🏆 {liga}",
        f"🆚 {home} x {away}",
        "",
        "━━━━━━━━━━━━━━━━━━━",
        "",
        "🎯 <b>MERCADO COM VALOR</b>"
    ]
    for a in achados[:PERNAS_MAX]:
        linhas.append(f"• {a['nome']} — @ {fmt(a['odd'])}")
        linhas.append(f"   Média das outras casas: @ {fmt(a['media'])}")
        linhas.append(f"   Diferença: +{a['diff']}%")
        linhas.append("")

    odd_final = 1.0
    for a in achados[:PERNAS_MAX]:
        odd_final *= a["odd"]

    linhas += [
        "━━━━━━━━━━━━━━━━━━━",
        "",
        f"💰 <b>ODD FINAL:</b> {fmt(odd_final)}",
        "",
        "━━━━━━━━━━━━━━━━━━━",
        "",
        "Cada um sabe o que faz com a informação. 🚀"
    ]
    return "\n".join(linhas), odd_final

def msg_odd_errada(liga, home, away, alertas):
    linhas = [
        "💰 <b>RD STATS | ODD ERRADA NA BET365</b>",
        "",
        f"🏆 {liga}",
        f"🆚 {home} x {away}",
        "",
        "━━━━━━━━━━━━━━━━━━━",
        "",
        "⚠️ <b>Bet365 pagando acima do mercado:</b>",
        ""
    ]
    for a in alertas:
        linhas.append(f"• {a['mercado']} ({a['valor']})")
        linhas.append(f"   Bet365: @ {fmt(a['bet365'])}")
        linhas.append(f"   Média das outras casas: @ {fmt(a['media'])}")
        linhas.append(f"   Diferença: +{a['diff']}%")
        linhas.append("")
    linhas.append("💡 Valor detectado. Aproveita.")
    return "\n".join(linhas)

def msg_bingo(entradas):
    linhas = [
        "🎰 <b>RD STATS | BINGO DO DIA</b>",
        "",
        f"📅 {datetime.now(pytz.timezone('America/Sao_Paulo')).strftime('%d/%m/%Y')}",
        f"🎯 {len(entradas)} jogos com contexto forte",
        "",
        "━━━━━━━━━━━━━━━━━━━"
    ]
    odd_final = 1.0
    for e in entradas:
        linhas.append(f"• {e['home']} x {e['away']} — {e['mercado']} @ {fmt(e['odd'])}")
        odd_final *= e["odd"]

    linhas += [
        "",
        "━━━━━━━━━━━━━━━━━━━",
        "",
        f"💰 <b>ODD FINAL:</b> {fmt(odd_final)} 🚨",
        "",
        "━━━━━━━━━━━━━━━━━━━",
        "",
        "Cada um sabe o que faz com a informação. 🚀"
    ]
    return "\n".join(linhas), odd_final

def msg_bingo_aviso(odd_final):
    return (
        f"🚨🚨🚨 <b>BINGO DETECTADO</b> 🚨🚨🚨\n\n"
        f"Odd final: <b>{fmt(odd_final)}</b>\n\n"
        f"Cada um sabe o que faz com a informação. 🚀"
    )

def msg_placar(entradas, horario):
    linhas = [
        "🎯 <b>RD STATS | RESULTADO CORRETO MÚLTIPLO</b>",
        "",
        f"🕐 Todos começam {horario[11:16]}",
        f"📅 {datetime.now(pytz.timezone('America/Sao_Paulo')).strftime('%d/%m/%Y')}",
        "",
        "━━━━━━━━━━━━━━━━━━━"
    ]
    odd_final = 1.0
    for e in entradas:
        linhas.append(f"• {e['home']} x {e['away']} — {e['placar']} @ {fmt(e['odd'])}")
        linhas.append(f"   ↳ {e['motivo']}")
        odd_final *= e["odd"]

    linhas += [
        "",
        "━━━━━━━━━━━━━━━━━━━",
        "",
        f"💰 <b>ODD FINAL:</b> {fmt(odd_final)} 🚨",
        "",
        "💡 Cashout viável após 60 min",
        "",
        "━━━━━━━━━━━━━━━━━━━",
        "",
        "Cada um sabe o que faz com a informação. 🚀"
    ]
    return "\n".join(linhas), odd_final

# ─────────────────────────────────────────────
# PROCESSAMENTO PRINCIPAL
# ─────────────────────────────────────────────

def processar_jogos(limite_jogos=None):
    global REQ_COUNT
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Iniciando análise...")
    print(f"Requisições usadas hoje: {REQ_COUNT}/{LIMITE_DIARIO}")

    if atingiu_alerta():
        print("⚠️ Alerta: limite próximo. Modo econômico.")

    enviados = carregar_enviados()
    jogos = get_jogos_do_dia()
    print(f"Jogos do dia: {len(jogos)}")

    if limite_jogos:
        jogos = jogos[:limite_jogos]
        print(f"⚙️ Limitado a {limite_jogos} jogos para teste")

    bingo_entradas = []
    bingo_ja = bingo_ja_enviado_hoje()
    placar_ja = placar_ja_enviado_hoje()
    odd_errada_hoje = carregar_odd_errada_hoje()
    dados_por_jogo = {}

    for jogo in jogos:
        if jogo["fixture"]["status"]["short"] != "NS":
            continue
        fixture_id = jogo["fixture"]["id"]

        liga_id   = jogo["league"]["id"]
        liga_nome = jogo["league"]["name"]
        home_id   = jogo["teams"]["home"]["id"]
        away_id   = jogo["teams"]["away"]["id"]
        home_nome = jogo["teams"]["home"]["name"]
        away_nome = jogo["teams"]["away"]["name"]
        horario = jogo["fixture"]["date"]

        print(f"\n→ {home_nome} x {away_nome}")

        jogos_casa = get_jogos_time(home_id, liga_id, casa=True)
        jogos_fora = get_jogos_time(away_id, liga_id, casa=False)

        if not jogos_casa or not jogos_fora:
            print("   Sem histórico.")
            continue

        mandante = analisar_mandante(jogos_casa, home_id)
        visitante = analisar_visitante(jogos_fora, away_id)

        if not mandante or not visitante:
            continue

        mandante["nome"] = home_nome
        visitante["nome"] = away_nome

        odds_data = get_odds_fixture(fixture_id)
        odds = extrair_odds(odds_data)

        if BET365_ID not in odds:
            print("   Sem Bet365.")
            continue

        # Guarda dados pro placar
        if not placar_ja:
            placar_odds = {}
            if ID_EXACT in odds[BET365_ID]:
                for v, o in odds[BET365_ID][ID_EXACT]:
                    placar_odds[v] = o
            dados_por_jogo[fixture_id] = {
                "mandante": mandante,
                "visitante": visitante,
                "placar_odds": placar_odds
            }

        ja_enviado = str(fixture_id) in enviados

        if ja_enviado:
            continue

        # ─── 1. ODD ERRADA (imediata) ───
        alertas = []
        for bet_id, valor, label in [
            (ID_GOALS, "Over 2.5", "Over 2.5 gols"),
            (ID_BTTS, "Yes", "Ambas marcam"),
            (ID_CARDS, "Over 3.5", "Over 3.5 cartões"),
            (ID_CORNERS, "Over 9.5", "Over 9.5 escanteios"),
        ]:
            chave = f"{fixture_id}-{bet_id}-{valor}"
            if chave in odd_errada_hoje:
                continue
            a = detectar_odd_errada(odds, bet_id, valor, label)
            if a:
                alertas.append(a)
                odd_errada_hoje.add(chave)

        if alertas:
            enviar_mensagem(msg_odd_errada(liga_nome, home_nome, away_nome, alertas))
            salvar_odd_errada_hoje(odd_errada_hoje)
            print(f"   💰 Odd errada enviada")
            time.sleep(ESPERA_ENTRE_MSGS)

        # ─── 2. ENTRADA PRINCIPAL ───
        achou_principal = False
        if mandante["media_fin"] >= MANDANTE_MIN_FIN and mandante["media_esc"] >= MANDANTE_MIN_ESC and visitante["reativo"]:
            pernas = montar_principal(mandante, visitante, odds, home_nome, away_nome)
            if len(pernas) >= PERNAS_MIN:
                achou_principal = True

                # Aviso
                enviar_mensagem(msg_aviso(liga_nome, home_nome, away_nome, horario))
                time.sleep(ESPERA_ENTRE_MSGS)

                # Entrada
                enviar_mensagem(msg_principal(liga_nome, home_nome, away_nome, mandante, visitante, pernas))
                print(f"   ✅ Principal ({len(pernas)} pernas)")
                time.sleep(ESPERA_ENTRE_MSGS)

        # ─── 3. ENTRADA NORMAL ───
        valores = buscar_valor_jogo(odds)
        if valores:
            # Aviso
            enviar_mensagem(msg_aviso(liga_nome, home_nome, away_nome, horario, "Procurando valor no mercado..."))
            time.sleep(ESPERA_ENTRE_MSGS)

            # Entrada
            msg, odd_f = msg_valor(liga_nome, home_nome, away_nome, valores)
            enviar_mensagem(msg)
            print(f"   ✅ Normal (odd {odd_f:.2f})")
            time.sleep(ESPERA_ENTRE_MSGS)

            if not bingo_ja:
                bingo_entradas.append({
                    "home": home_nome, "away": away_nome,
                    "mercado": valores[0]["nome"], "odd": valores[0]["odd"]
                })

        # Marca enviado se achou principal OU valor
        if achou_principal or valores:
            enviados.add(str(fixture_id))
            salvar_enviados(enviados)

        time.sleep(1)

    # ─── 4. BINGO DO DIA ───
    if not bingo_ja and len(bingo_entradas) >= BINGO_MIN_JOGOS:
        odd_bingo = 1.0
        for e in bingo_entradas:
            odd_bingo *= e["odd"]
        if odd_bingo >= ODD_BINGO_DIA:
            enviar_mensagem(
                "🎰 <b>RD STATS | BINGO DO DIA</b>\n\n"
                "Analisando os melhores jogos do dia...\n\n"
                f"🎯 {len(bingo_entradas)} jogos com contexto forte"
            )
            time.sleep(ESPERA_ENTRE_MSGS)

            enviar_mensagem(msg_bingo_aviso(odd_bingo))
            time.sleep(ESPERA_ENTRE_MSGS)

            msg, _ = msg_bingo(bingo_entradas)
            enviar_mensagem(msg)
            marcar_bingo_enviado()
            print(f"   🎰 BINGO DO DIA (odd {odd_bingo:.2f})")

    # ─── 5. PLACAR MÚLTIPLO ───
    if not placar_ja:
        multipla = montar_placar_multipla(jogos, dados_por_jogo)
        if multipla and len(multipla) >= PLACAR_MIN_JOGOS:
            enviar_mensagem(
                "🎯 <b>RD STATS | RESULTADO CORRETO MÚLTIPLO</b>\n\n"
                "Analisando placares do dia...\n\n"
                f"🎯 {len(multipla)} jogos no mesmo horário"
            )
            time.sleep(ESPERA_ENTRE_MSGS)

            horario = multipla[0]["horario"]
            msg, odd_p = msg_placar(multipla, horario)
            enviar_mensagem(msg)
            marcar_placar_enviado()
            print(f"   🎯 Placar múltiplo (odd {odd_p:.2f})")

    salvar_req(REQ_COUNT)
    print(f"\n✅ Ciclo finalizado. Req: {REQ_COUNT}/{LIMITE_DIARIO}")

# ─────────────────────────────────────────────
# LOOP PRINCIPAL
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("🚀 RD Stats iniciado.")
    while True:
        agora = datetime.now(pytz.timezone("America/Sao_Paulo"))
        if 8 <= agora.hour < 23:
            try:
                processar_jogos()
            except Exception as e:
                print(f"Erro no ciclo: {e}")
            time.sleep(INTERVALO_MIN * 60)
        else:
            print(f"[{agora.strftime('%H:%M')}] Fora do horário. Dormindo 1h...")
            time.sleep(3600)
