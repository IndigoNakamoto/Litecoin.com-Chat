---
title: What is MVRV?
category: Live Network Data
sourceTier: cms
reviewIntervalDays: 120
---

# What is MVRV

MVRV is the market-value-to-realized-value ratio. It compares two ways of pricing the coins that already exist. Market value is the usual market cap: the spot price of LTC multiplied by the circulating supply. Realized value reprices each coin at the price the last time that coin moved on-chain, then adds those up. MVRV is market value divided by realized value.

If MVRV is above 1, the market cap is higher than the sum of those last-move prices. If it is below 1, the market cap is lower than that sum. The ratio is a description of the existing UTXO set against a price. It is not a promise that the price will rise or fall, and it is not a signal published by the Litecoin protocol. Litecoin nodes do not enforce MVRV. Analysts and data sites compute it from chain history plus a price series.

This article defines the ratio only. It does not contain today's MVRV, today's price, or a realized price. A question that asks for MVRV right now, or for the current realized price, has to be answered from live data with a timestamp, or with a clear statement that the series has not been computed. Do not fill that gap with a number from memory or from this page. A definition and a live reading are different questions: "What is MVRV?" asks what the letters mean; "What is Litecoin's MVRV right now?" asks for a figure.

Realized value is sometimes called realized cap. Both names refer to the same idea: value coins at the price of their last on-chain move, not at today's spot price. Coins that have not moved in years stay at the old price inside the realized figure, which is why realized value and market value diverge.

---
*Editor note. Standard market-cap / realized-cap definition. No numeric example, so a model cannot quote a stale MVRV from this page. The live question "What is Litecoin's MVRV right now?" must keep routing to the metric lookup (golden id metric-not-computed), not to this article's absence of a number. Please confirm the category Live Network Data is the one editors want for a definition rather than Litecoin Basics.*
