---
title: "Litecoin Space REST API overview"
category: Build on Litecoin
sourceUrl: https://litecoinspace.org/docs/api/rest
sourceTier: pinned
reviewIntervalDays: 90
---

# Litecoin Space REST API overview

Litecoin Space exposes the same public REST API as mempool.space, served from **`https://litecoinspace.org/api`**. It is free to use, needs no key, and returns JSON (a few endpoints return plain text). Developers who already know the mempool.space API can use it unchanged, substituting Litecoin units (litoshis, lit/vB) and Litecoin's 2.5-minute blocks. The Litecoin Knowledge Hub's own live-data cards are built on these endpoints.

The full reference, with every parameter and response field, is at litecoinspace.org/docs/api/rest. The page is rendered in the browser, so this article summarises the endpoint families rather than reproducing it.

## General

- `GET /api/v1/difficulty-adjustment` – progress through the current 2,016-block retarget period, estimated change, remaining blocks and time.
- `GET /api/v1/historical-price?currency=USD` – LTC price history (USD, EUR, GBP, CAD, CHF, AUD, JPY).

## Addresses

- `GET /api/address/:address` – chain and mempool totals for an address (funded, spent, transaction count).
- `GET /api/address/:address/txs` – transaction history (paginated with `/txs/chain/:last_txid` and `/txs/mempool`).
- `GET /api/address/:address/utxo` – unspent outputs.

## Blocks

- `GET /api/blocks/tip/height` and `/api/blocks/tip/hash` – current chain tip (plain text).
- `GET /api/block-height/:height` – block hash at a height (plain text).
- `GET /api/block/:hash` – block header and summary (size, weight, transaction count, fee statistics, miner).
- `GET /api/block/:hash/txs[/:start_index]`, `/txids`, `/txid/:index`, `/raw`, `/status` – the block's contents.
- `GET /api/v1/blocks[/:height]` – recent blocks with extended data.

## Mempool

- `GET /api/mempool` – count, total vsize, total fees and a fee-rate histogram.
- `GET /api/mempool/txids` and `/api/mempool/recent` – pending transaction IDs and the latest arrivals.

## Fees

- `GET /api/v1/fees/recommended` – `fastestFee`, `halfHourFee`, `hourFee`, `economyFee`, `minimumFee` in lit/vB, derived from the projected blocks as described in the Litecoin Space FAQ.
- `GET /api/v1/fees/mempool-blocks` – the projected blocks themselves with their fee ranges.

## Mining

- `GET /api/v1/mining/pools/:timePeriod` – pools ranked by blocks found over `24h`, `3d`, `1w`, `1m`, `3m`, `6m`, `1y`, `2y`, `3y`.
- `GET /api/v1/mining/pool/:slug` – one pool's details and recent blocks.
- `GET /api/v1/mining/hashrate/:timePeriod` and `/api/v1/mining/hashrate/pools/:timePeriod` – network hashrate and difficulty history, overall or per pool.
- `GET /api/v1/mining/blocks/fees/:timePeriod`, `/rewards/:timePeriod`, `/sizes-weights/:timePeriod` – block fee, reward and size statistics over time.

## Transactions

- `GET /api/tx/:txid` – a transaction with inputs, outputs, fee, size, weight and confirmation status.
- `GET /api/tx/:txid/status`, `/hex`, `/raw`, `/merkle-proof`, `/outspend/:vout`, `/outspends` – status, raw form and spend tracking.
- `POST /api/tx` – broadcast a raw transaction (hex body); returns the txid.

## WebSocket and Electrum

- `wss://litecoinspace.org/api/v1/ws` streams new blocks, mempool updates, fee estimates and address or transaction tracking; documented under API – WebSocket.
- The Electrum RPC documentation describes the Electrum-protocol server interface used by wallets and by the explorer's own backend.

## Practical notes

- Values are in **litoshis**; fee rates in **lit/vB**; timestamps are Unix seconds.
- Some endpoints are slow on the public instance when they aggregate long ranges (the Knowledge Hub uses `/hashrate/3d` rather than `/1w` for that reason). Cache responses and avoid polling tight loops; for live updates prefer the WebSocket.
- The public instance is operated by the Litecoin Foundation on a best-effort basis. For guaranteed availability, self-host an instance and point your application at it.

---
*Editor note. Endpoint families follow the mempool.space REST API, which the ltcspace fork keeps; the entries used by the Hub (`/tx`, `/address`, `/block`, `/block-height`, `/blocks/tip/height`, `/mempool`, `/v1/fees/recommended`, `/v1/difficulty-adjustment`, `/v1/historical-price`, `/v1/mining/pools`, `/v1/mining/pool/:slug`, `/v1/mining/hashrate[/pools]`) are cross-checked against `backend/services/blockchain_client.py` and probed live (fees, mempool, tip height, pools, hashrate returned 200 on 2026-10-05; difficulty-adjustment returned a 502 at that moment). Other paths are from the upstream reference and should be spot-checked. The registry entry for the live docs page is disabled because the page is JavaScript-rendered.*
