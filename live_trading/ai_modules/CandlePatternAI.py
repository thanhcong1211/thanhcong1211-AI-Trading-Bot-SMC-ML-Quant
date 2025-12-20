import numpy as np

class CandlePatternAI:
    def __init__(self):
        pass

    def is_bullish(self, o, c):
        return c > o

    def is_bearish(self, o, c):
        return c < o

    ###############################################################
    # 1. BASIC CANDLE PATTERNS
    ###############################################################
    def doji(self, o, h, l, c):
        return abs(c - o) <= (h - l) * 0.1

    def spinning_top(self, o, h, l, c):
        body = abs(c - o)
        wick = (h - l) - body
        return body <= wick * 0.5

    def marubozu_bull(self, o, h, l, c):
        return c > o and abs(h - c) <= (h - l) * 0.05 and abs(o - l) <= (h - l) * 0.05

    def marubozu_bear(self, o, h, l, c):
        return c < o and abs(h - o) <= (h - l) * 0.05 and abs(c - l) <= (h - l) * 0.05

    ###############################################################
    # 2. REVERSAL PATTERNS
    ###############################################################
    def hammer(self, o, h, l, c):
        body = abs(c - o)
        lower = o - l if c >= o else c - l
        upper = h - c if c >= o else h - o
        return lower >= body * 2 and upper <= body

    def inverted_hammer(self, o, h, l, c):
        body = abs(c - o)
        lower = o - l if c >= o else c - l
        upper = h - c if c >= o else h - o
        return upper >= body * 2 and lower <= body

    def hanging_man(self, o, h, l, c):
        return self.hammer(o, h, l, c)

    def shooting_star(self, o, h, l, c):
        return self.inverted_hammer(o, h, l, c)

    def bullish_engulfing(self, prev, curr):
        return prev['c'] < prev['o'] and curr['c'] > curr['o'] and curr['c'] >= prev['o'] and curr['o'] <= prev['c']

    def bearish_engulfing(self, prev, curr):
        return prev['c'] > prev['o'] and curr['c'] < curr['o'] and curr['c'] <= prev['o'] and curr['o'] >= prev['c']

    def piercing(self, prev, o, h, l, c):
        mid = prev['o'] + (prev['c'] - prev['o']) / 2
        return prev['c'] < prev['o'] and c > mid and o < prev['c']

    def dark_cloud(self, prev, o, h, l, c):
        mid = prev['c'] + (prev['o'] - prev['c']) / 2
        return prev['c'] > prev['o'] and c < mid and o > prev['c']

    def morning_star(self, a, b, c):
        return a['c'] < a['o'] and abs(b['c'] - b['o']) <= (b['h'] - b['l']) * 0.3 and c['c'] > c['o']

    def evening_star(self, a, b, c):
        return a['c'] > a['o'] and abs(b['c'] - b['o']) <= (b['h'] - b['l']) * 0.3 and c['c'] < c['o']

    def harami_bull(self, a, b):
        return a['c'] < a['o'] and b['o'] > a['c'] and b['c'] < a['o']

    def harami_bear(self, a, b):
        return a['c'] > a['o'] and b['o'] < a['c'] and b['c'] > a['o']

    def tweezer_top(self, a, b):
        return abs(a['h'] - b['h']) <= (a['h'] - a['l']) * 0.1

    def tweezer_bottom(self, a, b):
        return abs(a['l'] - b['l']) <= (a['h'] - a['l']) * 0.1

    def dragonfly(self, o, h, l, c):
        return abs(h - max(o, c)) <= (h - l) * 0.1 and abs(o - c) <= (h - l) * 0.1

    def gravestone(self, o, h, l, c):
        return abs(min(o, c) - l) <= (h - l) * 0.1 and abs(o - c) <= (h - l) * 0.1

    ###############################################################
    # 3. CONTINUATION PATTERNS
    ###############################################################
    def rising_three(self, candles):
        a, b, c, d, e = candles
        uptrend = a['c'] > a['o']
        small = all(abs(x['c'] - x['o']) < abs(a['c'] - a['o']) for x in [b, c, d])
        final = e['c'] > a['c']
        return uptrend and small and final

    def falling_three(self, candles):
        a, b, c, d, e = candles
        downtrend = a['c'] < a['o']
        small = all(abs(x['c'] - x['o']) < abs(a['c'] - a['o']) for x in [b, c, d])
        final = e['c'] < a['c']
        return downtrend and small and final

    ###############################################################
    # 4. INSIDE / OUTSIDE BAR
    ###############################################################
    def inside_bar(self, prev, curr):
        return curr['h'] <= prev['h'] and curr['l'] >= prev['l']

    def outside_bar(self, prev, curr):
        return curr['h'] >= prev['h'] and curr['l'] <= prev['l']

    def three_inside_up(self, a, b, c):
        return self.inside_bar(a, b) and c['c'] > c['o']

    def three_inside_down(self, a, b, c):
        return self.inside_bar(a, b) and c['c'] < c['o']

    ###############################################################
    # 5. GAP PATTERNS
    ###############################################################
    def gap_up(self, prev, curr):
        return curr['l'] > prev['h']

    def gap_down(self, prev, curr):
        return curr['h'] < prev['l']

    ###############################################################
    # PATTERN ANALYZER (MAIN)
    ###############################################################
    def analyze(self, df):
        patterns = []
        if len(df) < 3:
            return patterns

        o, h, l, c = df['open'].iloc[-1], df['high'].iloc[-1], df['low'].iloc[-1], df['close'].iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]

        if self.doji(o, h, l, c): patterns.append("doji")
        if self.hammer(o, h, l, c): patterns.append("hammer")
        if self.inverted_hammer(o, h, l, c): patterns.append("inverted_hammer")
        if self.shooting_star(o, h, l, c): patterns.append("shooting_star")
        if self.marubozu_bull(o, h, l, c): patterns.append("marubozu_bull")
        if self.marubozu_bear(o, h, l, c): patterns.append("marubozu_bear")

        # Engulfing
        if self.bullish_engulfing(prev, df.iloc[-1]): patterns.append("bullish_engulfing")
        if self.bearish_engulfing(prev, df.iloc[-1]): patterns.append("bearish_engulfing")

        # Inside / Outside
        if self.inside_bar(prev, df.iloc[-1]): patterns.append("inside_bar")
        if self.outside_bar(prev, df.iloc[-1]): patterns.append("outside_bar")

        return patterns
