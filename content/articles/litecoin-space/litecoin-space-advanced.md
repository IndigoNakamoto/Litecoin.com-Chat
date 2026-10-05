---
title: "Litecoin Space advanced: full mempools, empty blocks, block audits and block health"
category: Mining & Network Security
sourceUrl: https://litecoinspace.org/docs/faq
sourceTier: pinned
reviewIntervalDays: 180
---

# Litecoin Space advanced: full mempools, empty blocks, block audits and block health

## What does it mean for the mempool to be "full"?

A node stores unconfirmed transactions in memory until they are mined. When transactions arrive faster than blocks confirm them, the mempool grows. By default Litecoin Core allocates **300 MB** to its mempool; when that is used up the node is "full" and starts **rejecting new transactions below a fee-rate threshold**, evicting the lowest-paying ones. When this happens, set a fee rate at least above that threshold or your transaction may never propagate. Litecoin Space shows the current threshold (the **purging** fee rate) and memory usage on its front page whenever mempools are full.

## How big is the mempool Litecoin Space uses?

Litecoin Space reads from several nodes. Some run the default 300 MB limit ("small nodes"); these let the site report the purge threshold most of the network applies. Others run a much larger limit ("big nodes") that never evict, so the site can show every pending transaction it has received, however low its fee. The **memory usage** figure on the front page comes from a big node, which is why it can exceed 300 MB during congestion: it is a node that is not evicting anything. A Raspberry Pi node with the default limit will never pass 300 MB.

Memory usage is always higher than the raw size of the pending transactions because Litecoin Core keeps indexes and pointers alongside them.

## Why are there empty blocks?

When a new block is found, pools often push a fresh block template to their miners before they have fully validated, or even fully received, the new block. During that window they cannot safely choose transactions (they do not yet know which ones conflict with the block just mined), so they mine on an empty template. Empty blocks add no transactions, but they still extend the chain and so add security to transactions already confirmed.

## Why don't block timestamps always increase?

Consensus does not require each block's timestamp to be later than its predecessor's. There is no central clock, so the rules only constrain timestamps within bounds, one of which is that a block's time cannot be older than the median of the previous 11 blocks' timestamps. As a result timestamps are only accurate to within about an hour and can appear out of order.

## Why doesn't a block's fee range match the fee rates of its transactions?

Litecoin Space shows a block's **effective** fee-rate range: what you would actually have needed to pay to get into that block. A transaction declaring 1 lit/vB may have been pulled in by a high-fee child (CPFP), so its effective rate was higher. Using the declared 1 lit/vB as the block's floor would be misleading. A transaction's page shows both its declared rate and, where relevant, its effective rate with links to ancestors and descendants.

## How do block audits work?

Litecoin Space continuously runs a re-implementation of Litecoin Core's transaction-selection algorithm on its own mempool view, every two seconds, to produce the projected blocks. When a block is mined, it saves the template it expected for that height, the **expected block**, and compares it with the **actual block**. The purpose is to infer when a miner deliberately included or excluded transactions.

Transactions are coloured by heuristic:

- **Added** (blue): in the actual block but not expected, and either far outside the expected fee range or never seen in the mempool, suggesting the miner prioritised it or accepted it out of band. Does not lower block health.
- **Recently broadcast** (dark pink): expected but missing, and first seen within three minutes of the block, so the miner may simply not have had it. Does not lower block health.
- **Marginal fee** (darkened): at the low end of the fee range and missing from one side; displaced by something else, not notable. Does not lower block health.
- **Removed** (bright pink): expected, well within the fee range, widely propagated, and still absent. Possibly excluded on purpose. Lowers block health.

Audits need substantial resources, so they are available only on the official Litecoin Space instance.

## What is block health?

Block health measures how many transactions appear to have been intentionally left out. Let *n* be the number of transactions present in both the expected and actual blocks and *r* the number judged "removed". Health is **n / (n + r)**. A block with no removed transactions scores 100% even if it looks very different from the expected block, because added and recently-broadcast transactions are not penalised. It is therefore a measure of apparent censorship, not of similarity.

## What is Mempool Analysis?

A set of filters that highlight transaction types in the mempool visualisation: RBF enabled or disabled; transaction version 1 or 2 (version 2 is required for CSV relative timelocks); output types (P2PK, bare multisig, P2PKH, P2SH, P2WPKH, P2WSH, Taproot); CPFP relationships and replacements; data-embedding methods (OP_RETURN, fake-pubkey data, Taproot witness inscriptions); heuristic categories (coinjoin, consolidation, batch payment); and the sighash flags used.

## What are sigops and adjusted vsize?

A **sigop** is an accounting unit for signature-checking operations in script (`OP_CHECKSIG`, `OP_CHECKMULTISIG` and their VERIFY forms), weighted by whether they are single- or multi-signature and where they appear. Each block may contain at most **80,000 sigops**. Most transactions are limited by weight, but some use disproportionately many sigops, so Litecoin Core computes an **adjusted vsize** equal to the larger of the real vsize and five times the sigop count, and selects transactions by fee per adjusted vsize. Litecoin Space measures effective fee rates the same way.

## Why do projected block fee ranges overlap?

Projected blocks obey the same constraints as real blocks. A nearly full block may still fit one tiny low-fee transaction while a larger high-fee one waits for the next block, and the sigop limit can leave a block with room only for zero-sigop transactions at lower rates. Both effects can make consecutive projected blocks' fee ranges overlap.

---
*Editor note. Snapshot of the "Advanced" section of litecoinspace.org/docs/faq, condensed. Two items to verify for the Litecoin fork: the FAQ states the median of the previous **12** blocks for the timestamp rule, whereas the Bitcoin/Litecoin consensus rule is the median of the previous 11 (used above); and the 300 MB default, 80,000 sigop limit and 4 MWU weight limit are inherited from mempool.space text, so confirm them against Litecoin Core. The page is JavaScript-rendered and cannot be imported by the registry.*
