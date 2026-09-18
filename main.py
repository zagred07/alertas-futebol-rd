import requests
import time
import os
from datetime import datetime
import pytz
import json

API_KEY = os.getenv("API_FOOTBALL_KEY")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_KEY}

LIGAS = [71, 72, 39, 140, 135, 78, 61, 40]
BOOKMAKERS = {"8": "Bet365", "2": "Pinnacle"}
ARQUIVO_ENVIADOS = "jogos_enviados.json"
SEASON = 2026  # ajustar se virar 2026/2027

# ─────────────────────────────────────────────
# UTILITÁRIOS
# ─────────────────────────────────────────────

def carregar_enviados():
    if os.path.exists(ARQUIVO_ENVIADOS):
        with open(ARQUIVO_ENVIADOS, "r") as f:
            return set(json.load(f))
    return set()

def salvar_enviados(enviados):
    with open(ARQUIVO_ENVIADOS, "w") as f:
        json.dump(list(enviados), f)

def enviar_mensagem(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}
    try:
        requests.post(url, data=payload, timeout=15)
    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")

# ─────────────────────────────────────────────
# BUSCAS NA API
# ─────────────────────────────────────────────

def get_jogos_do_dia():
    hoje = datetime.now(pytz.timezone("America/Sao_Paulo")).strftime("%Y-%m-%d")
    jogos = []
    for liga in LIGAS:
        url = f"{BASE_URL}/fixtures?date={hoje}&league={liga}&season={SEASON}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                jogos.extend(resp.json().get("response", []))
        except Exception as e:
            print(f"Erro liga {liga}: {e}")
        time.sleep(0.3)  # evita rate limit
    return jogos

def get_jogos_time_temporada(team_id, liga_id, apenas_casa=False, apenas_fora=False):
    """Busca TODOS os jogos do time na temporada, naquela liga específica."""
    url = f"{BASE_URL}/fixtures?team={team_id}&league={liga_id}&season={SEASON}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
        jogos = resp.json().get("response", [])
    except Exception as e:
        print(f"Erro buscando jogos do time {team_id}: {e}")
        return []

    # Filtra: só jogos finalizados, e por mando de campo se pedido
    filtrados = []
    for j in jogos:
        status = j["fixture"]["status"]["short"]
        if status not in ["FT", "AET", "PEN"]:
            continue
        if apenas_casa and j["teams"]["home"]["id"] != team_id:
            continue
        if apenas_fora and j["teams"]["away"]["id"] != team_id:
            continue
        filtrados.append(j)
    return filtrados

def get_stats_fixture(fixture_id):
    url = f"{BASE_URL}/fixtures/statistics?fixture={fixture_id}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        return resp.json().get("response", [])
    except:
        return None

def get_odds_fixture(fixture_id):
    url = f"{BASE_URL}/odds?fixture={fixture_id}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
        return resp.json().get("response", [])
    except:
        return []

# ─────────────────────────────────────────────
# CÁLCULOS
# ─────────────────────────────────────────────

def calcular_padroes(stats_list, team_id):
    finalizacoes, chutes_gol, cartoes, escanteios = [], [], [], []
    for stats in stats_list:
        if not stats:
            continue
        for team_stats in stats:
            if team_stats["team"]["id"] == team_id:
                for stat in team_stats["statistics"]:
                    tipo = stat["type"]
                    valor = stat["value"]
                    if isinstance(valor, int):
                        if tipo == "Total Shots":
                            finalizacoes.append(valor)
                        elif tipo == "Shots on Goal":
                            chutes_gol.append(valor)
                        elif tipo == "Yellow Cards":
                            cartoes.append(valor)
                        elif tipo == "Corner Kicks":
                            escanteios.append(valor)
    return finalizacoes, chutes_gol, cartoes, escanteios

def percentual_acerto(lista, linha):
    if not lista:
        return 0
    return sum(1 for v in lista if v >= linha) / len(lista)

def comparar_odds(odds_data):
    odds_bet365, odds_pinnacle = {}, {}
    for odd in odds_data:
        bookmaker = odd.get("bookmaker", {}).get("id")
        for bet in odd.get("bets", []):
            nome = bet.get("name")
            valores = bet.get("values", [])
            if bookmaker == 8:
                odds_bet365[nome] = valores
            elif bookmaker == 2:
                odds_pinnacle[nome] = valores
    return odds_bet365, odds_pinnacle

def achar_odd_errada(odds_bet365, odds_pinnacle):
    alertas = []
    for mercado in odds_bet365:
        if mercado in odds_pinnacle:
            for v1 in odds_bet365[mercado]:
                for v2 in odds_pinnacle[mercado]:
                    if v1.get("value") == v2.get("value"):
                        try:
                            o1 = float(v1.get("odd", 0))
                            o2 = float(v2.get("odd", 0))
                            if o2 > 0 and o1 / o2 > 1.20:
                                alertas.append(f"• {mercado} – {v1['value']}: Bet365 {o1} x Pinnacle {o2}")
                        except:
                            pass
    return alertas

def get_odd_mercado(odds_bet365, nome_mercado, valor_mercado):
    if nome_mercado in odds_bet365:
        for v in odds_bet365[nome_mercado]:
            if v.get("value") == valor_mercado:
                try:
                    return float(v.get("odd", 0))
                except:
                    return None
    return None

def calcular_confianca(percentuais):
    """Recebe lista de % (0-1) e retorna (nivel_texto, valor_medio)."""
    if not percentuais:
        return "BAIXA", 0
    media = sum(percentuais) / len(percentuais)
    if media >= 0.90:
        return "ALTA", media
    elif media >= 0.80:
        return "MÉDIA", media
    return "BAIXA", media

# ─────────────────────────────────────────────
# PROCESSAMENTO
# ─────────────────────────────────────────────

def processar_jogos():
    jogos_enviados = carregar_enviados()
    jogos = get_jogos_do_dia()

    for jogo in jogos:
        if jogo["fixture"]["status"]["short"] != "NS":
            continue

        fixture_id = jogo["fixture"]["id"]
        if str(fixture_id) in jogos_enviados:
            continue

        liga_id = jogo["league"]["id"]
        liga_nome = jogo["league"]["name"]
        home_id = jogo["teams"]["home"]["id"]
        away_id = jogo["teams"]["away"]["id"]
        home_name = jogo["teams"]["home"]["name"]
        away_name = jogo["teams"]["away"]["name"]
        horario = jogo["fixture"]["date"]

        # ── 1. Buscar jogos da temporada (mesma liga)
        jogos_casa_home = get_jogos_time_temporada(home_id, liga_id, apenas_casa=True)
        jogos_fora_away = get_jogos_time_temporada(away_id, liga_id, apenas_fora=True)

        # ── 2. Buscar stats de cada jogo
        stats_home = [get_stats_fixture(j["fixture"]["id"]) for j in jogos_casa_home]
        stats_away = [get_stats_fixture(j["fixture"]["id"]) for j in jogos_fora_away]

        # ── 3. Calcular padrões
        fin_home, chutes_home, cart_home, esc_home = calcular_padroes(stats_home, home_id)
        fin_away, chutes_away, cart_away, esc_away = calcular_padroes(stats_away, away_id)

        pct_fin_away   = percentual_acerto(fin_away, 8)
        pct_chutes_away = percentual_acerto(chutes_away, 2)
        pct_cart_home  = percentual_acerto(cart_home, 1)
        pct_esc_home   = percentual_acerto(esc_home, 4)

        # ── 4. Buscar odds
        odds_data = get_odds_fixture(fixture_id)
        odds_bet365, odds_pinnacle = comparar_odds(odds_data)

        # ── 5. Montar listas
        contexto = []
        mercados = []
        percentuais = []
        odd_final = 1.0

        # Contexto (sem odd, mas com %)
        if pct_fin_away >= 0.70 and len(fin_away) > 0:
            contexto.append(f"• {away_name} +7,5 chutes: {pct_fin_away*100:.0f}% ({len(fin_away)} jogos fora)")
        if pct_chutes_away >= 0.70 and len(chutes_away) > 0:
            contexto.append(f"• {away_name} +1,5 chutes ao gol: {pct_chutes_away*100:.0f}% ({len(chutes_away)} jogos fora)")
        if pct_cart_home >= 0.70 and len(cart_home) > 0:
            contexto.append(f"• {home_name} +0,5 cartões: {pct_cart_home*100:.0f}% ({len(cart_home)} jogos em casa)")
        if pct_esc_home >= 0.70 and len(esc_home) > 0:
            contexto.append(f"• {home_name} +4,5 escanteios: {pct_esc_home*100:.0f}% ({len(esc_home)} jogos em casa)")

        # Mercados COM odd
        def add_mercado(nome_mercado, valor_mercado, label, min_odd=1.30, min_pct=None):
            nonlocal odd_final
            odd = get_odd_mercado(odds_bet365, nome_mercado, valor_mercado)
            if odd and odd >= min_odd:
                mercados.append(f"• {label} — @ {odd:.2f}")
                odd_final *= odd
                return True
            return False

        add_mercado("Goals Over/Under", "Over 0.5", "Mais de 0,5 gols", 1.05)
        add_mercado("Goals Over/Under", "Over 1.5", "Mais de 1,5 gols", 1.30)
        add_mercado("Goals Over/Under", "Over 2.5", "Mais de 2,5 gols", 1.50)
        add_mercado("Both Teams Score", "Yes", "Ambas marcam", 1.50)
        add_mercado("Cards Over/Under", "Over 2.5", "Mais de 2,5 cartões", 1.30)
        add_mercado("Cards Over/Under", "Over 3.5", "Mais de 3,5 cartões", 1.50)

        # Confiança baseada no contexto + mercados
        percentuais = [p for p in [pct_fin_away, pct_chutes_away, pct_cart_home, pct_esc_home] if p >= 0.70]
        nivel, media = calcular_confianca(percentuais)

        # ── 6. Enviar (só se tiver contexto + mercados + odd >= 1.50)
        if contexto and mercados and odd_final >= 1.50:
            jogos_enviados.add(str(fixture_id))
            salvar_enviados(jogos_enviados)

            # Mensagem 1: aviso
            aviso = (
                f"⚽ <b>RD STATS | ANÁLISE EM ANDAMENTO</b>\n\n"
                f"🏆 {liga_nome}\n"
                f"🆚 {home_name} x {away_name}\n"
                f"🕐 {horario[11:16]}\n\n"
                f"🔎 Padrão identificado. Calculando valor..."
            )
            enviar_mensagem(aviso)
            time.sleep(5)

            # BINGO
            if odd_final >= 5.00:
                enviar_mensagem(
                    "🚨🚨🚨 <b>BINGO DETECTADO</b> 🚨🚨🚨\n\n"
                    f"Essa entrada tá com odd acima de 5.00!\n\n"
                    f"Cada um sabe o que faz com a informação. 🚀"
                )
                time.sleep(3)

            # Odd errada
            alertas = achar_odd_errada(odds_bet365, odds_pinnacle)
            if alertas:
                enviar_mensagem(
                    "⚠️ <b>RD Stats | Odd Errada na Bet365</b>\n\n" +
                    "\n".join(alertas) +
                    "\n\nCada um sabe o que faz com a informação. 🚀"
                )
                time.sleep(3)

            # Mensagem 2: entrada final
            linhas = [
                "⚽ <b>RD STATS | ENTRADA</b>",
                "",
                f"🏆 {liga_nome}",
                f"🆚 {home_name} x {away_name}",
                f"🕐 {horario[11:16]}",
                "",
                "━━━━━━━━━━━━━━━━━━━",
                "",
                "📊 <b>ANÁLISE</b>",
            ]
            linhas += contexto if contexto else ["• Sem dados suficientes"]
            linhas += [
                "",
                "━━━━━━━━━━━━━━━━━━━",
                "",
                "🎯 <b>ENTRADAS</b>",
            ]
            linhas += mercados if mercados else ["• Nenhum mercado com odd disponível"]
            linhas += [
                "",
                "━━━━━━━━━━━━━━━━━━━",
                "",
                f"💰 <b>ODD FINAL:</b> {odd_final:.2f}",
                f"📈 <b>Confiança:</b> {media*100:.0f}% ({nivel})",
                "",
                "━━━━━━━━━━━━━━━━━━━",
                "",
                "Cada um sabe o que faz com a informação. 🚀",
            ]
            enviar_mensagem("\n".join(linhas))

        # Pequeno delay pra não estourar rate limit
        time.sleep(1)

# ─────────────────────────────────────────────
# LOOP PRINCIPAL
# ─────────────────────────────────────────────

if __name__ == "__main__":
    while True:
        agora = datetime.now(pytz.timezone("America/Sao_Paulo"))
        if 8 <= agora.hour < 22:
            try:
                processar_jogos()
            except Exception as e:
                print(f"Erro no ciclo: {e}")
            time.sleep(1800)
        else:
            time.sleep(3600)
