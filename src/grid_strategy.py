import pandas as pd
import logging
from typing import Dict, List, Tuple, Optional

class GridStrategy:
    """
    Grid Trading Strategy

    Creates a grid of buy/sell orders around current price.
    Profits from market volatility in ranging markets.
    """

    def __init__(self, grid_levels: int = 5, grid_spacing_pct: float = 0.004,
                 profit_pct: float = 0.004):
        """
        Initialize Grid Strategy

        Args:
            grid_levels: Number of grid levels (default: 5)
            grid_spacing_pct: Distance between levels as percentage (default: 0.004 = 0.4%)
            profit_pct: Profit target per cycle (default: 0.004 = 0.4%)
        """
        self.grid_levels = grid_levels
        self.grid_spacing_pct = grid_spacing_pct
        self.profit_pct = profit_pct

    def calculate_grid_range(self, candles: list) -> Tuple[float, float, float]:
        """
        Calculate price range from recent candles (24h)

        Args:
            candles: OHLCV data from exchange

        Returns:
            (range_low, range_high, mid_price)
        """
        if not candles or len(candles) == 0:
            raise ValueError("No candle data provided")

        # Convert to DataFrame for easier analysis
        df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        # Get 24h range (assuming 15m candles = 96 candles for 24h)
        lookback = min(96, len(df))
        recent = df.tail(lookback)

        range_high = recent['high'].max()
        range_low = recent['low'].min()
        mid_price = (range_high + range_low) / 2

        logging.info(f"[GRID] Range calculated: Low=${range_low:.4f} | High=${range_high:.4f} | Mid=${mid_price:.4f}")

        return range_low, range_high, mid_price

    def generate_grid_levels(self, mid_price: float, range_low: float,
                            range_high: float, capital_per_level: float) -> List[Dict]:
        """
        Generate grid levels distributed across the range

        Args:
            mid_price: Middle price of range
            range_low: Bottom of range
            range_high: Top of range
            capital_per_level: USDT to allocate per level

        Returns:
            List of grid levels with price, side, and size
        """
        grid_levels = []

        # Calculate spacing
        spacing = mid_price * self.grid_spacing_pct

        # Generate levels around mid price
        for i in range(self.grid_levels):
            # Offset from mid price
            offset = (i - self.grid_levels // 2) * spacing
            level_price = mid_price + offset

            # Determine side based on position relative to mid
            if level_price < mid_price:
                side = 'BUY'
            elif level_price > mid_price:
                side = 'SELL'
            else:
                # Mid level - skip or make it BUY
                side = 'BUY'

            # Calculate size based on capital allocation
            # For BUY: size = capital / price
            # For SELL: we'll need to have the asset first, so we'll handle this dynamically
            size = capital_per_level / level_price

            grid_levels.append({
                'level': i + 1,
                'price': round(level_price, 8),
                'side': side,
                'size': round(size, 8),
                'capital': capital_per_level
            })

        logging.info(f"[GRID] Generated {len(grid_levels)} levels | Spacing: {self.grid_spacing_pct*100:.2f}%")

        return grid_levels

    def should_rebalance(self, current_price: float, grid_range: Tuple[float, float],
                        mid_price: float = None) -> bool:
        """
        Check if rebalancing is needed using Config threshold
        """
        from src.config import Config
        threshold = Config.GRID_REBALANCE_THRESHOLD

        range_low, range_high = grid_range

        # 1. Check Range Breach (Catastrophic failure of grid)
        # If price is completely outside range, we MUST rebalance
        if current_price < range_low or current_price > range_high:
             logging.warning(f"[GRID] Range Breach: Price ${current_price:.6f} outside ${range_low:.6f}-${range_high:.6f}")
             return True

        # 2. Check Center Deviation (Dynamic Drift)
        # Only if mid_price is provided (tracked state)
        if mid_price:
            deviation = abs(current_price - mid_price) / mid_price
            if deviation > threshold: # e.g. > 2%
                logging.info(f"[GRID] Deviation Rebalance: Price ${current_price:.6f} drifted {deviation*100:.2f}% from Center ${mid_price:.6f}")
                return True

        return False

    def calculate_opposite_order(self, filled_order: Dict) -> Dict:
        """
        Calculate opposite order after a grid order is filled

        Args:
            filled_order: {
                'side': 'BUY',
                'price': 100.0,
                'size': 0.1,
                'level': 2
            }

        Returns:
            Opposite order with profit target
        """
        side = filled_order['side']
        entry_price = filled_order['price']
        size = filled_order['size']

        if side == 'BUY':
            # Create SELL order above entry
            target_price = entry_price * (1 + self.profit_pct)
            opposite_side = 'SELL'
        else:  # SELL
            # Create BUY order below entry
            target_price = entry_price * (1 - self.profit_pct)
            opposite_side = 'BUY'

        return {
            'side': opposite_side,
            'price': round(target_price, 8),
            'size': size,
            'level': filled_order['level'],
            'entry_price': entry_price
        }

    def get_grid_metrics(self, completed_cycles: List[Dict]) -> Dict:
        """
        Calculate grid performance metrics

        Args:
            completed_cycles: List of completed buy-sell cycles

        Returns:
            Metrics dictionary
        """
        if not completed_cycles:
            return {
                'total_cycles': 0,
                'total_profit': 0.0,
                'avg_profit_per_cycle': 0.0,
                'win_rate': 0.0
            }

        total_profit = sum(cycle.get('profit', 0) for cycle in completed_cycles)
        winning_cycles = sum(1 for cycle in completed_cycles if cycle.get('profit', 0) > 0)

        return {
            'total_cycles': len(completed_cycles),
            'total_profit': round(total_profit, 2),
            'avg_profit_per_cycle': round(total_profit / len(completed_cycles), 4),
            'win_rate': round((winning_cycles / len(completed_cycles)) * 100, 2)
        }
