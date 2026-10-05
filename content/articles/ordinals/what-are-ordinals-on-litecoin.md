---
title: What are Ordinals on Litecoin?
category: Ordinals & Digital Artifacts
sourceTier: cms
reviewIntervalDays: 180
---

# What are Ordinals on Litecoin?

Ordinals are a way of giving every individual **litoshi** (the smallest unit of Litecoin, one hundred-millionth of 1 LTC) its own serial number and then tracking where that specific litoshi goes as it is spent. The scheme is called **ordinal theory**. On Litecoin it is implemented by **Ordinals Lite**, a port of the Bitcoin `ord` software that was completed in February 2023.

Ordinal theory does not change the Litecoin protocol. It needs no side chain, no separate token and no new consensus rules. It is a convention that an indexer applies to the ordinary blockchain: because every litoshi is numbered and every transfer follows a fixed rule, anyone running the indexer arrives at the same answer about which litoshi is where.

## How litoshis are numbered

Litoshis are numbered in the order they are mined. The first litoshi created in the genesis block is number 0, the next is 1, and so on through every block subsidy ever paid. Litecoin's total supply is capped at 84,000,000 LTC, so there will eventually be a little under 8.4 quadrillion numbered litoshis.

When litoshis move between transaction inputs and outputs they are assigned **first-in, first-out**: the litoshis of the first input fill the first output, then the second output, and so on, in order. Fees are treated as if they were a final output paid to the miner, so litoshis that are "spent as fees" end up in that block's coinbase. These two rules, numbering and FIFO transfer, are the whole of ordinal theory.

## Rarity on Litecoin

Ordinal theory groups litoshis by how notable the moment of their creation was. The rarity levels are the same as on Bitcoin, but the boundaries follow Litecoin's own parameters:

- **common** – any litoshi that is not the first litoshi of its block
- **uncommon** – the first litoshi of each block (a new block every 2.5 minutes)
- **rare** – the first litoshi of each difficulty-adjustment period (every 2,016 blocks, about 3.5 days)
- **epic** – the first litoshi of each halving epoch (every 840,000 blocks, about four years)
- **legendary** – the first litoshi of each *cycle*, the point where a halving and a difficulty adjustment land on the same block
- **mythic** – the first litoshi of the genesis block (litoshi 0)

On Litecoin a cycle is **three halvings, 2,520,000 blocks** (the smallest block count divisible by both 840,000 and 2,016). Bitcoin's cycle is six halvings, so legendary litoshis are more frequent on Litecoin than legendary sats are on Bitcoin. Litecoin's third halving, at block 2,520,000 in August 2023, completed the first cycle, so the first legendary litoshi after the genesis one has already been mined.

Approximate totals over Litecoin's whole issuance, derived from the rules above: roughly 27.7 million uncommon, about 13,750 rare, 32 epic, 10 legendary and 1 mythic litoshi. These are inclusive counts (a legendary litoshi is also the first of its epoch and period), mirroring how the upstream documentation counts them.

## What Ordinals are used for

Giving litoshis identities makes two things possible:

1. **Collecting rare litoshis.** Because rare, epic and legendary litoshis can be told apart from common ones, they can be held and traded for their scarcity, much like rare coins.
2. **Inscriptions.** Arbitrary content (an image, text, a document) can be attached to a specific litoshi by storing it on-chain. The litoshi then carries that content wherever it is sent, which is how Litecoin-native **digital artifacts** are created. See the companion article on inscriptions.

## Ordinals Lite: the Litecoin port

In early 2023 Indigo Nakamoto posted a 5 LTC bounty to port the Bitcoin `ord` software to Litecoin; community contributions raised it to 22 LTC. Developer Anthony Guerrera ("Crypto Anthony", GitHub `ynohtna92`) completed the port as **Ordinals Lite** (`ord-litecoin`). The first inscription on Litecoin preserved the MimbleWimble whitepaper on the Litecoin blockchain. The project provides an index, a block explorer (ordinalslite.com) and the `ord` command-line wallet, and is listed on the Litecoin Foundation's projects page for donations.

---
*Editor note. Sources: ordinal theory, rarity definitions and transfer rules from the `ord-litecoin` documentation and source (`crates/ordinals`: `CYCLE_EPOCHS = 3`, `SUPPLY = 8,399,999,990,760,000` litoshis, rarity tests), rewritten for Litecoin terminology; history from litecoin.com/projects/bounty-port-ordinals and litecoin.com/projects/ordinals-lite. The rarity totals are computed from Litecoin's parameters with the upstream counting convention, not quoted; please re-check them. The upstream `docs/src` text is Bitcoin-worded and was deliberately not imported.*
