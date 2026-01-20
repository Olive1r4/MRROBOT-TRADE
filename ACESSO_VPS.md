# 🖥️ Como Acessar a VPS

## 🎯 Problema Identificado

O terminal integrado do Cursor está com um erro temporário. **Solução:** Use o Terminal nativo do macOS!

---

## ✅ SOLUÇÃO RÁPIDA

### 1️⃣ Abrir Terminal do Mac

**Opção A - Spotlight:**

- Pressione `Cmd + Espaço`
- Digite: `Terminal`
- Pressione `Enter`

**Opção B - Finder:**

- Abra o Finder
- Vá em: `Aplicativos > Utilitários > Terminal`

**Opção C - iTerm2** (se você tem instalado):

- Pressione `Cmd + Espaço`
- Digite: `iTerm`
- Pressione `Enter`

---

### 2️⃣ Acessar a VPS

No terminal que abriu, execute:

```bash
ssh root@49.13.1.177
```

✅ **Pronto!** Você está conectado na VPS!

---

## 🔍 VERIFICAÇÃO RÁPIDA DA VPS

Depois de conectado, copie e cole este bloco completo:

```bash
echo "════════════════════════════════════════════════════════════"
echo "🔍 VERIFICAÇÃO RÁPIDA DO BOT"
echo "════════════════════════════════════════════════════════════"
echo ""

echo "📁 Repositório:"
if [ -d /root/MRROBOT-FUTURE ]; then
    echo "   ✅ Encontrado em /root/MRROBOT-FUTURE"
    cd /root/MRROBOT-FUTURE
    echo "   📊 Última atualização:"
    git log -1 --format='      %h - %s (%ar)' 2>/dev/null || echo "      ⚠️  Não é repo git"
else
    echo "   ❌ NÃO encontrado"
fi
echo ""

echo "📄 Arquivo .env:"
if [ -f /root/MRROBOT-FUTURE/.env ]; then
    echo "   ✅ Existe"
    echo "   🔑 Variáveis configuradas:"
    grep -c "=" /root/MRROBOT-FUTURE/.env 2>/dev/null | awk '{print "      " $1 " variáveis"}'
    echo "   📝 Mode configurado:"
    grep "^MODE=" /root/MRROBOT-FUTURE/.env 2>/dev/null | awk -F= '{print "      " $2}' || echo "      ⚠️  MODE não definido"
else
    echo "   ❌ NÃO existe"
fi
echo ""

echo "🐍 Python:"
python3 --version 2>/dev/null && echo "   ✅ Instalado" || echo "   ❌ NÃO instalado"
echo ""

echo "📦 Ambiente Virtual:"
if [ -d /root/MRROBOT-FUTURE/venv ]; then
    echo "   ✅ Existe"
else
    echo "   ❌ NÃO existe"
fi
echo ""

echo "🐳 Docker:"
if command -v docker &> /dev/null; then
    docker --version
    echo "   ✅ Docker instalado"
    echo "   📦 Containers rodando:"
    docker ps --format '      {{.Names}} - {{.Status}}' 2>/dev/null || echo "      Nenhum"
else
    echo "   ❌ Docker NÃO instalado"
fi
echo ""

echo "🤖 Bot Status (Systemd):"
if systemctl list-unit-files | grep -q scalping-bot.service; then
    if systemctl is-active --quiet scalping-bot; then
        echo "   ✅ RODANDO"
    else
        echo "   ⚠️  Configurado mas PARADO"
    fi
else
    echo "   ❌ Serviço não configurado"
fi
echo ""

echo "🌐 API Status:"
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "   ✅ API Respondendo"
    curl -s http://localhost:8000/health | head -3
else
    echo "   ❌ API NÃO responde"
fi
echo ""

echo "🔥 Portas Abertas:"
ss -tlnp 2>/dev/null | grep -E ":(8000|22)" | awk '{print "   " $4}' || echo "   ℹ️  ss não disponível"
echo ""

echo "════════════════════════════════════════════════════════════"
echo "✅ Verificação concluída!"
echo "════════════════════════════════════════════════════════════"
```

---

## 🚀 SE O BOT NÃO ESTIVER RODANDO

### Opção A: Iniciar com Docker (RECOMENDADO)

```bash
cd /root/MRROBOT-FUTURE

# Verificar se Docker está instalado
docker --version

# Se não estiver, instalar:
# curl -fsSL https://get.docker.com | sh

# Iniciar bot
docker-compose up -d

# Ver logs
docker-compose logs -f
```

### Opção B: Iniciar com Systemd

```bash
# Iniciar serviço
sudo systemctl start scalping-bot

# Ver status
sudo systemctl status scalping-bot

# Ver logs em tempo real
sudo journalctl -u scalping-bot -f
```

---

## 🧪 FAZER TRADE DE TESTE

```bash
curl -X POST http://localhost:8000/trade/manual \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTCUSDT"}'
```

**Se Telegram configurado:** Você receberá notificação! 📱

---

## 📊 VERIFICAR LOGS

```bash
# Opção 1: Docker
docker-compose logs -f

# Opção 2: Systemd
sudo journalctl -u scalping-bot -f

# Opção 3: Arquivo direto
tail -f /root/MRROBOT-FUTURE/logs/scalping_bot.log

# Ver últimas 50 linhas
tail -50 /root/MRROBOT-FUTURE/logs/scalping_bot.log
```

---

## 🔧 COMANDOS ÚTEIS NA VPS

```bash
# Ver trades abertos
curl http://localhost:8000/trades/open | jq

# Ver estatísticas
curl http://localhost:8000/stats | jq

# Ver moedas configuradas
curl http://localhost:8000/config/coins | jq

# Health check
curl http://localhost:8000/health

# Reiniciar bot (Docker)
docker-compose restart

# Reiniciar bot (Systemd)
sudo systemctl restart scalping-bot

# Atualizar código
git pull
docker-compose build
docker-compose up -d
```

---

## 📱 CONFIGURAR TELEGRAM (se ainda não fez)

```bash
# Editar .env
nano /root/MRROBOT-FUTURE/.env

# Adicionar (se não tiver):
# TELEGRAM_BOT_TOKEN=seu_token_aqui
# TELEGRAM_CHAT_ID=seu_chat_id_aqui

# Salvar: Ctrl+X, depois Y, depois Enter

# Reiniciar bot
docker-compose restart
```

**Como obter:**

1. **Token:** Telegram → @BotFather → `/newbot`
2. **Chat ID:** Telegram → @userinfobot → `/start`

---

## 🆘 SE ALGO NÃO FUNCIONAR

### Bot não inicia:

```bash
# Ver erro completo
sudo journalctl -u scalping-bot -n 100

# Ou (Docker)
docker-compose logs --tail=100
```

### API não responde:

```bash
# Verificar se porta está aberta
ss -tlnp | grep 8000

# Abrir porta no firewall
sudo ufw allow 8000

# Verificar firewall
sudo ufw status
```

### Módulo não encontrado:

```bash
cd /root/MRROBOT-FUTURE
source venv/bin/activate
pip install -r requirements.txt --upgrade
```

### Docker não instalado:

```bash
# Instalar Docker
curl -fsSL https://get.docker.com | sh

# Iniciar Docker
sudo systemctl start docker
sudo systemctl enable docker
```

---

## 📸 EXEMPLO DE SAÍDA ESPERADA

Quando tudo estiver OK, você deve ver:

```
════════════════════════════════════════════════════════════
🔍 VERIFICAÇÃO RÁPIDA DO BOT
════════════════════════════════════════════════════════════

📁 Repositório:
   ✅ Encontrado em /root/MRROBOT-FUTURE
   📊 Última atualização:
      abc1234 - Add Telegram notifications (2 hours ago)

📄 Arquivo .env:
   ✅ Existe
   🔑 Variáveis configuradas:
      25 variáveis
   📝 Mode configurado:
      MOCK

🐍 Python:
Python 3.10.12
   ✅ Instalado

📦 Ambiente Virtual:
   ✅ Existe

🐳 Docker:
Docker version 24.0.7
   ✅ Docker instalado
   📦 Containers rodando:
      mrrobot-future - Up 2 hours

🤖 Bot Status (Systemd):
   ✅ RODANDO

🌐 API Status:
   ✅ API Respondendo
{"status":"healthy","mode":"MOCK","timestamp":"2024-01-19T..."}

🔥 Portas Abertas:
   0.0.0.0:8000
   0.0.0.0:22

════════════════════════════════════════════════════════════
✅ Verificação concluída!
════════════════════════════════════════════════════════════
```

---

## 💡 DICA PRO

Crie um alias no seu Mac para facilitar:

```bash
# No seu Mac (Terminal local)
echo 'alias vps="ssh root@49.13.1.177"' >> ~/.zshrc
source ~/.zshrc

# Agora você só precisa digitar:
vps
```

---

## 🔄 DESCONECTAR DA VPS

```bash
exit
```

Ou pressione: `Ctrl + D`

---

## ✅ RESUMO

1. **Abrir Terminal do Mac** (Cmd + Espaço → Terminal)
2. **Conectar:** `ssh root@49.13.1.177`
3. **Verificar:** Copiar/colar o bloco de verificação
4. **Se necessário:** Iniciar bot com Docker ou Systemd
5. **Testar:** Fazer trade manual
6. **Monitorar:** Ver logs

---

**🎯 O problema não é SSH ou permissões - é só usar o Terminal nativo do Mac em vez do terminal integrado do Cursor!**

**📱 Qualquer dúvida, me avise depois de tentar! 🚀**
