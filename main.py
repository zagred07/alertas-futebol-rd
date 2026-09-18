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

def enviar_alerta(mensagem):
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

def get_ultimos_jogos(team_id, local):
    # local = "home" ou "away"
    url = f"{BASE_URL}/fixtures?team={team_id}&last=10"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        return []
    jogos = resp.json().get("response", [])
    # Filtrar por local
    return [j for j in jogos if j["fixture"]["venue"]["city"] == local]

def get_stats_fixture(fixture_id):
    url = f"{BASE_URL}/fixtures/statistics?fixture={fixture_id}"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        return None
    return resp.json().get("response", [])

def calcular_padroes(stats_list, team_id):
    finalizacoes = []
    chutes_gol = []
    cartoes = []
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
    return finalizacoes, chutes_gol, cartoes

def percentual_acerto(lista, linha):
    if not lista:
        return 0
    return sum(1 for v in lista if v >= linha) / len(lista)

def processar_jogos():
    jogos = get_jogos_do_dia()
    for jogo in jogos:
        # Ignorar jogos que já começaram
        if jogo["fixture"]["status"]["short"] != "NS":
            continue
        home_id = jogo["teams"]["home"]["id"]
        away_id = jogo["teams"]["away"]["id"]
        home_name = jogo["teams"]["home"]["name"]
        away_name = jogo["teams"]["away"]["name"]

        # Buscar últimos 10 jogos do mandante em casa
        jogos_home = get_ultimos_jogos(home_id, "home")
        stats_home = [get_stats_fixture(j["fixture"]["id"]) for j in jogos_home]
        stats_home = [s for s in stats_home if s]

        # Buscar últimos 10 jogos do visitante fora
        jogos_away = get_ultimos_jogos(away_id, "away")
        stats_away = [get_stats_fixture(j["fixture"]["id"]) for j in jogos_away]
        stats_away = [s for s in stats_away if s]

        # Calcular padrões
        fin_home, chutes_home, cart_home = calcular_padroes(stats_home, home_id)
        fin_away, chutes_away, cart_away = calcular_padroes(stats_away, away_id)

        # Percentuais do visitante
        pct_fin_away = percentual_acerto(fin_away, 8)  # +7,5
        pct_chutes_away = percentual_acerto(chutes_away, 2)  # +1,5
        pct_cart_away = percentual_acerto(cart_away, 1)  # +0,5

        # Percentuais do mandante
        pct_fin_home = percentual_acerto(fin_home, 8)  # +7,5
        pct_cart_home = percentual_acerto(cart_home, 1)  # +0,5

        # Cruzamento: se o mandante é agressivo e o visitante é reativo
        if pct_fin_away >= 0.8 and pct_chutes_away >= 0.8 and pct_cart_home >= 0.9:
            msg = f"🧠 <b>RD Stats – Entrada</b>\n\n"
            msg += f"<b>Jogo:</b> {home_name} x {away_name}\n\n"
            msg += f"<b>Mercados:</b>\n"
            msg += f"· {away_name} +7,5 chutes ({pct_fin_away*100:.0f}% de acerto)\n"
            msg += f"· {away_name} +1,5 chutes ao gol ({pct_chutes_away*100:.0f}% de acerto)\n"
            msg += f"· {home_name} +0,5 cartões ({pct_cart_home*100:.0f}% de acerto)\n\n"
            msg += f"<b>Contexto:</b> O {home_name} é agressivo em casa e o {away_name} é reativo fora. O visitante finaliza 8+ em {pct_fin_away*100:.0f}% dos jogos e chuta 2+ no gol em {pct_chutes_away*100:.0f}%.\n\n"
            msg += f"Cada um sabe o que faz com a informação. 🚀"
            enviar_alerta(msg)

if __name__ == "__main__":
    fuso = pytz.timezone("America/Sao_Paulo")
    while True:
        agora = datetime.now(fuso)
        # Roda das 8h às 22h, a cada 30 minutos
        if 8 <= agora.hour < 22:
            processar_jogos()
            time.sleep(1800)  # 30 minutos
        else:
            time.sleep(3600)  # 1 hora fora do horário
