module.exports = {
  port: process.env.PORT || 4000,
  redisUrl: process.env.REDIS_URL || null,
  corsOrigin: process.env.CORS_ORIGIN || '*',
  tickIntervalMs: Number(process.env.TICK_INTERVAL_MS || 2000),
  cacheKey: 'market-flow:snapshot',
  cacheTtlSeconds: 30
};
