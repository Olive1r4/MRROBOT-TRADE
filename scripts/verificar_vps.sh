#!/bin/bash

# Script para verificar status completo do bot na VPS
# Uso: ./scripts/verificar_vps.sh

VPS_IP="49.13.1.177"
VPS_USER="root"
BOT_DIR="/root/MRROBOT-FUTURE"

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                                                                              ║"
echo "║                    🔍 VERIFICAÇÃO COMPLETA DA VPS 🔍                         ║"
echo "║                                                                              ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Função para executar comando na VPS
run_remote() {
    ssh -o ConnectTimeout=10 $VPS_USER@$VPS_IP "$@"
}

# 1. Teste de conexão
echo "┌──────────────────────────────────────────────────────────────────────────────┐"
echo "│ 1️⃣  TESTE DE CONEXÃO                                                         │"
echo "└──────────────────────────────────────────────────────────────────────────────┘"
if run_remote "echo '✅ Conexão estabelecida com sucesso!'" 2>/dev/null; then
    echo "✅ SSH funcionando"
else
    echo "❌ Erro ao conectar na VPS"
    exit 1
fi
echo ""

# 2. Informações do sistema
echo "┌──────────────────────────────────────────────────────────────────────────────┐"
echo "│ 2️⃣  INFORMAÇÕES DO SISTEMA                                                   │"
echo "└──────────────────────────────────────────────────────────────────────────────┘"
run_remote "
echo '🖥️  Hostname: ' \$(hostname)
echo '🐧 OS: ' \$(cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"')
echo '⚙️  Kernel: ' \$(uname -r)
echo '💾 Disco:'
df -h / | tail -1 | awk '{print \"   Usado: \" \$3 \" de \" \$2 \" (\" \$5 \")\"}'
echo '🧠 Memória:'
free -h | grep Mem | awk '{print \"   Usado: \" \$3 \" de \" \$2}'
"
echo ""

# 3. Verificar repositório
echo "┌──────────────────────────────────────────────────────────────────────────────┐"
echo "│ 3️⃣  REPOSITÓRIO DO BOT                                                       │"
echo "└──────────────────────────────────────────────────────────────────────────────┘"
run_remote "
if [ -d '$BOT_DIR' ]; then
    echo '✅ Repositório encontrado em: $BOT_DIR'
    echo ''
    echo '📁 Arquivos principais:'
    ls -lh $BOT_DIR/src/*.py 2>/dev/null | awk '{print \"   \" \$9 \" (\" \$5 \")\"}' | grep -v '^   $'
    echo ''
    echo '📄 Arquivos de configuração:'
    ls -lh $BOT_DIR/.env 2>/dev/null && echo '   ✅ .env encontrado' || echo '   ❌ .env NÃO encontrado'
    ls -lh $BOT_DIR/requirements.txt 2>/dev/null && echo '   ✅ requirements.txt encontrado' || echo '   ❌ requirements.txt NÃO encontrado'
    echo ''
    echo '📊 Última atualização (git):'
    cd $BOT_DIR && git log -1 --format='   %h - %s (%ar)' 2>/dev/null || echo '   ⚠️  Não é um repositório git'
else
    echo '❌ Repositório NÃO encontrado em: $BOT_DIR'
    echo '💡 Execute: git clone https://github.com/seu-usuario/MRROBOT-FUTURE.git $BOT_DIR'
fi
"
echo ""

# 4. Verificar Python
echo "┌──────────────────────────────────────────────────────────────────────────────┐"
echo "│ 4️⃣  PYTHON E AMBIENTE VIRTUAL                                                │"
echo "└──────────────────────────────────────────────────────────────────────────────┘"
run_remote "
echo '🐍 Python:'
python3 --version 2>/dev/null | awk '{print \"   Versão: \" \$2}' || echo '   ❌ Python não encontrado'
echo ''
echo '📦 Ambiente Virtual:'
if [ -d '$BOT_DIR/venv' ]; then
    echo '   ✅ venv encontrado'
    echo '   📚 Pacotes instalados:'
    source $BOT_DIR/venv/bin/activate 2>/dev/null
    pip list 2>/dev/null | grep -E '(fastapi|ccxt|supabase|uvicorn)' | awk '{print \"      \" \$1 \" (\" \$2 \")\"}' || echo '      ⚠️  Nenhum pacote principal encontrado'
else
    echo '   ❌ venv NÃO encontrado'
    echo '   💡 Execute: cd $BOT_DIR && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt'
fi
"
echo ""

# 5. Verificar Docker
echo "┌──────────────────────────────────────────────────────────────────────────────┐"
echo "│ 5️⃣  DOCKER                                                                   │"
echo "└──────────────────────────────────────────────────────────────────────────────┘"
run_remote "
if command -v docker &> /dev/null; then
    echo '✅ Docker instalado'
    docker --version | awk '{print \"   Versão: \" \$3}'
    echo ''
    echo '📦 Containers rodando:'
    docker ps --format '   {{.Names}} - {{.Status}}' 2>/dev/null | grep -v '^$' || echo '   ℹ️  Nenhum container rodando'
    echo ''
    echo '🖼️  Imagens disponíveis:'
    docker images --format '   {{.Repository}}:{{.Tag}} ({{.Size}})' 2>/dev/null | grep -i robot || echo '   ℹ️  Nenhuma imagem do bot encontrada'
else
    echo '❌ Docker NÃO instalado'
    echo '💡 Execute: curl -fsSL https://get.docker.com | sh'
fi
"
echo ""

# 6. Verificar serviço systemd
echo "┌──────────────────────────────────────────────────────────────────────────────┐"
echo "│ 6️⃣  SERVIÇO SYSTEMD                                                          │"
echo "└──────────────────────────────────────────────────────────────────────────────┘"
run_remote "
if systemctl list-unit-files | grep -q scalping-bot.service; then
    echo '✅ Serviço scalping-bot configurado'
    echo ''
    echo '📊 Status:'
    systemctl status scalping-bot --no-pager -l | head -15 | sed 's/^/   /'
else
    echo '❌ Serviço scalping-bot NÃO configurado'
    echo '💡 Execute: sudo cp $BOT_DIR/systemd/scalping-bot.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable scalping-bot'
fi
"
echo ""

# 7. Verificar portas e processos
echo "┌──────────────────────────────────────────────────────────────────────────────┐"
echo "│ 7️⃣  PORTAS E PROCESSOS                                                       │"
echo "└──────────────────────────────────────────────────────────────────────────────┘"
run_remote "
echo '🌐 Portas abertas:'
ss -tlnp 2>/dev/null | grep -E ':(8000|22)' | awk '{print \"   \" \$1 \" \" \$4}' || echo '   ℹ️  Porta 8000 não está aberta'
echo ''
echo '🔄 Processos Python rodando:'
ps aux | grep -E '[p]ython.*main' | awk '{print \"   PID \" \$2 \": \" \$11 \" \" \$12 \" \" \$13}' | head -5 || echo '   ℹ️  Nenhum processo do bot encontrado'
"
echo ""

# 8. Verificar firewall
echo "┌──────────────────────────────────────────────────────────────────────────────┐"
echo "│ 8️⃣  FIREWALL (UFW)                                                           │"
echo "└──────────────────────────────────────────────────────────────────────────────┘"
run_remote "
if command -v ufw &> /dev/null; then
    echo '✅ UFW instalado'
    echo ''
    sudo ufw status 2>/dev/null | sed 's/^/   /' || echo '   ⚠️  UFW inativo'
else
    echo '❌ UFW não instalado'
    echo '💡 Execute: sudo apt install ufw -y'
fi
"
echo ""

# 9. Verificar configuração (.env)
echo "┌──────────────────────────────────────────────────────────────────────────────┐"
echo "│ 9️⃣  CONFIGURAÇÃO (.env)                                                      │"
echo "└──────────────────────────────────────────────────────────────────────────────┘"
run_remote "
if [ -f '$BOT_DIR/.env' ]; then
    echo '✅ Arquivo .env encontrado'
    echo ''
    echo '📝 Variáveis configuradas (valores ocultos):'
    cat $BOT_DIR/.env | grep -v '^#' | grep -v '^$' | cut -d= -f1 | awk '{print \"   ✅ \" \$1}'
    echo ''
    echo '🔑 Variáveis críticas:'
    grep -q '^MODE=' $BOT_DIR/.env && echo '   ✅ MODE configurado: ' \$(grep '^MODE=' $BOT_DIR/.env | cut -d= -f2) || echo '   ❌ MODE não configurado'
    grep -q '^BINANCE_API_KEY=' $BOT_DIR/.env && echo '   ✅ BINANCE_API_KEY configurado' || echo '   ❌ BINANCE_API_KEY não configurado'
    grep -q '^SUPABASE_URL=' $BOT_DIR/.env && echo '   ✅ SUPABASE_URL configurado' || echo '   ❌ SUPABASE_URL não configurado'
    grep -q '^TELEGRAM_BOT_TOKEN=' $BOT_DIR/.env && echo '   ✅ TELEGRAM_BOT_TOKEN configurado' || echo '   ⚠️  TELEGRAM_BOT_TOKEN não configurado (opcional)'
else
    echo '❌ Arquivo .env NÃO encontrado'
    echo '💡 Execute: cp $BOT_DIR/env.template $BOT_DIR/.env && nano $BOT_DIR/.env'
fi
"
echo ""

# 10. Verificar logs
echo "┌──────────────────────────────────────────────────────────────────────────────┐"
echo "│ 🔟 LOGS RECENTES                                                             │"
echo "└──────────────────────────────────────────────────────────────────────────────┘"
run_remote "
echo '📜 Últimas 10 linhas do log da aplicação:'
if [ -f '$BOT_DIR/logs/scalping_bot.log' ]; then
    tail -10 $BOT_DIR/logs/scalping_bot.log | sed 's/^/   /'
elif [ -f '/var/log/scalping-bot/output.log' ]; then
    tail -10 /var/log/scalping-bot/output.log | sed 's/^/   /'
else
    echo '   ℹ️  Nenhum log encontrado'
fi
"
echo ""

# 11. Teste de API (se estiver rodando)
echo "┌──────────────────────────────────────────────────────────────────────────────┐"
echo "│ 1️⃣1️⃣ TESTE DE API                                                            │"
echo "└──────────────────────────────────────────────────────────────────────────────┘"
run_remote "
echo '🔌 Testando endpoint /health:'
curl -s http://localhost:8000/health 2>/dev/null | head -5 | sed 's/^/   /' || echo '   ❌ API não está respondendo'
"
echo ""

# Resumo final
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                                                                              ║"
echo "║                          ✅ VERIFICAÇÃO CONCLUÍDA                            ║"
echo "║                                                                              ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "💡 PRÓXIMOS PASSOS:"
echo ""

# Verificar o que está faltando
run_remote "
cd $BOT_DIR 2>/dev/null || { echo '   ❌ Clone o repositório'; exit 1; }
[ ! -f .env ] && echo '   1. Configurar .env: cp env.template .env && nano .env'
[ ! -d venv ] && echo '   2. Criar ambiente virtual: python3 -m venv venv'
[ ! -f venv/bin/activate ] && echo '   3. Instalar dependências: source venv/bin/activate && pip install -r requirements.txt'
! systemctl is-active scalping-bot &>/dev/null && echo '   4. Iniciar o bot: systemctl start scalping-bot ou docker-compose up -d'
echo '   5. Ver logs: tail -f logs/scalping_bot.log'
echo '   6. Testar API: curl http://localhost:8000/health'
"
echo ""
