const { Server } = require('socket.io');
const { cacheSet } = require('../redisClient');
const { cacheKey, cacheTtlSeconds, tickIntervalMs } = require('../config');

/**
 * Wires the Socket.io server: every client gets the current snapshot on
 * connect, then a `market-flow:update` event on every simulated tick.
 *
 * @param {import('http').Server} httpServer
 * @param {import('../marketDataService').MarketDataService} marketDataService
 * @param {string} corsOrigin
 */
function attachSocketServer(httpServer, marketDataService, corsOrigin) {
  const io = new Server(httpServer, {
    cors: { origin: corsOrigin, methods: ['GET', 'POST'] }
  });

  io.on('connection', (socket) => {
    socket.emit('market-flow:snapshot', marketDataService.getSnapshot());
  });

  const interval = setInterval(() => {
    const snapshot = marketDataService.tick();
    cacheSet(cacheKey, snapshot, cacheTtlSeconds);
    io.emit('market-flow:update', snapshot);
  }, tickIntervalMs);

  io.httpServer.on('close', () => clearInterval(interval));

  return io;
}

module.exports = { attachSocketServer };
