#!/bin/bash

# Script para verificar VPS do Mac (duplo clique funciona)
# Salvo como .command para funcionar no Finder

VPS="root@49.13.1.177"

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                                                                              ║"
echo "║                    🔍 VERIFICANDO BOT NA VPS 🔍                              ║"
echo "║                         49.13.1.177                                        ║"
echo "║                                                                              ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

echo "🔌 Conectando na VPS..."
echo ""

ssh -o ConnectTimeout=10 $VPS 'bash -s' << 'ENDSSH'
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
    echo "   🔑 Variáveis configuradas: $(grep -c "=" /root/MRROBOT-FUTURE/.env 2>/dev/null) variáveis"
    MODE=$(grep "^MODE=" /root/MRROBOT-FUTURE/.env 2>/dev/null | cut -d= -f2)
    if [ -n "$MODE" ]; then
        echo "   📝 Mode: $MODE"
    else
        echo "   ⚠️  MODE não definido"
    fi
else
    echo "   ❌ NÃO existe"
fi
echo ""

echo "🐍 Python:"
if python3 --version 2>/dev/null; then
    echo "   ✅ Instalado"
else
    echo "   ❌ NÃO instalado"
fi
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
    echo "   ✅ Instalado: $(docker --version)"
    echo "   📦 Containers rodando:"
    docker ps --format '      {{.Names}} - {{.Status}}' 2>/dev/null | grep -v "^$" || echo "      Nenhum"
else
    echo "   ❌ NÃO instalado"
fi
echo ""

echo "🤖 Bot Status (Systemd):"
if systemctl list-unit-files 2>/dev/null | grep -q scalping-bot.service; then
    if systemctl is-active --quiet scalping-bot 2>/dev/null; then
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
    curl -s http://localhost:8000/health 2>/dev/null | head -3 | sed 's/^/      /'
else
    echo "   ❌ API NÃO responde na porta 8000"
fi
echo ""

echo "🔥 Processos Python:"
PYTHON_COUNT=$(ps aux | grep -c "[p]ython.*main")
if [ $PYTHON_COUNT -gt 0 ]; then
    echo "   ✅ $PYTHON_COUNT processo(s) encontrado(s)"
    ps aux | grep "[p]ython.*main" | awk '{print "      PID " $2 ": " $11 " " $12}' | head -3
else
    echo "   ⚠️  Nenhum processo Python do bot rodando"
fi
echo ""

echo "════════════════════════════════════════════════════════════"
echo ""

# Diagnóstico e sugestões
if [ -d /root/MRROBOT-FUTURE ]; then
    if [ ! -f /root/MRROBOT-FUTURE/.env ]; then
        echo "⚠️  AÇÃO NECESSÁRIA:"
        echo "   1. Configurar .env: cp /root/MRROBOT-FUTURE/env.template /root/MRROBOT-FUTURE/.env"
        echo "   2. Editar .env: nano /root/MRROBOT-FUTURE/.env"
        echo ""
    fi

    if ! systemctl is-active --quiet scalping-bot 2>/dev/null && ! docker ps 2>/dev/null | grep -q robot; then
        echo "💡 BOT NÃO ESTÁ RODANDO. Para iniciar:"
        echo ""
        echo "   Opção A - Docker (recomendado):"
        echo "      cd /root/MRROBOT-FUTURE && docker-compose up -d"
        echo ""
        echo "   Opção B - Systemd:"
        echo "      sudo systemctl start scalping-bot"
        echo ""
    fi

    if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "⚠️  API não está respondendo. Verificar logs:"
        echo "   docker-compose logs -f"
        echo "   OU"
        echo "   sudo journalctl -u scalping-bot -f"
        echo ""
    fi
else
    echo "❌ REPOSITÓRIO NÃO ENCONTRADO!"
    echo ""
    echo "Execute na VPS:"
    echo "   cd /root"
    echo "   git clone https://github.com/seu-usuario/MRROBOT-FUTURE.git"
    echo ""
fi

echo "════════════════════════════════════════════════════════════"
echo "✅ Verificação concluída!"
echo "════════════════════════════════════════════════════════════"
ENDSSH

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "💡 Para conectar na VPS:"
echo "   ssh root@49.13.1.177"
echo ""
echo "📚 Ver guia completo:"
echo "   cat ACESSO_VPS.md"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Pressione qualquer tecla para fechar..."
read -n 1
