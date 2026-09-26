# 🤖 RD STATS — Football Intelligence System

> Sistema de inteligência artificial para análise estatística de futebol e detecção automática de valor em apostas esportivas.

---

## 🧠 O que é

RD STATS é um bot de análise de futebol que roda 24/7 em produção. Ele coleta dados históricos de cada time, processa estatísticas, detecta padrões e envia alertas automáticos no Telegram quando uma oportunidade é identificada — sem intervenção manual.

Criado por **@RD_UNK** como parte do ecossistema **PREDZR**.

---

## ⚙️ Como funciona

O sistema roda dois ciclos em paralelo:

**Ciclo Principal** — a cada 30 minutos (08h–23h):
1. Busca os jogos do dia nas ligas monitoradas
2. Analisa o histórico de cada time (mandante e visitante)
3. Detecta padrões estatísticos de valor
4. Monta entradas e envia alertas no Telegram

**Caçador de Odds** — a cada 30 minutos (24/7):
1. Varre todos os jogos do dia com status NS
2. Compara Bet365 com Pinnacle e outras casas
3. Detecta odds erradas e envia alerta imediato

---

## 🎯 Módulos de Análise

### VISITANTE REATIVO
Detecta jogos onde o visitante tende a pressionar mais quando está perdendo. Critérios:
- Mandante com média ≥ 12 finalizações e ≥ 4 escanteios em casa
- Visitante com média de finalizações maior quando perde do que a média geral
- Mínimo de 10 jogos de histórico por time

Monta múltiplas com até 4 pernas: finalizações do visitante, chutes ao gol, cartões, escanteios, gols marcados.

### ODD ERRADA
Compara a Bet365 contra Pinnacle, Marathonbet, William Hill, BetVictor e 1xBet. Dispara quando a Bet365 está pagando 25%–40% acima da média de mercado nos mercados:
- Gols 1º tempo, Ambas Marcam, Escanteios totais e 1º tempo
- Cartões mandante/visitante, Chutes ao gol, Amarelos 1º tempo, Finalizações totais

### BINGO DO DIA
Ao final de cada ciclo, monta uma múltipla com os melhores jogos de valor encontrados no dia. Dispara somente se a odd combinada for ≥ 3.00.

### PLACAR MÚLTIPLO (RESULTADO CORRETO)
Usa modelo de Poisson ajustado para prever placares prováveis. Considera:
- Médias de gols históricos por time, ajustadas pelo nível do adversário (forte/médio/fraco)
- Classificação de estilo de jogo (aberto, equilibrado, fechado)
- Posição na tabela e poder/fraqueza relativa
- Filtro de odds entre 6.00 e 25.00 na Bet365

Monta múltiplas com 3–4 jogos do mesmo horário.

---

## 🏆 Ligas Monitoradas

| Liga | País |
|------|------|
| Série A | 🇧🇷 Brasil |
| Série B | 🇧🇷 Brasil |
| Premier League | 🏴󠁧󠁢󠁥󠁮󠁧󠁿 Inglaterra |
| La Liga | 🇪🇸 Espanha |
| Serie A | 🇮🇹 Itália |
| Bundesliga | 🇩🇪 Alemanha |
| Ligue 1 | 🇫🇷 França |
| Championship | 🏴󠁧󠁢󠁥󠁮󠁧󠁿 Inglaterra |

*Análise de Visitante Reativo exclusiva para Brasileirão Série A e B.*

---

## 🛠️ Tech Stack

- **Python** — lógica principal
- **API-Football** — dados de jogos, odds e estatísticas em tempo real
- **Telegram Bot API** — envio de alertas formatados em HTML
- **Railway** — deploy e execução contínua em produção
- **Modelo de Poisson** — cálculo de probabilidade de placares

---

## 🔧 Configuração

Defina as variáveis de ambiente no Railway:

```env
API_FOOTBALL_KEY=sua_chave
TELEGRAM_BOT_TOKEN=seu_token
TELEGRAM_CHAT_ID=seu_chat_id
```

---

## 📦 Dependências

```txt
requests
pytz
```

---

## 📊 Controle de Requisições

O sistema controla o consumo da API automaticamente:
- Limite diário: **7.000 requisições**
- Alerta interno a partir de **6.000**
- Cache local de estatísticas, odds, eventos e standings para evitar re-requisições desnecessárias

---

> Built by RODRIGX @RD_UNK· RD STATS · PREDZR ecosystem
