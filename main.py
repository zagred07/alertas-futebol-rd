import requests
import time
import os
from datetime import datetime, timedelta
import pytz
import json
import statistics
import math
from collections import defaultdict

API_KEY   = os.getenv("API_FOOTBALL_KEY")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

BASE_URL = "https://v3.football.api-sports.io"
HEADERS  = {"x-apisports-key": API_KEY}

LIGAS = [71, 72, 39, 140, 135, 78, 61, 40]
LIGAS_VISITANTE_REATIVO = [71, 72]
SEASON = 2026

BET365_ID    = 8
PINNACLE_ID  = 4
OUTRAS_CASAS = [2, 7, 36, 11]

ARQUIVO_ENVIADOS     = "jogos_enviados.json"
ARQUIVO_CACHE        = "cache_stats.json"
ARQUIVO_REQ          = "req_count.json"
ARQUIVO_BINGO        = "bingo_do_dia.json"
ARQUIVO_PLACAR_HORA  = "placar_por_horario.json"
ARQUIVO_ODD_ERR      = "odd_errada_hoje.json"
ARQUIVO_STANDINGS    = "standings_cache.json"
ARQUIVO_EVENTS       = "cache_events.json"
ARQUIVO_CACADOR      = "cacador_odds.json"

LIMITE_DIARIO = 7000
ALERTA_LIMITE = 6000

MANDANTE_MIN_FIN   = 12
MANDANTE_MIN_ESC   = 4
TAXA_MIN_ACERTO    = 0.70
TAXA_MIN_VIS_GOL   = 0.85
MIN_JOGOS          = 10
PERNAS_MIN         = 2
PERNAS_MAX         = 4
ODD_MIN_PERNA      = 1.20
ODD_MIN_FINAL      = 1.50
ODD_BINGO_DIA      = 3.00
ODD_ERRADA_MIN     = 1.25
ODD_ERRADA_MAX     = 1.40
ODD_ERRADA_MIN_ODD = 1.50
ODD_VALOR_MIN      = 1.15

POISSON_MAX_GOLS   = 7
PLACAR_ODD_MIN     = 6.00
PLACAR_ODD_MAX     = 25.00

# Classificação de estilo
ESTILO_ABERTO      = 3.0
ESTILO_FECHADO     = 2.4

AJUSTE_LAMBDA      = 0.5

PODER_MEDIA_CASA    = 3.0
PODER_MAIOR_PLACAR  = 5
PODER_POSICAO_G4    = 4
FRAQUEZA_MEDIA_SOFRIDA_FORA = 2.5
FRAQUEZA_PCT_DERROTAS_FORA  = 0.70
FRAQUEZA_POSICAO_Z4 = 4

INTERVALO_MIN = 30
INTERVALO_CACADOR = 30
BINGO_MIN_JOGOS = 2
PLACAR_MIN_JOGOS = 3
PLACAR_MAX_JOGOS = 4
ESPERA_ENTRE_MSGS = 30
ESPERA_ENTRE_JOGOS = 30

# ─────────────────────────────────────────────
# MERCADOS E LIMITES
# ─────────────────────────────────────────────

MERCADOS_ODD_ERRADA = {
    6:   {"nome": "Gols 1ºT",            "limites": ["Over 0.5", "Over 1.5"]},
    8:   {"nome": "Ambas Marcam",        "limites": ["Yes", "No"]},
    45:  {"nome": "Escanteios Totais",   "limites": ["Over 7.5", "Over 8.5", "Over 9.5"]},
    77:  {"nome": "Escanteios 1ºT",      "limites": ["Over 3.5", "Over 4.5", "Over 5.5"]},
    82:  {"nome": "Cartões Mandante",    "limites": ["Over 0.5", "Over 1.5"]},
    83:  {"nome": "Cartões Visitante",   "limites": ["Over 0.5", "Over 1.5"]},
    87:  {"nome": "Chutes ao Gol Totais","limites": ["Over 6.5", "Over 7.5", "Over 8.5"]},
    155: {"nome": "Amarelos 1ºT",        "limites": ["Over 0.5", "Over 1.5"]},
    211: {"nome": "Finalizações Totais", "limites": ["Over 20.5", "Over 25.5"]},
}

# ─────────────────────────────────────────────
# ANTI-DUPLICAÇÃO
# ─────────────────────────────────────────────

def ler_ultimas_mensagens(limit=50):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    try:
        r = requests.get(url, params={"limit": limit, "allowed_updates": '["channel_post"]'}, timeout=15)
        if r.status_code != 200:
            return []
        updates = r.json().get("result", [])
        textos = []
        for u in updates:
            post = u.get("channel_post", {})
            txt = post.get("text", "")
            if txt:
                textos.append(txt)
        return textos
    except Exception as e:
        print(f"Erro lendo Telegram: {e}")
        return []

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
# CACHE EVENTOS
# ─────────────────────────────────────────────

def carregar_events_cache():
    if os.path.exists(ARQUIVO_EVENTS):
        try:
            with open(ARQUIVO_EVENTS) as f:
                return json.load(f)
        except:
            return {}
    return {}

def salvar_events_cache(cache):
    with open(ARQUIVO_EVENTS, "w") as f:
        json.dump(cache, f)

EVENTS_CACHE = carregar_events_cache()

def get_eventos_fixture(fixture_id):
    fid = str(fixture_id)
    if fid in EVENTS_CACHE:
        return EVENTS_CACHE[fid]
    resp = api_get("fixtures/events", {"fixture": fixture_id})
    if resp is None:
        return []
    EVENTS_CACHE[fid] = resp
    salvar_events_cache(EVENTS_CACHE)
    return resp

def quem_fez_primeiro_gol(fixture_id, home_id, away_id):
    eventos = get_eventos_fixture(fixture_id)
    if not eventos:
        return None
    for ev in eventos:
        if ev.get("type") == "Goal":
            team_id = ev.get("team", {}).get("id")
            if team_id == home_id:
                return "home"
            elif team_id == away_id:
                return "away"
    return None

# ─────────────────────────────────────────────
# STANDINGS
# ─────────────────────────────────────────────

def carregar_standings_cache():
    if os.path.exists(ARQUIVO_STANDINGS):
        try:
            with open(ARQUIVO_STANDINGS) as f:
                d = json.load(f)
            if d.get("data") == _hoje_str():
                return d.get("standings", {})
        except:
            pass
    return {}

def salvar_standings_cache(standings):
    with open(ARQUIVO_STANDINGS, "w") as f:
        json.dump({"data": _hoje_str(), "standings": standings}, f)

STANDINGS_CACHE = carregar_standings_cache()

def get_posicao_time(team_id, liga_id):
    chave = f"{liga_id}"
    if chave not in STANDINGS_CACHE:
        resp = api_get("standings", {"league": liga_id, "season": SEASON})
        tabela = {}
        if resp:
            try:
                liga_data = resp[0]["league"]["standings"]
                for grupo in liga_data:
                    for entry in grupo:
                        tid = entry["team"]["id"]
                        tabela[tid] = entry["rank"]
            except:
                pass
        STANDINGS_CACHE[chave] = tabela
        salvar_standings_cache(STANDINGS_CACHE)
    return STANDINGS_CACHE.get(chave, {}).get(team_id)

def total_times_liga(liga_id):
    chave = f"{liga_id}"
    return len(STANDINGS_CACHE.get(chave, {})) or 20

def classificar_nivel_time(team_id, liga_id):
    pos = get_posicao_time(team_id, liga_id)
    total = total_times_liga(liga_id)
    if pos is None:
        return "medio"
    if pos <= 4:
        return "forte"
    elif pos > (total - 4):
        return "fraco"
    return "medio"

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

def carregar_placar_horarios():
    if os.path.exists(ARQUIVO_PLACAR_HORA):
        try:
            with open(ARQUIVO_PLACAR_HORA) as f:
                d = json.load(f)
            if d.get("data") == _hoje_str():
                return set(d.get("horarios", []))
        except:
            pass
    return set()

def salvar_placar_horarios(horarios):
    with open(ARQUIVO_PLACAR_HORA, "w") as f:
        json.dump({"data": _hoje_str(), "horarios": list(horarios)}, f)

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

def carregar_cacador():
    if os.path.exists(ARQUIVO_CACADOR):
        try:
            with open(ARQUIVO_CACADOR) as f:
                d = json.load(f)
            if d.get("data") == _hoje_str():
                return set(d.get("ids", []))
        except:
            pass
    return set()

def salvar_cacador(ids):
    with open(ARQUIVO_CACADOR, "w") as f:
        json.dump({"data": _hoje_str(), "ids": list(ids)}, f)

CACADOR_ENVIADOS = carregar_cacador()

# ─────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────

def formatar_data_jogo(horario_iso):
    try:
        dt_jogo = datetime.fromisoformat(horario_iso.replace("Z", "+00:00"))
        dt_jogo = dt_jogo.astimezone(pytz.timezone("America/Sao_Paulo"))
        hoje = datetime.now(pytz.timezone("America/Sao_Paulo")).date()
        amanha = hoje + timedelta(days=1)
        if dt_jogo.date() == hoje:
            return f"Hoje, {dt_jogo.strftime('%H:%M')}"
        elif dt_jogo.date() == amanha:
            return f"Amanhã, {dt_jogo.strftime('%H:%M')}"
        else:
            return f"{dt_jogo.strftime('%d/%m')}, {dt_jogo.strftime('%H:%M')}"
    except:
        return horario_iso[11:16]

def converter_horario_brasilia(horario_iso):
    try:
        dt_jogo = datetime.fromisoformat(horario_iso.replace("Z", "+00:00"))
        dt_brasilia = dt_jogo.astimezone(pytz.timezone("America/Sao_Paulo"))
        return dt_brasilia.strftime("%H:%M")
    except:
        return horario_iso[11:16]

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
# STATS
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
    vitorias = 0
    jogos_marcou = 0
    jogos_abriu_placar = 0
    for j in jogos:
        stats = get_stats_fixture(j["fixture"]["id"])
        s = extrair_stats_jogo(stats, team_id)
        fin.append(s["finalizacoes"])
        esc.append(s["escanteios"])
        cart.append(s["cartoes"])
        gf = get_gols(j, team_id)
        gs = get_gols_sofridos(j, team_id)
        gols_feitos.append(gf)
        gols_sofridos.append(gs)
        if gf > gs:
            vitorias += 1
        if gf > 0:
            jogos_marcou += 1
        home_id = j["teams"]["home"]["id"]
        away_id = j["teams"]["away"]["id"]
        quem = quem_fez_primeiro_gol(j["fixture"]["id"], home_id, away_id)
        if quem == "home" and home_id == team_id:
            jogos_abriu_placar += 1
        elif quem == "away" and away_id == team_id:
            jogos_abriu_placar += 1
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
        "min_gols": min(gols_feitos),
        "max_gols": max(gols_feitos),
        "sempre_marca": all(g > 0 for g in gols_feitos),
        "pct_marcou": jogos_marcou / len(jogos) if jogos else 0,
        "pct_vitorias": vitorias / len(jogos) if jogos else 0,
        "pct_abriu_placar": jogos_abriu_placar / len(jogos) if jogos else 0,
        "lista_fin": fin,
        "lista_esc": esc,
        "lista_cart": cart,
        "lista_gols_feitos": gols_feitos,
        "lista_gols_sofridos": gols_sofridos,
    }

def analisar_visitante(jogos, team_id):
    if not jogos:
        return None
    fin, chutes, cart = [], [], []
    v, e, d = [], [], []
    gols_feitos, gols_sofridos = [], []
    derrotas = 0
    jogos_marcou = 0
    jogos_levou_primeiro = 0
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
        if gf > 0:
            jogos_marcou += 1
        if gf > gs:
            v.append(s["finalizacoes"])
        elif gf < gs:
            d.append(s["finalizacoes"])
            derrotas += 1
        else:
            e.append(s["finalizacoes"])
        home_id = j["teams"]["home"]["id"]
        away_id = j["teams"]["away"]["id"]
        quem = quem_fez_primeiro_gol(j["fixture"]["id"], home_id, away_id)
        if quem == "home" and away_id == team_id:
            jogos_levou_primeiro += 1
        elif quem == "away" and home_id == team_id:
            jogos_levou_primeiro += 1
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
        "min_gols": min(gols_feitos),
        "max_gols": max(gols_feitos),
        "pct_derrotas": derrotas / len(jogos) if jogos else 0,
        "pct_marcou": jogos_marcou / len(jogos) if jogos else 0,
        "pct_levou_primeiro": jogos_levou_primeiro / len(jogos) if jogos else 0,
        "reativo": reativo,
        "lista_fin": fin,
        "lista_chutes_gol": chutes,
        "lista_cartoes": cart,
        "lista_gols_feitos": gols_feitos,
        "lista_gols_sofridos": gols_sofridos,
    }

def taxa(lista, linha):
    if not lista:
        return 0, 0
    acertos = sum(1 for v in lista if v >= linha)
    return acertos / len(lista), acertos

def escolher_linha_mais_assertiva(lista, linhas_possiveis, min_linha):
    melhor = None
    melhor_taxa = 0
    melhor_acertos = 0
    for linha in linhas_possiveis:
        if linha < min_linha:
            continue
        t, ac = taxa(lista, linha)
        if t >= TAXA_MIN_ACERTO:
            if t > melhor_taxa or (t == melhor_taxa and (melhor is None or linha > melhor)):
                melhor = linha
                melhor_taxa = t
                melhor_acertos = ac
    return melhor, melhor_taxa, melhor_acertos

def analisar_por_nivel(jogos, team_id, liga_id, casa=True):
    resultado = {"contra_forte": [], "contra_medio": [], "contra_fraco": []}
    for j in jogos:
        if casa:
            adv_id = j["teams"]["away"]["id"]
        else:
            adv_id = j["teams"]["home"]["id"]
        nivel_adv = classificar_nivel_time(adv_id, liga_id)
        gf = get_gols(j, team_id)
        resultado[f"contra_{nivel_adv}"].append(gf)
    return {
        "media_forte": statistics.mean(resultado["contra_forte"]) if resultado["contra_forte"] else 0,
        "media_medio": statistics.mean(resultado["contra_medio"]) if resultado["contra_medio"] else 0,
        "media_fraco": statistics.mean(resultado["contra_fraco"]) if resultado["contra_fraco"] else 0,
        "n_forte": len(resultado["contra_forte"]),
        "n_medio": len(resultado["contra_medio"]),
        "n_fraco": len(resultado["contra_fraco"]),
    }

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

def get_odd_com_fallback(odds, bet_id, valor):
    o365 = get_odd(odds, BET365_ID, bet_id, valor)
    if o365:
        return o365, "bet365"
    opinnacle = get_odd(odds, PINNACLE_ID, bet_id, valor)
    if opinnacle:
        return opinnacle, "pinnacle"
    return None, None

def media_outras_casas(odds, bet_id, valor):
    valores = []
    odd_pinnacle = get_odd(odds, PINNACLE_ID, bet_id, valor)
    if odd_pinnacle:
        valores.append(odd_pinnacle)
        valores.append(odd_pinnacle)
    for bm_id in OUTRAS_CASAS:
        o = get_odd(odds, bm_id, bet_id, valor)
        if o:
            valores.append(o)
    if len(valores) < 2:
        return None
    return statistics.mean(valores)

# ─────────────────────────────────────────────
# VALIDAÇÃO MULTI-CASAS (BTTS)
# ─────────────────────────────────────────────

def validar_mercado_multicasas(odds, bet_id, valor_365, o365):
    if not o365:
        return False
    if bet_id == 8:
        yes_365 = get_odd(odds, BET365_ID, 8, "Yes")
        no_365 = get_odd(odds, BET365_ID, 8, "No")
        if not (yes_365 and no_365):
            return True
        sentido_365 = "yes" if yes_365 > no_365 else "no"
        votos_discordam = 0
        for bm_id in [PINNACLE_ID, 2, 7, 36, 11]:
            yes_ref = get_odd(odds, bm_id, 8, "Yes")
            no_ref = get_odd(odds, bm_id, 8, "No")
            if yes_ref and no_ref:
                sentido_ref = "yes" if yes_ref > no_ref else "no"
                if sentido_ref != sentido_365:
                    votos_discordam += 1
        if votos_discordam >= 2:
            print(f"   ⚠️ BTTS invertido!")
            return False
        return True
    return True

# ─────────────────────────────────────────────
# DETECTAR ODD ERRADA
# ─────────────────────────────────────────────

def detectar_odd_errada_focado(odds):
    if BET365_ID not in odds:
        return None
    melhores = []
    for bet_id, config in MERCADOS_ODD_ERRADA.items():
        if bet_id not in odds[BET365_ID]:
            continue
        for valor_365, odd_365 in odds[BET365_ID][bet_id]:
            if valor_365 not in config["limites"]:
                continue
            try:
                odd_float = float(odd_365)
            except:
                continue
            if odd_float < ODD_ERRADA_MIN_ODD:
                continue
            if bet_id == 8:
                if not validar_mercado_multicasas(odds, bet_id, valor_365, odd_float):
                    continue
            media = media_outras_casas(odds, bet_id, valor_365)
            if not media:
                continue
            diff = odd_float / media
            if ODD_ERRADA_MIN <= diff <= ODD_ERRADA_MAX:
                odds_casas = {}
                opinnacle = get_odd(odds, PINNACLE_ID, bet_id, valor_365)
                if opinnacle:
                    odds_casas["Pinnacle"] = opinnacle
                for bm_id in OUTRAS_CASAS:
                    o = get_odd(odds, bm_id, bet_id, valor_365)
                    if o:
                        nome_casa = {2: "Marathonbet", 7: "William Hill", 36: "BetVictor", 11: "1xBet"}.get(bm_id, f"Casa {bm_id}")
                        odds_casas[nome_casa] = o
                melhores.append({
                    "mercado": config["nome"], "valor": valor_365,
                    "bet365": odd_float, "media": media,
                    "diff": int((diff - 1) * 100),
                    "bet_id": bet_id, "odds_casas": odds_casas,
                })
    if not melhores:
        return None
    melhores.sort(key=lambda x: x["diff"], reverse=True)
    return melhores[0]

# ─────────────────────────────────────────────
# CLASSIFICAÇÃO DE ESTILO (NOVO)
# ─────────────────────────────────────────────

def classificar_estilo(media_feitos, media_sofridos):
    """Classifica o time como aberto, equilibrado ou fechado."""
    total = media_feitos + media_sofridos
    if total >= ESTILO_ABERTO:
        return "aberto"
    elif total <= ESTILO_FECHADO:
        return "fechado"
    return "equilibrado"

def calcular_placar_minimo(estilo_mand, estilo_vis):
    """Retorna o mínimo de gols pro jogo, baseado nos estilos."""
    # Aberto x Aberto → 3 gols
    if estilo_mand == "aberto" and estilo_vis == "aberto":
        return 3
    # Aberto x Equilibrado → 3 gols
    if estilo_mand == "aberto" and estilo_vis == "equilibrado":
        return 3
    if estilo_mand == "equilibrado" and estilo_vis == "aberto":
        return 3
    # Todos os outros casos → 2 gols (aceita 1:1, 2:0)
    return 2

def placar_permitido(placar, estilo_mand, estilo_vis):
    """Verifica se o placar é permitido (não muito arriscado)."""
    g_casa, g_fora = map(int, placar.split(":"))

    # Nunca aceita 1:0 ou 0:1 (muito arriscado pra cashout)
    if (g_casa == 1 and g_fora == 0) or (g_casa == 0 and g_fora == 1):
        return False

    # Nunca aceita 0:0
    if g_casa == 0 and g_fora == 0:
        return False

    return True

# ─────────────────────────────────────────────
# POISSON
# ─────────────────────────────────────────────

def poisson_probabilidade(k, lamb):
    if lamb <= 0:
        return 0
    return (lamb ** k) * math.exp(-lamb) / math.factorial(k)

def analisar_poder_fraqueza(mandante, visitante, pos_mand=None, pos_vis=None, total_times=20):
    if not mandante or not visitante:
        return False, False
    media_casa = mandante.get("media_gols_feitos", 0)
    max_casa = mandante.get("max_gols", 0)
    no_g4 = pos_mand is not None and pos_mand <= PODER_POSICAO_G4
    poderoso = (media_casa >= PODER_MEDIA_CASA) or (max_casa >= PODER_MAIOR_PLACAR) or no_g4
    media_sofre_fora = visitante.get("media_gols_sofridos", 0)
    pct_der = visitante.get("pct_derrotas", 0)
    no_z4 = pos_vis is not None and pos_vis > (total_times - FRAQUEZA_POSICAO_Z4)
    fraco = (media_sofre_fora >= FRAQUEZA_MEDIA_SOFRIDA_FORA) or (pct_der >= FRAQUEZA_PCT_DERROTAS_FORA) or no_z4
    return poderoso, fraco

def calcular_gols_esperados_por_nivel(mandante, visitante, nivel_adv_mand, nivel_adv_vis, mandante_por_nivel, visitante_por_nivel):
    if nivel_adv_mand == "forte":
        gols_mand = mandante_por_nivel.get("media_forte", 0) or mandante.get("media_gols_feitos", 1.5)
    elif nivel_adv_mand == "fraco":
        gols_mand = mandante_por_nivel.get("media_fraco", 0) or mandante.get("media_gols_feitos", 1.5)
    else:
        gols_mand = mandante_por_nivel.get("media_medio", 0) or mandante.get("media_gols_feitos", 1.5)
    if nivel_adv_vis == "forte":
        gols_vis = visitante_por_nivel.get("media_forte", 0) or visitante.get("media_gols_feitos", 1.0)
    elif nivel_adv_vis == "fraco":
        gols_vis = visitante_por_nivel.get("media_fraco", 0) or visitante.get("media_gols_feitos", 1.0)
    else:
        gols_vis = visitante_por_nivel.get("media_medio", 0) or visitante.get("media_gols_feitos", 1.0)
    if gols_mand == 0:
        gols_mand = mandante.get("media_gols_feitos", 1.5)
    if gols_vis == 0:
        gols_vis = visitante.get("media_gols_feitos", 1.0)
    return gols_mand, gols_vis

def poisson_ajustado(mandante, visitante, gols_esperados_mand, gols_esperados_vis, poderoso, fraco):
    lambda_casa = gols_esperados_mand
    lambda_fora = gols_esperados_vis
    media_sofre_fora = visitante.get("media_gols_sofridos", 0)
    if media_sofre_fora >= 2.5:
        lambda_casa += AJUSTE_LAMBDA
    elif media_sofre_fora >= 2.0:
        lambda_casa += AJUSTE_LAMBDA * 0.6
    if poderoso:
        lambda_casa += AJUSTE_LAMBDA * 0.6
    media_sofre_casa = mandante.get("media_gols_sofridos", 0)
    if media_sofre_casa <= 0.5:
        lambda_fora -= AJUSTE_LAMBDA * 0.4
    elif media_sofre_casa >= 2.0:
        lambda_fora += AJUSTE_LAMBDA * 0.6
    if fraco:
        lambda_fora -= AJUSTE_LAMBDA * 0.4
    lambda_casa = max(0.5, lambda_casa)
    lambda_fora = max(0.2, lambda_fora)
    return lambda_casa, lambda_fora

def calcular_placares_possiveis(mandante, visitante, estilo_mand, estilo_vis):
    """Retorna placares possíveis + placar mais comum + placar mínimo."""
    placares_validos = []
    media_casa = mandante.get("media_gols_feitos", 1.5)
    max_casa = mandante.get("max_gols", 3)
    lista_gols_casa = mandante.get("lista_gols_feitos", [])
    n_casa = len(lista_gols_casa) or 1

    media_fora = visitante.get("media_gols_feitos", 1.0)
    max_fora = visitante.get("max_gols", 3)
    lista_gols_fora = visitante.get("lista_gols_feitos", [])
    n_fora = len(lista_gols_fora) or 1

    limite_casa = min(max_casa, int(media_casa) + 1)
    limite_fora = min(max_fora, int(media_fora) + 1)

    placar_min = calcular_placar_minimo(estilo_mand, estilo_vis)

    placares_casa = {}
    for g in lista_gols_casa:
        placares_casa[g] = placares_casa.get(g, 0) + 1
    placar_comum_casa = max(placares_casa, key=placares_casa.get) if placares_casa else 1

    placares_fora = {}
    for g in lista_gols_fora:
        placares_fora[g] = placares_fora.get(g, 0) + 1
    placar_comum_fora = max(placares_fora, key=placares_fora.get) if placares_fora else 1

    for g_casa in range(0, limite_casa + 1):
        for g_fora in range(0, limite_fora + 1):
            if g_casa + g_fora < placar_min:
                continue
            placar_str = f"{g_casa}:{g_fora}"
            if not placar_permitido(placar_str, estilo_mand, estilo_vis):
                continue
            pct_casa = sum(1 for g in lista_gols_casa if g >= g_casa) / n_casa
            pct_fora = sum(1 for g in lista_gols_fora if g >= g_fora) / n_fora
            if pct_casa >= 0.30 and pct_fora >= 0.30:
                placares_validos.append(placar_str)

    return placares_validos, placar_comum_casa, placar_comum_fora, placar_min

def calcular_placares_poisson(lambda_casa, lambda_fora):
    placares = {}
    for g_casa in range(0, POISSON_MAX_GOLS + 1):
        for g_fora in range(0, POISSON_MAX_GOLS + 1):
            p_casa = poisson_probabilidade(g_casa, lambda_casa)
            p_fora = poisson_probabilidade(g_fora, lambda_fora)
            placares[f"{g_casa}:{g_fora}"] = p_casa * p_fora
    return sorted(placares.items(), key=lambda x: x[1], reverse=True)

def escolher_placar_poisson(mandante, visitante, placar_odds, poderoso, fraco, nivel_adv_mand, nivel_adv_vis, mandante_por_nivel, visitante_por_nivel):
    if not mandante or not visitante or not placar_odds:
        return None, None, None, None, None, None
    if mandante.get("media_gols_feitos", 0) < 0.30:
        return None, None, None, None, None, None
    if visitante.get("media_gols_feitos", 0) < 0.30:
        return None, None, None, None, None, None

    # Classifica estilos
    estilo_mand = classificar_estilo(mandante.get("media_gols_feitos", 0), mandante.get("media_gols_sofridos", 0))
    estilo_vis = classificar_estilo(visitante.get("media_gols_feitos", 0), visitante.get("media_gols_sofridos", 0))

    gols_mand, gols_vis = calcular_gols_esperados_por_nivel(
        mandante, visitante, nivel_adv_mand, nivel_adv_vis,
        mandante_por_nivel, visitante_por_nivel
    )
    lambda_casa, lambda_fora = poisson_ajustado(mandante, visitante, gols_mand, gols_vis, poderoso, fraco)

    placares_possiveis, placar_comum_casa, placar_comum_fora, placar_min = calcular_placares_possiveis(mandante, visitante, estilo_mand, estilo_vis)

    placares_ordenados = calcular_placares_poisson(lambda_casa, lambda_fora)
    placares_ordenados = [(p, prob) for p, prob in placares_ordenados if p in placares_possiveis]

    for placar, prob in placares_ordenados:
        if placar in placar_odds:
            odd = placar_odds[placar]
            if PLACAR_ODD_MIN <= odd <= PLACAR_ODD_MAX:
                contexto = (
                    f"{mandante.get('nome','Mandante')} (casa): média {mandante['media_gols_feitos']:.2f} gols/jogo, "
                    f"estilo {estilo_mand}, placar comum {placar_comum_casa}:X. "
                    f"{visitante.get('nome','Visitante')} (fora): média {visitante['media_gols_feitos']:.2f} gols/jogo, "
                    f"estilo {estilo_vis}, placar comum X:{placar_comum_fora}."
                )
                return placar, odd, prob, lambda_casa, lambda_fora, contexto
    return None, None, None, None, None, None
    # ─────────────────────────────────────────────
# ENTRADA PRINCIPAL — VISITANTE REATIVO
# ─────────────────────────────────────────────

def montar_principal(mandante, visitante, odds, home_nome, away_nome):
    pernas = []
    if not visitante:
        return []

    linha_fin, t_fin, ac_fin = escolher_linha_mais_assertiva(
        visitante["lista_fin"], [6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5], min_linha=6.5
    )
    if linha_fin is None:
        return []

    odd_fin, _ = get_odd_com_fallback(odds, 276, f"Over {linha_fin}")
    pernas.append({
        "nome": f"{away_nome} +{linha_fin} finalizações",
        "taxa": t_fin, "acertos": ac_fin, "total": visitante["n_jogos"],
        "odd": odd_fin, "bet_id": 276, "valor": f"Over {linha_fin}"
    })

    linha, t, ac = escolher_linha_mais_assertiva(visitante["lista_chutes_gol"], [1.5, 2.5, 3.5, 4.5], min_linha=1.5)
    if linha is not None:
        pernas.append({
            "nome": f"{away_nome} +{linha} chutes ao gol",
            "taxa": t, "acertos": ac, "total": visitante["n_jogos"],
            "odd": None, "bet_id": None, "valor": None
        })

    linha, t, ac = escolher_linha_mais_assertiva(visitante["lista_cartoes"], [0.5, 1.5, 2.5], min_linha=0.5)
    if linha is not None:
        odd, _ = get_odd_com_fallback(odds, 83, f"Over {linha}")
        pernas.append({
            "nome": f"{away_nome} +{linha} cartões",
            "taxa": t, "acertos": ac, "total": visitante["n_jogos"],
            "odd": odd, "bet_id": 83, "valor": f"Over {linha}"
        })

    if mandante:
        linha, t, ac = escolher_linha_mais_assertiva(mandante["lista_cart"], [0.5, 1.5, 2.5], min_linha=0.5)
        if linha is not None:
            odd, _ = get_odd_com_fallback(odds, 82, f"Over {linha}")
            pernas.append({
                "nome": f"{home_nome} +{linha} cartões",
                "taxa": t, "acertos": ac, "total": mandante["n_jogos"],
                "odd": odd, "bet_id": 82, "valor": f"Over {linha}"
            })

        linha, t, ac = escolher_linha_mais_assertiva(mandante["lista_esc"], [3.5, 4.5, 5.5, 6.5], min_linha=3.5)
        if linha is not None:
            odd, _ = get_odd_com_fallback(odds, 57, f"Over {linha}")
            pernas.append({
                "nome": f"{home_nome} +{linha} escanteios",
                "taxa": t, "acertos": ac, "total": mandante["n_jogos"],
                "odd": odd, "bet_id": 57, "valor": f"Over {linha}"
            })

    if mandante and mandante.get("pct_marcou", 0) >= TAXA_MIN_ACERTO:
        odd, _ = get_odd_com_fallback(odds, 16, "Over 0.5")
        if odd:
            pernas.append({
                "nome": f"{home_nome} marca (+0.5 gols)",
                "taxa": mandante["pct_marcou"],
                "acertos": int(mandante["pct_marcou"] * mandante["n_jogos"]),
                "total": mandante["n_jogos"],
                "odd": odd, "bet_id": 16, "valor": "Over 0.5"
            })

    if visitante and visitante.get("pct_marcou", 0) >= TAXA_MIN_VIS_GOL:
        odd, _ = get_odd_com_fallback(odds, 17, "Over 0.5")
        if odd:
            pernas.append({
                "nome": f"{away_nome} marca (+0.5 gols)",
                "taxa": visitante["pct_marcou"],
                "acertos": int(visitante["pct_marcou"] * visitante["n_jogos"]),
                "total": visitante["n_jogos"],
                "odd": odd, "bet_id": 17, "valor": "Over 0.5"
            })

    odd_252 = get_odd(odds, BET365_ID, 252, "Yes")
    odd_300 = get_odd(odds, BET365_ID, 300, "Yes")
    odd_80  = get_odd(odds, BET365_ID, 80, "Over 3.5")

    if odd_252:
        pernas.append({"nome": "Ambos recebem cartão", "taxa": 0.75, "acertos": 0, "total": 0,
                       "odd": odd_252, "bet_id": 252, "valor": "Yes", "tipo": "ambos"})
    elif odd_300:
        pernas.append({"nome": "Ambos recebem 2+ cartões", "taxa": 0.70, "acertos": 0, "total": 0,
                       "odd": odd_300, "bet_id": 300, "valor": "Yes", "tipo": "ambos"})
    elif odd_80 and odd_80 >= ODD_MIN_PERNA:
        pernas.append({"nome": "Mais de 3,5 cartões", "taxa": 0.70, "acertos": 0, "total": 0,
                       "odd": odd_80, "bet_id": 80, "valor": "Over 3.5", "tipo": "ambos"})

    pernas_filtradas = []
    for p in pernas:
        if p.get("odd"):
            if p["odd"] >= ODD_MIN_PERNA:
                pernas_filtradas.append(p)
        else:
            pernas_filtradas.append(p)

    pernas_ordenadas = []
    if pernas_filtradas and "finalizações" in pernas_filtradas[0]["nome"]:
        pernas_ordenadas.append(pernas_filtradas[0])
        resto = pernas_filtradas[1:]
        resto.sort(key=lambda x: x.get("taxa", 0), reverse=True)
        pernas_ordenadas.extend(resto)
    else:
        pernas_filtradas.sort(key=lambda x: x.get("taxa", 0), reverse=True)
        pernas_ordenadas = pernas_filtradas

    com_odd = [p for p in pernas_ordenadas if p.get("odd")]
    if len(com_odd) < PERNAS_MIN:
        if len(pernas_ordenadas) >= PERNAS_MIN:
            return pernas_ordenadas[:PERNAS_MAX]
        return []
    return pernas_ordenadas[:PERNAS_MAX]

# ─────────────────────────────────────────────
# ENTRADA NORMAL — VALOR (9 MERCADOS)
# ─────────────────────────────────────────────

def buscar_valor_jogo_completo(odds):
    achados = []

    mercados = [
        (6, "Over 0.5", "Mais de 0,5 gols 1ºT"),
        (6, "Over 1.5", "Mais de 1,5 gols 1ºT"),
        (8, "Yes", "Ambas marcam"),
        (45, "Over 8.5", "Mais de 8,5 escanteios"),
        (45, "Over 9.5", "Mais de 9,5 escanteios"),
        (77, "Over 4.5", "Mais de 4,5 escanteios 1ºT"),
        (77, "Over 5.5", "Mais de 5,5 escanteios 1ºT"),
        (82, "Over 0.5", "Mandante +0,5 cartões"),
        (83, "Over 0.5", "Visitante +0,5 cartões"),
        (87, "Over 8.5", "Mais de 8,5 chutes ao gol"),
        (87, "Over 9.5", "Mais de 9,5 chutes ao gol"),
        (155, "Over 0.5", "Mais de 0,5 amarelos 1ºT"),
        (155, "Over 1.5", "Mais de 1,5 amarelos 1ºT"),
        (211, "Over 20.5", "Mais de 20,5 finalizações"),
        (211, "Over 25.5", "Mais de 25,5 finalizações"),
    ]

    for bet_id, valor, label in mercados:
        o365 = get_odd(odds, BET365_ID, bet_id, valor)
        if not o365 or o365 < ODD_MIN_PERNA:
            continue

        if bet_id == 8:
            if not validar_mercado_multicasas(odds, bet_id, valor, o365):
                continue

        media = media_outras_casas(odds, bet_id, valor)
        if not media:
            continue
        if o365 / media >= ODD_VALOR_MIN:
            odds_casas = {"Bet365": o365}
            opinnacle = get_odd(odds, PINNACLE_ID, bet_id, valor)
            if opinnacle:
                odds_casas["Pinnacle"] = opinnacle
            for bm_id in OUTRAS_CASAS:
                o = get_odd(odds, bm_id, bet_id, valor)
                if o:
                    nome_casa = {2: "Marathonbet", 7: "William Hill", 36: "BetVictor", 11: "1xBet"}.get(bm_id, f"Casa {bm_id}")
                    odds_casas[nome_casa] = o
            achados.append({
                "nome": label, "odd": o365, "media": media,
                "diff": int((o365 / media - 1) * 100),
                "bet_id": bet_id, "valor": valor, "odds_casas": odds_casas
            })
    return achados

def buscar_valor_jogo(odds):
    return buscar_valor_jogo_completo(odds)

# ─────────────────────────────────────────────
# PLACAR MÚLTIPLO
# ─────────────────────────────────────────────

def montar_placar_multipla(jogos, dados_por_jogo, horarios_ja_enviados):
    por_horario = defaultdict(list)
    for jogo in jogos:
        horario_brasilia = converter_horario_brasilia(jogo["fixture"]["date"])
        por_horario[horario_brasilia].append(jogo)

    for horario, lista in sorted(por_horario.items()):
        if horario in horarios_ja_enviados:
            continue
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

            resultado = escolher_placar_poisson(
                dados["mandante"], dados["visitante"], dados["placar_odds"],
                dados.get("poderoso", False), dados.get("fraco", False),
                dados.get("nivel_adv_mand", "medio"), dados.get("nivel_adv_vis", "medio"),
                dados.get("mandante_por_nivel", {}), dados.get("visitante_por_nivel", {})
            )

            if not resultado or not resultado[0]:
                continue

            placar, odd, prob, lambda_casa, lambda_fora, contexto = resultado

            candidatos.append({
                "home": jogo["teams"]["home"]["name"],
                "away": jogo["teams"]["away"]["name"],
                "placar": placar, "odd": odd, "prob": prob,
                "lambda_casa": lambda_casa, "lambda_fora": lambda_fora,
                "poderoso": dados.get("poderoso", False),
                "fraco": dados.get("fraco", False),
                "mandante": dados["mandante"],
                "visitante": dados["visitante"],
                "contexto": contexto,
                "horario": horario, "data": jogo["fixture"]["date"]
            })

        if len(candidatos) >= PLACAR_MIN_JOGOS:
            candidatos.sort(key=lambda x: x["odd"])
            return candidatos[:PLACAR_MAX_JOGOS]
    return None

# ─────────────────────────────────────────────
# FORMATADORES
# ─────────────────────────────────────────────

def fmt(v):
    return f"{v:.2f}"

def msg_aviso(liga, home, away, horario, texto="Padrão identificado. Calculando valor..."):
    return (f"⚽ <b>RD STATS | ANÁLISE EM ANDAMENTO</b>\n\n"
            f"🏆 {liga}\n🆚 {home} x {away}\n🕐 {horario}\n\n🔎 {texto}")

def msg_principal(liga, home, away, mandante, visitante, pernas, odd_final=None, todas_odds=False, usando_pinnacle=False):
    taxas = [p["taxa"] for p in pernas if p.get("taxa")]
    pct = int((sum(taxas) / len(taxas)) * 100) if taxas else 0
    nivel = "ALTA" if pct >= 90 else "MÉDIA" if pct >= 80 else "BAIXA"

    linhas = [
        "⚽ <b>RD STATS | VISITANTE REATIVO</b>", "",
        f"📅 {liga} | {home} x {away}", "",
        "━━━━━━━━━━━━━━━━━━━", "",
        "🎯 <b>POR QUE ESSA ENTRADA?</b>",
        f"O {away} é reativo fora: finaliza {visitante['media_fin_perdendo']:.1f} quando perde (média {visitante['media_fin']:.1f}).",
        f"O {home} é agressivo em casa: {mandante['media_fin']:.1f} fin/jogo e {mandante['media_esc']:.1f} esc/jogo.", "",
        f"📊 {home} abre placar: {int(mandante.get('pct_abriu_placar',0)*100)}%",
        f"📊 {away} leva 1º gol: {int(visitante.get('pct_levou_primeiro',0)*100)}%", "",
        "━━━━━━━━━━━━━━━━━━━", "", "📋 <b>APOSTAS SUGERIDAS</b>"
    ]
    for p in pernas:
    if p.get("total"):
        linha = f"✅{p['nome']}: {int(p['taxa']*100)}% ({p['acertos']}/{p['total']})"
    else:
        linha = f"✅{p['nome']}: {int(p['taxa']*100)}%"
    if p.get("odd"):
        linha += f" — @ {fmt(p['odd'])}"
    linhas.append(linha)

    linhas += ["", "━━━━━━━━━━━━━━━━━━━", ""]

    if odd_final and todas_odds:
        linhas.append(f"💰 <b>ODD FINAL:</b> {fmt(odd_final)}")
    elif odd_final:
        linhas.append(f"💰 <b>ODD FINAL:</b> {fmt(odd_final)} (parcial)")
        linhas.append("⚠️ Confira a odd na Bet365")
    else:
        linhas.append("⚠️ <b>Odd não disponível na Bet365</b>")
        linhas.append("Confira as odds antes de apostar")

    linhas += ["", f"📈 <b>Confiança:</b> {pct}% ({nivel})", "", "━━━━━━━━━━━━━━━━━━━", "", "🤖 <b>RD Stats</b> | Análise automatizada"]
    return "\n".join(linhas)

def msg_valor(liga, home, away, achados):
    linhas = ["⚽ <b>RD STATS | ENTRADA</b>", "", f"📅 {liga} | {home} x {away}", "", "━━━━━━━━━━━━━━━━━━━", "", "🎯 <b>APOSTA SUGERIDA</b>"]

    for a in achados[:PERNAS_MAX]:
        linhas.append(f"• {a['nome']} — @ {fmt(a['odd'])}")

    odd_final = 1.0
    for a in achados[:PERNAS_MAX]:
        odd_final *= a["odd"]

    linhas += ["", f"💰 <b>ODD FINAL:</b> {fmt(odd_final)}", "", "━━━━━━━━━━━━━━━━━━━", "", "📊 <b>DE ONDE VEM O VALOR</b>"]

    for a in achados[:PERNAS_MAX]:
        linhas.append(f"• {a['nome']}:")
        for casa, odd in list(a["odds_casas"].items())[:4]:
            if casa == "Bet365":
                linhas.append(f"   {casa}: @ {fmt(odd)} ← MELHOR")
            else:
                linhas.append(f"   {casa}: @ {fmt(odd)}")
        linhas.append(f"   Média: @ {fmt(a['media'])} (+{a['diff']}%)")
        linhas.append("")

    linhas += ["━━━━━━━━━━━━━━━━━━━", "", "🤖 <b>RD Stats</b> | Análise automatizada"]
    return "\n".join(linhas), odd_final

def msg_odd_errada(liga, home, away, alerta):
    linhas = [
        "💰 <b>RD STATS | ODD ERRADA</b>", "",
        f"📅 {liga} | {home} x {away}", "",
        "━━━━━━━━━━━━━━━━━━━", "",
        f"⚠️ Bet365 pagando +{alerta['diff']}% acima:", "",
        f"• {alerta['mercado']} ({alerta['valor']})",
        f"   Bet365: @ {fmt(alerta['bet365'])}"
    ]
    for casa, odd in alerta["odds_casas"].items():
        linhas.append(f"   {casa}: @ {fmt(odd)}")
    linhas.append(f"   Média: @ {fmt(alerta['media'])}")
    linhas += ["", "━━━━━━━━━━━━━━━━━━━", "", "🤖 <b>RD Stats</b>"]
    return "\n".join(linhas)

def msg_bingo(entradas):
    linhas = ["🎰 <b>RD STATS | BINGO DO DIA</b>", "",
              f"📅 {datetime.now(pytz.timezone('America/Sao_Paulo')).strftime('%d/%m/%Y')}",
              f"🎯 {len(entradas)} jogos com contexto forte", "", "━━━━━━━━━━━━━━━━━━━"]
    odd_final = 1.0
    for e in entradas:
        linhas.append(f"• {e['home']} x {e['away']} — {e['mercado']} @ {fmt(e['odd'])}")
        odd_final *= e["odd"]
    linhas += ["", "━━━━━━━━━━━━━━━━━━━", "", f"💰 <b>ODD FINAL:</b> {fmt(odd_final)} 🚨", "", "━━━━━━━━━━━━━━━━━━━", "", "🤖 <b>RD Stats</b>"]
    return "\n".join(linhas), odd_final

def msg_bingo_aviso(odd_final):
    return f"🚨🚨🚨 <b>BINGO DETECTADO</b> 🚨🚨🚨\n\nOdd final: <b>{fmt(odd_final)}</b>\n\n🤖 <b>RD Stats</b>"

def msg_placar(entradas, horario, data_iso):
    data_fmt = ""
    try:
        dt = datetime.fromisoformat(data_iso.replace("Z", "+00:00"))
        dt = dt.astimezone(pytz.timezone("America/Sao_Paulo"))
        data_fmt = dt.strftime("%d/%m/%Y")
    except:
        data_fmt = datetime.now(pytz.timezone("America/Sao_Paulo")).strftime("%d/%m/%Y")

    linhas = ["🎯 <b>RD STATS | RESULTADO CORRETO MÚLTIPLO</b>", "",
              f"🕐 Todos começam {horario}", f"📅 {data_fmt}", "", "━━━━━━━━━━━━━━━━━━━"]
    odd_final = 1.0
    for e in entradas:
        linhas.append(f"• {e['home']} x {e['away']} — {e['placar']} @ {fmt(e['odd'])}")
        linhas.append(f"   {e['contexto']}")
        linhas.append(f"   🎯 Probabilidade: {e['prob']*100:.2f}%")
        if e.get("poderoso") and e.get("fraco"):
            linhas.append(f"   🔥 {e['home']} PODEROSO x {e['away']} FRACO → goleada possível")
        linhas.append("")
        odd_final *= e["odd"]
    linhas += ["━━━━━━━━━━━━━━━━━━━", "", f"💰 <b>ODD FINAL:</b> {fmt(odd_final)} 🚨", "", "💡 Cashout viável após 60 min", "", "━━━━━━━━━━━━━━━━━━━", "", "🤖 <b>RD Stats</b>"]
    return "\n".join(linhas), odd_final

# ─────────────────────────────────────────────
# MODO CAÇADOR
# ─────────────────────────────────────────────

def cacar_odds():
    global CACADOR_ENVIADOS
    print(f"\n[CAÇADOR] Iniciando caçada...")
    jogos = get_jogos_do_dia()
    jogos_ns = [j for j in jogos if j["fixture"]["status"]["short"] == "NS"]
    print(f"[CAÇADOR] {len(jogos_ns)} jogos NS")

    achou = False
    alertas_enviados = 0

    for jogo in jogos_ns:
        if alertas_enviados >= 3:
            break

        fixture_id = jogo["fixture"]["id"]
        liga_nome = jogo["league"]["name"]
        home_nome = jogo["teams"]["home"]["name"]
        away_nome = jogo["teams"]["away"]["name"]
        chave = f"{fixture_id}-cacador"
        if chave in CACADOR_ENVIADOS:
            continue
        odds_data = get_odds_fixture(fixture_id)
        odds = extrair_odds(odds_data)
        if BET365_ID not in odds:
            continue

        alerta = detectar_odd_errada_focado(odds)
        if alerta:
            enviar_mensagem(msg_odd_errada(liga_nome, home_nome, away_nome, alerta))
            CACADOR_ENVIADOS.add(chave)
            salvar_cacador(CACADOR_ENVIADOS)
            print(f"[CAÇADOR] 💰 ODD ERRADA: {home_nome} x {away_nome} (+{alerta['diff']}%)")
            achou = True
            alertas_enviados += 1
            time.sleep(ESPERA_ENTRE_MSGS)

        time.sleep(0.5)

    if not achou:
        print("[CAÇADOR] Nenhuma oportunidade.")
    print("[CAÇADOR] Fim do ciclo.\n")

# ─────────────────────────────────────────────
# PROCESSAMENTO PRINCIPAL
# ─────────────────────────────────────────────

def processar_jogos(limite_jogos=None):
    global REQ_COUNT
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Iniciando análise principal...")
    print(f"Requisições usadas hoje: {REQ_COUNT}/{LIMITE_DIARIO}")
    if atingiu_alerta():
        print("⚠️ Alerta: limite próximo.")

    enviados = carregar_enviados()
    jogos = get_jogos_do_dia()
    print(f"Jogos do dia: {len(jogos)}")
    if limite_jogos:
        jogos = jogos[:limite_jogos]
        print(f"⚙️ Limitado a {limite_jogos} jogos")

    bingo_entradas = []
    bingo_ja = bingo_ja_enviado_hoje()
    horarios_placar_ja = carregar_placar_horarios()
    odd_errada_hoje = carregar_odd_errada_hoje()
    dados_por_jogo = {}
    msgs_canal = ler_ultimas_mensagens(50)

    entradas_enviadas = 0
    odd_errada_enviadas = 0

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
        horario_iso = jogo["fixture"]["date"]
        horario_fmt = formatar_data_jogo(horario_iso)

        print(f"\n→ {home_nome} x {away_nome} ({horario_fmt})")
        chave_tg = f"{home_nome} x {away_nome}"
        ja_no_canal = any(chave_tg in m and "VISITANTE REATIVO" in m for m in msgs_canal)

        jogos_casa = get_jogos_time(home_id, liga_id, casa=True)
        jogos_fora = get_jogos_time(away_id, liga_id, casa=False)
        if not jogos_casa or not jogos_fora:
            print(f"   ❌ Sem histórico")
            continue

        mandante = analisar_mandante(jogos_casa, home_id)
        visitante = analisar_visitante(jogos_fora, away_id)
        if not mandante or not visitante:
            print(f"   ❌ Erro análise")
            continue

        mandante["nome"] = home_nome
        visitante["nome"] = away_nome

        # Classifica estilos
        estilo_mand = classificar_estilo(mandante.get("media_gols_feitos", 0), mandante.get("media_gols_sofridos", 0))
        estilo_vis = classificar_estilo(visitante.get("media_gols_feitos", 0), visitante.get("media_gols_sofridos", 0))

        odds_data = get_odds_fixture(fixture_id)
        odds = extrair_odds(odds_data)
        tem_bet365 = BET365_ID in odds
        tem_pinnacle = PINNACLE_ID in odds

        if not tem_bet365 and not tem_pinnacle:
            print(f"   ❌ Sem Bet365 nem Pinnacle")
            continue
        if not tem_bet365:
            print(f"   ⚠️ Sem Bet365 — usando Pinnacle")

        print(f"   📊 Mandante: {mandante['n_jogos']}j | {estilo_mand}")
        print(f"   📊 Visitante: {visitante['n_jogos']}j | {estilo_vis}")

        # Sempre coleta dados pro placar
        if tem_bet365:
            placar_odds = {}
            if 10 in odds[BET365_ID]:
                for v, o in odds[BET365_ID][10]:
                    placar_odds[v] = o
            pos_mand = get_posicao_time(home_id, liga_id)
            pos_vis = get_posicao_time(away_id, liga_id)
            tot_times = total_times_liga(liga_id)
            poderoso, fraco = analisar_poder_fraqueza(mandante, visitante, pos_mand, pos_vis, tot_times)
            nivel_mand = classificar_nivel_time(home_id, liga_id)
            nivel_vis = classificar_nivel_time(away_id, liga_id)
            mandante_por_nivel = analisar_por_nivel(jogos_casa, home_id, liga_id, casa=True)
            visitante_por_nivel = analisar_por_nivel(jogos_fora, away_id, liga_id, casa=False)

            dados_por_jogo[fixture_id] = {
                "mandante": mandante, "visitante": visitante, "placar_odds": placar_odds,
                "poderoso": poderoso, "fraco": fraco,
                "nivel_adv_mand": nivel_vis, "nivel_adv_vis": nivel_mand,
                "mandante_por_nivel": mandante_por_nivel, "visitante_por_nivel": visitante_por_nivel,
                "pos_mand": pos_mand, "pos_vis": pos_vis, "total_times": tot_times,
                "estilo_mand": estilo_mand, "estilo_vis": estilo_vis
            }

        ja_enviado = str(fixture_id) in enviados
        if ja_enviado or ja_no_canal:
            print(f"   ⏭️ Já enviado")
            continue

        # ODD ERRADA
        if tem_bet365 and odd_errada_enviadas < 3:
            alerta = detectar_odd_errada_focado(odds)
            if alerta:
                chave = f"{fixture_id}-{alerta['bet_id']}-{alerta['valor']}"
                if chave not in odd_errada_hoje:
                    enviar_mensagem(msg_odd_errada(liga_nome, home_nome, away_nome, alerta))
                    odd_errada_hoje.add(chave)
                    salvar_odd_errada_hoje(odd_errada_hoje)
                    print(f"   💰 ODD ERRADA (+{alerta['diff']}%)")
                    odd_errada_enviadas += 1
                    time.sleep(ESPERA_ENTRE_MSGS)

        # ENTRADA PRINCIPAL
        liga_eh_brasileira = liga_id in LIGAS_VISITANTE_REATIVO
        if not liga_eh_brasileira:
            print(f"   ⏭️ Principal: liga não brasileira")
        elif mandante["n_jogos"] < MIN_JOGOS:
            print(f"   ⏭️ Principal: mandante {mandante['n_jogos']}j")
        elif visitante["n_jogos"] < MIN_JOGOS:
            print(f"   ⏭️ Principal: visitante {visitante['n_jogos']}j")
        elif mandante["media_fin"] < MANDANTE_MIN_FIN:
            print(f"   ⏭️ Principal: mandante não agressivo")
        elif mandante["media_esc"] < MANDANTE_MIN_ESC:
            print(f"   ⏭️ Principal: mandante não escanteia")
        elif not visitante["reativo"]:
            print(f"   ⏭️ Principal: visitante não reativo")
        else:
            print(f"   ✅ Principal: PADRÃO OK!")
            pernas = montar_principal(mandante, visitante, odds, home_nome, away_nome)
            print(f"   📊 Pernas: {len(pernas)}")
            if len(pernas) >= PERNAS_MIN:
                odd_final_principal = 1.0
                tem_odd = False
                todas_odds = True
                for p in pernas:
                    if p.get("odd"):
                        odd_final_principal *= p["odd"]
                        tem_odd = True
                    else:
                        todas_odds = False
                enviados.add(str(fixture_id))
                salvar_enviados(enviados)
                enviar_mensagem(msg_aviso(liga_nome, home_nome, away_nome, horario_fmt))
                time.sleep(ESPERA_ENTRE_MSGS)
                enviar_mensagem(msg_principal(liga_nome, home_nome, away_nome, mandante, visitante, pernas, odd_final_principal if tem_odd else None, todas_odds, not tem_bet365))
                print(f"   ✅ Principal ENVIADA")
                time.sleep(ESPERA_ENTRE_MSGS)
            else:
                print(f"   ⏭️ Principal: só {len(pernas)} perna(s)")

        # ENTRADA NORMAL
        valores = []
        if tem_bet365 and entradas_enviadas < 3:
            valores = buscar_valor_jogo_completo(odds)
        if valores:
            print(f"   💰 Normal: {len(valores)} mercado(s)")
            enviados.add(str(fixture_id))
            salvar_enviados(enviados)
            enviar_mensagem(msg_aviso(liga_nome, home_nome, away_nome, horario_fmt, "Procurando valor no mercado..."))
            time.sleep(ESPERA_ENTRE_MSGS)
            msg, odd_f = msg_valor(liga_nome, home_nome, away_nome, valores)
            enviar_mensagem(msg)
            print(f"   ✅ Normal ENVIADA (odd {odd_f:.2f})")
            entradas_enviadas += 1
            time.sleep(ESPERA_ENTRE_MSGS)

            if not bingo_ja:
                bingo_entradas.append({
                    "home": home_nome, "away": away_nome,
                    "mercado": valores[0]["nome"], "odd": valores[0]["odd"]
                })

        time.sleep(1)

    # BINGO
    print(f"\n📊 Bingo: {len(bingo_entradas)} jogo(s)")
    if not bingo_ja and len(bingo_entradas) >= BINGO_MIN_JOGOS:
        odd_bingo = 1.0
        for e in bingo_entradas:
            odd_bingo *= e["odd"]
        if odd_bingo >= ODD_BINGO_DIA:
            enviar_mensagem("🎰 <b>RD STATS | BINGO DO DIA</b>\n\nAnalisando os melhores jogos do dia...\n\n" f"🎯 {len(bingo_entradas)} jogos com contexto forte")
            time.sleep(ESPERA_ENTRE_MSGS)
            enviar_mensagem(msg_bingo_aviso(odd_bingo))
            time.sleep(ESPERA_ENTRE_MSGS)
            msg, _ = msg_bingo(bingo_entradas)
            enviar_mensagem(msg)
            marcar_bingo_enviado()
            print(f"   🎰 BINGO ENVIADO (odd {odd_bingo:.2f})")

    # PLACAR MÚLTIPLO
    print(f"\n🎯 Placar: horários já enviados hoje: {horarios_placar_ja}")
    multipla = montar_placar_multipla(jogos, dados_por_jogo, horarios_placar_ja)
    if multipla and len(multipla) >= PLACAR_MIN_JOGOS:
        horario = multipla[0]["horario"]
        data_iso = multipla[0]["data"]

        enviar_mensagem("🎯 <b>RD STATS | RESULTADO CORRETO MÚLTIPLO</b>\n\nAnalisando placares do dia...\n\n" f"🎯 {len(multipla)} jogos no horário {horario}")
        time.sleep(ESPERA_ENTRE_MSGS)
        msg, odd_p = msg_placar(multipla, horario, data_iso)
        enviar_mensagem(msg)

        horarios_placar_ja.add(horario)
        salvar_placar_horarios(horarios_placar_ja)
        print(f"   🎯 Placar múltiplo ENVIADO ({horario} | odd {odd_p:.2f})")
    else:
        print(f"   ⏭️ Placar: nenhum horário novo com 3+ jogos")

    salvar_req(REQ_COUNT)
    print(f"\n✅ Ciclo finalizado. Req: {REQ_COUNT}/{LIMITE_DIARIO}")

# ─────────────────────────────────────────────
# LOOP PRINCIPAL
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("🚀 RD Stats iniciado.")
    ultimo_principal = 0
    ultimo_cacador = 0
    while True:
        agora = datetime.now(pytz.timezone("America/Sao_Paulo"))
        ts = time.time()
        if ts - ultimo_cacador >= INTERVALO_CACADOR * 60:
            try:
                cacar_odds()
                ultimo_cacador = ts
            except Exception as e:
                print(f"Erro no caçador: {e}")
        if 8 <= agora.hour < 23:
            if ts - ultimo_principal >= INTERVALO_MIN * 60:
                try:
                    processar_jogos()
                    ultimo_principal = ts
                except Exception as e:
                    print(f"Erro no ciclo: {e}")
        time.sleep(60)
