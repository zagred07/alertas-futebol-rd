import requests
import time
import os
from datetime import datetime, timedelta
import pytz

API_KEY = os.getenv("API_FOOTBALL_KEY")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_KEY}

# IDs das ligas: 71 = Série A, 72 = Série B
LIGAS = [71, 72]

# IDs das casas de apostas: 8 = Bet365, 2 = Pinnacle
BOOKMAKERS = {"8": "Bet365", "2": "Pinnacle"}

def enviar_mensagem(mensagem):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mensagem, "parse_mode": "HTML"}
    requests.post(url, data=payload)

def get_jogos_do_dia():
    hoje = datetime.now(pytz.timezone("America/Sao_Paulo")).strftime("%Y-%m-%d")
    jogos = []
    for liga in LIGAS:
        url = f"{BASE_URL}/fixtures?date={hoje}&league={liga}&season=2026"
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code == 200:
            jogos.extend(resp.json().get("response", []))
    return jogos

def get_jogos_time(team_id, season=2026):
    url = f"{BASE_URL}/fixtures?team={team_id}&season={season}"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        return []
    return resp.json().get("response", [])

def get_stats_fixture(fixture_id):
    url = f"{BASE_URL}/fixtures/statistics?fixture={fixture_id}"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        return None
    return resp.json().get("response", [])

def get_odds_fixture(fixture_id):
    url = f"{BASE_URL}/odds?fixture={fixture_id}"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        return []
    return resp.json().get("response", [])

def calcular_padroes(stats_list, team_id):
    finalizacoes = []
    chutes_gol = []
    cartoes = []
    escanteios = []
    for stats in stats_list:
        for team_stats in stats:
            if team_stats["team"]["id"] == team_id:
                for stat in team_stats["statistics"]:
                    if stat["type"] == "Total Shots" and isinstance(stat["value"], int):
                        finalizacoes.append(stat["value"])
                    if stat["type"] == "Shots on Goal" and isinstance(stat["value"], int):
                        chutes_gol.append(stat["value"])
                    if stat["type"] == "Yellow Cards" and isinstance(stat["value"], int):
                        cartoes.append(stat["value"])
                    if stat["type"] == "Corner Kicks" and isinstance(stat["value"], int):
                        escanteios.append(stat["value"])
    return finalizacoes, chutes_gol, cartoes, escanteios

def percentual_acerto(lista, linha):
    if not lista:
        return 0
    return sum(1 for v in lista if v >= linha) / len(lista)

def comparar_odds(odds_data, fixture_id):
    odds_bet365 = {}
    odds_pinnacle = {}
    for odd in odds_data:
        bookmaker = odd.get("bookmaker", {}).get("id")
        bets = odd.get("bets", [])
        for bet in bets:
            nome = bet.get("name")
            valores = bet.get("values", [])
            if bookmaker == 8:
                odds_bet365[nome] = valores
            elif bookmaker == 2:
                odds_pinnacle[nome] = valores
    return odds_bet365, odds_pinnacle

def processar_jogos():
    jogos = get_jogos_do_dia()
    for jogo in jogos:
        if jogo["fixture"]["status"]["short"] != "NS":
            continue
        home_id = jogo["teams"]["home"]["id"]
        away_id = jogo["teams"]["away"]["id"]
        home_name = jogo["teams"]["home"]["name"]
        away_name = jogo["teams"]["away"]["name"]
        fixture_id = jogo["fixture"]["id"]

        # Buscar todos os jogos do mandante em casa e do visitante fora
        jogos_home = get_jogos_time(home_id)
        jogos_away = get_jogos_time(away_id)

        stats_home = []
        for j in jogos_home:
            if j["teams"]["home"]["id"] == home_id:
                stats = get_stats_fixture(j["fixture"]["id"])
                if stats:
                    stats_home.append(stats)

        stats_away = []
        for j in jogos_away:
            if j["teams"]["away"]["id"] == away_id:
                stats = get_stats_fixture(j["fixture"]["id"])
                if stats:
                    stats_away.append(stats)

        # Calcular padrões
        fin_home, chutes_home, cart_home, esc_home = calcular_padroes(stats_home, home_id)
        fin_away, chutes_away, cart_away, esc_away = calcular_padroes(stats_away, away_id)

        # Taxas de acerto
        pct_fin_away = percentual_acerto(fin_away, 8)
        pct_chutes_away = percentual_acerto(chutes_away, 2)
        pct_cart_home = percentual_acerto(cart_home, 1)
        pct_esc_home = percentual_acerto(esc_home, 4)

        # Buscar odds
        odds_data = get_odds_fixture(fixture_id)
        odds_bet365, odds_pinnacle = comparar_odds(odds_data, fixture_id)

        # Montar entrada
        mercados = []
        if pct_fin_away >= 0.8:
            mercados.append(f"· {away_name} +7,5 chutes ({pct_fin_away*100:.0f}% de acerto em {len(fin_away)} jogos fora)")
        if pct_chutes_away >= 0.8:
            mercados.append(f"· {away_name} +1,5 chutes ao gol ({pct_chutes_away*100:.0f}% de acerto em {len(chutes_away)} jogos fora)")
        if pct_cart_home >= 0.9:
            mercados.append(f"· {home_name} +0,5 cartões ({pct_cart_home*100:.0f}% de acerto em {len(cart_home)} jogos em casa)")
        if pct_esc_home >= 0.8:
            mercados.append(f"· {home_name} +3,5 escanteios ({pct_esc_home*100:.0f}% de acerto em {len(esc_home)} jogos em casa)")

        if mercados:
            # Mensagem de aquecimento
            enviar_mensagem(f"🔍 <b>RD Stats – Atenção</b>\n\nAnalisando {home_name} x {away_name}...\nPadrão identificado. Calculando valor.\n\n<b>Entrada em breve.</b> 🚀")
            time.sleep(5)

            # Mensagem de entrada
            msg = f"🧠 <b>RD Stats – Entrada</b>\n\n"
            msg += f"<b>Jogo:</b> {home_name} x {away_name}\n\n"
            msg += f"<b>Mercados:</b>\n" + "\n".join(mercados) + "\n\n"
            msg += f"<b>Contexto:</b> O {home_name} é agressivo em casa e o {away_name} é reativo fora.\n\n"
            msg += f"Cada um sabe o que faz com a informação. 🚀"
            enviar_mensagem(msg)

if __name__ == "__main__":
    fuso = pytz.timezone("America/Sao_Paulo")
    while True:
        agora = datetime.now(fuso)
        if 8 <= agora.hour < 22:
            processar_jogos()
            time.sleep(1800)
        else:
            time.sleep(3600)
