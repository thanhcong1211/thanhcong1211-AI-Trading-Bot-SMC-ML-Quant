const express = require('express');

/**
 * @param {import('../marketDataService').MarketDataService} marketDataService
 */
function createMarketFlowRouter(marketDataService) {
  const router = express.Router();

  // GET /api/v1/market-flow
  router.get('/market-flow', (req, res) => {
    res.json(marketDataService.getSnapshot());
  });

  return router;
}

module.exports = { createMarketFlowRouter };
