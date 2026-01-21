"""
Integração com Supabase para gerenciamento de dados
"""
from typing import Dict, List, Optional
from datetime import datetime, date, timezone
from supabase import create_client, Client
import logging

logger = logging.getLogger(__name__)


class Database:
    """Classe para interação com o banco de dados Supabase"""

    def __init__(self, config):
        self.config = config
        self.client: Client = None
        self._initialize_connection()

    def _initialize_connection(self):
        """Inicializa a conexão com o Supabase"""
        try:
            self.client = create_client(
                self.config.SUPABASE_URL,
                self.config.SUPABASE_KEY
            )
            logger.info("✅ Conectado ao Supabase")
        except Exception as e:
            logger.error(f"❌ Erro ao conectar ao Supabase: {str(e)}")
            raise

    # ============================================
    # COINS CONFIG
    # ============================================

    def get_coin_config(self, symbol: str) -> Optional[Dict]:
        """Obtém a configuração de uma moeda"""
        try:
            response = self.client.table('coins_mrrobot')\
                .select('*')\
                .eq('symbol', symbol)\
                .single()\
                .execute()

            return response.data if response.data else None
        except Exception as e:
            logger.error(f"❌ Erro ao obter configuração de {symbol}: {str(e)}")
            return None

    def get_active_coins(self) -> List[Dict]:
        """Obtém todas as moedas ativas"""
        try:
            response = self.client.table('coins_mrrobot')\
                .select('*')\
                .eq('is_active', True)\
                .execute()

            return response.data if response.data else []
        except Exception as e:
            logger.error(f"❌ Erro ao obter moedas ativas: {str(e)}")
            return []

    def update_coin_status(self, symbol: str, is_active: bool):
        """Atualiza o status de uma moeda"""
        try:
            self.client.table('coins_mrrobot')\
                .update({'is_active': is_active})\
                .eq('symbol', symbol)\
                .execute()

            logger.info(f"✅ Status de {symbol} atualizado para {'ativo' if is_active else 'inativo'}")
        except Exception as e:
            logger.error(f"❌ Erro ao atualizar status de {symbol}: {str(e)}")
            raise

    # ============================================
    # TRADES HISTORY
    # ============================================

    def create_trade(self, trade_data: Dict) -> int:
        """
        Cria um novo registro de trade

        Args:
            trade_data: Dicionário com os dados do trade

        Returns:
            ID do trade criado
        """
        try:
            response = self.client.table('trades_mrrobot')\
                .insert(trade_data)\
                .execute()

            trade_id = response.data[0]['id'] if response.data else None
            logger.info(f"✅ Trade criado com ID: {trade_id}")

            return trade_id
        except Exception as e:
            logger.error(f"❌ Erro ao criar trade: {str(e)}")
            raise

    def update_trade(self, trade_id: int, update_data: Dict):
        """Atualiza um trade existente"""
        try:
            self.client.table('trades_mrrobot')\
                .update(update_data)\
                .eq('id', trade_id)\
                .execute()

            logger.info(f"✅ Trade {trade_id} atualizado")
        except Exception as e:
            logger.error(f"❌ Erro ao atualizar trade {trade_id}: {str(e)}")
            raise

    def close_trade(self, trade_id: int, exit_price: float, exit_reason: str, order_id_exit: str = None):
        """Fecha um trade e calcula o PnL"""
        try:
            # Obter dados do trade
            response = self.client.table('trades_mrrobot')\
                .select('*')\
                .eq('id', trade_id)\
                .single()\
                .execute()

            trade = response.data

            if not trade:
                raise Exception(f"Trade {trade_id} não encontrado")

            # Calcular PnL
            entry_price = float(trade['entry_price'])
            quantity = float(trade['quantity'])
            leverage = int(trade.get('leverage', 1))

            # PnL bruto (quantity já contempla o valor nominal / alavancagem)
            pnl_gross = (exit_price - entry_price) * quantity

            # Descontar taxas (entrada + saída)
            trading_fee = self.config.TRADING_FEE
            fees = (entry_price * quantity * trading_fee) + (exit_price * quantity * trading_fee)
            pnl_net = pnl_gross - fees

            # Porcentagem
            pnl_percentage = ((exit_price - entry_price) / entry_price) * 100

            # Atualizar trade
            update_data = {
                'exit_price': exit_price,
                'exit_time': datetime.now(timezone.utc).isoformat(),
                'pnl': pnl_net,
                'pnl_percentage': pnl_percentage,
                'status': 'closed',
                'exit_reason': exit_reason,
                'order_id_exit': order_id_exit
            }

            self.update_trade(trade_id, update_data)

            # Atualizar PnL diário
            self.update_daily_pnl(datetime.now(timezone.utc).date(), pnl_net)

            logger.info(f"✅ Trade {trade_id} fechado")
            logger.info(f"   Entry: ${entry_price:.4f} | Exit: ${exit_price:.4f}")
            logger.info(f"   PnL: ${pnl_net:.2f} ({pnl_percentage:+.2f}%)")

            return pnl_net, pnl_percentage

        except Exception as e:
            logger.error(f"❌ Erro ao fechar trade {trade_id}: {str(e)}")
            raise

    def get_open_trades(self) -> List[Dict]:
        """Obtém todos os trades abertos"""
        try:
            response = self.client.table('trades_mrrobot')\
                .select('*')\
                .eq('status', 'open')\
                .execute()

            return response.data if response.data else []
        except Exception as e:
            logger.error(f"❌ Erro ao obter trades abertos: {str(e)}")
            return []

    def get_trade_by_id(self, trade_id: int) -> Optional[Dict]:
        """Obtém um trade específico por ID"""
        try:
            response = self.client.table('trades_mrrobot')\
                .select('*')\
                .eq('id', trade_id)\
                .single()\
                .execute()

            return response.data if response.data else None
        except Exception as e:
            logger.error(f"❌ Erro ao obter trade {trade_id}: {str(e)}")
            return None

    def update_trade_exit(self, trade_id: str, exit_price: float, exit_reason: str, pnl_percent: float, pnl_usdt: float):
        """
        Atualiza um trade com dados de saída
        Usado pelo TradeMonitor
        """
        try:
            update_data = {
                'exit_price': exit_price,
                'exit_time': datetime.now(timezone.utc).isoformat(),
                'exit_reason': exit_reason,
                'pnl': pnl_usdt,
                'pnl_percentage': pnl_percent * 100,  # Converter para percentual
                'status': 'closed'
            }

            self.client.table('trades_mrrobot')\
                .update(update_data)\
                .eq('id', trade_id)\
                .execute()

            logger.info(f"✅ Trade {trade_id} atualizado com saída")
        except Exception as e:
            logger.error(f"❌ Erro ao atualizar saída do trade {trade_id}: {str(e)}")
            raise

    def get_trades_by_symbol(self, symbol: str, status: str = None) -> List[Dict]:
        """Obtém trades de um símbolo específico"""
        try:
            query = self.client.table('trades_mrrobot').select('*').eq('symbol', symbol)

            if status:
                query = query.eq('status', status)

            response = query.order('entry_time', desc=True).execute()

            return response.data if response.data else []
        except Exception as e:
            logger.error(f"❌ Erro ao obter trades de {symbol}: {str(e)}")
            return []

    def save_trade_history(self, trade_data: Dict) -> str:
        """
        Salva um novo trade (usado pelo Market Scanner)
        Retorna o ID do trade criado
        """
        try:
            response = self.client.table('trades_mrrobot')\
                .insert(trade_data)\
                .execute()

            if response.data and len(response.data) > 0:
                trade_id = response.data[0]['id']
                logger.info(f"✅ Trade salvo: {trade_id}")
                return str(trade_id)

            return None
        except Exception as e:
            logger.error(f"❌ Erro ao salvar trade: {str(e)}")
            raise

    # ============================================
    # BOT LOGS
    # ============================================

    def log(self, level: str, message: str, details: Dict = None, symbol: str = None, trade_id: int = None):
        """Registra um log no banco de dados"""
        try:
            log_data = {
                'level': level,
                'message': message,
                'details': details,
                'symbol': symbol,
                'trade_id': trade_id
            }

            self.client.table('logs_mrrobot').insert(log_data).execute()
        except Exception as e:
            # Não propagar erro de log para não interromper operação
            logger.error(f"❌ Erro ao salvar log no banco: {str(e)}")

    # ============================================
    # DAILY PNL
    # ============================================

    def get_daily_pnl(self, trade_date: date = None) -> Optional[Dict]:
        """Obtém o PnL de um dia específico"""
        try:
            if not trade_date:
                trade_date = datetime.now(timezone.utc).date()

            response = self.client.table('daily_stats_mrrobot')\
                .select('*')\
                .eq('trade_date', trade_date.isoformat())\
                .limit(1)\
                .execute()

            # Retornar primeiro item ou None
            return response.data[0] if response.data and len(response.data) > 0 else None
        except Exception as e:
            # Se não existe registro para hoje, retornar None
            if "No rows found" in str(e) or "Could not find" in str(e):
                return None
            logger.error(f"❌ Erro ao obter PnL diário: {str(e)}")
            return None

    def update_daily_pnl(self, trade_date: date, pnl_usdt: float):
        """Atualiza o PnL diário (usado pelo TradeMonitor)"""
        try:
            is_win = pnl_usdt > 0
            daily_pnl = self.get_daily_pnl(trade_date)

            if not daily_pnl:
                # Criar novo registro
                data = {
                    'trade_date': trade_date.isoformat(),
                    'total_pnl': pnl_usdt,
                    'total_trades': 1,
                    'winning_trades': 1 if is_win else 0,
                    'losing_trades': 0 if is_win else 1,
                    'is_circuit_breaker_active': False
                }
                self.client.table('daily_stats_mrrobot').insert(data).execute()
            else:
                # Atualizar registro existente
                data = {
                    'total_pnl': float(daily_pnl['total_pnl']) + pnl_usdt,
                    'total_trades': int(daily_pnl['total_trades']) + 1,
                    'winning_trades': int(daily_pnl['winning_trades']) + (1 if is_win else 0),
                    'losing_trades': int(daily_pnl['losing_trades']) + (0 if is_win else 1),
                }

                self.client.table('daily_stats_mrrobot')\
                    .update(data)\
                    .eq('trade_date', trade_date.isoformat())\
                    .execute()

            logger.info(f"✅ PnL diário atualizado: {'+' if pnl_usdt > 0 else ''}{pnl_usdt:.2f}")
        except Exception as e:
            logger.error(f"❌ Erro ao atualizar PnL diário: {str(e)}")

    def activate_circuit_breaker(self, trade_date: date):
        """Ativa o circuit breaker para um dia"""
        try:
            self.client.table('daily_stats_mrrobot')\
                .update({
                    'is_circuit_breaker_active': True,
                    'circuit_breaker_activated_at': datetime.now(timezone.utc).isoformat()
                })\
                .eq('trade_date', trade_date.isoformat())\
                .execute()

            logger.warning(f"🔴 Circuit breaker ATIVADO para {trade_date}")
        except Exception as e:
            logger.error(f"❌ Erro ao ativar circuit breaker: {str(e)}")

    # ============================================
    # TRADE COOLDOWN
    # ============================================

    def get_trade_cooldown(self, symbol: str) -> Optional[Dict]:
        """Obtém o cooldown de uma moeda"""
        try:
            response = self.client.table('cooldown_mrrobot')\
                .select('*')\
                .eq('symbol', symbol)\
                .single()\
                .execute()

            return response.data if response.data else None
        except Exception as e:
            msg = str(e)
            if "No rows found" in msg or "Could not find" in msg or "PGRST116" in msg:
                return None
            logger.error(f"❌ Erro ao obter cooldown de {symbol}: {msg}")
            return None

    def set_trade_cooldown(self, symbol: str, last_trade_time: datetime, cooldown_until: datetime):
        """Define o cooldown para uma moeda"""
        try:
            existing = self.get_trade_cooldown(symbol)

            data = {
                'symbol': symbol,
                'last_trade_time': last_trade_time.isoformat(),
                'cooldown_until': cooldown_until.isoformat()
            }

            if existing:
                # Atualizar
                self.client.table('cooldown_mrrobot')\
                    .update(data)\
                    .eq('symbol', symbol)\
                    .execute()
            else:
                # Inserir
                self.client.table('cooldown_mrrobot').insert(data).execute()

            logger.debug(f"✅ Cooldown de {symbol} definido até {cooldown_until}")
        except Exception as e:
            logger.error(f"❌ Erro ao definir cooldown de {symbol}: {str(e)}")

    # ============================================
    # ESTATÍSTICAS
    # ============================================

    def get_statistics(self, days: int = 30) -> Dict:
        """Obtém estatísticas dos últimos N dias"""
        try:
            # PnL por dia
            response = self.client.table('daily_stats_mrrobot')\
                .select('*')\
                .order('trade_date', desc=True)\
                .limit(days)\
                .execute()

            daily_stats = response.data if response.data else []

            # Performance por moeda (VIEW)
            response = self.client.from_('performance_by_symbol_mrrobot').select('*').execute()
            performance = response.data if response.data else []

            # Calcular totais
            total_pnl = sum(float(day['total_pnl']) for day in daily_stats)
            total_trades = sum(int(day['total_trades']) for day in daily_stats)
            winning_trades = sum(int(day['winning_trades']) for day in daily_stats)
            losing_trades = sum(int(day['losing_trades']) for day in daily_stats)

            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

            return {
                'total_pnl': total_pnl,
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': win_rate,
                'daily_stats': daily_stats,
                'performance_by_symbol': performance
            }
        except Exception as e:
            logger.error(f"❌ Erro ao obter estatísticas: {str(e)}")
            return {}

    # ============================================
    # HELPERS
    # ============================================

    def get_active_symbols(self) -> List[Dict]:
        """Obtém lista de símbolos ativos (usado pelo scanner)"""
        try:
            response = self.client.table('coins_mrrobot')\
                .select('symbol')\
                .eq('is_active', True)\
                .execute()

            return response.data if response.data else []
        except Exception as e:
            logger.error(f"❌ Erro ao obter símbolos ativos: {str(e)}")
            return []
