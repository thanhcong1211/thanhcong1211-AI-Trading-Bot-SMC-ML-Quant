const http = require('http');
const express = require('express');
const cors = require('cors');

const { port, corsOrigin } = require('./src/config');
const { MarketDataService } = require('./src/marketDataService');
const { createMarketFlowRouter } = require('./src/routes/marketFlow');
const { attachSocketServer } = require('./src/socket');

const app = express();
app.use(cors({ origin: corsOrigin }));
app.use(express.json());

const marketDataService = new MarketDataService();

app.get('/health', (req, res) => res.json({ status: 'ok' }));
app.use('/api/v1', createMarketFlowRouter(marketDataService));

const httpServer = http.createServer(app);
attachSocketServer(httpServer, marketDataService, corsOrigin);

httpServer.listen(port, () => {
  console.log(`[dashboard-backend] listening on :${port}`);
});
