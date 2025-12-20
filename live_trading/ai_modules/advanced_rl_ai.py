"""
Advanced Reinforcement Learning AI - Q-Learning + Auto-Parameter Tuning
========================================================================

Features:
1. Q-Learning with state-action-reward
2. Auto-tune parameters based on performance
3. Pattern recognition from trade history
4. Dynamic weight adjustment
5. Multi-metric optimization

"""

import json
import os
import numpy as np
from collections import defaultdict, deque
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class AdvancedReinforcementLearningAI:
    """
    Advanced RL system with Q-Learning and parameter auto-tuning
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.persist_path = self.config.get('persist_path', 'live_trading/state/advanced_rl_state.json')
        
        # Q-Learning parameters
        self.learning_rate = self.config.get('learning_rate', 0.1)  # Alpha
        self.discount_factor = self.config.get('discount_factor', 0.9)  # Gamma
        self.epsilon = self.config.get('epsilon', 0.1)  # Exploration rate
        
        # Data structures
        self.q_table = defaultdict(lambda: defaultdict(float))  # Q(state, action) values
        self.trade_history = deque(maxlen=1000)  # Last 1000 trades
        self.pattern_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pnl': 0.0, 'trades': 0})
        self.parameter_history = defaultdict(list)  # Track parameter changes
        
        # Auto-tuning parameters
        self.tunable_params = {
            'atr_multiplier': {'min': 1.0, 'max': 3.0, 'current': 1.5, 'step': 0.1},
            'ob_depth': {'min': 5, 'max': 30, 'current': 10, 'step': 1},
            'fvg_min_size': {'min': 0.0001, 'max': 0.001, 'current': 0.0003, 'step': 0.0001},
            'confidence_threshold': {'min': 30.0, 'max': 70.0, 'current': 50.0, 'step': 5.0},
        }
        
        self._load()
    
    def _load(self):
        """Load persisted state"""
        try:
            if os.path.exists(self.persist_path):
                with open(self.persist_path, 'r') as f:
                    data = json.load(f)
                    
                    # Load Q-table
                    if 'q_table' in data:
                        for state, actions in data['q_table'].items():
                            self.q_table[state] = defaultdict(float, actions)
                    
                    # Load pattern stats
                    if 'pattern_stats' in data:
                        for pattern, stats in data['pattern_stats'].items():
                            self.pattern_stats[pattern] = stats
                    
                    # Load tunable params
                    if 'tunable_params' in data:
                        for param, value_dict in data['tunable_params'].items():
                            if param in self.tunable_params:
                                self.tunable_params[param].update(value_dict)
                    
                    # Load trade history (last 100 only for performance)
                    if 'trade_history' in data:
                        self.trade_history = deque(data['trade_history'][-100:], maxlen=1000)
                    
                    logger.info(f"✅ Loaded RL state: {len(self.q_table)} states, {len(self.pattern_stats)} patterns")
        except Exception as e:
            logger.warning(f"⚠️ Failed to load RL state: {e}")
    
    def _save(self):
        """Save state to disk"""
        try:
            data = {
                'q_table': {state: dict(actions) for state, actions in self.q_table.items()},
                'pattern_stats': dict(self.pattern_stats),
                'tunable_params': self.tunable_params,
                'trade_history': list(self.trade_history),
                'last_updated': datetime.now().isoformat()
            }
            
            os.makedirs(os.path.dirname(self.persist_path) or ".", exist_ok=True)
            with open(self.persist_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"❌ Failed to save RL state: {e}")
    
    def get_state_key(self, market_context: Dict[str, Any]) -> str:
        """
        Create discrete state key from market context
        
        Args:
            market_context: {
                'trend': 'bullish'|'bearish'|'neutral',
                'phase': 'accumulation'|'manipulation'|'expansion'|'distribution',
                'volatility': 'low'|'medium'|'high',
                'session': 'asia'|'london'|'newyork'
            }
        """
        trend = market_context.get('trend', 'neutral')
        phase = market_context.get('phase', 'uncertain')
        volatility = market_context.get('volatility', 'medium')
        session = market_context.get('session', 'unknown')
        
        return f"{trend}_{phase}_{volatility}_{session}"
    
    def choose_action(self, state_key: str, available_actions: List[str]) -> str:
        """
        Choose action using epsilon-greedy policy
        
        Args:
            state_key: Current state
            available_actions: ['BUY', 'SELL', 'NONE']
            
        Returns:
            chosen_action: str
        """
        # Epsilon-greedy: explore vs exploit
        if np.random.random() < self.epsilon:
            # Explore: random action
            action = np.random.choice(available_actions)
            logger.debug(f"🎲 RL exploring: {action}")
        else:
            # Exploit: best known action
            q_values = {action: self.q_table[state_key][action] for action in available_actions}
            action = max(q_values, key=q_values.get)
            logger.debug(f"🎯 RL exploiting: {action} (Q={q_values[action]:.3f})")
        
        return action
    
    def update_q_value(self, state: str, action: str, reward: float, next_state: str):
        """
        Update Q-value using Q-Learning formula:
        Q(s,a) = Q(s,a) + α * [R + γ * max(Q(s',a')) - Q(s,a)]
        """
        current_q = self.q_table[state][action]
        
        # Max Q-value for next state
        max_next_q = max(self.q_table[next_state].values()) if self.q_table[next_state] else 0.0
        
        # Q-Learning update
        new_q = current_q + self.learning_rate * (reward + self.discount_factor * max_next_q - current_q)
        
        self.q_table[state][action] = new_q
        
        logger.debug(f"📊 Q-Update: {state} -> {action}: {current_q:.3f} → {new_q:.3f} (reward: {reward:.3f})")
    
    def register_trade_result(self, trade_info: Dict[str, Any]):
        """
        Register trade result and update RL system
        
        Args:
            trade_info: {
                'state': str,  # Market state
                'action': 'BUY'|'SELL',
                'profit': float,  # PnL in $
                'pattern': str,  # Pattern/strategy name
                'duration_minutes': int,
                'market_context': dict
            }
        """
        try:
            # Add to history
            trade_info['timestamp'] = datetime.now().isoformat()
            self.trade_history.append(trade_info)
            
            # Update pattern stats
            pattern = trade_info.get('pattern', 'unknown')
            self.pattern_stats[pattern]['trades'] += 1
            self.pattern_stats[pattern]['pnl'] += trade_info['profit']
            
            if trade_info['profit'] > 0:
                self.pattern_stats[pattern]['wins'] += 1
            else:
                self.pattern_stats[pattern]['losses'] += 1
            
            # Calculate reward (normalized)
            reward = self._calculate_reward(trade_info)
            
            # Update Q-value
            state = trade_info['state']
            action = trade_info['action']
            next_state = self.get_state_key(trade_info.get('market_context', {}))
            
            self.update_q_value(state, action, reward, next_state)
            
            # Check if we should auto-tune parameters
            if len(self.trade_history) % 20 == 0:  # Every 20 trades
                self._auto_tune_parameters()
            
            # Persist
            self._save()
            
            logger.info(f"📈 RL registered: {pattern} {action} → ${trade_info['profit']:.2f} (reward: {reward:.3f})")
            
        except Exception as e:
            logger.error(f"❌ RL register error: {e}")
    
    def _calculate_reward(self, trade_info: Dict) -> float:
        """
        Calculate reward from trade result
        
        Reward formula:
        - Positive profit: reward = profit / initial_risk (scaled)
        - Negative profit: reward = profit / initial_risk (penalty)
        - Bonus for quick wins, penalty for long losses
        """
        profit = trade_info['profit']
        duration_minutes = trade_info.get('duration_minutes', 60)
        
        # Normalize by risk (assume 2% risk = $100 for normalization)
        normalized_profit = profit / 100.0
        
        # Time factor (quick wins bonus, long losses penalty)
        if profit > 0:
            time_factor = 1.0 + (1.0 / max(1, duration_minutes / 60))  # Bonus for <1hr wins
        else:
            time_factor = 1.0 - (duration_minutes / 1440)  # Penalty for long losses (max 24hr)
        
        reward = normalized_profit * time_factor
        
        # Clip to [-1, 1]
        reward = np.clip(reward, -1.0, 1.0)
        
        return float(reward)
    
    def _auto_tune_parameters(self):
        """
        Auto-tune parameters based on recent performance
        """
        logger.info("🔧 Auto-tuning parameters...")
        
        if len(self.trade_history) < 20:
            return
        
        # Analyze recent 20 trades
        recent = list(self.trade_history)[-20:]
        
        winrate = sum(1 for t in recent if t['profit'] > 0) / len(recent)
        avg_profit = sum(t['profit'] for t in recent) / len(recent)
        avg_duration = sum(t.get('duration_minutes', 60) for t in recent) / len(recent)
        
        # Tune confidence threshold
        if winrate < 0.4:  # Low winrate → increase confidence threshold
            self._adjust_parameter('confidence_threshold', +1)
        elif winrate > 0.6:  # High winrate → can lower threshold
            self._adjust_parameter('confidence_threshold', -1)
        
        # Tune ATR multiplier
        if avg_profit < 0:  # Losing → tighten stops
            self._adjust_parameter('atr_multiplier', -1)
        elif avg_profit > 50 and avg_duration < 180:  # Quick wins → can widen stops
            self._adjust_parameter('atr_multiplier', +1)
        
        logger.info(f"✅ Auto-tune complete: WR={winrate:.1%}, AvgProfit=${avg_profit:.2f}")
    
    def _adjust_parameter(self, param_name: str, direction: int):
        """Adjust parameter by one step"""
        if param_name not in self.tunable_params:
            return
        
        param = self.tunable_params[param_name]
        step = param['step'] * direction
        new_value = param['current'] + step
        
        # Clamp to min/max
        new_value = max(param['min'], min(param['max'], new_value))
        
        if new_value != param['current']:
            old_value = param['current']
            param['current'] = new_value
            
            # Record change
            self.parameter_history[param_name].append({
                'timestamp': datetime.now().isoformat(),
                'old': old_value,
                'new': new_value
            })
            
            logger.info(f"⚙️ Parameter {param_name}: {old_value} → {new_value}")
    
    def get_optimized_parameters(self) -> Dict[str, float]:
        """Get current optimized parameters"""
        return {name: params['current'] for name, params in self.tunable_params.items()}
    
    def get_pattern_performance(self, pattern: str) -> Dict[str, Any]:
        """Get performance stats for a pattern"""
        stats = self.pattern_stats.get(pattern, {'wins': 0, 'losses': 0, 'pnl': 0.0, 'trades': 0})
        
        trades = stats['trades']
        winrate = stats['wins'] / trades if trades > 0 else 0.0
        avg_pnl = stats['pnl'] / trades if trades > 0 else 0.0
        
        return {
            'pattern': pattern,
            'trades': trades,
            'wins': stats['wins'],
            'losses': stats['losses'],
            'winrate': winrate,
            'total_pnl': stats['pnl'],
            'avg_pnl': avg_pnl,
            'confidence': min(1.0, winrate + 0.2) if trades >= 10 else 0.5  # Confidence based on performance
        }
    
    def recommend_weight(self, pattern: str, base_weight: float) -> float:
        """
        Recommend weight adjustment based on pattern performance
        """
        perf = self.get_pattern_performance(pattern)
        
        if perf['trades'] < 5:  # Not enough data
            return base_weight
        
        # Adjust weight based on winrate
        winrate = perf['winrate']
        
        if winrate > 0.65:
            factor = 1.5  # Boost good patterns
        elif winrate > 0.55:
            factor = 1.2
        elif winrate < 0.35:
            factor = 0.3  # Reduce bad patterns
        elif winrate < 0.45:
            factor = 0.7
        else:
            factor = 1.0
        
        return base_weight * factor
    
    def get_stats(self) -> Dict[str, Any]:
        """Get overall RL stats"""
        total_trades = len(self.trade_history)
        
        if total_trades == 0:
            return {'total_trades': 0, 'states_learned': 0, 'patterns_tracked': 0}
        
        wins = sum(1 for t in self.trade_history if t['profit'] > 0)
        total_pnl = sum(t['profit'] for t in self.trade_history)
        
        return {
            'total_trades': total_trades,
            'wins': wins,
            'losses': total_trades - wins,
            'winrate': wins / total_trades,
            'total_pnl': total_pnl,
            'avg_pnl': total_pnl / total_trades,
            'states_learned': len(self.q_table),
            'patterns_tracked': len(self.pattern_stats),
            'optimized_params': self.get_optimized_parameters()
        }


# Singleton
_advanced_rl_ai = None

def get_advanced_rl_ai(config: Optional[Dict[str, Any]] = None) -> AdvancedReinforcementLearningAI:
    """Get singleton instance"""
    global _advanced_rl_ai
    if _advanced_rl_ai is None:
        _advanced_rl_ai = AdvancedReinforcementLearningAI(config)
    return _advanced_rl_ai
