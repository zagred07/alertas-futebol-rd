# Alertas Futebol - API Football + Telegram

Bot que envia alertas no Telegram com base em jogos ao vivo da API-Football.

## Funcionalidades
- ⚽ Favorito < 1.3 levando gol no 1º tempo
- 🔥 Mais de 4 finalizações até 15 minutos
- 🚀 Mais de 7 finalizações até 30 minutos

## Configuração
Defina as variáveis de ambiente no Railway:
- API_FOOTBALL_KEY: chave da API-Football
- TELEGRAM_BOT_TOKEN: token do bot do Telegram
- TELEGRAM_CHAT_ID: chat ou grupo para envio

O bot roda das 10h às 18h (horário de Brasília) e verifica a cada 2 minutos.
