---
title: "Using Litecoin Space: looking up transactions, addresses, blocks and fee estimates"
category: Fees, Payments & Everyday Use
sourceUrl: https://litecoinspace.org/docs/faq
sourceTier: pinned
reviewIntervalDays: 180
---

# Using Litecoin Space: looking up transactions, addresses, blocks and fee estimates

## Looking things up

The search box at the top right of litecoinspace.org accepts:

- a **transaction ID** (txid), to see the transaction's inputs, outputs, fee, fee rate, confirmation status and any RBF or CPFP relationships;
- a **Litecoin address** (legacy `L…`, script `M…` or `3…`, or native SegWit `ltc1…`), to see its balance and transaction history;
- a **block height or block hash**, to see the block's transactions, size, fee range, miner and, on the official instance, its block audit.

Pages carry the same information as JSON for developers; see the API overview article.

## Reading the fee estimates

The dashboard shows four suggested fee rates in lit/vB. They are derived from the **projected blocks**, Litecoin Space's forecast of what the next blocks will contain given the current mempool:

- **High priority**: the median fee rate of the first projected block. Use it when you want confirmation in the next block.
- **Medium priority**: the average of the medians of the first and second projected blocks.
- **Low priority**: the average of the Medium rate and the median of the third projected block. Use it when soon is fine but not urgent.
- **No priority**: the lower of twice the minimum relay fee rate or the Low rate. Use it when you do not mind waiting.

Two adjustments apply. If any projected block used in a calculation is not full, the suggestion is lowered (if the only projected block is less than half full, Litecoin Space suggests 1 lit/vB rather than that block's median). And projected blocks are **forecasts**: each miner has its own view of the mempool and its own selection algorithm, so real blocks differ. Treat the estimates as a guide, not a guarantee of confirmation within any period.

## Why Litecoin's fees are usually low

Because Litecoin blocks arrive every 2.5 minutes and demand for block space is typically well below capacity, the projected blocks are often not full and the suggested rate sits at the minimum (1 lit/vB). Fee rates rise during bursts of activity, such as waves of inscriptions, and fall back once the backlog clears.

## Historical trends

The **graphs** page shows aggregate trends over time: mempool size, incoming transaction rate, fee rates, block sizes and weights, mining pool shares and hashrate. These are useful for seeing whether current conditions are unusual.

## Mining pages

The mining section lists pools ranked by blocks found over a selectable window (24 hours, 3 days, 1 week and longer), each pool's share of hashrate, and network hashrate and difficulty history, including progress toward the next difficulty adjustment (every 2,016 blocks).

---
*Editor note. Snapshot of the "Using this website" section of litecoinspace.org/docs/faq plus the dashboard/graphs/mining pages as observed; the fee-tier definitions are quoted closely because the Hub's live fee card shows exactly these figures. The page is JavaScript-rendered and cannot be imported automatically. The "usually low fees" paragraph is our framing, not FAQ text.*
