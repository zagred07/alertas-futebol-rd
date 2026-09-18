import requests
import time
import os
from datetime import datetime
import pytz
import json
import statistics

API_KEY   = os.getenv("API_FOOTBALL_KEY")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

BASE_URL = "https://v3.football.api-sports.io"
HEADERS  = {"x-apisports-key": API_KEY}

LIGAS = [71, 72, 39, 140, 135, 78, 61, 40]
SEASON = 2026

BET365_ID    = 8
PINNACLE_ID  = 4
OUTRAS_CASAS = [4, 32, 11, 7]

ARQUIVO_ENVIADOS = "jogos_enviados.json"

MANDANTE_MIN_FIN   = 12
MANDANTE_MIN_ESC   = 4
TAXA_MIN_ACERTO    = 0.70
PERNAS_MIN         = 2
PERNAS_MAX         = 4
ODD_MIN_FINAL      = 1.50
ODD_BINGO          = 5.00
ODD_ERRADA_MIN     = 1.30
ODD_ERRADA_MIN_ODD = 1.50

INTERVALO_MIN = 30

def carregar_enviados():
    if os.path.exists(ARQUIVO_ENVIADOS):
        try:
            with open(ARQUIVO_ENVIADOS, "r") as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def salvar_enviados(enviados):
    with open(ARQUIVO_ENVIADOS, "w") as f:
        json.dump(list(enviados), f)

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

def api_get(endpoint, params=None):
    url = f"{BASE_URL}/{endpoint}"
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=20)
        if r.status_code != 200:
            return None
        return r.json().get("response", [])
    except Exception as e:
        print(f"Erro API {endpoint}: {e}")
        return None

def get_jogos_do_dia():
    hoje = datetime.now(pytz.timezone("America/Sao_Paulo")).strftime("%Y-%m-%d")
    jogos = []
    for liga in LIGAS:
        resp = api_get("fixtures", {"date": hoje, "league": liga, "season": SEASON})
        if resp:
            jogos.extend(resp)
        time.sleep(0.3)
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

def get_stats_fixture(fixture_id):
    resp = api_get("fixtures/statistics", {"fixture": fixture_id})
    return resp if resp else []

def get_odds_fixture(fixture_id):
    resp = api_get("odds", {"fixture": fixture_id})
    return resp if resp else []

def extrair_stats_jogo(stats, team_id):
    res = {"finalizacoes": 0, "chutes_gol": 0, "cartoes": 0, "escanteios": 0, "gols": 0}
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

def get_gols_jogo(jogo, team_id):
    if jogo["teams"]["home"]["id"] == team_id:
        return jogo["goals"]["home"] or 0
    else:
        return jogo["goals"]["away"] or 0

def get_gols_sofridos(jogo, team_id):
    if jogo["teams"]["home"]["id"] == team_id:
        return jogo["goals"]["away"] or 0
    else:
        return jogo["goals"]["home"] or 0

def analisar_mandante(jogos, team_id):
    if not jogos:
        return None
    finalizacoes, escanteios, cartoes = [], [], []
    for j in jogos:
        stats = get_stats_fixture(j["fixture"]["id"])
        s = extrair_stats_jogo(stats, team_id)
        finalizacoes.append(s["finalizacoes"])
        escanteios.append(s["escanteios"])
        cartoes.append(s["cartoes"])
        time.sleep(0.2)
    if not finalizacoes:
        return None
    return {
        "n_jogos": len(finalizacoes),
        "media_fin": statistics.mean(finalizacoes),
        "media_esc": statistics.mean(escanteios),
        "media_cart": statistics.mean(cartoes) if cartoes else 0,
        "lista_fin": finalizacoes,
        "lista_esc": escanteios,
        "lista_cart": cartoes,
    }

def mandante_e_agressivo(m):
    if not m:
        return False
    return (m["media_fin"] >= MANDANTE_MIN_FIN and
            m["media_esc"] >= MANDANTE_MIN_ESC)

def analisar_visitante(jogos, team_id):
    if not jogos:
        return None
    finalizacoes, chutes_gol, cartoes = [], [], []
    jogos_vitoria, jogos_empate, jogos_derrota = [], [], []

    for j in jogos:
        stats = get_stats_fixture(j["fixture"]["id"])
        s = extrair_stats_jogo(stats, team_id)
        finalizacoes.append(s["finalizacoes"])
        chutes_gol.append(s["chutes_gol"])
        cartoes.append(s["cartoes"])

        gols_pro = get_gols_jogo(j, team_id)
        gols_contra = get_gols_sofridos(j, team_id)
        if gols_pro > gols_contra:
            jogos_vitoria.append(s["finalizacoes"])
        elif gols_pro < gols_contra:
            jogos_derrota.append(s["finalizacoes"])
        else:
            jogos_empate.append(s["finalizacoes"])
        time.sleep(0.2)

    if not finalizacoes:
        return None

    media_geral = statistics.mean(finalizacoes)
    media_perdendo = statistics.mean(jogos_derrota) if jogos_derrota else 0
    media_ganhando = statistics.mean(jogos_vitoria) if jogos_vitoria else 0
    media_empatando = statistics.mean(jogos_empate) if jogos_empate else 0

    reativo = media_perdendo > media_geral if jogos_derrota else False

    return {
        "n_jogos": len(finalizacoes),
        "media_fin": media_geral,
        "media_fin_perdendo": media_perdendo,
        "media_fin_ganhando": media_ganhando,
        "media_fin_empatando": media_empatando,
        "media_cart": statistics.mean(cartoes) if cartoes else 0,
        "n_derrotas": len(jogos_derrota),
        "n_vitorias": len(jogos_vitoria),
        "n_empates": len(jogos_empate),
        "reativo": reativo,
        "lista_fin": finalizacoes,
        "lista_chutes_gol": chutes_gol,
        "lista_cartoes": cartoes,
    }

def taxa_acerto(lista, linha):
    if not lista:
        return 0
    return sum(1 for v in lista if v >= linha) / len(lista)

def extrair_odds(odds_data):
    resultado = {}
    if not odds_data:
        return resultado
    for item in odds_data:
        for bm in item.get("bookmakers", []):
            bm_id = bm.get("id")
            if bm_id not in resultado:
                resultado[bm_id] = {}
            for bet in bm.get("bets", []):
                bet_id = bet.get("id")
                valores = [(v.get("value"), float(v.get("odd", 0))) for v in bet.get("values", [])]
                resultado[bm_id][bet_id] = valores
    return resultado

def get_odd(odds_dict, bm_id, bet_id, valor_alvo):
    if bm_id not in odds_dict:
        return None
    if bet_id not in odds_dict[bm_id]:
        return None
    for valor, odd in odds_dict[bm_id][bet_id]:
        if valor == valor_alvo:
            return odd
    return None

def media_outras_casas(odds_dict, bet_id, valor_alvo):
    odds = []
    for bm_id in OUTRAS_CASAS:
        o = get_odd(odds_dict, bm_id, bet_id, valor_alvo)
        if o:
            odds.append(o)
    if not odds:
        return None
    return statistics.mean(odds)

def detectar_odd_errada(odds_dict, bet_id, valor_alvo, nome_mercado):
    odd_bet365 = get_odd(odds_dict, BET365_ID, bet_id, valor_alvo)
    if not odd_bet365 or odd_bet365 < ODD_ERRADA_MIN_ODD:
        return None
    media = media_outras_casas(odds_dict, bet_id, valor_alvo)
    if not media or media <= 0:
        return None
    if odd_bet365 / media >= ODD_ERRADA_MIN:
        return {
            "mercado": nome_mercado,
            "valor": valor_alvo,
            "bet365": odd_bet365,
            "media": media,
            "diff_pct": int((odd_bet365 / media - 1) * 100)
        }
    return None

BET_GOALS        = 5
BET_BTTS         = 8
BET_CORNERS      = 45
BET_CARDS        = 80
BET_HOME_CARDS   = 82
BET_AWAY_CARDS   = 83
BET_SHOTS_ON_TGT = 87
BET_TOTAL_SHOTS  = 211

def montar_pernas(mandante, visitante, odds_dict):
    pernas = []

    if visitante:
        for linha in [8.5, 7.5]:
            taxa = taxa_acerto(visitante["lista_fin"], linha)
            if taxa >= TAXA_MIN_ACERTO:
                pernas.append({
                    "nome": f"Visitante +{linha} finalizações",
                    "taxa": taxa,
                    "odd": None,
                    "tipo": "contexto"
                })
                break

    if visitante:
        for linha in [2.5, 1.5]:
            taxa = taxa_acerto(visitante["lista_chutes_gol"], linha)
            if taxa >= TAXA_MIN_ACERTO:
                pernas.append({
                    "nome": f"Visitante +{linha} chutes ao gol",
                    "taxa": taxa,
                    "odd": None,
                    "tipo": "contexto"
                })
                break

    if mandante:
        for linha in [1.5, 0.5]:
            taxa = taxa_acerto(mandante["lista_cart"], linha)
            if taxa >= TAXA_MIN_ACERTO:
                valor = f"Over {linha}"
                odd = get_odd(odds_dict, BET365_ID, BET_HOME_CARDS, valor)
                if odd:
                    pernas.append({
                        "nome": f"Mandante Over {linha} cartões",
                        "taxa": taxa,
                        "odd": odd,
                        "bet_id": BET_HOME_CARDS,
                        "valor": valor,
                        "tipo": "odd"
                    })
                break

    if mandante:
        for linha in [4.5, 3.5]:
            taxa = taxa_acerto(mandante["lista_esc"], linha)
            if taxa >= TAXA_MIN_ACERTO:
                valor = f"Over {linha}"
                odd = get_odd(odds_dict, BET365_ID, BET_CORNERS, valor)
                if not odd:
                    odd = get_odd(odds_dict, BET365_ID, 57, valor)
                if odd:
                    pernas.append({
                        "nome": f"Mandante Over {linha} escanteios",
                        "taxa": taxa,
                        "odd": odd,
                        "bet_id": BET_CORNERS,
                        "valor": valor,
                        "tipo": "odd"
                    })
                break

    if mandante and visitante:
        media_cart_total = mandante["media_cart"] + visitante["media_cart"]
        if media_cart_total >= 3.5:
            valor = "Over 3.5"
            odd = get_odd(odds_dict, BET365_ID, BET_CARDS, valor)
            if odd:
                pernas.append({
                    "nome": "Total Over 3,5 cartões",
                    "taxa": 0.75,
                    "odd": odd,
                    "bet_id": BET_CARDS,
                    "valor": valor,
                    "tipo": "odd"
                })

    if mandante and visitante:
        if mandante["media_fin"] >= 12 and visitante["media_fin"] >= 8:
            odd = get_odd(odds_dict, BET365_ID, BET_BTTS, "Yes")
            if odd:
                pernas.append({
                    "nome": "Ambas marcam",
                    "taxa": 0.70,
                    "odd": odd,
                    "bet_id": BET_BTTS,
                    "valor": "Yes",
                    "tipo": "odd"
                })

    return pernas

def montar_entrada_final(pernas):
    com_odd = [p for p in pernas if p.get("odd")]
    contexto = [p for p in pernas if not p.get("odd")]

    if not com_odd:
        return None, None, contexto

    selecionadas = com_odd[:PERNAS_MAX]

    odd_final = 1.0
    for p in selecionadas:
        odd_final *= p["odd"]

    if odd_final < ODD_MIN_FINAL:
        extra = next((p for p in com_odd if p["nome"] not in [s["nome"] for s in selecionadas]), None)
        if extra:
            selecionadas.append(extra)
            odd_final *= extra["odd"]

    return selecionadas, odd_final, contexto

def fmt_moeda(v):
    return f"{v:.2f}"

def montar_msg_analise(liga, home, away):
    return (
        f"⚽ <b>RD STATS | ANÁLISE EM ANDAMENTO</b>\n\n"
        f"🏆 {liga}\n"
        f"🆚 {home} x {away}\n\n"
        f"🔎 Padrão identificado. Calculando valor..."
    )

def montar_msg_bingo(odd_final):
    return (
        f"🚨🚨🚨 <b>BINGO DETECTADO</b> 🚨🚨🚨\n\n"
        f"Essa entrada tá com odd acima de {ODD_BINGO:.2f}!\n"
        f"Odd final: <b>{fmt_moeda(odd_final)}</b>\n\n"
        f"Cada um sabe o que faz com a informação. 🚀"
    )

def montar_msg_odd_errada(liga, home, away, alertas):
    linhas = [
        "💰 <b>RD STATS | ODD ERRADA NA BET365</b>",
        "",
        f"🏆 {liga}",
        f"🆚 {home} x {away}",
        "",
        "⚠️ <b>Bet365 pagando acima do mercado:</b>",
        ""
    ]
    for a in alertas:
        linhas.append(f"• {a['mercado']} ({a['valor']})")
        linhas.append(f"   Bet365: @ {fmt_moeda(a['bet365'])}")
        linhas.append(f"   Média outras casas: @ {fmt_moeda(a['media'])}")
        linhas.append(f"   Diferença: +{a['diff_pct']}%")
        linhas.append("")
    linhas.append("💡 Valor detectado. Aproveita.")
    return "\n".join(linhas)

def montar_msg_entrada(liga, home, away, pernas_odd, pernas_ctx, odd_final, nivel, pct):
    linhas = [
        "⚽ <b>RD STATS | ENTRADA</b>",
        "",
        f"🏆 {liga}",
        f"🆚 {home} x {away}",
        "",
        "━━━━━━━━━━━━━━━━━━━",
        "",
        "📊 <b>ANÁLISE</b>"
    ]
    if pernas_ctx:
        for p in pernas_ctx:
            linhas.append(f"• {p['nome']}: {int(p['taxa']*100)}%")
    else:
        linhas.append("• Padrão visitante reativo confirmado")

    linhas += [
        "",
        "━━━━━━━━━━━━━━━━━━━",
        "",
        "🎯 <b>ENTRADAS</b>"
    ]
    for p in pernas_odd:
        linhas.append(f"• {p['nome']} — @ {fmt_moeda(p['odd'])}")

    linhas += [
        "",
        "━━━━━━━━━━━━━━━━━━━",
        "",
        f"💰 <b>ODD FINAL:</b> {fmt_moeda(odd_final)}",
        f"📈 <b>Confiança:</b> {pct}% ({nivel})",
        "",
        "━━━━━━━━━━━━━━━━━━━",
        "",
        "Cada um sabe o que faz com a informação. 🚀"
    ]
    return "\n".join(linhas)

def calcular_confianca(pernas):
    taxas = [p["taxa"] for p in pernas if p.get("taxa")]
    if not taxas:
        return 0, "BAIXA"
    media = sum(taxas) / len(taxas)
    pct = int(media * 100)
    if media >= 0.90:
        return pct, "ALTA"
    elif media >= 0.80:
        return pct, "MÉDIA"
    return pct, "BAIXA"

def processar_jogos():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Iniciando análise...")
    enviados = carregar_enviados()
    jogos = get_jogos_do_dia()
    print(f"Jogos do dia: {len(jogos)}")

    for jogo in jogos:
        if jogo["fixture"]["status"]["short"] != "NS":
            continue

        fixture_id = jogo["fixture"]["id"]
        if str(fixture_id) in enviados:
            continue

        liga_id   = jogo["league"]["id"]
        liga_nome = jogo["league"]["name"]
        home_id   = jogo["teams"]["home"]["id"]
        away_id   = jogo["teams"]["away"]["id"]
        home_name = jogo["teams"]["home"]["name"]
        away_name = jogo["teams"]["away"]["name"]

        print(f"\n→ Analisando {home_name} x {away_name}...")

        jogos_casa = get_jogos_time(home_id, liga_id, casa=True)
        jogos_fora = get_jogos_time(away_id, liga_id, casa=False)

        if not jogos_casa or not jogos_fora:
            print("   Sem histórico suficiente.")
            continue

        mandante = analisar_mandante(jogos_casa, home_id)
        visitante = analisar_visitante(jogos_fora, away_id)

        if not mandante or not visitante:
            print("   Erro ao analisar.")
            continue

        if not mandante_e_agressivo(mandante):
            print(f"   Mandante não agressivo (fin {mandante['media_fin']:.1f}, esc {mandante['media_esc']:.1f})")
            continue

        if not visitante["reativo"]:
            print(f"   Visitante não reativo (perdendo {visitante['media_fin_perdendo']:.1f} x geral {visitante['media_fin']:.1f})")
            continue

        print(f"   PADRAO OK! Mandante agressivo + Visitante reativo")

        odds_data = get_odds_fixture(fixture_id)
        odds_dict = extrair_odds(odds_data)

        if BET365_ID not in odds_dict:
            print("   Sem odds da Bet365.")
            continue

        pernas = montar_pernas(mandante, visitante, odds_dict)
        selecionadas, odd_final, contexto = montar_entrada_final(pernas)

        if not selecionadas or not odd_final:
            print("   Sem pernas com odd.")
            continue

        if odd_final < ODD_MIN_FINAL:
            print(f"   Odd final baixa: {odd_final:.2f}")
            continue

        enviados.add(str(fixture_id))
        salvar_enviados(enviados)

        enviar_mensagem(montar_msg_analise(liga_nome, home_name, away_name))
        time.sleep(5)

        if odd_final >= ODD_BINGO:
            enviar_mensagem(montar_msg_bingo(odd_final))
            time.sleep(3)

        alertas_odd = []
        for p in selecionadas:
            if p.get("bet_id") and p.get("valor"):
                a = detectar_odd_errada(odds_dict, p["bet_id"], p["valor"], p["nome"])
                if a:
                    alertas_odd.append(a)
        if alertas_odd:
            enviar_mensagem(montar_msg_odd_errada(liga_nome, home_name, away_name, alertas_odd))
            time.sleep(3)

        pct, nivel = calcular_confianca(selecionadas + contexto)
        enviar_mensagem(montar_msg_entrada(liga_nome, home_name, away_name, selecionadas, contexto, odd_final, nivel, pct))
        print(f"   Entrada enviada (odd {odd_final:.2f})")

        time.sleep(2)

if __name__ == "__main__":
    print("RD Stats iniciado.")
    while True:
        agora = datetime.now(pytz.timezone("America/Sao_Paulo"))
        if 8 <= agora.hour < 23:
            try:
                processar_jogos()
            except Exception as e:
                print(f"Erro no ciclo: {e}")
            print(f"\nAguardando {INTERVALO_MIN} minutos...")
            time.sleep(INTERVALO_MIN * 60)
        else:
            print(f"[{agora.strftime('%H:%M')}] Fora do horario. Dormindo 1h...")
            time.sleep(3600)
