# 🤖 MRROBOT-FUTURE - Bot de Scalping para Binance Futures

Bot profissional de Scalping para Binance Futures com análise técnica avançada, gerenciamento de risco inteligente e deploy automatizado.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 📋 Índice

- [Características](#-características)
- [Arquitetura](#-arquitetura)
- [Requisitos](#-requisitos)
- [Instalação](#-instalação)
- [Configuração](#-configuração)
- [Uso](#-uso)
- [Deploy](#-deploy)
- [Monitoramento](#-monitoramento)
- [Segurança](#-segurança)
- [FAQ](#-faq)

## ✨ Características

### 🎯 Estratégias de Trading

- **Indicadores Técnicos Avançados:**
  - RSI (Índice de Força Relativa) para identificar sobrevenda/sobrecompra
  - Bandas de Bollinger para detectar volatilidade e pontos de entrada
  - EMA 200 como filtro de tendência
  - ATR (Average True Range) para stop loss dinâmico

- **Scalping Long:**
  - Lucro alvo de 0.6% (configurável)
  - Stop loss dinâmico baseado em volatilidade
  - Execução rápida via webhook

### 🛡️ Guardrails de Segurança

1. **Daily Stop Loss (Circuit Breaker):** Desativa o bot se a perda diária atingir o limite configurado
2. **Max Open Trades:** Limita trades simultâneos para controlar exposição
3. **Anti-Whipsaw (Cooldown):** Período de espera de 5 minutos entre trades da mesma moeda
4. **Rate Limiter:** Controla número de ordens por minuto (máx. 5)
5. **Validação de Moedas:** Sistema de whitelist no banco de dados

### 🔄 Modos de Operação

- **MOCK:** Simulação completa - lê dados reais mas NÃO executa ordens
- **PROD:** Produção real - executa ordens na Binance Futures

### 🏗️ Infraestrutura

- **Webhook FastAPI:** Recebe sinais de alta velocidade
- **Supabase (PostgreSQL):** Banco de dados robusto e escalável
- **GitHub Actions:** Deploy automatizado via SSH
- **Systemd:** Gerenciamento de serviço com auto-restart

## 🏛️ Arquitetura

```
┌─────────────────┐
│  TradingView    │
│  ou Webhook     │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────┐
│      FastAPI Webhook Server         │
│  ┌───────────────────────────────┐  │
│  │   Risk Manager (Guardrails)   │  │
│  └───────────────────────────────┘  │
│  ┌───────────────────────────────┐  │
│  │  Signal Analyzer (Indicators) │  │
│  └───────────────────────────────┘  │
│  ┌───────────────────────────────┐  │
│  │  Exchange Manager (CCXT)      │  │
│  └───────────────────────────────┘  │
└──────────┬──────────────────────┬───┘
           │                      │
           ▼                      ▼
   ┌──────────────┐      ┌──────────────┐
   │   Supabase   │      │   Binance    │
   │  (Database)  │      │   Futures    │
   └──────────────┘      └──────────────┘
```

## 📦 Requisitos

- Python 3.10+
- Conta na Binance com API habilitada para Futures
- Conta no Supabase (gratuita)
- VPS Linux (Ubuntu 20.04+ recomendado)
- Git

## 🚀 Instalação

### Opção 1: Docker (Recomendado para VPS) 🐳

```bash
# 1. Clone
git clone https://github.com/seu-usuario/MRROBOT-FUTURE.git
cd MRROBOT-FUTURE

# 2. Configure
cp env.template .env
nano .env  # Preencha suas credenciais

# 3. Execute
chmod +x scripts/docker-deploy.sh
./scripts/docker-deploy.sh
```

**Veja o guia completo:** [docs/DOCKER_SETUP.md](docs/DOCKER_SETUP.md)

---

### Opção 2: Instalação Local

#### 1. Clone o Repositório

```bash
git clone https://github.com/seu-usuario/MRROBOT-FUTURE.git
cd MRROBOT-FUTURE
```

#### 2. Crie o Ambiente Virtual

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows
```

#### 3. Instale as Dependências

```bash
pip install -r requirements.txt
```

### 4. Configure o Banco de Dados

1. Acesse [Supabase](https://app.supabase.com/)
2. Crie um novo projeto
3. Vá em **SQL Editor**
4. Execute o script `database/supabase_setup.sql`
5. Verifique se todas as tabelas foram criadas

### 5. Configure as Variáveis de Ambiente

```bash
cp .env.template .env
nano .env  # ou use seu editor preferido
```

Preencha com suas credenciais:

```env
MODE=MOCK  # Use MOCK para testar, PROD para produção

# Binance API
BINANCE_API_KEY=sua_api_key_aqui
BINANCE_SECRET_KEY=sua_secret_key_aqui

# Supabase
SUPABASE_URL=https://seu-projeto.supabase.co
SUPABASE_KEY=sua_chave_anon_aqui

# Webhook
WEBHOOK_SECRET=gere_um_token_seguro_aqui
```

## ⚙️ Configuração

### Parâmetros Principais

Edite o arquivo `.env` para ajustar:

```env
# Trading
TARGET_PROFIT=0.006        # 0.6% de lucro alvo
TRADING_FEE=0.0004         # 0.04% de taxa
DEFAULT_LEVERAGE=10        # Alavancagem padrão

# Indicadores
RSI_PERIOD=14
RSI_OVERSOLD=30
BB_PERIOD=20
EMA_PERIOD=200
ATR_PERIOD=14
TIMEFRAME=5m

# Guardrails
DAILY_STOP_LOSS=0.05       # 5% de perda máxima diária
MAX_OPEN_TRADES=2          # Máximo 2 trades simultâneos
TRADE_COOLDOWN_SECONDS=300 # 5 minutos de cooldown
MAX_ORDERS_PER_MINUTE=5    # Rate limit
```

### Configurar Moedas

As moedas são gerenciadas no banco de dados. Para adicionar/ativar moedas:

**Opção 1: SQL direto no Supabase**

```sql
INSERT INTO coins_config (symbol, is_active, min_pnl, max_position_size, leverage) 
VALUES ('ETHUSDT', true, 0.006, 300.00, 10);
```

**Opção 2: Via API**

```bash
curl -X POST http://localhost:8000/config/coins/ETHUSDT/toggle
```

## 🎮 Uso

### Modo Local (Desenvolvimento)

```bash
# Ativar ambiente virtual
source venv/bin/activate

# Executar o bot
python -m src.main
```

O servidor estará disponível em: `http://localhost:8000`

### Endpoints da API

#### 1. Health Check

```bash
curl http://localhost:8000/health
```

#### 2. Enviar Sinal via Webhook

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "x-webhook-secret: seu_token_secreto" \
  -d '{
    "symbol": "BTCUSDT",
    "action": "buy",
    "price": 50000.00
  }'
```

#### 3. Trade Manual

```bash
curl -X POST http://localhost:8000/trade/manual \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "ETHUSDT"
  }'
```

#### 4. Ver Trades Abertos

```bash
curl http://localhost:8000/trades/open
```

#### 5. Estatísticas

```bash
curl http://localhost:8000/stats?days=30
```

#### 6. Fechar Trade Manualmente

```bash
curl -X POST http://localhost:8000/trades/123/close
```

### Integração com TradingView

No TradingView, configure um **Alert** com webhook:

**URL:** `https://seu-vps.com:8000/webhook`

**Message:**

```json
{
  "symbol": "{{ticker}}",
  "action": "buy",
  "price": {{close}},
  "timestamp": "{{time}}"
}
```

**Headers:**

```
x-webhook-secret: seu_token_secreto
```

## 🚢 Deploy

### Configuração da VPS

Veja o guia completo: [docs/VPS_SETUP.md](docs/VPS_SETUP.md)

**Resumo:**

```bash
# 1. Atualizar sistema
sudo apt update && sudo apt upgrade -y

# 2. Instalar Python e dependências
sudo apt install python3.10 python3.10-venv git -y

# 3. Clonar repositório
git clone https://github.com/seu-usuario/MRROBOT-FUTURE.git
cd MRROBOT-FUTURE

# 4. Criar ambiente virtual e instalar dependências
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. Configurar .env
cp .env.template .env
nano .env

# 6. Configurar systemd
sudo cp systemd/scalping-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable scalping-bot
sudo systemctl start scalping-bot

# 7. Verificar status
sudo systemctl status scalping-bot
```

### GitHub Actions (Deploy Automatizado)

#### Deploy com Docker (Recomendado)

Use o workflow `.github/workflows/deploy-docker.yml`

1. **Configure os Secrets no GitHub:**

   Vá em: `Settings > Secrets and variables > Actions`

   Adicione:
   - `VPS_SSH_KEY`: Chave privada SSH
   - `VPS_HOST`: IP da VPS (ex: 192.168.1.100)
   - `VPS_USER`: Usuário SSH (ex: ubuntu)
   - `VPS_PATH`: Caminho do projeto (ex: /home/ubuntu/MRROBOT-FUTURE)

2. **Prepare a VPS:**

```bash
# Instalar Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Instalar Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

3. **Faça push para a branch main:**

```bash
git add .
git commit -m "Deploy inicial"
git push origin main
```

4. **Acompanhe o deploy:**

   `Actions > Deploy Docker para VPS`

---

#### Deploy Tradicional (Systemd)

Use o workflow `.github/workflows/deploy.yml` (arquivo original)

## 📊 Monitoramento

### Logs do Sistema

```bash
# Logs em tempo real
sudo journalctl -u scalping-bot -f

# Últimas 100 linhas
sudo journalctl -u scalping-bot -n 100

# Logs do arquivo
tail -f /var/log/scalping-bot/output.log
```

### Logs da Aplicação

```bash
tail -f logs/scalping_bot.log
```

### Verificar Status

```bash
# Status do serviço
sudo systemctl status scalping-bot

# Health check via API
curl http://localhost:8000/health
```

### Supabase Dashboard

Acesse o painel do Supabase para visualizar:

- Trades em tempo real (tabela `trades_history`)
- PnL diário (tabela `daily_pnl`)
- Logs do bot (tabela `bot_logs`)
- Estatísticas (views: `daily_stats`, `performance_by_symbol`)

### 📱 Notificações Telegram

Configure notificações em tempo real no seu Telegram:

**Notificações Automáticas:**
- ✅ Inicialização do bot
- ✅ Abertura de trades (com indicadores e preços)
- ✅ Fechamento de trades (com lucro/prejuízo)
- ✅ Circuit breaker ativado
- ✅ Erros críticos

**Configuração Rápida (3 passos):**

```bash
# 1. Criar bot no Telegram (@BotFather)
# 2. Obter Chat ID (@userinfobot)
# 3. Adicionar no .env:
TELEGRAM_BOT_TOKEN=seu_token_aqui
TELEGRAM_CHAT_ID=seu_chat_id_aqui
```

**Exemplo de notificação:**

```
✅ VENDA EXECUTADA - LUCRO

💎 Moeda: BTCUSDT
💰 Preço entrada: $42,350.0000
💰 Preço saída: $42,638.0000
📊 Quantidade: 0.0236
⚡ Alavancagem: 10x

✅ Resultado:
  • PnL: $6.80
  • PnL %: +0.68%
  • Duração: 12 min

🎭 Ordem SIMULADA
```

**Guias Disponíveis:**
- 📱 [TELEGRAM_QUICKSTART.md](TELEGRAM_QUICKSTART.md) - Configuração em 3 passos
- 📖 [docs/TELEGRAM_SETUP.md](docs/TELEGRAM_SETUP.md) - Guia completo
- 📊 [TELEGRAM_EXEMPLO.txt](TELEGRAM_EXEMPLO.txt) - Exemplos de notificações

## 🔐 Segurança

### ✅ Boas Práticas Implementadas

- ✅ Credenciais em variáveis de ambiente (nunca no código)
- ✅ Token secreto para validação de webhook
- ✅ `.gitignore` configurado para não vazar credenciais
- ✅ Modo Mock para testes sem risco
- ✅ Múltiplos guardrails de segurança
- ✅ Rate limiting
- ✅ Circuit breaker automático

### 🔒 Recomendações Adicionais

1. **Use HTTPS:** Configure um certificado SSL (Let's Encrypt)
2. **Firewall:** Abra apenas portas necessárias
3. **Chaves SSH:** Use autenticação por chave (desabilite senha)
4. **API Keys:** Use keys com permissões restritas (apenas trading)
5. **Backup:** Configure backup automático do banco de dados
6. **Monitoramento:** Configure alertas de erro

### Configurar Firewall (UFW)

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 8000  # Porta do webhook
sudo ufw enable
```

## 📈 Performance e Otimizações

### Melhorias Implementadas

- Monitoramento assíncrono de trades em background
- Cache de rate limiter em memória
- Índices otimizados no banco de dados
- Conexão persistente com Supabase
- Rate limiting da API da Binance

### Sugestões para Escalar

1. **Redis:** Para cache e rate limiting distribuído
2. **Celery:** Para processamento assíncrono de tarefas
3. **Prometheus + Grafana:** Para métricas avançadas
4. **Load Balancer:** Para múltiplas instâncias
5. **Docker:** Para containerização

## 🐛 Troubleshooting

### Bot não inicia

```bash
# Verificar logs
sudo journalctl -u scalping-bot -n 50

# Verificar sintaxe do Python
python -m py_compile src/main.py

# Testar manualmente
source venv/bin/activate
python -m src.main
```

### Erro de conexão com Binance

- Verifique se as API keys estão corretas
- Verifique se a API tem permissão para Futures
- Teste a conexão: `python -c "import ccxt; print(ccxt.binance().fetch_ticker('BTC/USDT'))"`

### Erro de conexão com Supabase

- Verifique URL e chave no `.env`
- Verifique se as tabelas foram criadas
- Teste no navegador: `https://seu-projeto.supabase.co`

### Circuit Breaker ativado

O circuit breaker ativa quando a perda diária atinge o limite. Para desativar manualmente:

```sql
UPDATE daily_pnl 
SET is_circuit_breaker_active = false 
WHERE trade_date = CURRENT_DATE;
```

⚠️ **Use com cautela!** O circuit breaker existe para proteger seu capital.

## 💡 Melhorias Futuras

- [ ] Suporte a Shorts (venda a descoberto)
- [ ] Machine Learning para otimização de parâmetros
- [ ] Dashboard web em tempo real
- [ ] Notificações via Telegram/Discord
- [ ] Backtesting integrado
- [ ] Modo paper trading estendido
- [ ] Suporte a múltiplas exchanges
- [ ] API REST completa para gerenciamento

## 📚 Documentação Adicional

- [Guia de Setup da VPS](docs/VPS_SETUP.md)
- [Arquitetura Detalhada](docs/ARCHITECTURE.md)
- [Estratégias de Trading](docs/STRATEGIES.md)
- [API Reference](docs/API.md)

## 🤝 Contribuindo

Contribuições são bem-vindas! Por favor:

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/MinhaFeature`)
3. Commit suas mudanças (`git commit -m 'Adiciona MinhaFeature'`)
4. Push para a branch (`git push origin feature/MinhaFeature`)
5. Abra um Pull Request

## ⚠️ Disclaimer

**ATENÇÃO:** Trading de criptomoedas envolve risco significativo de perda. Este bot é fornecido "como está", sem garantias. 

- ❌ NÃO invista dinheiro que não pode perder
- ❌ NÃO use em produção sem testes extensivos em modo MOCK
- ❌ NÃO culpe os desenvolvedores por perdas
- ✅ SEMPRE teste em modo simulação primeiro
- ✅ SEMPRE comece com valores pequenos
- ✅ SEMPRE monitore o bot ativamente

**Use por sua conta e risco.**

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.

## 👤 Autor

Desenvolvido com ❤️ para a comunidade de trading quantitativo.

---

**⭐ Se este projeto foi útil, considere dar uma estrela no GitHub!**

```
 __  __ ____  ____   ___  ____   ___ _____      _____ _   _ _____ _   _ ____  _____ 
|  \/  |  _ \|  _ \ / _ \| __ ) / _ \_   _|    |  ___| | | |_   _| | | |  _ \| ____|
| |\/| | |_) | |_) | | | |  _ \| | | || |_____ | |_  | | | | | | | | | | |_) |  _|  
| |  | |  _ <|  _ <| |_| | |_) | |_| || |_____|  _| | |_| | | | | |_| |  _ <| |___ 
|_|  |_|_| \_\_| \_\\___/|____/ \___/ |_|     |_|    \___/  |_|  \___/|_| \_\_____|
```

🤖 **Happy Trading!** 🚀

<!-- Deploy automatizado testado em Mon Jan 19 17:40:52 -03 2026 -->
