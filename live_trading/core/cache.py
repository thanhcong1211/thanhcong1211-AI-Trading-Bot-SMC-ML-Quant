"""
Cache Module - Indicator and Data Caching
==========================================
Provides caching mechanisms for indicators and market data to improve performance
"""


class IndicatorCache:
    """Lightweight indicator cache to avoid recomputing O(n) indicators each tick"""
    
    def __init__(self):
        # key -> (last_len, value)
        self._cache = {}

    def get(self, key, length):
        """Get cached value if data length matches"""
        v = self._cache.get(key)
        if v is None:
            return None
        last_len, value = v
        if last_len == length:
            return value
        return None

    def set(self, key, length, value):
        """Cache value with data length"""
        try:
            self._cache[key] = (length, value)
        except Exception:
            pass


class DataCache:
    """Data cache engine for market data and indicators"""
    
    def __init__(self):
        self.last_timestamp = None
        self.cached_indicators = {}
        self.cached_smc = {}


# Global cache instances
indicator_cache = IndicatorCache()
data_cache = DataCache()
