#!/bin/bash

# Script para verificar status do bot na VPS

VPS_IP="49.13.1.177"
VPS_USER="root"

echo "════════════════════════════════════════════════════════════════════════════"
echo "🔍 VERIFICANDO VPS: $VPS_IP"
echo "════════════════════════════════════════════════════════════════════════════"
echo ""

# 1. Teste de conexão
echo "1️⃣ Testando conexão SSH..."
ssh -o ConnectTimeout=5 $VPS_USER@$VPS_IP "echo '✅ Conexão estabelecida'" || {
    echo "❌ Erro ao conectar na VPS"
    exit 1
}
echo ""

# 2. Informações do sistema
echo "2️⃣ Informações do Sistema:"
ssh $VPS_USER@$VPS_IP "uname -a && cat /etc/os-release | grep PRETTY_NAME"
echo ""

# 3. Verificar se repositório existe
echo "3️⃣ Verificando repositório:"
ssh $VPS_USER@$VPS_IP "ls -la /root/MRROBOT-FUTURE 2>/dev/null && echo '✅ Repositório encontrado' || echo '❌ Repositório não encontrado'"
echo ""

# 4. Verificar Python
echo "4️⃣ Verificando Python:"
ssh $VPS_USER@$VPS_IP "python3 --version && which python3"
echo ""

# 5. Verificar Docker
echo "5️⃣ Verificando Docker:"
ssh $VPS_USER@$VPS_IP "docker --version 2>/dev/null && docker ps 2>/dev/null || echo 'Docker não instalado/rodando'"
echo ""

# 6. Verificar serviço systemd
echo "6️⃣ Verificando serviço systemd:"
ssh $VPS_USER@$VPS_IP "systemctl status scalping-bot 2>/dev/null | head -10 || echo 'Serviço não configurado'"
echo ""

# 7. Verificar portas abertas
echo "7️⃣ Verificando portas:"
ssh $VPS_USER@$VPS_IP "ss -tlnp | grep -E ':(8000|22)' || netstat -tlnp | grep -E ':(8000|22)' 2>/dev/null"
echo ""

# 8. Verificar firewall
echo "8️⃣ Verificando firewall (UFW):"
ssh $VPS_USER@$VPS_IP "ufw status 2>/dev/null || echo 'UFW não configurado'"
echo ""

# 9. Ver arquivos no diretório do bot (se existir)
echo "9️⃣ Arquivos no diretório do bot:"
ssh $VPS_USER@$VPS_IP "ls -lh /root/MRROBOT-FUTURE/ 2>/dev/null | head -20"
echo ""

# 10. Verificar .env
echo "🔟 Verificando .env:"
ssh $VPS_USER@$VPS_IP "test -f /root/MRROBOT-FUTURE/.env && echo '✅ Arquivo .env existe' || echo '❌ Arquivo .env não encontrado'"
echo ""

echo "════════════════════════════════════════════════════════════════════════════"
echo "✅ Verificação concluída!"
echo "════════════════════════════════════════════════════════════════════════════"
