import requests
import time
import os
from datetime import datetime, timedelta
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
LIGAS_VISITANTE_REATIVO = [71, 72]
SEASON = 2026

BET365_ID    = 8
OUTRAS_CASAS = [4, 32, 11, 7]

ARQUIVO_ENVIADOS = "jogos_enviados.json"
ARQUIVO_CACHE    = "cache_stats.json"
ARQUIVO_REQ      = "req_count.json"
ARQUIVO_BINGO    = "bingo_do_dia.json"
ARQUIVO_PLACAR   = "placar_do_dia.json"
ARQUIVO_ODD_ERR  = "odd_errada_hoje.json"
ARQUIVO_STANDINGS = "standings_cache.json"

LIMITE_DIARIO = 7000
ALERTA_LIMITE = 6000

MANDANTE_MIN_FIN   = 12
MANDANTE_MIN_ESC   = 4
TAXA_MIN_ACERTO    = 0.70
TAXA_MIN_VIS_GOL   = 0.85
MIN_JOGOS          = 10
MIN_JOGOS_PLACAR   = 5
PERNAS_MIN         = 2
PERNAS_MAX         = 4
ODD_MIN_PERNA      = 1.20
ODD_MIN_FINAL      = 1.50
ODD_BINGO_DIA      = 5.00
ODD_ERRADA_MIN     = 1.30
ODD_ERRADA_MIN_ODD = 1.50
ODD_VALOR_MIN      = 1.30

PODER_MEDIA_CASA    = 3.0
PODER_MAIOR_PLACAR  = 5
PODER_POSICAO_G4    = 4
FRAQUEZA_MEDIA_SOFRIDA_FORA = 2.5
FRAQUEZA_PCT_DERROTAS_FORA  = 0.70
FRAQUEZA_POSICAO_Z4 = 4

INTERVALO_MIN = 30
BINGO_MIN_JOGOS = 3
PLACAR_MIN_JOGOS = 3
PLACAR_MAX_JOGOS = 4
ESPERA_ENTRE_MSGS = 15

# ─────────────────────────────────────────────
# ANTI-DUPLICAÇÃO VIA TELEGRAM
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

# ─────────────────────────────────────────────
# BUSCAS
# ─────────────────────────────────────────────

def get_jogos_do_dia():
    hoje = datetime.now(pytz.timezone("America/Sao_Paulo")).strftime("%Y-%m-%d")
    amanha = (datetime.now(pytz.timezone("America/Sao_Paulo")) + timedelta(days=1)).strftime("%Y-%m-%d")
    jogos = []
    for liga in LIGAS:
        for data in [hoje, amanha]:
            resp = api_get("fixtures", {"date": data, "league": liga, "season": SEASON})
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
    derrotas = 0
    jogos_marcou = 0
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

ID_GOALS         = 5
ID_BTTS          = 8
ID_EXACT         = 10
ID_HOME_TOTAL    = 16
ID_AWAY_TOTAL    = 17
ID_CORNERS       = 45
ID_CARDS         = 80
ID_HOME_CARDS    = 82
ID_AWAY_CARDS    = 83
ID_HOME_CORN     = 57
ID_AWAY_CORN     = 58
ID_TOTAL_SHOT    = 211
ID_TOTAL_SOG     = 87
ID_AWAY_SHOTS    = 276
ID_BOTH_CARDS    = 252
ID_BOTH_2CARDS   = 300
# ─────────────────────────────────────────────
# ENTRADA PRINCIPAL — VISITANTE REATIVO
# ─────────────────────────────────────────────

def montar_principal(mandante, visitante, odds, home_nome, away_nome):
    pernas = []

    if not visitante:
        return []

    # FINALIZAÇÕES DO VISITANTE (OBRIGATÓRIA)
    linha_fin, t_fin, ac_fin = escolher_linha_mais_assertiva(
        visitante["lista_fin"],
        [7.5, 8.5, 9.5, 10.5, 11.5, 12.5],
        min_linha=7.5
    )
    if linha_fin is None:
        return []

    odd_fin = get_odd(odds, BET365_ID, ID_AWAY_SHOTS, f"Over {linha_fin}")
    pernas.append({
        "nome": f"{away_nome} +{linha_fin} finalizações",
        "taxa": t_fin, "acertos": ac_fin, "total": visitante["n_jogos"],
        "odd": odd_fin, "bet_id": ID_AWAY_SHOTS, "valor": f"Over {linha_fin}"
    })

    # CHUTES AO GOL DO VISITANTE (contexto)
    linha, t, ac = escolher_linha_mais_assertiva(
        visitante["lista_chutes_gol"],
        [1.5, 2.5, 3.5, 4.5],
        min_linha=1.5
    )
    if linha is not None:
        pernas.append({
            "nome": f"{away_nome} +{linha} chutes ao gol",
            "taxa": t, "acertos": ac, "total": visitante["n_jogos"],
            "odd": None, "bet_id": None, "valor": None
        })

    # CARTÕES DO VISITANTE
    linha, t, ac = escolher_linha_mais_assertiva(
        visitante["lista_cartoes"],
        [0.5, 1.5, 2.5],
        min_linha=0.5
    )
    if linha is not None:
        odd = get_odd(odds, BET365_ID, ID_AWAY_CARDS, f"Over {linha}")
        pernas.append({
            "nome": f"{away_nome} +{linha} cartões",
            "taxa": t, "acertos": ac, "total": visitante["n_jogos"],
            "odd": odd, "bet_id": ID_AWAY_CARDS, "valor": f"Over {linha}"
        })

    if mandante:
        # CARTÕES DO MANDANTE
        linha, t, ac = escolher_linha_mais_assertiva(
            mandante["lista_cart"],
            [0.5, 1.5, 2.5],
            min_linha=0.5
        )
        if linha is not None:
            odd = get_odd(odds, BET365_ID, ID_HOME_CARDS, f"Over {linha}")
            pernas.append({
                "nome": f"{home_nome} +{linha} cartões",
                "taxa": t, "acertos": ac, "total": mandante["n_jogos"],
                "odd": odd, "bet_id": ID_HOME_CARDS, "valor": f"Over {linha}"
            })

        # ESCANTEIOS DO MANDANTE
        linha, t, ac = escolher_linha_mais_assertiva(
            mandante["lista_esc"],
            [3.5, 4.5, 5.5, 6.5],
            min_linha=3.5
        )
        if linha is not None:
            odd = get_odd(odds, BET365_ID, ID_HOME_CORN, f"Over {linha}")
            pernas.append({
                "nome": f"{home_nome} +{linha} escanteios",
                "taxa": t, "acertos": ac, "total": mandante["n_jogos"],
                "odd": odd, "bet_id": ID_HOME_CORN, "valor": f"Over {linha}"
            })

    # MANDANTE OVER 0.5 GOLS
    if mandante and mandante.get("pct_marcou", 0) >= TAXA_MIN_ACERTO:
        odd = get_odd(odds, BET365_ID, ID_HOME_TOTAL, "Over 0.5")
        if odd:
            pernas.append({
                "nome": f"{home_nome} marca (+0.5 gols)",
                "taxa": mandante["pct_marcou"],
                "acertos": int(mandante["pct_marcou"] * mandante["n_jogos"]),
                "total": mandante["n_jogos"],
                "odd": odd, "bet_id": ID_HOME_TOTAL, "valor": "Over 0.5"
            })

    # VISITANTE OVER 0.5 GOLS (só se taxa ≥ 85%)
    if visitante and visitante.get("pct_marcou", 0) >= TAXA_MIN_VIS_GOL:
        odd = get_odd(odds, BET365_ID, ID_AWAY_TOTAL, "Over 0.5")
        if odd:
            pernas.append({
                "nome": f"{away_nome} marca (+0.5 gols)",
                "taxa": visitante["pct_marcou"],
                "acertos": int(visitante["pct_marcou"] * visitante["n_jogos"]),
                "total": visitante["n_jogos"],
                "odd": odd, "bet_id": ID_AWAY_TOTAL, "valor": "Over 0.5"
            })

    # AMBOS RECEBEM CARTÃO (252 → 300 → 80)
    odd_252 = get_odd(odds, BET365_ID, ID_BOTH_CARDS, "Yes")
    odd_300 = get_odd(odds, BET365_ID, ID_BOTH_2CARDS, "Yes")
    odd_80  = get_odd(odds, BET365_ID, ID_CARDS, "Over 3.5")

    if odd_252:
        pernas.append({
            "nome": "Ambos recebem cartão",
            "taxa": 0.75, "acertos": 0, "total": 0,
            "odd": odd_252, "bet_id": ID_BOTH_CARDS, "valor": "Yes",
            "tipo": "ambos"
        })
    elif odd_300:
        pernas.append({
            "nome": "Ambos recebem 2+ cartões",
            "taxa": 0.70, "acertos": 0, "total": 0,
            "odd": odd_300, "bet_id": ID_BOTH_2CARDS, "valor": "Yes",
            "tipo": "ambos"
        })
    elif odd_80 and odd_80 >= ODD_MIN_PERNA:
        pernas.append({
            "nome": "Mais de 3,5 cartões",
            "taxa": 0.70, "acertos": 0, "total": 0,
            "odd": odd_80, "bet_id": ID_CARDS, "valor": "Over 3.5",
            "tipo": "ambos"
        })

    # FILTRO DE ODD MÍNIMA POR PERNA
    pernas_filtradas = []
    for p in pernas:
        if p.get("odd"):
            if p["odd"] >= ODD_MIN_PERNA:
                pernas_filtradas.append(p)
        else:
            pernas_filtradas.append(p)

    # ORDENAR: finalização primeiro, resto por taxa
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
        # Sem 2 pernas com odd — mas ainda pode mandar sem odd
        # Retorna mesmo assim se tiver pelo menos 2 pernas no total
        if len(pernas_ordenadas) >= PERNAS_MIN:
            return pernas_ordenadas[:PERNAS_MAX]
        return []

    return pernas_ordenadas[:PERNAS_MAX]

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
# PLACAR MÚLTIPLO — COM PODER
# ─────────────────────────────────────────────

def eh_poderoso(mandante, posicao, total_times):
    if not mandante:
        return False
    media = mandante.get("media_gols_feitos", 0)
    maior = mandante.get("max_gols", 0)
    no_g4 = posicao is not None and posicao <= PODER_POSICAO_G4
    return (media >= PODER_MEDIA_CASA) or (maior >= PODER_MAIOR_PLACAR) or no_g4

def eh_fraco(visitante, posicao, total_times):
    if not visitante:
        return False
    sofre = visitante.get("media_gols_sofridos", 0)
    pct_der = visitante.get("pct_derrotas", 0)
    no_z4 = posicao is not None and posicao > (total_times - FRAQUEZA_POSICAO_Z4)
    return (sofre >= FRAQUEZA_MEDIA_SOFRIDA_FORA) or (pct_der >= FRAQUEZA_PCT_DERROTAS_FORA) or no_z4

def escolher_placar_com_contexto(mandante, visitante, placar_odds, pos_mand=None, pos_vis=None, total_times=20):
    if not mandante or not visitante or not placar_odds:
        return None, None, None

    # DESCARTA se não tem stats
    if mandante.get("max_gols", 0) == 0 and mandante.get("media_gols_feitos", 0) == 0:
        return None, None, None
    if visitante.get("max_gols", 0) == 0 and visitante.get("media_gols_feitos", 0) == 0:
        return None, None, None

    gols_casa = mandante.get("media_gols_feitos", 1.5)
    gols_fora = visitante.get("media_gols_feitos", 1.0)
    min_casa = mandante.get("min_gols", 0)
    max_casa = mandante.get("max_gols", 3)
    min_fora = visitante.get("min_gols", 0)
    max_fora = visitante.get("max_gols", 3)

    poderoso = eh_poderoso(mandante, pos_mand, total_times)
    fraco = eh_fraco(visitante, pos_vis, total_times)

    if poderoso and fraco:
        candidatos = ["4:0", "5:0", "3:0", "4:1", "5:1", "6:0"]
    elif poderoso:
        candidatos = ["3:0", "3:1", "2:0", "2:1", "4:1"]
    elif fraco:
        candidatos = ["2:0", "3:0", "2:1", "1:0"]
    else:
        candidatos = ["2:1", "1:0", "1:1", "2:0", "0:0"]

    placar = None
    for c in candidatos:
        if c in placar_odds and 6.00 <= placar_odds[c] <= 15.00:
            placar = c
            break

    if not placar:
        for c, o in placar_odds.items():
            if 6.00 <= o <= 15.00:
                placar = c
                break

    if not placar:
        return None, None, None

    motivo = f"{mandante.get('nome','Mandante')} (casa): {min_casa} a {max_casa} gols/jogo"
    if mandante.get("sempre_marca"):
        motivo += f" | sempre marca ({mandante['n_jogos']}/{mandante['n_jogos']})"

    motivo += f"\n      {visitante.get('nome','Visitante')} (fora): {min_fora} a {max_fora} gols/jogo"

    if fraco and poderoso:
        motivo += " | 💥 PODEROSO x FRACO → goleada possível"
    elif poderoso:
        motivo += " | ⚡ mandante poderoso em casa"
    elif fraco:
        motivo += " | ⚠️ visitante fraco fora"

    if gols_fora >= 0.7 and int(placar.split(":")[1]) == 0 and "4:1" not in candidatos[:2]:
        placar_alt = f"{placar.split(':')[0]}:1"
        if placar_alt in placar_odds and 6.00 <= placar_odds[placar_alt] <= 15.00:
            placar = placar_alt
            motivo += " | visitante marca fora → ajustado com gol dele"

    return placar, placar_odds[placar], motivo

def montar_placar_multipla(jogos, dados_por_jogo):
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
                dados["mandante"], dados["visitante"], dados["placar_odds"],
                pos_mand=dados.get("pos_mand"), pos_vis=dados.get("pos_vis"),
                total_times=dados.get("total_times", 20)
            )
            if placar and odd:
                candidatos.append({
                    "home": jogo["teams"]["home"]["name"],
                    "away": jogo["teams"]["away"]["name"],
                    "placar": placar,
                    "odd": odd,
                    "motivo": motivo,
                    "horario": horario,
                    "data": jogo["fixture"]["date"]
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
    return (
        f"⚽ <b>RD STATS | ANÁLISE EM ANDAMENTO</b>\n\n"
        f"🏆 {liga}\n"
        f"🆚 {home} x {away}\n"
        f"🕐 {horario}\n\n"
        f"🔎 {texto}"
    )

def msg_principal(liga, home, away, mandante, visitante, pernas, odd_final=None):
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
        if p.get("total"):
            linha = f"• {p['nome']}: {int(p['taxa']*100)}% ({p['acertos']}/{p['total']})"
        else:
            linha = f"• {p['nome']}: {int(p['taxa']*100)}%"
        if p.get("odd"):
            linha += f" — @ {fmt(p['odd'])}"
        linhas.append(linha)

    taxas = [p["taxa"] for p in pernas if p.get("taxa")]
    pct = int((sum(taxas) / len(taxas)) * 100) if taxas else 0
    nivel = "ALTA" if pct >= 90 else "MÉDIA" if pct >= 80 else "BAIXA"

    linhas += [
        "",
        "━━━━━━━━━━━━━━━━━━━",
        ""
    ]

    if odd_final:
        linhas.append(f"💰 <b>ODD FINAL:</b> {fmt(odd_final)}")
    else:
        linhas.append("⚠️ <b>Odd não disponível ainda na Bet365</b>")
        linhas.append("Confira as odds antes de apostar")

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

def msg_placar(entradas, horario, data_iso):
    data_fmt = ""
    try:
        dt = datetime.fromisoformat(data_iso.replace("Z", "+00:00"))
        dt = dt.astimezone(pytz.timezone("America/Sao_Paulo"))
        data_fmt = dt.strftime("%d/%m/%Y")
    except:
        data_fmt = datetime.now(pytz.timezone("America/Sao_Paulo")).strftime("%d/%m/%Y")

    linhas = [
        "🎯 <b>RD STATS | RESULTADO CORRETO MÚLTIPLO</b>",
        "",
        f"🕐 Todos começam {horario[11:16]}",
        f"📅 {data_fmt}",
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
# PROCESSAMENTO
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

    msgs_canal = ler_ultimas_mensagens(50)

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
            print(f"   ❌ Sem histórico: casa={len(jogos_casa)} | fora={len(jogos_fora)}")
            continue

        mandante = analisar_mandante(jogos_casa, home_id)
        visitante = analisar_visitante(jogos_fora, away_id)

        if not mandante or not visitante:
            print(f"   ❌ Erro ao analisar histórico")
            continue

        mandante["nome"] = home_nome
        visitante["nome"] = away_nome

        odds_data = get_odds_fixture(fixture_id)
        odds = extrair_odds(odds_data)

        if BET365_ID not in odds:
            print(f"   ❌ Sem odds da Bet365")
            continue

        print(f"   📊 Mandante: {mandante['n_jogos']} jogos | {mandante['media_fin']:.1f} fin | {mandante['media_esc']:.1f} esc")
        print(f"   📊 Visitante: {visitante['n_jogos']} jogos | perdendo={visitante['media_fin_perdendo']:.1f} x geral={visitante['media_fin']:.1f}")

        if not placar_ja:
            placar_odds = {}
            if ID_EXACT in odds[BET365_ID]:
                for v, o in odds[BET365_ID][ID_EXACT]:
                    placar_odds[v] = o

            pos_mand = get_posicao_time(home_id, liga_id)
            pos_vis = get_posicao_time(away_id, liga_id)
            tot_times = total_times_liga(liga_id)

            dados_por_jogo[fixture_id] = {
                "mandante": mandante,
                "visitante": visitante,
                "placar_odds": placar_odds,
                "pos_mand": pos_mand,
                "pos_vis": pos_vis,
                "total_times": tot_times
            }

        ja_enviado = str(fixture_id) in enviados
        if ja_enviado or ja_no_canal:
            print(f"   ⏭️ Já enviado anteriormente")
            continue

        # ─── 1. ODD ERRADA ───
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
            print(f"   💰 ODD ERRADA enviada ({len(alertas)} alerta(s))")
            time.sleep(ESPERA_ENTRE_MSGS)
        else:
            print(f"   ⏭️ Odd errada: nenhuma detectada")

        # ─── 2. ENTRADA PRINCIPAL ───
        achou_principal = False
        liga_eh_brasileira = liga_id in LIGAS_VISITANTE_REATIVO

        if not liga_eh_brasileira:
            print(f"   ⏭️ Principal: liga {liga_id} não é brasileira (só 71/72)")
        elif mandante["n_jogos"] < MIN_JOGOS:
            print(f"   ⏭️ Principal: mandante tem {mandante['n_jogos']} jogos (mín {MIN_JOGOS})")
        elif visitante["n_jogos"] < MIN_JOGOS:
            print(f"   ⏭️ Principal: visitante tem {visitante['n_jogos']} jogos (mín {MIN_JOGOS})")
        elif mandante["media_fin"] < MANDANTE_MIN_FIN:
            print(f"   ⏭️ Principal: mandante não agressivo ({mandante['media_fin']:.1f} < {MANDANTE_MIN_FIN})")
        elif mandante["media_esc"] < MANDANTE_MIN_ESC:
            print(f"   ⏭️ Principal: mandante não escanteia ({mandante['media_esc']:.1f} < {MANDANTE_MIN_ESC})")
        elif not visitante["reativo"]:
            print(f"   ⏭️ Principal: visitante NÃO reativo")
        else:
            print(f"   ✅ Principal: PADRÃO OK! Montando entrada...")
            pernas = montar_principal(mandante, visitante, odds, home_nome, away_nome)
            print(f"   📊 Pernas montadas: {len(pernas)}")

            if len(pernas) >= PERNAS_MIN:
                odd_final_principal = 1.0
                tem_odd = False
                for p in pernas:
                    if p.get("odd"):
                        odd_final_principal *= p["odd"]
                        tem_odd = True

                achou_principal = True
                enviar_mensagem(msg_aviso(liga_nome, home_nome, away_nome, horario_fmt))
                time.sleep(ESPERA_ENTRE_MSGS)
                enviar_mensagem(msg_principal(liga_nome, home_nome, away_nome, mandante, visitante, pernas, odd_final_principal if tem_odd else None))

                if tem_odd:
                    print(f"   ✅ Principal ENVIADA ({len(pernas)} pernas | odd {odd_final_principal:.2f})")
                else:
                    print(f"   ✅ Principal ENVIADA SEM ODD ({len(pernas)} pernas)")
                time.sleep(ESPERA_ENTRE_MSGS)
            else:
                print(f"   ⏭️ Principal: só {len(pernas)} perna(s) (mín {PERNAS_MIN})")

        # ─── 3. ENTRADA NORMAL ───
        valores = buscar_valor_jogo(odds)
        if valores:
            print(f"   💰 Normal: {len(valores)} mercado(s) com valor")
            enviar_mensagem(msg_aviso(liga_nome, home_nome, away_nome, horario_fmt, "Procurando valor no mercado..."))
            time.sleep(ESPERA_ENTRE_MSGS)
            msg, odd_f = msg_valor(liga_nome, home_nome, away_nome, valores)
            enviar_mensagem(msg)
            print(f"   ✅ Normal ENVIADA (odd {odd_f:.2f})")
            time.sleep(ESPERA_ENTRE_MSGS)

            if not bingo_ja:
                bingo_entradas.append({
                    "home": home_nome, "away": away_nome,
                    "mercado": valores[0]["nome"], "odd": valores[0]["odd"]
                })
        else:
            print(f"   ⏭️ Normal: sem valor detectado")

        if achou_principal or valores:
            enviados.add(str(fixture_id))
            salvar_enviados(enviados)

        time.sleep(1)

    # ─── 4. BINGO DO DIA ───
    print(f"\n📊 Total de jogos com valor no bingo: {len(bingo_entradas)}")
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
            print(f"   🎰 BINGO DO DIA ENVIADO (odd {odd_bingo:.2f})")
        else:
            print(f"   ⏭️ Bingo: odd final {odd_bingo:.2f} < {ODD_BINGO_DIA}")
    elif bingo_ja:
        print(f"   ⏭️ Bingo: já enviado hoje")
    else:
        print(f"   ⏭️ Bingo: só {len(bingo_entradas)} jogo(s) (mín {BINGO_MIN_JOGOS})")

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
            data_iso = multipla[0]["data"]
            msg, odd_p = msg_placar(multipla, horario, data_iso)
            enviar_mensagem(msg)
            marcar_placar_enviado()
            print(f"   🎯 Placar múltiplo ENVIADO (odd {odd_p:.2f})")
        else:
            print(f"   ⏭️ Placar múltiplo: sem jogos suficientes")
    else:
        print(f"   ⏭️ Placar múltiplo: já enviado hoje")

    salvar_req(REQ_COUNT)
    print(f"\n✅ Ciclo finalizado. Req: {REQ_COUNT}/{LIMITE_DIARIO}")

# ─────────────────────────────────────────────
# LOOP
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
