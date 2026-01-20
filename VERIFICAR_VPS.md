# 🔍 Verificar VPS - Guia Rápido

## ⚡ Verificação Automática

```bash
# Execute este script para verificação completa
bash scripts/verificar_vps.sh
```

---

## 🖥️ Comandos Manuais

Se preferir verificar manualmente, execute estes comandos:

### 1️⃣ Conectar na VPS

```bash
ssh root@49.13.1.177
```

---

### 2️⃣ Verificar se o repositório existe

```bash
ls -la /root/MRROBOT-FUTURE
```

**Esperado:** Lista de arquivos do projeto

**Se não existir:**

```bash
cd /root
git clone https://github.com/seu-usuario/MRROBOT-FUTURE.git
```

---

### 3️⃣ Verificar arquivo .env

```bash
cat /root/MRROBOT-FUTURE/.env | grep -v "^#" | head -20
```

**Esperado:** Ver suas configurações (MODE, BINANCE_API_KEY, etc.)

**Se não existir:**

```bash
cd /root/MRROBOT-FUTURE
cp env.template .env
nano .env
# Configure suas keys
```

---

### 4️⃣ Verificar se Python está instalado

```bash
python3 --version
which python3
```

**Esperado:** Python 3.10 ou superior

**Se não instalado:**

```bash
sudo apt update
sudo apt install python3.10 python3.10-venv python3-pip -y
```

---

### 5️⃣ Verificar ambiente virtual

```bash
ls -la /root/MRROBOT-FUTURE/venv/
```

**Se não existir:**

```bash
cd /root/MRROBOT-FUTURE
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

### 6️⃣ Verificar Docker

```bash
docker --version
docker ps
docker images | grep robot
```

**Se não instalado:**

```bash
curl -fsSL https://get.docker.com | sh
```

---

### 7️⃣ Verificar se o bot está rodando

#### Via Systemd:

```bash
systemctl status scalping-bot
```

**Se não estiver configurado:**

```bash
sudo cp /root/MRROBOT-FUTURE/systemd/scalping-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable scalping-bot
sudo systemctl start scalping-bot
```

#### Via Docker:

```bash
docker-compose ps
```

**Se não estiver rodando:**

```bash
cd /root/MRROBOT-FUTURE
docker-compose up -d
```

---

### 8️⃣ Ver logs do bot

#### Systemd:

```bash
# Tempo real
sudo journalctl -u scalping-bot -f

# Últimas 50 linhas
sudo journalctl -u scalping-bot -n 50
```

#### Docker:

```bash
cd /root/MRROBOT-FUTURE
docker-compose logs -f
```

#### Arquivo de log:

```bash
tail -f /root/MRROBOT-FUTURE/logs/scalping_bot.log
```

---

### 9️⃣ Testar API do bot

```bash
# Health check
curl http://localhost:8000/health

# Estatísticas
curl http://localhost:8000/stats

# Trades abertos
curl http://localhost:8000/trades/open

# Moedas configuradas
curl http://localhost:8000/config/coins
```

**Esperado:** Respostas JSON

**Se não responder:**

- Bot não está rodando
- Porta 8000 não está aberta

---

### 🔟 Verificar portas abertas

```bash
ss -tlnp | grep 8000
# ou
netstat -tlnp | grep 8000
```

**Esperado:** Porta 8000 LISTEN

---

### 1️⃣1️⃣ Verificar firewall

```bash
sudo ufw status
```

**Deve ter:**

- 22/tcp (SSH) - ALLOW
- 8000/tcp (Webhook) - ALLOW

**Se não configurado:**

```bash
sudo ufw allow ssh
sudo ufw allow 8000
sudo ufw enable
```

---

### 1️⃣2️⃣ Verificar processos Python rodando

```bash
ps aux | grep python
```

**Esperado:** Ver processo `python -m src.main`

---

### 1️⃣3️⃣ Verificar último deploy (Git)

```bash
cd /root/MRROBOT-FUTURE
git log -1
git status
```

---

## 🚀 Iniciar o Bot

### Opção 1: Systemd (Recomendado para produção)

```bash
sudo systemctl start scalping-bot
sudo systemctl status scalping-bot
sudo journalctl -u scalping-bot -f
```

### Opção 2: Docker (Recomendado)

```bash
cd /root/MRROBOT-FUTURE
docker-compose up -d
docker-compose logs -f
```

### Opção 3: Manual (Para testes)

```bash
cd /root/MRROBOT-FUTURE
source venv/bin/activate
python -m src.main
```

---

## 🛑 Parar o Bot

### Systemd:

```bash
sudo systemctl stop scalping-bot
```

### Docker:

```bash
cd /root/MRROBOT-FUTURE
docker-compose down
```

### Manual:

```bash
# Encontrar PID
ps aux | grep "python.*main"

# Matar processo
kill <PID>
```

---

## 🔄 Reiniciar o Bot

### Systemd:

```bash
sudo systemctl restart scalping-bot
```

### Docker:

```bash
cd /root/MRROBOT-FUTURE
docker-compose restart
```

---

## 📊 Monitoramento Contínuo

### Script de monitoramento em tempo real:

```bash
# Criar script
cat > /root/monitor.sh << 'EOF'
#!/bin/bash
while true; do
  clear
  echo "════════════════════════════════════════════════════════════"
  echo "🤖 BOT DE SCALPING - MONITORAMENTO"
  echo "════════════════════════════════════════════════════════════"
  echo ""

  echo "🏥 SAÚDE:"
  curl -s http://localhost:8000/health | jq -r '.status, .mode' 2>/dev/null || echo "❌ API offline"
  echo ""

  echo "📊 TRADES ABERTOS:"
  curl -s http://localhost:8000/trades/open | jq -r '.count' 2>/dev/null || echo "N/A"
  echo ""

  echo "💰 PNL HOJE:"
  curl -s http://localhost:8000/stats?days=1 | jq -r '.statistics.total_pnl' 2>/dev/null || echo "N/A"
  echo ""

  echo "📈 WIN RATE:"
  curl -s http://localhost:8000/stats?days=1 | jq -r '.statistics.win_rate' 2>/dev/null || echo "N/A"
  echo ""

  echo "════════════════════════════════════════════════════════════"
  sleep 10
done
EOF

chmod +x /root/monitor.sh

# Executar
/root/monitor.sh
```

---

## 🧪 Fazer Trade de Teste

```bash
# Trade manual
curl -X POST http://localhost:8000/trade/manual \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTCUSDT"}'
```

---

## 📱 Verificar Notificações Telegram

```bash
# Ver se Telegram está configurado
cd /root/MRROBOT-FUTURE
cat .env | grep TELEGRAM
```

**Deve ter:**

- `TELEGRAM_BOT_TOKEN=...`
- `TELEGRAM_CHAT_ID=...`

**Para testar:**

- Inicie o bot
- Você deve receber mensagem de "BOT INICIADO"
- Faça um trade manual
- Você deve receber notificação de compra

---

## 🔧 Troubleshooting

### Bot não inicia:

```bash
# Ver erro
sudo journalctl -u scalping-bot -n 50

# Ou (Docker)
docker-compose logs
```

### API não responde:

```bash
# Verificar se porta está aberta
ss -tlnp | grep 8000

# Verificar firewall
sudo ufw status

# Abrir porta
sudo ufw allow 8000
```

### Erro de permissão:

```bash
# Dar permissões corretas
cd /root/MRROBOT-FUTURE
chmod -R 755 .
chown -R root:root .
```

### Erro de dependências:

```bash
cd /root/MRROBOT-FUTURE
source venv/bin/activate
pip install -r requirements.txt --upgrade
```

---

## 📚 Arquivos de Log

- **Systemd:** `/var/log/scalping-bot/output.log`
- **Aplicação:** `/root/MRROBOT-FUTURE/logs/scalping_bot.log`
- **Docker:** `docker-compose logs`

---

## ✅ Checklist Rápido

```bash
# Execute todos de uma vez:
echo "1. Repositório:" && ls /root/MRROBOT-FUTURE >/dev/null 2>&1 && echo "✅" || echo "❌"
echo "2. .env:" && test -f /root/MRROBOT-FUTURE/.env && echo "✅" || echo "❌"
echo "3. venv:" && test -d /root/MRROBOT-FUTURE/venv && echo "✅" || echo "❌"
echo "4. Python:" && python3 --version >/dev/null 2>&1 && echo "✅" || echo "❌"
echo "5. Docker:" && docker --version >/dev/null 2>&1 && echo "✅" || echo "❌"
echo "6. Bot rodando:" && systemctl is-active scalping-bot >/dev/null 2>&1 && echo "✅" || echo "❌"
echo "7. API:" && curl -s http://localhost:8000/health >/dev/null 2>&1 && echo "✅" || echo "❌"
echo "8. Porta 8000:" && ss -tlnp | grep -q 8000 && echo "✅" || echo "❌"
```

---

**🔍 Para verificação automática completa, execute:**

```bash
bash /root/MRROBOT-FUTURE/scripts/verificar_vps.sh
```
