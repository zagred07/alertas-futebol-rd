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

LIGAS = [71, 72]
BOOKMAKERS = {"8": "Bet365", "2": "Pinnacle"}

ARQUIVO_ENVIADOS = "jogos_enviados.json"

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

def comparar_odds(odds_data):
    odds_bet365 = {}
    odds_pinnacle = {}
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
                                alertas.append(f"· {mercado} - {v1['value']}: Bet365 {o1} x Pinnacle {o2}")
                        except:
                            pass
    return alertas

def processar_jogos():
    jogos_enviados = carregar_enviados()
    jogos = get_jogos_do_dia()
    for jogo in jogos:
        if jogo["fixture"]["status"]["short"] != "NS":
            continue

        fixture_id = jogo["fixture"]["id"]

        if str(fixture_id) in jogos_enviados:
            continue

        home_id = jogo["teams"]["home"]["id"]
        away_id = jogo["teams"]["away"]["id"]
        home_name = jogo["teams"]["home"]["name"]
        away_name = jogo["teams"]["away"]["name"]

        stats_home = []
        for j in get_jogos_do_dia():
            if j["teams"]["home"]["id"] == home_id:
                s = get_stats_fixture(j["fixture"]["id"])
                if s: stats_home.append(s)

        stats_away = []
        for j in get_jogos_do_dia():
            if j["teams"]["away"]["id"] == away_id:
                s = get_stats_fixture(j["fixture"]["id"])
                if s: stats_away.append(s)

        fin_home, chutes_home, cart_home, esc_home = calcular_padroes(stats_home, home_id)
        fin_away, chutes_away, cart_away, esc_away = calcular_padroes(stats_away, away_id)

        pct_fin_away = percentual_acerto(fin_away, 8)
        pct_chutes_away = percentual_acerto(chutes_away, 2)
        pct_cart_home = percentual_acerto(cart_home, 1)
        pct_esc_home = percentual_acerto(esc_home, 4)

        odds_data = get_odds_fixture(fixture_id)
        odds_bet365, odds_pinnacle = comparar_odds(odds_data)

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
            jogos_enviados.add(str(fixture_id))
            salvar_enviados(jogos_enviados)

            alertas_odd = achar_odd_errada(odds_bet365, odds_pinnacle)

            odd_bingo = False
            if odds_bet365:
                for mercado in odds_bet365:
                    for v in odds_bet365[mercado]:
                        try:
                            if float(v.get("odd", 0)) >= 5.00:
                                odd_bingo = True
                        except:
                            pass

            enviar_mensagem(f"🔍 <b>RD Stats – Atenção</b>\n\nAnalisando {home_name} x {away_name}...\nPadrão identificado. Calculando valor.\n\n<b>Entrada em breve.</b> 🚀")
            time.sleep(5)

            if odd_bingo:
                enviar_mensagem(f"🎯 <b>RD Stats – BINGO</b>\n\nOdd alta encontrada com contexto forte!\n\nCada um sabe o que faz com a informação. 🚀")
                time.sleep(3)

            if alertas_odd:
                enviar_mensagem(f"⚠️ <b>RD Stats – Odd Errada na Bet365</b>\n\n" + "\n".join(alertas_odd) + "\n\nCada um sabe o que faz com a informação. 🚀")
                time.sleep(3)

            msg = f"🧠 <b>RD Stats – Entrada</b>\n\n"
            msg += f"<b>Jogo:</b> {home_name} x {away_name}\n\n"
            msg += f"<b>Mercados:</b>\n" + "\n".join(mercados) + "\n\n"
            msg += f"<b>Contexto:</b> O {home_name} é agressivo em casa e o {away_name} é reativo fora.\n\n"
            msg += f"Cada um sabe o que faz com a informação. 🚀"
            enviar_mensagem(msg)

if __name__ == "__main__":
    while True:
        agora = datetime.now(pytz.timezone("America/Sao_Paulo"))
        if 8 <= agora.hour < 22:
            processar_jogos()
            time.sleep(1800)
        else:
            time.sleep(3600)
