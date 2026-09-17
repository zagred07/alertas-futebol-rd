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

# Para evitar alertas repetidos
alertas_enviados = set()

def enviar_alerta(mensagem):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mensagem, "parse_mode": "HTML"}
    requests.post(url, data=payload)

def get_jogos_ao_vivo():
    url = f"{BASE_URL}/fixtures?live=all"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code == 200:
        return resp.json().get("response", [])
    return []

def processar_alertas():
    jogos = get_jogos_ao_vivo()
    for jogo in jogos:
        fixture_id = jogo["fixture"]["id"]
        minuto = jogo["fixture"]["status"]["elapsed"] or 0
        home = jogo["teams"]["home"]["name"]
        away = jogo["teams"]["away"]["name"]
        gols_home = jogo["goals"]["home"]
        gols_away = jogo["goals"]["away"]

        # Odds (se existirem)
        odds = None
        try:
            odds_data = jogo.get("odds", [])
            if odds_data:
                odds = odds_data[0]["value"]
        except:
            pass

        # Estatísticas de finalizações
        stats_url = f"{BASE_URL}/fixtures/statistics?fixture={fixture_id}"
        stats_resp = requests.get(stats_url, headers=HEADERS)
        total_finalizacoes = 0
        if stats_resp.status_code == 200:
            stats_data = stats_resp.json().get("response", [])
            for team_stats in stats_data:
                for stat in team_stats.get("statistics", []):
                    if stat["type"] == "Total Shots" and isinstance(stat["value"], int):
                        total_finalizacoes += stat["value"]

        # 1️⃣ Favorito < 1.3 levando gol no 1º tempo
        if minuto <= 45 and odds is not None and odds < 1.3:
            if (gols_home > gols_away and jogo["teams"]["away"]["winner"]) or                (gols_away > gols_home and jogo["teams"]["home"]["winner"]):
                alerta_id = f"{fixture_id}-gol-fav"
                if alerta_id not in alertas_enviados:
                    msg = f"⚽ <b>ALERTA: FAVORITO SOFRENDO GOL</b>\nJogo: {home} {gols_home}x{gols_away} {away}\nMinuto: {minuto}'\nOdd inicial favorito: {odds}\nMotivo: Gol sofrido no 1º tempo"
                    enviar_alerta(msg)
                    alertas_enviados.add(alerta_id)

        # 2️⃣ Mais de 4 finalizações até 15 min
        if minuto <= 15 and total_finalizacoes > 4:
            alerta_id = f"{fixture_id}-fin4"
            if alerta_id not in alertas_enviados:
                msg = f"🔥 <b>ALERTA: FINALIZAÇÕES > 4 (até 15')</b>\nJogo: {home} {gols_home}x{gols_away} {away}\nFinalizações totais: {total_finalizacoes}\nMinuto: {minuto}'"
                enviar_alerta(msg)
                alertas_enviados.add(alerta_id)

        # 3️⃣ Mais de 7 finalizações até 30 min
        if minuto <= 30 and total_finalizacoes > 7:
            alerta_id = f"{fixture_id}-fin7"
            if alerta_id not in alertas_enviados:
                msg = f"🚀 <b>ALERTA: FINALIZAÇÕES > 7 (até 30')</b>\nJogo: {home} {gols_home}x{gols_away} {away}\nFinalizações totais: {total_finalizacoes}\nMinuto: {minuto}'"
                enviar_alerta(msg)
                alertas_enviados.add(alerta_id)

if __name__ == "__main__":
    fuso = pytz.timezone("America/Sao_Paulo")
    while True:
        agora = datetime.now(fuso)
        if 10 <= agora.hour < 18:
            processar_alertas()
            time.sleep(120)  # 2 minutos
        else:
            time.sleep(300)  # 5 minutos fora do horário
