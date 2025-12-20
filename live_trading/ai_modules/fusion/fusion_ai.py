import numpy as np

class FusionAIUpgraded:
    """
    Upgraded FusionAI: combines all logic from v1, v3, v4, v5 (weight, threshold, priority, veto, ensemble).
    Use this class for all fusion logic in the bot pipeline.
    """
    def __init__(self, weights=None, thresholds=None, priority=None):
        self.weights = weights or {
            'trend': 0.30,
            'pattern': 0.20,
            'macd': 0.20,
            'momentum': 0.20,
            'volume': 0.10,
            'structure': 0.20,
            'reversal': 0.10,
            'candle': 0.05,
            'liquidity': 0.20,
            'sentiment': 0.025
        }
        self.thresholds = thresholds or {'strong': 0.7, 'weak': 0.4}
        self.priority = priority or ['structure','trend','liquidity','pattern','macd','momentum','volume','reversal','candle','sentiment']
        self.veto_keys = ['volatility','risk_block','session']

    def fuse(self, signals, context=None):
        context = context or {}
        reasons = []
        meta = {'component_scores':{}}
        # Veto logic
        vol = signals.get('volatility') or signals.get('vol_ai') or {}
        if isinstance(vol, dict):
            vol_idx = float(vol.get('vol_index', 0.0))
            regime = vol.get('regime','unknown')
            if regime == 'high_vol' or vol_idx > context.get('volatility_block_threshold', 0.05):
                return {'side':'none','score':0.0,'reasons':['veto_volatility'],'meta':{'volatility':vol},'blocked':True,'blocked_reason':'high_volatility'}
        rb = signals.get('risk_block')
        if rb:
            blocked_flag = False
            if isinstance(rb, (list,tuple)) and len(rb)>=1:
                blocked_flag = bool(rb[0])
                blocked_reason = rb[1] if len(rb)>1 else 'risk_block'
            elif isinstance(rb, dict):
                blocked_flag = bool(rb.get('blocked',False))
                blocked_reason = rb.get('reason','risk_block')
            if blocked_flag:
                return {'side':'none','score':0.0,'reasons':['veto_risk'],'meta':{'risk_block':rb},'blocked':True,'blocked_reason':blocked_reason}
        # Weighted voting
        buy_score = 0.0
        sell_score = 0.0
        for key in self.priority:
            weight = self.weights.get(key, 0.0)
            val = signals.get(key)
            side, score = self._read(val)
            meta['component_scores'][key] = {'side':side,'score':score,'weight':weight}
            if side == 'buy':
                buy_score += score * weight
                reasons.append(f'{key}=buy({score:.2f})')
            elif side == 'sell':
                sell_score += score * weight
                reasons.append(f'{key}=sell({score:.2f})')
            else:
                reasons.append(f'{key}=none')
        max_possible = sum(self.weights.values()) or 1.0
        buy_score_norm = buy_score / max_possible
        sell_score_norm = sell_score / max_possible
        # MACD VETO logic: nếu MACD cho tín hiệu mạnh ngược chiều, block lệnh
        macd_signal = signals.get('macd')
        if isinstance(macd_signal, (tuple, list)):
            macd_side, macd_score = macd_signal[0], float(macd_signal[1] or 0.0)
            if macd_score >= self.thresholds['strong']:
                if macd_side == 'buy' and context.get('force_sell', False):
                    return {'side':'none','score':0.0,'reasons':['veto_macd_buy'],'meta':{'macd':macd_signal},'blocked':True,'blocked_reason':'macd_buy_veto'}
                if macd_side == 'sell' and context.get('force_buy', False):
                    return {'side':'none','score':0.0,'reasons':['veto_macd_sell'],'meta':{'macd':macd_signal},'blocked':True,'blocked_reason':'macd_sell_veto'}
        # Decision
        if buy_score_norm >= self.thresholds['strong'] and buy_score_norm > sell_score_norm:
            return {'side':'buy','score':round(buy_score_norm,3),'reasons':reasons,'meta':meta}
        if sell_score_norm >= self.thresholds['strong'] and sell_score_norm > buy_score_norm:
            return {'side':'sell','score':round(sell_score_norm,3),'reasons':reasons,'meta':meta}
        return {'side':'none','score':round(max(buy_score_norm,sell_score_norm),3),'reasons':reasons,'meta':meta}
    def _read(self, sig):
        if sig is None:
            return ('none', 0.0)
        if isinstance(sig, (tuple, list)):
            return (str(sig[0]).lower(), float(sig[1] or 0.0))
        if isinstance(sig, dict):
            return (str(sig.get('side','none')).lower(), float(sig.get('score',0.0)))
        if isinstance(sig, str):
            s = sig.lower()
            if s in ('buy','long','bull','1','+1'): return ('buy',1.0)
            if s in ('sell','short','bear','-1'): return ('sell',1.0)
            return ('none',0.0)
        return ('none',0.0)

