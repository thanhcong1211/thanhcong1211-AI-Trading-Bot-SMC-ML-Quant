const Redis = require('ioredis');
const { redisUrl } = require('./config');

let client = null;

if (redisUrl) {
  client = new Redis(redisUrl, {
    lazyConnect: true,
    maxRetriesPerRequest: 1,
    retryStrategy: () => null
  });

  client.on('error', (err) => {
    console.warn('[redis] connection error, caching disabled:', err.message);
  });

  client.connect().catch((err) => {
    console.warn('[redis] unable to connect, caching disabled:', err.message);
  });
} else {
  console.warn('[redis] REDIS_URL not set, price cache disabled (in-memory only)');
}

async function cacheSet(key, value, ttlSeconds) {
  if (!client || client.status !== 'ready') return;
  try {
    await client.set(key, JSON.stringify(value), 'EX', ttlSeconds);
  } catch (err) {
    console.warn('[redis] set failed:', err.message);
  }
}

async function cacheGet(key) {
  if (!client || client.status !== 'ready') return null;
  try {
    const raw = await client.get(key);
    return raw ? JSON.parse(raw) : null;
  } catch (err) {
    console.warn('[redis] get failed:', err.message);
    return null;
  }
}

module.exports = { cacheSet, cacheGet };
