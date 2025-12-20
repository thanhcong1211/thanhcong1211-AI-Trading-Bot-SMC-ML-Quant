"""
Real-time Chart Pattern Detection for Trading Bot
Detects 16 classical chart patterns from the image provided
"""
import numpy as np
import pandas as pd
from typing import Tuple, Optional, Dict
from scipy.signal import find_peaks, argrelextrema
from scipy.stats import linregress


class ChartPatternDetector:
    """
    Phát hiện các mô hình biểu đồ kinh điển:
    - Head & Shoulders / Inverse H&S
    - Double Top / Double Bottom
    - Triple Top / Triple Bottom
    - Triangles (Ascending, Descending, Symmetrical)
    - Wedges (Rising, Falling)
    - Flags (Bullish, Bearish)
    - Pennant
    - Rectangle
    - Cup & Handle
    - Consolidation
    """
    
    def __init__(self, tolerance: float = 0.01, min_pattern_bars: int = 20):
        """
        Args:
            tolerance: Mức độ sai số cho phép khi so sánh đỉnh/đáy (1% default - chặt chẽ hơn)
            min_pattern_bars: Số nến tối thiểu để tạo thành pattern
        """
        self.tolerance = tolerance
        self.min_pattern_bars = min_pattern_bars
        
        # Pattern priority (cao hơn = ưu tiên hơn khi conflict)
        self.pattern_priority = {
            'symmetrical_triangle': 100,  # Ưu tiên cao nhất
            'ascending_triangle': 95,
            'descending_triangle': 95,
            'head_and_shoulders': 90,
            'inverse_head_and_shoulders': 90,
            'double_top': 85,
            'double_bottom': 85,
            'triple_top': 80,
            'triple_bottom': 80,  # Giảm priority để tránh false positive
            'rising_wedge': 75,
            'falling_wedge': 75,
            'bullish_flag': 70,
            'bearish_flag': 70,
            'cup_and_handle': 65,
        }
        
    def detect_all_patterns(self, df: pd.DataFrame, lookback: int = 100) -> Dict:
        """
        Phát hiện tất cả patterns trên data window
        
        Args:
            df: DataFrame with columns: open, high, low, close, volume
            lookback: Số nến nhìn lại
            
        Returns:
            Dict chứa kết quả của từng pattern:
            {
                'head_and_shoulders': {'detected': bool, 'confidence': float, 'signal': 'BUY'/'SELL'},
                'double_top': {...},
                ...
            }
        """
        if len(df) < self.min_pattern_bars:
            return {}
            
        window = df.tail(lookback).copy()
        
        # Detect triangles FIRST (highest priority)
        symmetrical = self._detect_triangle(window, symmetrical=True)
        ascending = self._detect_triangle(window, ascending=True)
        descending = self._detect_triangle(window, descending=True)
        
        results = {
            # HIGH PRIORITY: Triangles (detect first)
            'symmetrical_triangle': symmetrical,
            'ascending_triangle': ascending,
            'descending_triangle': descending,
            
            # Reversal Patterns - Bearish
            'head_and_shoulders': self._detect_head_shoulders(window, inverse=False),
            'double_top': self._detect_double_top(window),
            'triple_top': self._detect_triple_top(window),
            'rising_wedge': self._detect_wedge(window, rising=True),
            'rounded_top': self._detect_rounded_top(window),
            'evening_star': self._detect_evening_star(window),
            
            # Reversal Patterns - Bullish
            'inverse_head_and_shoulders': self._detect_head_shoulders(window, inverse=True),
            'double_bottom': self._detect_double_bottom(window),
            'triple_bottom': self._detect_triple_bottom(window) if not symmetrical['detected'] else {'detected': False, 'confidence': 0.0},  # Skip nếu đã có symmetrical
            'falling_wedge': self._detect_wedge(window, rising=False),
            'rounded_bottom': self._detect_rounded_bottom(window),
            'morning_star': self._detect_morning_star(window),
            
            # Continuation Patterns
            'bullish_flag': self._detect_flag(window, bullish=True),
            'bearish_flag': self._detect_flag(window, bullish=False),
            'bullish_pennant': self._detect_pennant(window, bullish=True),
            'bearish_pennant': self._detect_pennant(window, bullish=False),
            'bullish_rectangle': self._detect_rectangle(window, bullish=True),
            'bearish_rectangle': self._detect_rectangle(window, bullish=False),
            'rising_channel': self._detect_channel(window, rising=True),
            'falling_channel': self._detect_channel(window, rising=False),
            
            # Neutral/Biphasic Patterns
            'diamond_top': self._detect_diamond(window, top=True),
            'diamond_bottom': self._detect_diamond(window, top=False),
            'expanding_triangle': self._detect_expanding_triangle(window),
            'megaphone': self._detect_megaphone(window),
            'cup_and_handle': self._detect_cup_handle(window),
            'inverse_cup_and_handle': self._detect_cup_handle(window, inverse=True),
            
            # Special
            'consolidation': self._detect_consolidation(window),
        }
        
        # Apply pattern priority for conflict resolution
        results = self._resolve_pattern_conflicts(results)
        
        return results
    
    def _resolve_pattern_conflicts(self, results: Dict) -> Dict:
        """
        Giải quyết xung đột khi nhiều pattern detected cùng lúc
        Ưu tiên pattern có priority cao hơn và confidence cao hơn
        """
        detected = {k: v for k, v in results.items() if v.get('detected', False)}
        
        if len(detected) <= 1:
            return results  # Không có conflict
            
        # Tìm pattern có priority + confidence cao nhất
        best_score = -1
        best_pattern = None
        
        for pattern_name, pattern_data in detected.items():
            priority = self.pattern_priority.get(pattern_name, 50)
            confidence = pattern_data.get('confidence', 0.0)
            score = priority * confidence  # Combine priority và confidence
            
            if score > best_score:
                best_score = score
                best_pattern = pattern_name
        
        # Giữ lại ONLY best pattern, disable các pattern khác
        filtered_results = {}
        for pattern_name, pattern_data in results.items():
            if pattern_name == best_pattern:
                filtered_results[pattern_name] = pattern_data
            else:
                filtered_results[pattern_name] = {'detected': False, 'confidence': 0.0}
                
        return filtered_results
    
    def get_strongest_pattern(self, results: Dict) -> Tuple[str, Dict]:
        """Trả về pattern có confidence cao nhất"""
        best_pattern = None
        best_conf = 0.0
        best_data = {}
        
        for pattern_name, data in results.items():
            if data.get('detected', False) and data.get('confidence', 0) > best_conf:
                best_conf = data['confidence']
                best_pattern = pattern_name
                best_data = data
                
        return best_pattern, best_data
    
    def _find_peaks_troughs(self, series: pd.Series, order: int = 5) -> Tuple[np.ndarray, np.ndarray]:
        """Tìm đỉnh và đáy cục bộ"""
        peaks = argrelextrema(series.values, np.greater, order=order)[0]
        troughs = argrelextrema(series.values, np.less, order=order)[0]
        return peaks, troughs
    
    def _is_similar_level(self, level1: float, level2: float) -> bool:
        """Kiểm tra 2 mức giá có tương đương không"""
        return abs(level1 - level2) / level1 <= self.tolerance
    
    def _detect_head_shoulders(self, df: pd.DataFrame, inverse: bool = False) -> Dict:
        """
        Head & Shoulders pattern:
        - 3 đỉnh: trái vai < đầu > vai phải
        - Neckline nối 2 đáy giữa các vai
        - Bearish pattern (SELL signal)
        
        Inverse H&S: ngược lại (SELL signal)
        """
        if len(df) < 30:
            return {'detected': False, 'confidence': 0.0}
            
        series = df['low'] if inverse else df['high']
        extrema, _ = self._find_peaks_troughs(series if inverse else -series)
        
        if len(extrema) < 3:
            return {'detected': False, 'confidence': 0.0}
            
        # Lấy 3 đỉnh/đáy gần nhất
        recent = extrema[-3:]
        
        left_shoulder_idx = recent[0]
        head_idx = recent[1]
        right_shoulder_idx = recent[2]
        
        left_shoulder = series.iloc[left_shoulder_idx]
        head = series.iloc[head_idx]
        right_shoulder = series.iloc[right_shoulder_idx]
        
        # Kiểm tra: vai trái ≈ vai phải, đầu cao/thấp hơn hẳn
        if inverse:
            # Inverse: head thấp nhất, 2 vai cao hơn
            is_pattern = (
                head < left_shoulder and 
                head < right_shoulder and
                self._is_similar_level(left_shoulder, right_shoulder)
            )
            signal = 'BUY'  # Sau khi phá neckline = BUY
        else:
            # Normal: head cao nhất, 2 vai thấp hơn
            is_pattern = (
                head > left_shoulder and 
                head > right_shoulder and
                self._is_similar_level(left_shoulder, right_shoulder)
            )
            signal = 'SELL'  # Sau khi phá neckline = SELL
            
        if not is_pattern:
            return {'detected': False, 'confidence': 0.0}
            
        # Tính confidence dựa trên độ rõ ràng của pattern
        shoulder_similarity = 1.0 - abs(left_shoulder - right_shoulder) / left_shoulder
        head_prominence = abs(head - (left_shoulder + right_shoulder) / 2) / head
        confidence = min(0.95, (shoulder_similarity * 0.5 + head_prominence * 10) * 0.7)
        
        return {
            'detected': True,
            'confidence': float(confidence),
            'signal': signal,
            'description': f"{'Inverse ' if inverse else ''}Head & Shoulders detected",
            'left_shoulder': float(left_shoulder),
            'head': float(head),
            'right_shoulder': float(right_shoulder),
        }
    
    def _detect_double_top(self, df: pd.DataFrame) -> Dict:
        """
        Double Top: 2 đỉnh gần như bằng nhau SAU UPTREND
        Bearish reversal pattern (SELL signal sau khi phá neckline)
        
        YÊU CẦU:
        1. Phải có uptrend trước peak 1 (ít nhất 10 nến tăng)
        2. 2 peaks ngang nhau (tolerance 2%)
        3. Có neckline (low giữa 2 peaks)
        4. Price hiện tại gần hoặc dưới neckline (đang phá hoặc đã phá)
        5. Distance hợp lý: 8-40 bars
        """
        if len(df) < 30:
            return {'detected': False, 'confidence': 0.0}
            
        peaks, _ = self._find_peaks_troughs(df['high'])
        
        if len(peaks) < 2:
            return {'detected': False, 'confidence': 0.0}
            
        # Lấy 2 đỉnh gần nhất
        last_two = peaks[-2:]
        peak1_idx = last_two[0]
        peak2_idx = last_two[1]
        peak1 = df['high'].iloc[peak1_idx]
        peak2 = df['high'].iloc[peak2_idx]
        
        # CHECK 1: 2 peaks phải tương đương
        if not self._is_similar_level(peak1, peak2):
            return {'detected': False, 'confidence': 0.0}
            
        # CHECK 2: Distance hợp lý (8-40 bars)
        distance = peak2_idx - peak1_idx
        if distance < 8 or distance > 40:
            return {'detected': False, 'confidence': 0.0}
            
        # CHECK 3: Phải có UPTREND trước peak1 (10+ nến)
        if peak1_idx < 15:  # Không đủ data để check uptrend
            return {'detected': False, 'confidence': 0.0}
            
        pre_peak1 = df['close'].iloc[peak1_idx-15:peak1_idx]
        uptrend_pct = (pre_peak1.iloc[-1] - pre_peak1.iloc[0]) / pre_peak1.iloc[0]
        
        if uptrend_pct < 0.008:  # Không có uptrend rõ ràng (< 0.8%)
            return {'detected': False, 'confidence': 0.0}
            
        # CHECK 4: Tìm neckline (low giữa 2 peaks)
        between_peaks = df['low'].iloc[peak1_idx:peak2_idx+1]
        neckline = between_peaks.min()
        
        # CHECK 5: Price hiện tại phải gần hoặc dưới neckline
        current_price = df['close'].iloc[-1]
        
        # Nếu price còn cao hơn neckline 2% → chưa phải double top
        if current_price > neckline * 1.02:
            return {'detected': False, 'confidence': 0.0}
            
        # CHECK 6: Peak2 phải là peak gần nhất (không có peak cao hơn sau đó)
        if len(df) > peak2_idx + 5:
            after_peak2 = df['high'].iloc[peak2_idx+1:]
            if len(after_peak2) > 0 and after_peak2.max() > peak2 * 0.998:
                return {'detected': False, 'confidence': 0.0}
        
        # Tính confidence
        similarity = 1.0 - abs(peak1 - peak2) / peak1
        neckline_break = max(0, (neckline - current_price) / neckline)  # 0 nếu chưa phá, dương nếu đã phá
        uptrend_strength = min(1.0, uptrend_pct * 50)  # Mạnh hơn = confidence cao hơn
        
        confidence = min(0.88, (similarity * 0.4 + neckline_break * 0.3 + uptrend_strength * 0.3) * 0.95)
        
        # Nếu confidence < 50% → không đủ tin cậy
        if confidence < 0.50:
            return {'detected': False, 'confidence': 0.0}
        
        return {
            'detected': True,
            'confidence': float(confidence),
            'signal': 'SELL',
            'description': 'Double Top detected - Bearish reversal',
            'peak1': float(peak1),
            'peak2': float(peak2),
            'neckline': float(neckline),
            'current_price': float(current_price),
            'neckline_broken': current_price < neckline,
            'distance_bars': int(distance),
            'uptrend_before': f"{uptrend_pct*100:.2f}%",
        }
    
    def _detect_double_bottom(self, df: pd.DataFrame) -> Dict:
        """
        Double Bottom: 2 đáy gần như bằng nhau SAU DOWNTREND
        Bullish reversal pattern (BUY signal sau khi phá neckline)
        
        YÊU CẦU:
        1. Phải có downtrend trước trough 1 (ít nhất 10 nến giảm)
        2. 2 troughs ngang nhau (tolerance 2%)
        3. Có neckline (high giữa 2 troughs)
        4. Price hiện tại gần hoặc trên neckline (đang phá hoặc đã phá)
        5. Distance hợp lý: 8-40 bars
        """
        if len(df) < 30:
            return {'detected': False, 'confidence': 0.0}
            
        _, troughs = self._find_peaks_troughs(df['low'])
        
        if len(troughs) < 2:
            return {'detected': False, 'confidence': 0.0}
            
        last_two = troughs[-2:]
        trough1_idx = last_two[0]
        trough2_idx = last_two[1]
        trough1 = df['low'].iloc[trough1_idx]
        trough2 = df['low'].iloc[trough2_idx]
        
        # CHECK 1: 2 troughs phải tương đương
        if not self._is_similar_level(trough1, trough2):
            return {'detected': False, 'confidence': 0.0}
            
        # CHECK 2: Distance hợp lý (8-40 bars)
        distance = trough2_idx - trough1_idx
        if distance < 8 or distance > 40:
            return {'detected': False, 'confidence': 0.0}
            
        # CHECK 3: Phải có DOWNTREND trước trough1 (10+ nến)
        if trough1_idx < 15:
            return {'detected': False, 'confidence': 0.0}
            
        pre_trough1 = df['close'].iloc[trough1_idx-15:trough1_idx]
        downtrend_pct = (pre_trough1.iloc[0] - pre_trough1.iloc[-1]) / pre_trough1.iloc[0]
        
        if downtrend_pct < 0.008:  # Không có downtrend rõ ràng (< 0.8%)
            return {'detected': False, 'confidence': 0.0}
            
        # CHECK 4: Tìm neckline (high giữa 2 troughs)
        between_troughs = df['high'].iloc[trough1_idx:trough2_idx+1]
        neckline = between_troughs.max()
        
        # CHECK 5: Price hiện tại phải gần hoặc trên neckline
        current_price = df['close'].iloc[-1]
        
        # Nếu price còn thấp hơn neckline 2% → chưa phải double bottom
        if current_price < neckline * 0.98:
            return {'detected': False, 'confidence': 0.0}
            
        # CHECK 6: Trough2 phải là trough gần nhất
        if len(df) > trough2_idx + 5:
            after_trough2 = df['low'].iloc[trough2_idx+1:]
            if len(after_trough2) > 0 and after_trough2.min() < trough2 * 1.002:
                return {'detected': False, 'confidence': 0.0}
        
        # Tính confidence
        similarity = 1.0 - abs(trough1 - trough2) / trough1
        neckline_break = max(0, (current_price - neckline) / neckline)
        downtrend_strength = min(1.0, downtrend_pct * 50)
        
        confidence = min(0.88, (similarity * 0.4 + neckline_break * 0.3 + downtrend_strength * 0.3) * 0.95)
        
        if confidence < 0.50:
            return {'detected': False, 'confidence': 0.0}
        
        return {
            'detected': True,
            'confidence': float(confidence),
            'signal': 'BUY',
            'description': 'Double Bottom detected - Bullish reversal',
            'trough1': float(trough1),
            'trough2': float(trough2),
            'neckline': float(neckline),
            'current_price': float(current_price),
            'neckline_broken': current_price > neckline,
            'distance_bars': int(distance),
            'downtrend_before': f"{downtrend_pct*100:.2f}%",
        }
    
    def _detect_triple_top(self, df: pd.DataFrame) -> Dict:
        """Triple Top: 3 đỉnh tương đương - Bearish"""
        if len(df) < 30:
            return {'detected': False, 'confidence': 0.0}
            
        peaks, _ = self._find_peaks_troughs(df['high'])
        
        if len(peaks) < 3:
            return {'detected': False, 'confidence': 0.0}
            
        last_three = peaks[-3:]
        p1 = df['high'].iloc[last_three[0]]
        p2 = df['high'].iloc[last_three[1]]
        p3 = df['high'].iloc[last_three[2]]
        
        if not (self._is_similar_level(p1, p2) and self._is_similar_level(p2, p3)):
            return {'detected': False, 'confidence': 0.0}
            
        avg_peak = (p1 + p2 + p3) / 3
        deviation = (abs(p1 - avg_peak) + abs(p2 - avg_peak) + abs(p3 - avg_peak)) / 3
        similarity = 1.0 - (deviation / avg_peak)
        confidence = min(0.88, similarity * 0.80)
        
        return {
            'detected': True,
            'confidence': float(confidence),
            'signal': 'SELL',
            'description': 'Triple Top - Strong bearish reversal',
        }
    
    def _detect_triple_bottom(self, df: pd.DataFrame) -> Dict:
        """Triple Bottom: 3 đáy tương đương - Bullish (CHẶT CHẼ)"""
        if len(df) < 40:
            return {'detected': False, 'confidence': 0.0}
            
        _, troughs = self._find_peaks_troughs(df['low'], order=7)  # Tăng order để tránh noise
        
        if len(troughs) < 3:
            return {'detected': False, 'confidence': 0.0}
            
        last_three = troughs[-3:]
        idx1, idx2, idx3 = last_three[0], last_three[1], last_three[2]
        t1 = df['low'].iloc[idx1]
        t2 = df['low'].iloc[idx2]
        t3 = df['low'].iloc[idx3]
        
        # 1. CHECK: 3 đáy phải THẬT SỰ ngang nhau (tolerance 0.5% thay vì 1%)
        strict_tolerance = 0.005
        if not (abs(t1 - t2) / t1 <= strict_tolerance and 
                abs(t2 - t3) / t2 <= strict_tolerance and
                abs(t1 - t3) / t1 <= strict_tolerance):
            return {'detected': False, 'confidence': 0.0}
            
        # 2. CHECK: Phải có downtrend TRƯỚC bottom thứ nhất (15 bars)
        if idx1 >= 15:
            pre_trend = df['close'].iloc[idx1-15:idx1]
            downtrend_pct = (pre_trend.iloc[0] - pre_trend.iloc[-1]) / pre_trend.iloc[0]
            if downtrend_pct < 0.008:  # Phải giảm ít nhất 0.8%
                return {'detected': False, 'confidence': 0.0}
        
        # 3. CHECK: Khoảng cách giữa các bottom (phải đủ xa - 10-50 bars)
        dist1 = idx2 - idx1
        dist2 = idx3 - idx2
        if not (10 <= dist1 <= 50 and 10 <= dist2 <= 50):
            return {'detected': False, 'confidence': 0.0}
            
        # 4. CHECK: Có neckline (peak giữa các bottom)
        peaks_between = []
        for i in range(idx1 + 1, idx3):
            if i in troughs:
                continue
            if df['high'].iloc[i] > max(t1, t2, t3) * 1.005:
                peaks_between.append(df['high'].iloc[i])
        
        if len(peaks_between) < 1:
            return {'detected': False, 'confidence': 0.0}  # Phải có ít nhất 1 peak giữa
            
        neckline = max(peaks_between)
        
        # 5. CHECK: Giá hiện tại gần neckline (chuẩn bị breakout)
        current_price = df['close'].iloc[-1]
        if current_price < neckline * 0.98:  # Phải trong 2% của neckline
            return {'detected': False, 'confidence': 0.0}
            
        # 6. CHECK: Không có bottom thấp hơn sau bottom3
        if len(df) > idx3 + 5:
            future_lows = df['low'].iloc[idx3+1:]
            if len(future_lows) > 0 and future_lows.min() < t3 * 0.995:
                return {'detected': False, 'confidence': 0.0}
        
        # Tính confidence
        avg_trough = (t1 + t2 + t3) / 3
        deviation = (abs(t1 - avg_trough) + abs(t2 - avg_trough) + abs(t3 - avg_trough)) / 3
        similarity = 1.0 - (deviation / avg_trough)
        
        # Bonus nếu giá rất gần neckline
        breakout_proximity = 1.0 - abs(current_price - neckline) / neckline
        
        confidence = min(0.90, similarity * 0.6 + breakout_proximity * 0.3)
        
        if confidence < 0.50:  # Minimum confidence giảm để dễ detect
            return {'detected': False, 'confidence': 0.0}
        
        return {
            'detected': True,
            'confidence': float(confidence),
            'signal': 'BUY',
            'description': 'Triple Bottom - Strong bullish reversal (validated)',
            'neckline': float(neckline),
            'bottoms': [float(t1), float(t2), float(t3)],
        }
    
    def _detect_triangle(self, df: pd.DataFrame, ascending=False, descending=False, symmetrical=False) -> Dict:
        """
        Triangle patterns:
        - Ascending: Đáy tăng dần, đỉnh ngang (Bullish)
        - Descending: Đỉnh giảm dần, đáy ngang (Bearish)
        - Symmetrical: Cả 2 hội tụ (Continuation)
        """
        if len(df) < 25:
            return {'detected': False, 'confidence': 0.0}
            
        peaks, troughs = self._find_peaks_troughs(df['high'])
        _, lows_idx = self._find_peaks_troughs(df['low'])
        
        if len(peaks) < 2 or len(troughs) < 2:
            return {'detected': False, 'confidence': 0.0}
            
        # Linear regression cho đỉnh và đáy
        highs = df['high'].iloc[peaks[-3:]] if len(peaks) >= 3 else df['high'].iloc[peaks]
        lows = df['low'].iloc[lows_idx[-3:]] if len(lows_idx) >= 3 else df['low'].iloc[lows_idx]
        
        if len(highs) < 2 or len(lows) < 2:
            return {'detected': False, 'confidence': 0.0}
            
        high_slope, _, high_r, _, _ = linregress(range(len(highs)), highs.values)
        low_slope, _, low_r, _, _ = linregress(range(len(lows)), lows.values)
        
        # Xác định loại triangle
        detected = False
        signal = 'NONE'
        pattern_type = ''
        
        if ascending:
            # Ascending: đáy tăng, đỉnh ngang
            if low_slope > 0.01 and abs(high_slope) < 0.01:
                detected = True
                signal = 'BUY'
                pattern_type = 'Ascending Triangle'
        elif descending:
            # Descending: đỉnh giảm, đáy ngang
            if high_slope < -0.01 and abs(low_slope) < 0.01:
                detected = True
                signal = 'SELL'
                pattern_type = 'Descending Triangle'
        elif symmetrical:
            # Symmetrical: cả 2 hội tụ - PHẢI có convergence rõ ràng
            # Lower lows tăng dần + Higher highs giảm dần
            is_converging = (low_slope > 0.008 and high_slope < -0.008)
            
            # Check regression fit (R-squared phải cao)
            good_fit = (abs(high_r) > 0.7 and abs(low_r) > 0.7)
            
            # Check convergence angle (không quá rộng, không quá hẹp)
            slope_ratio = abs(low_slope / high_slope) if high_slope != 0 else 0
            good_angle = (0.3 < slope_ratio < 3.0)  # Góc hợp lý
            
            if is_converging and good_fit and good_angle:
                detected = True
                signal = 'CONTINUATION'  # Theo xu hướng trước đó
                pattern_type = 'Symmetrical Triangle'
                
                # Check price compression (range phải thu hẹp)
                recent_range = df['high'].iloc[-5:].max() - df['low'].iloc[-5:].max()
                earlier_range = df['high'].iloc[-25:-20].max() - df['low'].iloc[-25:-20].min()
                if recent_range >= earlier_range:  # Range phải thu hẹp
                    detected = False
                
        if not detected:
            return {'detected': False, 'confidence': 0.0}
            
        confidence = min(0.85, (abs(high_r) + abs(low_r)) / 2 * 0.9)
        
        return {
            'detected': True,
            'confidence': float(confidence),
            'signal': signal,
            'description': f'{pattern_type} detected',
            'high_slope': float(high_slope),
            'low_slope': float(low_slope),
        }
    
    def _detect_wedge(self, df: pd.DataFrame, rising: bool = True) -> Dict:
        """
        Wedge patterns:
        - Rising Wedge: Cả đỉnh và đáy đều tăng nhưng hội tụ (Bearish)
        - Falling Wedge: Cả đỉnh và đáy đều giảm nhưng hội tụ (Bullish)
        """
        if len(df) < 25:
            return {'detected': False, 'confidence': 0.0}
            
        peaks, _ = self._find_peaks_troughs(df['high'])
        _, troughs = self._find_peaks_troughs(df['low'])
        
        if len(peaks) < 3 or len(troughs) < 3:
            return {'detected': False, 'confidence': 0.0}
            
        highs = df['high'].iloc[peaks[-3:]]
        lows = df['low'].iloc[troughs[-3:]]
        
        high_slope, _, high_r, _, _ = linregress(range(len(highs)), highs.values)
        low_slope, _, low_r, _, _ = linregress(range(len(lows)), lows.values)
        
        detected = False
        signal = 'NONE'
        
        if rising:
            # Rising Wedge: cả 2 tăng nhưng low tăng nhanh hơn (hội tụ)
            if high_slope > 0 and low_slope > 0 and low_slope > high_slope * 0.5:
                detected = True
                signal = 'SELL'  # Bearish reversal
        else:
            # Falling Wedge: cả 2 giảm nhưng high giảm nhanh hơn (hội tụ)
            if high_slope < 0 and low_slope < 0 and abs(high_slope) > abs(low_slope) * 0.5:
                detected = True
                signal = 'BUY'  # Bullish reversal
                
        if not detected:
            return {'detected': False, 'confidence': 0.0}
            
        confidence = min(0.82, (abs(high_r) + abs(low_r)) / 2 * 0.85)
        
        return {
            'detected': True,
            'confidence': float(confidence),
            'signal': signal,
            'description': f"{'Rising' if rising else 'Falling'} Wedge - {'Bearish' if rising else 'Bullish'}",
        }
    
    def _detect_flag(self, df: pd.DataFrame, bullish: bool = True) -> Dict:
        """
        Flag pattern:
        - Pole: Di chuyển mạnh theo 1 hướng
        - Flag: Consolidation ngắn ngược chiều pole
        - Continuation pattern
        """
        if len(df) < 30:
            return {'detected': False, 'confidence': 0.0}
            
        # Tìm pole: 10-20 nến có momentum mạnh
        pole_len = 15
        if len(df) < pole_len + 10:
            return {'detected': False, 'confidence': 0.0}
            
        pole = df['close'].iloc[-pole_len-10:-10]
        flag_section = df['close'].iloc[-10:]
        
        # Pole phải có momentum rõ ràng
        pole_change = (pole.iloc[-1] - pole.iloc[0]) / pole.iloc[0]
        
        if bullish:
            # Bullish flag: pole tăng mạnh, flag giảm nhẹ hoặc sideway
            if pole_change < 0.01:  # Pole không đủ mạnh
                return {'detected': False, 'confidence': 0.0}
            flag_slope, _, flag_r, _, _ = linregress(range(len(flag_section)), flag_section.values)
            # Flag phải giảm hoặc sideway
            if flag_slope > 0.001:
                return {'detected': False, 'confidence': 0.0}
        else:
            # Bearish flag: pole giảm mạnh, flag tăng nhẹ hoặc sideway
            if pole_change > -0.01:
                return {'detected': False, 'confidence': 0.0}
            flag_slope, _, flag_r, _, _ = linregress(range(len(flag_section)), flag_section.values)
            # Flag phải tăng hoặc sideway
            if flag_slope < -0.001:
                return {'detected': False, 'confidence': 0.0}
                
        confidence = min(0.80, abs(pole_change) * 10 * 0.75)
        
        return {
            'detected': True,
            'confidence': float(confidence),
            'signal': 'BUY' if bullish else 'SELL',
            'description': f"{'Bullish' if bullish else 'Bearish'} Flag - Continuation",
            'pole_change_pct': float(pole_change * 100),
        }
    
    def _detect_pennant(self, df: pd.DataFrame, bullish: bool = True) -> Dict:
        """
        Pennant: Tương tự flag nhưng flag section là symmetrical triangle nhỏ
        Bullish Pennant: Pole tăng + triangle
        Bearish Pennant: Pole giảm + triangle
        """
        if len(df) < 30:
            return {'detected': False, 'confidence': 0.0}
            
        # Kiểm tra pole
        pole_len = 12
        pole = df['close'].iloc[-pole_len-8:-8]
        pennant_section = df.iloc[-8:]
        
        pole_change = (pole.iloc[-1] - pole.iloc[0]) / pole.iloc[0]
        
        # Check direction
        if bullish:
            if pole_change < 0.008:  # Pole phải tăng
                return {'detected': False, 'confidence': 0.0}
        else:
            if pole_change > -0.008:  # Pole phải giảm
                return {'detected': False, 'confidence': 0.0}
            
        # Pennant section phải có triangle shape
        triangle_result = self._detect_triangle(pennant_section, symmetrical=True)
        
        if not triangle_result.get('detected', False):
            return {'detected': False, 'confidence': 0.0}
            
        signal = 'BUY' if bullish else 'SELL'
        confidence = min(0.78, triangle_result['confidence'] * 0.9)
        
        return {
            'detected': True,
            'confidence': float(confidence),
            'signal': signal,
            'description': f"{'Bullish' if bullish else 'Bearish'} Pennant - Strong continuation",
        }
    
    def _detect_rectangle(self, df: pd.DataFrame, bullish: bool = None) -> Dict:
        """
        Rectangle (Range): Giá dao động trong range ngang
        Bullish Rectangle: Continuation trong uptrend
        Bearish Rectangle: Continuation trong downtrend
        Neutral Rectangle: Chờ breakout
        """
        if len(df) < 20:
            return {'detected': False, 'confidence': 0.0}
            
        highs = df['high'].tail(20)
        lows = df['low'].tail(20)
        
        # Kiểm tra xem high/low có nằm trong range không
        resistance = highs.max()
        support = lows.min()
        range_size = (resistance - support) / support
        
        # Range phải đủ nhỏ (sideway)
        if range_size > 0.03:  # > 3% không phải rectangle
            return {'detected': False, 'confidence': 0.0}
            
        # Kiểm tra price touches support/resistance nhiều lần
        touches_resistance = (highs > resistance * 0.995).sum()
        touches_support = (lows < support * 1.005).sum()
        
        if touches_resistance < 2 or touches_support < 2:
            return {'detected': False, 'confidence': 0.0}
            
        # Xác định signal
        current_price = df['close'].iloc[-1]
        
        if bullish is not None:
            # Specific rectangle type
            if bullish:
                # Bullish rectangle: cần có uptrend trước đó
                pre_rect = df['close'].iloc[-30:-20] if len(df) >= 30 else df['close'].iloc[:-20]
                if len(pre_rect) > 5:
                    trend = (pre_rect.iloc[-1] - pre_rect.iloc[0]) / pre_rect.iloc[0]
                    if trend < 0.005:  # Không có uptrend
                        return {'detected': False, 'confidence': 0.0}
                signal = 'BUY'
                desc = 'Bullish Rectangle - Consolidation before continuation'
            else:
                # Bearish rectangle
                pre_rect = df['close'].iloc[-30:-20] if len(df) >= 30 else df['close'].iloc[:-20]
                if len(pre_rect) > 5:
                    trend = (pre_rect.iloc[0] - pre_rect.iloc[-1]) / pre_rect.iloc[0]
                    if trend < 0.005:  # Không có downtrend
                        return {'detected': False, 'confidence': 0.0}
                signal = 'SELL'
                desc = 'Bearish Rectangle - Consolidation before continuation'
        else:
            # Neutral - check breakout
            if current_price > resistance * 1.001:
                signal = 'BUY'
                desc = 'Rectangle Breakout - Bullish'
            elif current_price < support * 0.999:
                signal = 'SELL'
                desc = 'Rectangle Breakout - Bearish'
            else:
                signal = 'WAIT'
                desc = 'Rectangle/Range - Wait for breakout'
            
        confidence = min(0.75, 0.5 + (touches_resistance + touches_support) * 0.05)
        
        return {
            'detected': True,
            'confidence': float(confidence),
            'signal': signal,
            'description': desc,
            'resistance': float(resistance),
            'support': float(support),
        }
    
    def _detect_cup_handle(self, df: pd.DataFrame, inverse: bool = False) -> Dict:
        """
        Cup & Handle: 
        - Cup: Đáy hình chữ U (normal) hoặc đỉnh ngược (inverse)
        - Handle: Pullback nhỏ sau cup
        - Normal: Bullish continuation
        - Inverse: Bearish continuation
        """
        if len(df) < 40:
            return {'detected': False, 'confidence': 0.0}
            
        # Cup: 60-80% data, Handle: 20-40%
        cup_len = int(len(df) * 0.7)
        cup_series = df['close' if not inverse else 'close'].iloc[:cup_len]
        handle = df['close'].iloc[cup_len:]
        
        if len(handle) < 5:
            return {'detected': False, 'confidence': 0.0}
            
        # Cup shape check
        cup_left = cup_series.iloc[:len(cup_series)//3].mean()
        cup_right = cup_series.iloc[2*len(cup_series)//3:].mean()
        
        if not inverse:
            # Normal: đáy thấp hơn 2 đầu
            cup_bottom = cup_series.iloc[len(cup_series)//3:2*len(cup_series)//3].min()
            if not (cup_bottom < cup_left * 0.98 and cup_bottom < cup_right * 0.98):
                return {'detected': False, 'confidence': 0.0}
            # Handle: pullback giảm
            handle_slope, _, handle_r, _, _ = linregress(range(len(handle)), handle.values)
            if handle_slope > 0.001:
                return {'detected': False, 'confidence': 0.0}
            signal = 'BUY'
            desc = 'Cup & Handle - Bullish breakout imminent'
        else:
            # Inverse: đỉnh cao hơn 2 đầu
            cup_top = cup_series.iloc[len(cup_series)//3:2*len(cup_series)//3].max()
            if not (cup_top > cup_left * 1.02 and cup_top > cup_right * 1.02):
                return {'detected': False, 'confidence': 0.0}
            # Handle: pullback tăng
            handle_slope, _, handle_r, _, _ = linregress(range(len(handle)), handle.values)
            if handle_slope < -0.001:
                return {'detected': False, 'confidence': 0.0}
            signal = 'SELL'
            desc = 'Inverse Cup & Handle - Bearish breakdown imminent'
            
        # Cup symmetry
        cup_symmetry = 1.0 - abs(cup_left - cup_right) / cup_left
        if cup_symmetry < 0.95:
            return {'detected': False, 'confidence': 0.0}
            
        confidence = min(0.85, cup_symmetry * 0.88)
        
        return {
            'detected': True,
            'confidence': float(confidence),
            'signal': signal,
            'description': desc,
        }
    
    def _detect_rounded_top(self, df: pd.DataFrame) -> Dict:
        """
        Rounded Top (Bearish reversal): Giá tạo đỉnh tròn như nửa vòng tròn
        """
        if len(df) < 30:
            return {'detected': False, 'confidence': 0.0}
            
        highs = df['high'].tail(30)
        
        # Fit polynomial degree 2 (parabola)
        x = np.arange(len(highs))
        try:
            coeffs = np.polyfit(x, highs.values, 2)
            # Coefficient a < 0 = parabola opens downward (rounded top)
            if coeffs[0] >= -0.00001:  # Không đủ cong xuống
                return {'detected': False, 'confidence': 0.0}
                
            # R-squared để đo độ fit
            poly = np.poly1d(coeffs)
            y_pred = poly(x)
            ss_res = np.sum((highs.values - y_pred) ** 2)
            ss_tot = np.sum((highs.values - np.mean(highs.values)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
            
            if r_squared < 0.7:  # Không đủ rounded
                return {'detected': False, 'confidence': 0.0}
                
            confidence = min(0.82, r_squared * 0.85)
            
            return {
                'detected': True,
                'confidence': float(confidence),
                'signal': 'SELL',
                'description': 'Rounded Top - Bearish reversal',
            }
        except:
            return {'detected': False, 'confidence': 0.0}
    
    def _detect_rounded_bottom(self, df: pd.DataFrame) -> Dict:
        """
        Rounded Bottom (Bullish reversal): Giá tạo đáy tròn như nửa vòng tròn ngược
        """
        if len(df) < 30:
            return {'detected': False, 'confidence': 0.0}
            
        lows = df['low'].tail(30)
        
        x = np.arange(len(lows))
        try:
            coeffs = np.polyfit(x, lows.values, 2)
            # Coefficient a > 0 = parabola opens upward (rounded bottom)
            if coeffs[0] <= 0.00001:
                return {'detected': False, 'confidence': 0.0}
                
            poly = np.poly1d(coeffs)
            y_pred = poly(x)
            ss_res = np.sum((lows.values - y_pred) ** 2)
            ss_tot = np.sum((lows.values - np.mean(lows.values)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
            
            if r_squared < 0.7:
                return {'detected': False, 'confidence': 0.0}
                
            confidence = min(0.82, r_squared * 0.85)
            
            return {
                'detected': True,
                'confidence': float(confidence),
                'signal': 'BUY',
                'description': 'Rounded Bottom - Bullish reversal',
            }
        except:
            return {'detected': False, 'confidence': 0.0}
    
    def _detect_consolidation(self, df: pd.DataFrame) -> Dict:
        """
        Consolidation: Giá dao động nhỏ trong thời gian dài
        Thường là breakout setup
        """
        if len(df) < 15:
            return {'detected': False, 'confidence': 0.0}
            
        closes = df['close'].tail(15)
        
        # Tính volatility
        returns = closes.pct_change().dropna()
        volatility = returns.std()
        
        # Consolidation = low volatility
        if volatility > 0.01:  # > 1% std = không phải consolidation
            return {'detected': False, 'confidence': 0.0}
            
        # Tính range
        price_range = (closes.max() - closes.min()) / closes.mean()
        
        if price_range > 0.02:  # > 2% range = không consolidation
            return {'detected': False, 'confidence': 0.0}
            
        confidence = min(0.70, (1.0 - volatility * 50) * 0.75)
        
        return {
            'detected': True,
            'confidence': float(confidence),
            'signal': 'WAIT',
            'description': 'Consolidation - Expect breakout soon',
            'volatility': float(volatility),
            'range_pct': float(price_range * 100),
        }


    def _detect_evening_star(self, df: pd.DataFrame) -> Dict:
        """
        Evening Star (Bearish reversal candlestick pattern):
        3 nến: Tăng mạnh → Doji/Small body → Giảm mạnh
        """
        if len(df) < 3:
            return {'detected': False, 'confidence': 0.0}
            
        c1, c2, c3 = df.iloc[-3:].itertuples(index=False, name=None)
        
        # Nến 1: Bullish (close > open)
        body1 = c1[3] - c1[0]  # close - open
        if body1 <= 0:
            return {'detected': False, 'confidence': 0.0}
            
        # Nến 2: Small body (doji-like)
        body2 = abs(c2[3] - c2[0])
        range2 = c2[1] - c2[2]  # high - low
        if body2 > range2 * 0.3:  # Body > 30% range
            return {'detected': False, 'confidence': 0.0}
            
        # Nến 3: Bearish (close < open)
        body3 = c3[0] - c3[3]  # open - close
        if body3 <= 0:
            return {'detected': False, 'confidence': 0.0}
            
        # Nến 3 phải close dưới middle của nến 1
        if c3[3] > (c1[0] + c1[3]) / 2:
            return {'detected': False, 'confidence': 0.0}
            
        confidence = min(0.80, 0.75)
        
        return {
            'detected': True,
            'confidence': float(confidence),
            'signal': 'SELL',
            'description': 'Evening Star - Bearish reversal candle pattern',
        }
    
    def _detect_morning_star(self, df: pd.DataFrame) -> Dict:
        """
        Morning Star (Bullish reversal candlestick pattern):
        3 nến: Giảm mạnh → Doji/Small body → Tăng mạnh
        """
        if len(df) < 3:
            return {'detected': False, 'confidence': 0.0}
            
        c1, c2, c3 = df.iloc[-3:].itertuples(index=False, name=None)
        
        # Nến 1: Bearish
        body1 = c1[0] - c1[3]
        if body1 <= 0:
            return {'detected': False, 'confidence': 0.0}
            
        # Nến 2: Small body
        body2 = abs(c2[3] - c2[0])
        range2 = c2[1] - c2[2]
        if body2 > range2 * 0.3:
            return {'detected': False, 'confidence': 0.0}
            
        # Nến 3: Bullish
        body3 = c3[3] - c3[0]
        if body3 <= 0:
            return {'detected': False, 'confidence': 0.0}
            
        # Nến 3 phải close trên middle của nến 1
        if c3[3] < (c1[0] + c1[3]) / 2:
            return {'detected': False, 'confidence': 0.0}
            
        confidence = min(0.80, 0.75)
        
        return {
            'detected': True,
            'confidence': float(confidence),
            'signal': 'BUY',
            'description': 'Morning Star - Bullish reversal candle pattern',
        }
    
    def _detect_diamond(self, df: pd.DataFrame, top: bool = True) -> Dict:
        """
        Diamond Top/Bottom: Expanding rồi contracting
        - Nửa đầu: highs/lows diverge (widening)
        - Nửa sau: highs/lows converge (narrowing)
        """
        if len(df) < 40:
            return {'detected': False, 'confidence': 0.0}
            
        mid = len(df) // 2
        first_half = df.iloc[:mid]
        second_half = df.iloc[mid:]
        
        # First half: expanding (volatility tăng)
        fh_range = (first_half['high'].max() - first_half['low'].min())
        fh_early = first_half.iloc[:len(first_half)//2]
        fh_late = first_half.iloc[len(first_half)//2:]
        fh_expansion = (fh_late['high'].max() - fh_late['low'].min()) / (fh_early['high'].max() - fh_early['low'].min())
        
        if fh_expansion < 1.1:  # Không expand đủ
            return {'detected': False, 'confidence': 0.0}
            
        # Second half: contracting
        sh_early = second_half.iloc[:len(second_half)//2]
        sh_late = second_half.iloc[len(second_half)//2:]
        sh_contraction = (sh_late['high'].max() - sh_late['low'].min()) / (sh_early['high'].max() - sh_early['low'].min())
        
        if sh_contraction > 0.9:  # Không contract đủ
            return {'detected': False, 'confidence': 0.0}
            
        confidence = min(0.78, 0.70)
        signal = 'SELL' if top else 'BUY'
        
        return {
            'detected': True,
            'confidence': float(confidence),
            'signal': signal,
            'description': f"Diamond {'Top' if top else 'Bottom'} - {'Bearish' if top else 'Bullish'} reversal",
        }
    
    def _detect_expanding_triangle(self, df: pd.DataFrame) -> Dict:
        """
        Expanding Triangle (Broadening Formation): Highs cao dần, lows thấp dần
        Volatility tăng - thường bearish
        """
        if len(df) < 25:
            return {'detected': False, 'confidence': 0.0}
            
        peaks, troughs = self._find_peaks_troughs(df['high'])
        _, lows_idx = self._find_peaks_troughs(df['low'])
        
        if len(peaks) < 3 or len(lows_idx) < 3:
            return {'detected': False, 'confidence': 0.0}
            
        recent_peaks = df['high'].iloc[peaks[-3:]]
        recent_lows = df['low'].iloc[lows_idx[-3:]]
        
        # Highs phải tăng dần
        if not (recent_peaks.iloc[-1] > recent_peaks.iloc[0]):
            return {'detected': False, 'confidence': 0.0}
            
        # Lows phải giảm dần
        if not (recent_lows.iloc[-1] < recent_lows.iloc[0]):
            return {'detected': False, 'confidence': 0.0}
            
        confidence = min(0.76, 0.68)
        
        return {
            'detected': True,
            'confidence': float(confidence),
            'signal': 'SELL',
            'description': 'Expanding Triangle - Increased volatility, bearish',
        }
    
    def _detect_megaphone(self, df: pd.DataFrame) -> Dict:
        """
        Megaphone Pattern: Tương tự Expanding Triangle nhưng dài hơn và wild hơn
        """
        if len(df) < 40:
            return {'detected': False, 'confidence': 0.0}
            
        # Chia làm 3 sections
        section_len = len(df) // 3
        s1 = df.iloc[:section_len]
        s2 = df.iloc[section_len:2*section_len]
        s3 = df.iloc[2*section_len:]
        
        r1 = s1['high'].max() - s1['low'].min()
        r2 = s2['high'].max() - s2['low'].min()
        r3 = s3['high'].max() - s3['low'].min()
        
        # Range phải tăng dần
        if not (r2 > r1 * 1.05 and r3 > r2 * 1.05):
            return {'detected': False, 'confidence': 0.0}
            
        confidence = min(0.74, 0.65)
        
        return {
            'detected': True,
            'confidence': float(confidence),
            'signal': 'SELL',
            'description': 'Megaphone Pattern - High volatility expansion',
        }
    
    def _detect_channel(self, df: pd.DataFrame, rising: bool = True) -> Dict:
        """
        Channel: Giá di chuyển trong channel song song
        - Rising Channel: Uptrend với parallel support/resistance
        - Falling Channel: Downtrend với parallel support/resistance
        """
        if len(df) < 30:
            return {'detected': False, 'confidence': 0.0}
            
        highs = df['high'].tail(30)
        lows = df['low'].tail(30)
        
        # Linear regression
        x = np.arange(len(highs))
        high_slope, high_intercept, high_r, _, _ = linregress(x, highs.values)
        low_slope, low_intercept, low_r, _, _ = linregress(x, lows.values)
        
        # Slopes phải gần bằng nhau (parallel)
        slope_diff = abs(high_slope - low_slope) / abs(high_slope) if high_slope != 0 else 999
        if slope_diff > 0.3:  # Không parallel
            return {'detected': False, 'confidence': 0.0}
            
        # Check direction
        if rising:
            if high_slope <= 0.0001 or low_slope <= 0.0001:
                return {'detected': False, 'confidence': 0.0}
            signal = 'BUY'
            desc = 'Rising Channel - Uptrend continuation'
        else:
            if high_slope >= -0.0001 or low_slope >= -0.0001:
                return {'detected': False, 'confidence': 0.0}
            signal = 'SELL'
            desc = 'Falling Channel - Downtrend continuation'
            
        # R-squared phải cao (fit tốt)
        avg_r = (abs(high_r) + abs(low_r)) / 2
        if avg_r < 0.7:
            return {'detected': False, 'confidence': 0.0}
            
        confidence = min(0.80, avg_r * 0.85)
        
        return {
            'detected': True,
            'confidence': float(confidence),
            'signal': signal,
            'description': desc,
        }

# ============================================================================
# TÍCH HỢP VÀO BOT
# ============================================================================

def integrate_pattern_detection(live_data: pd.DataFrame, logger=None) -> Dict:
    """
    Function để tích hợp vào bot chính
    
    Args:
        live_data: DataFrame from bot (OHLCV)
        logger: Logger instance
        
    Returns:
        Dict với pattern detection results
    """
    try:
        detector = ChartPatternDetector(tolerance=0.02, min_pattern_bars=20)
        
        # Phát hiện tất cả patterns
        results = detector.detect_all_patterns(live_data, lookback=100)
        
        # Lấy pattern mạnh nhất
        strongest_pattern, pattern_data = detector.get_strongest_pattern(results)
        
        if logger and strongest_pattern:
            logger.info(f"📊 CHART PATTERN: {strongest_pattern.upper()}")
            logger.info(f"   Confidence: {pattern_data.get('confidence', 0)*100:.1f}%")
            logger.info(f"   Signal: {pattern_data.get('signal', 'NONE')}")
            logger.info(f"   {pattern_data.get('description', '')}")
        
        return {
            'all_patterns': results,
            'strongest_pattern': strongest_pattern,
            'pattern_data': pattern_data,
            'has_pattern': strongest_pattern is not None,
        }
        
    except Exception as e:
        if logger:
            logger.warning(f"⚠️ Pattern detection error: {e}")
        return {
            'all_patterns': {},
            'strongest_pattern': None,
            'pattern_data': {},
            'has_pattern': False,
        }
