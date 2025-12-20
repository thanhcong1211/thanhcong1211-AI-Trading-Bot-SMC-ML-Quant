"""
Pattern Probability Filter Module
==================================

Lưu lịch sử win rate của từng pattern, filter tín hiệu có win rate thấp.

Database structure:
{
    'pattern_hash': {
        'wins': int,
        'losses': int,
        'total': int,
        'win_rate': float,
        'last_updated': datetime
    }
}
"""

import logging
import json
import hashlib
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class PatternProbabilityFilter:
    """
    Lọc tín hiệu dựa trên xác suất thắng lịch sử của pattern tương tự
    
    Features:
    - Lưu kết quả của mỗi pattern
    - Tính win rate cho pattern tương tự
    - Filter tín hiệu có win rate < ngưỡng
    - Auto-update từ trade results
    """
    
    def __init__(self, 
                 min_win_rate: float = 0.65,
                 min_sample_size: int = 10,
                 db_path: Optional[str] = None):
        """
        Args:
            min_win_rate: Win rate tối thiểu để accept (0-1)
            min_sample_size: Số lượng trades tối thiểu để có thống kê tin cậy
            db_path: Path đến file database JSON
        """
        self.min_win_rate = min_win_rate
        self.min_sample_size = min_sample_size
        
        # Setup database path
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / "data" / "pattern_probability.json"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load database
        self.patterns_db = self._load_database()
        
        logger.info(f"✅ PatternProbabilityFilter initialized")
        logger.info(f"   Min win rate: {min_win_rate*100:.0f}%")
        logger.info(f"   Min sample size: {min_sample_size}")
        logger.info(f"   Database: {len(self.patterns_db)} patterns loaded")
    
    def _load_database(self) -> Dict:
        """Load pattern database from JSON"""
        try:
            if self.db_path.exists():
                with open(self.db_path, 'r') as f:
                    data = json.load(f)
                    logger.debug(f"📂 Loaded {len(data)} patterns from {self.db_path}")
                    return data
            else:
                logger.debug(f"📂 No existing database, creating new")
                return {}
        except Exception as e:
            logger.warning(f"⚠️ Database load failed: {e}, using empty database")
            return {}
    
    def _save_database(self):
        """Save pattern database to JSON"""
        try:
            with open(self.db_path, 'w') as f:
                json.dump(self.patterns_db, f, indent=2)
            logger.debug(f"💾 Saved {len(self.patterns_db)} patterns to database")
        except Exception as e:
            logger.error(f"❌ Database save failed: {e}")
    
    def _extract_pattern(self, signal: Dict[str, Any]) -> str:
        """
        Trích xuất pattern fingerprint từ signal
        
        Pattern bao gồm:
        - Action (BUY/SELL)
        - Regime type
        - Volatility level
        - SMC structure
        - Liquidity condition
        
        Returns:
            pattern_hash: MD5 hash của pattern
        """
        try:
            # Extract key features
            action = signal.get('action', 'NONE')
            regime = signal.get('regime', {}).get('type', 'unknown')
            volatility = signal.get('volatility', {}).get('level', 'unknown')
            
            smc_data = signal.get('smc_data', {})
            ob_detected = smc_data.get('order_block', {}).get('detected', False)
            fvg_detected = smc_data.get('fvg', {}).get('detected', False)
            structure_type = smc_data.get('structure', {}).get('type', 'unknown')
            
            liquidity_data = signal.get('liquidity_sweep_ai', {})
            sweep_detected = liquidity_data.get('sweep_detected', False)
            stop_hunt = liquidity_data.get('stop_hunt', False)
            
            # Create pattern string
            pattern_str = f"{action}|{regime}|{volatility}|OB:{ob_detected}|FVG:{fvg_detected}|" \
                         f"STRUCT:{structure_type}|SWEEP:{sweep_detected}|HUNT:{stop_hunt}"
            
            # Hash pattern (để tránh key quá dài)
            pattern_hash = hashlib.md5(pattern_str.encode()).hexdigest()
            
            return pattern_hash
            
        except Exception as e:
            logger.debug(f"⚠️ Pattern extraction error: {e}")
            return "unknown_pattern"
    
    def get_pattern_stats(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Lấy thống kê win rate của pattern tương tự
        
        Returns:
            {
                'pattern_hash': str,
                'wins': int,
                'losses': int,
                'total': int,
                'win_rate': float,
                'has_enough_data': bool,
                'meets_threshold': bool
            }
        """
        try:
            pattern_hash = self._extract_pattern(signal)
            
            # Get stats from database
            pattern_data = self.patterns_db.get(pattern_hash, {
                'wins': 0,
                'losses': 0,
                'total': 0,
                'win_rate': 0.5,  # Neutral assumption
                'last_updated': None
            })
            
            total = pattern_data['total']
            win_rate = pattern_data['win_rate']
            
            # Check if enough data
            has_enough_data = total >= self.min_sample_size
            
            # Check if meets threshold
            meets_threshold = win_rate >= self.min_win_rate if has_enough_data else True  # Allow if not enough data
            
            return {
                'pattern_hash': pattern_hash,
                'wins': pattern_data['wins'],
                'losses': pattern_data['losses'],
                'total': total,
                'win_rate': win_rate,
                'has_enough_data': has_enough_data,
                'meets_threshold': meets_threshold
            }
            
        except Exception as e:
            logger.error(f"❌ Pattern stats retrieval failed: {e}")
            return {
                'pattern_hash': 'error',
                'wins': 0,
                'losses': 0,
                'total': 0,
                'win_rate': 0.5,
                'has_enough_data': False,
                'meets_threshold': True  # Allow on error (conservative)
            }
    
    def should_trade(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Quyết định có nên trade dựa trên pattern probability
        
        Returns:
            {
                'should_trade': bool,
                'reason': str,
                'stats': dict
            }
        """
        try:
            stats = self.get_pattern_stats(signal)
            
            # Decision logic
            if not stats['has_enough_data']:
                # Chưa đủ data → cho phép (learning phase)
                logger.info(f"📊 Pattern Probability: ALLOW (insufficient data: {stats['total']}/{self.min_sample_size})")
                return {
                    'should_trade': True,
                    'reason': 'insufficient_data_allow_for_learning',
                    'stats': stats
                }
            
            elif stats['meets_threshold']:
                # Win rate đủ cao → cho phép
                logger.info(f"📊 Pattern Probability: ✅ ACCEPT (win_rate: {stats['win_rate']*100:.1f}% >= {self.min_win_rate*100:.0f}%, n={stats['total']})")
                return {
                    'should_trade': True,
                    'reason': 'high_historical_win_rate',
                    'stats': stats
                }
            
            else:
                # Win rate thấp → từ chối
                logger.warning(f"📊 Pattern Probability: ❌ REJECT (win_rate: {stats['win_rate']*100:.1f}% < {self.min_win_rate*100:.0f}%, n={stats['total']})")
                logger.warning(f"   Pattern has {stats['wins']}W-{stats['losses']}L history")
                return {
                    'should_trade': False,
                    'reason': 'low_historical_win_rate',
                    'stats': stats
                }
                
        except Exception as e:
            logger.error(f"❌ Pattern probability filter error: {e}")
            # On error, allow trade (conservative)
            return {
                'should_trade': True,
                'reason': 'error_allow_conservative',
                'stats': {},
                'error': str(e)
            }
    
    def record_trade_result(self, signal: Dict[str, Any], won: bool):
        """
        Ghi nhận kết quả trade để cập nhật database
        
        Args:
            signal: Signal đã trade
            won: True nếu thắng, False nếu thua
        """
        try:
            pattern_hash = self._extract_pattern(signal)
            
            # Get or create pattern entry
            if pattern_hash not in self.patterns_db:
                self.patterns_db[pattern_hash] = {
                    'wins': 0,
                    'losses': 0,
                    'total': 0,
                    'win_rate': 0.0,
                    'last_updated': None
                }
            
            pattern_data = self.patterns_db[pattern_hash]
            
            # Update counts
            if won:
                pattern_data['wins'] += 1
            else:
                pattern_data['losses'] += 1
            
            pattern_data['total'] += 1
            
            # Recalculate win rate
            pattern_data['win_rate'] = pattern_data['wins'] / pattern_data['total']
            pattern_data['last_updated'] = datetime.now().isoformat()
            
            # Log update
            result_emoji = "✅" if won else "❌"
            logger.info(f"{result_emoji} Pattern result recorded: {pattern_data['wins']}W-{pattern_data['losses']}L "
                       f"(WR: {pattern_data['win_rate']*100:.1f}%)")
            
            # Save database
            self._save_database()
            
        except Exception as e:
            logger.error(f"❌ Trade result recording failed: {e}")
    
    def get_top_patterns(self, limit: int = 10) -> List[Dict]:
        """Lấy top patterns có win rate cao nhất"""
        try:
            # Filter patterns with enough data
            valid_patterns = [
                {
                    'hash': hash_key,
                    'wins': data['wins'],
                    'losses': data['losses'],
                    'total': data['total'],
                    'win_rate': data['win_rate']
                }
                for hash_key, data in self.patterns_db.items()
                if data['total'] >= self.min_sample_size
            ]
            
            # Sort by win rate
            sorted_patterns = sorted(valid_patterns, key=lambda x: x['win_rate'], reverse=True)
            
            return sorted_patterns[:limit]
            
        except Exception as e:
            logger.error(f"❌ Top patterns retrieval failed: {e}")
            return []
    
    def get_worst_patterns(self, limit: int = 10) -> List[Dict]:
        """Lấy worst patterns có win rate thấp nhất"""
        try:
            valid_patterns = [
                {
                    'hash': hash_key,
                    'wins': data['wins'],
                    'losses': data['losses'],
                    'total': data['total'],
                    'win_rate': data['win_rate']
                }
                for hash_key, data in self.patterns_db.items()
                if data['total'] >= self.min_sample_size
            ]
            
            sorted_patterns = sorted(valid_patterns, key=lambda x: x['win_rate'])
            
            return sorted_patterns[:limit]
            
        except Exception as e:
            logger.error(f"❌ Worst patterns retrieval failed: {e}")
            return []
    
    def get_statistics(self) -> Dict[str, Any]:
        """Lấy thống kê tổng quan"""
        try:
            total_patterns = len(self.patterns_db)
            
            patterns_with_data = [p for p in self.patterns_db.values() if p['total'] >= self.min_sample_size]
            patterns_above_threshold = [p for p in patterns_with_data if p['win_rate'] >= self.min_win_rate]
            
            avg_win_rate = sum(p['win_rate'] for p in patterns_with_data) / len(patterns_with_data) if patterns_with_data else 0
            
            return {
                'total_patterns': total_patterns,
                'patterns_with_enough_data': len(patterns_with_data),
                'patterns_above_threshold': len(patterns_above_threshold),
                'avg_win_rate': avg_win_rate,
                'threshold': self.min_win_rate,
                'min_sample_size': self.min_sample_size
            }
            
        except Exception as e:
            logger.error(f"❌ Statistics calculation failed: {e}")
            return {}
