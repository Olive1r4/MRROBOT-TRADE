# 🤖 MRROBOT-FUTURE - Resumo do Projeto

## ✅ O Que Foi Criado

Este é um **Bot de Scalping profissional** para Binance Futures com recursos avançados de segurança e monitoramento.

---

## 📦 Arquitetura do Projeto

```
MRROBOT-FUTURE/
├── 📱 NOTIFICAÇÕES TELEGRAM
│   ├── src/telegram_notifier.py          # Módulo de notificações
│   ├── TELEGRAM_QUICKSTART.md            # Configuração rápida (3 passos)
│   ├── TELEGRAM_EXEMPLO.txt              # Exemplos visuais
│   └── docs/TELEGRAM_SETUP.md            # Guia completo
│
├── 🤖 CÓDIGO DO BOT
│   ├── src/main.py                       # Aplicação FastAPI principal
│   ├── src/config.py                     # Configurações e variáveis
│   ├── src/database.py                   # Integração Supabase
│   ├── src/exchange_manager.py           # API Binance (MOCK/PROD)
│   ├── src/indicators.py                 # Indicadores técnicos
│   └── src/risk_manager.py               # Guardrails de segurança
│
├── 🗄️ BANCO DE DADOS
│   └── database/supabase_setup.sql       # Schema completo
│
├── 🐳 DOCKER
│   ├── Dockerfile                        # Imagem do bot
│   ├── docker-compose.yml                # Configuração local
│   ├── docker-compose.prod.yml           # Configuração produção
│   ├── DOCKER_QUICKSTART.md              # Guia rápido Docker
│   └── DOCKER_COMPLETO.md                # Guia completo Docker
│
├── 🚀 DEPLOY
│   ├── .github/workflows/deploy.yml      # Deploy via SSH
│   ├── .github/workflows/deploy-docker.yml # Deploy via Docker
│   ├── systemd/scalping-bot.service      # Serviço Linux
│   └── docs/VPS_SETUP.md                 # Setup VPS completo
│
├── 🔍 VERIFICAÇÃO VPS
│   ├── scripts/verificar_vps.sh          # Script automático
│   ├── VERIFICAR_VPS.md                  # Guia manual
│   └── COMANDOS_VPS.txt                  # Comandos rápidos
│
├── 📚 DOCUMENTAÇÃO
│   ├── README.md                         # Documentação principal
│   ├── COMECE_AGORA.md                   # Início rápido
│   ├── GARANTIA_SEGURANCA.txt            # Sobre MODE=MOCK
│   ├── TESTE_SEGURO.md                   # Guia de testes
│   ├── CONTRIBUTING.md                   # Guia de contribuição
│   └── docs/
│       ├── API_EXAMPLES.md               # Exemplos de API
│       ├── DOCKER_SETUP.md               # Setup Docker
│       ├── ESTRATEGIAS.md                # Estratégias de trading
│       ├── QUICK_START.md                # Início rápido
│       ├── TESTES.md                     # Guia de testes
│       └── VPS_SETUP.md                  # Setup VPS
│
├── 🛠️ SCRIPTS ÚTEIS
│   ├── scripts/start_bot.sh              # Iniciar bot local
│   ├── scripts/check_health.sh           # Health check
│   ├── scripts/docker-deploy.sh          # Deploy Docker
│   └── scripts/verificar_vps.sh          # Verificar VPS
│
└── ⚙️ CONFIGURAÇÃO
    ├── .env.template                     # Template de configuração
    ├── requirements.txt                  # Dependências Python
    └── .gitignore                        # Arquivos ignorados
```

---

## 🎯 Recursos Principais

### 🤖 Bot de Trading

- ✅ **Estratégia:** Scalping Long baseado em RSI, Bollinger Bands, EMA 200 e ATR
- ✅ **Execução:** Rápida via webhook FastAPI
- ✅ **Indicadores:** Cálculo em tempo real com dados da Binance
- ✅ **Modos:** MOCK (simulação) e PROD (real)
- ✅ **Alavancagem:** Configurável (padrão 10x)
- ✅ **Lucro alvo:** 0.6% (configurável)

### 🛡️ Segurança (Guardrails)

- ✅ **Daily Stop Loss:** Circuit breaker automático
- ✅ **Max Open Trades:** Limita posições simultâneas (padrão: 2)
- ✅ **Anti-Whipsaw:** Cooldown de 5 minutos entre trades
- ✅ **Rate Limiter:** Máximo 5 ordens/minuto
- ✅ **Whitelist:** Apenas moedas aprovadas no banco
- ✅ **Stop Loss Dinâmico:** Baseado em ATR

### 📊 Banco de Dados (Supabase)

- ✅ **coins_config:** Moedas ativas e configurações
- ✅ **trades_history:** Histórico completo de trades
- ✅ **bot_logs:** Logs de eventos e erros
- ✅ **daily_pnl:** PnL diário para circuit breaker
- ✅ **trade_cooldown:** Controle anti-whipsaw
- ✅ **rate_limiter:** Controle de taxa
- ✅ **Views:** Estatísticas e performance

### 📱 Notificações Telegram

- ✅ **Inicialização:** Notifica quando bot inicia
- ✅ **Compras:** Detalhes completos (preço, indicadores, alvos)
- ✅ **Vendas:** Resultado (lucro/prejuízo, duração)
- ✅ **Circuit Breaker:** Alerta de stop loss diário
- ✅ **Erros:** Notificação de problemas críticos
- ✅ **Formatação:** Mensagens HTML com emojis
- ✅ **Opcional:** Funciona sem Telegram configurado

### 🐳 Docker

- ✅ **Multi-stage build:** Imagem otimizada
- ✅ **docker-compose:** Fácil deploy local
- ✅ **docker-compose.prod.yml:** Deploy produção
- ✅ **Watchtower:** Auto-update de containers
- ✅ **Health checks:** Monitoramento automático
- ✅ **Volumes:** Persistência de dados e logs
- ✅ **Network:** Rede isolada

### 🚀 Deploy Automatizado

- ✅ **GitHub Actions:** CI/CD automático
- ✅ **Deploy via SSH:** Push to deploy
- ✅ **Deploy via Docker:** Build e deploy automático
- ✅ **Systemd:** Serviço Linux com auto-restart
- ✅ **Rollback:** Fácil retorno a versões anteriores

### 📡 API REST

- ✅ `/health` - Status do bot
- ✅ `/webhook` - Receber sinais (TradingView)
- ✅ `/trade/manual` - Trade manual
- ✅ `/trades/open` - Trades abertos
- ✅ `/trades/{id}` - Detalhes de um trade
- ✅ `/trades/{id}/close` - Fechar trade
- ✅ `/stats` - Estatísticas (PnL, win rate)
- ✅ `/config/coins` - Moedas configuradas
- ✅ `/config/coins/{symbol}/toggle` - Ativar/desativar moeda

---

## 🔧 Tecnologias Utilizadas

### Backend

- **Python 3.10+**
- **FastAPI** - Framework web assíncrono
- **CCXT** - API unificada de exchanges
- **Supabase** - Database as a Service (PostgreSQL)
- **Uvicorn** - ASGI server

### Bibliotecas

- **NumPy & Pandas** - Cálculo de indicadores
- **httpx** - Cliente HTTP assíncrono (Telegram)
- **pydantic** - Validação de dados
- **python-dotenv** - Variáveis de ambiente

### DevOps

- **Docker & Docker Compose**
- **GitHub Actions**
- **systemd**
- **UFW** - Firewall

### Monitoramento

- **Supabase Dashboard**
- **Logs estruturados**
- **Health checks**
- **Telegram notificações**

---

## 📊 Indicadores Técnicos

| Indicador           | Uso                     | Configuração Padrão             |
| ------------------- | ----------------------- | ------------------------------- |
| **RSI**             | Detectar sobrevenda     | Período: 14, Oversold: 30       |
| **Bollinger Bands** | Volatilidade e extremos | Período: 20, Desvio: 2          |
| **EMA 200**         | Filtro de tendência     | Período: 200                    |
| **ATR**             | Stop loss dinâmico      | Período: 14, Multiplicador: 2.0 |

---

## 🔐 Segurança Implementada

- ✅ Credenciais em variáveis de ambiente
- ✅ `.gitignore` para não vazar secrets
- ✅ Webhook com token secreto
- ✅ Modo MOCK para testes sem risco
- ✅ Múltiplos guardrails de proteção
- ✅ Rate limiting
- ✅ Circuit breaker automático
- ✅ Firewall configurado (UFW)
- ✅ HTTPS recomendado
- ✅ SSH com chaves

---

## 📈 Métricas Monitoradas

- **PnL (Profit and Loss):** Lucro/prejuízo total
- **Win Rate:** Taxa de acerto das operações
- **Total Trades:** Quantidade de operações
- **Trades Abertos:** Posições ativas
- **Daily PnL:** Lucro/prejuízo do dia
- **Performance por Moeda:** Estatísticas individuais
- **Circuit Breaker Status:** Estado do stop diário

---

## 🎓 Como Usar

### 1️⃣ Setup Inicial Local

```bash
# Clonar
git clone https://github.com/seu-usuario/MRROBOT-FUTURE.git
cd MRROBOT-FUTURE

# Configurar
cp .env.template .env
nano .env  # Adicionar suas keys

# Instalar
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configurar Supabase
# (executar SQL do arquivo database/supabase_setup.sql)

# Iniciar
python -m src.main
```

### 2️⃣ Setup com Docker (Recomendado)

```bash
# Configurar
cp .env.template .env
nano .env

# Iniciar
docker-compose up -d

# Ver logs
docker-compose logs -f
```

### 3️⃣ Deploy na VPS

```bash
# Configurar secrets no GitHub
# VPS_SSH_KEY, VPS_HOST, VPS_USER, VPS_PATH

# Push para deploy
git push origin main

# Verificar na VPS
ssh root@sua-vps
bash scripts/verificar_vps.sh
```

---

## 📱 Configurar Telegram (Opcional)

### 3 Passos:

1. **Criar bot:** @BotFather → `/newbot` → Copiar TOKEN
2. **Obter Chat ID:** @userinfobot → `/start` → Copiar ID
3. **Configurar .env:**
   ```env
   TELEGRAM_BOT_TOKEN=seu_token
   TELEGRAM_CHAT_ID=seu_chat_id
   ```

**Guias:** `TELEGRAM_QUICKSTART.md` ou `docs/TELEGRAM_SETUP.md`

---

## 🧪 Testar

```bash
# 1. Health check
curl http://localhost:8000/health

# 2. Trade manual
curl -X POST http://localhost:8000/trade/manual \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTCUSDT"}'

# 3. Ver resultado
curl http://localhost:8000/trades/open

# 4. Estatísticas
curl http://localhost:8000/stats
```

---

## 🔍 Verificar VPS

```bash
# Automático (local)
bash scripts/verificar_vps.sh

# Manual (na VPS)
ssh root@49.13.1.177
# Seguir comandos em COMANDOS_VPS.txt
```

---

## 📚 Documentação Disponível

| Arquivo                  | Descrição                        |
| ------------------------ | -------------------------------- |
| `README.md`              | Documentação completa do projeto |
| `COMECE_AGORA.md`        | Guia de início rápido            |
| `GARANTIA_SEGURANCA.txt` | Explicação sobre MODE=MOCK       |
| `TESTE_SEGURO.md`        | Como testar com segurança        |
| `TELEGRAM_QUICKSTART.md` | Configurar Telegram (3 passos)   |
| `TELEGRAM_EXEMPLO.txt`   | Exemplos de notificações         |
| `DOCKER_QUICKSTART.md`   | Usar Docker rapidamente          |
| `DOCKER_COMPLETO.md`     | Guia completo de Docker          |
| `VERIFICAR_VPS.md`       | Verificar e gerenciar VPS        |
| `COMANDOS_VPS.txt`       | Comandos prontos para VPS        |
| `docs/VPS_SETUP.md`      | Setup inicial da VPS             |
| `docs/TELEGRAM_SETUP.md` | Guia completo Telegram           |
| `docs/API_EXAMPLES.md`   | Exemplos de uso da API           |
| `docs/ESTRATEGIAS.md`    | Estratégias de trading           |
| `docs/TESTES.md`         | Como testar o bot                |
| `CONTRIBUTING.md`        | Como contribuir                  |

---

## 🎯 Fluxo de Trabalho

```
1. 📱 TradingView detecta sinal
        ↓
2. 🌐 Envia webhook para bot
        ↓
3. 🤖 Bot recebe e valida
        ↓
4. 🛡️ Guardrails checam segurança
        ↓
5. 📊 Bot busca dados da Binance
        ↓
6. 🧮 Calcula indicadores (RSI, BB, EMA, ATR)
        ↓
7. ✅ Confirma sinal de entrada
        ↓
8. 💰 Executa ordem (MOCK ou REAL)
        ↓
9. 💾 Salva no Supabase
        ↓
10. 📱 Envia notificação Telegram
        ↓
11. 👀 Monitora em background
        ↓
12. 🎯 Fecha em TP ou SL
        ↓
13. 💾 Atualiza banco com resultado
        ↓
14. 📱 Notifica fechamento (lucro/prejuízo)
```

---

## ⚡ Comandos Mais Usados

```bash
# Iniciar bot
docker-compose up -d

# Ver logs
docker-compose logs -f

# Parar bot
docker-compose down

# Reiniciar bot
docker-compose restart

# Trade de teste
curl -X POST http://localhost:8000/trade/manual \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTCUSDT"}'

# Ver status
curl http://localhost:8000/health

# Verificar VPS
bash scripts/verificar_vps.sh
```

---

## 🌟 Próximos Passos Sugeridos

- [ ] Configurar Telegram (opcional mas recomendado)
- [ ] Testar 7+ dias em MODE=MOCK
- [ ] Analisar estatísticas no Supabase
- [ ] Ajustar parâmetros se necessário
- [ ] Quando confiante, testar PROD com valores mínimos
- [ ] Implementar estratégias adicionais (Short, Swing)
- [ ] Adicionar mais indicadores (MACD, Stochastic)
- [ ] Dashboard web (React/Vue)
- [ ] Backtesting com dados históricos

---

## 🆘 Suporte

**Problemas?**

1. Ver logs: `docker-compose logs` ou `sudo journalctl -u scalping-bot -f`
2. Ver documentação: `README.md` e arquivos em `docs/`
3. Verificar VPS: `bash scripts/verificar_vps.sh`
4. Abrir issue no GitHub

---

## 📜 Licença

MIT License - Veja `LICENSE`

---

## 🙏 Contribuir

Veja `CONTRIBUTING.md`

---

**🚀 Bot profissional pronto para uso! Teste com segurança e boa sorte! 📈**

---

**Criado com ❤️ para traders que levam segurança a sério** 🛡️
