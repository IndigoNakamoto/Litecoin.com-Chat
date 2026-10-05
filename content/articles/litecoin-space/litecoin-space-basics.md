---
title: "Litecoin Space basics: mempools, explorers, vB/WU and lit/vB"
category: Live Network Data
sourceUrl: https://litecoinspace.org/docs/faq
sourceTier: pinned
reviewIntervalDays: 180
---

# Litecoin Space basics: mempools, explorers, vB/WU and lit/vB

**Litecoin Space** (litecoinspace.org) is the Litecoin Foundation's mempool and blockchain explorer, a port of the open-source mempool.space project that was funded through a Foundation bounty. It shows pending and confirmed transactions, the fee market, mining pools and network statistics. This article collects the basic definitions from its FAQ.

## What is a mempool?

A mempool ("memory pool") is the queue of pending, unconfirmed transactions held by a Litecoin node. There is no single global mempool: every node keeps its own, so two nodes can hold slightly different sets of transactions depending on what has reached them.

## What is a mempool explorer?

A mempool explorer lets you see real-time and historical information about a node's mempool, visualise the waiting transactions, and search for them. Litecoin Space draws a node's mempool as **projected blocks**: the transactions it expects to be mined next, grouped into blocks and shown to the left of a dotted line. Confirmed blocks appear to the right. The half-filled block in its logo comes from that view.

## What is a blockchain, and a block explorer?

The blockchain is the distributed ledger that records Litecoin's transactions; miners extend it by mining new blocks. A block explorer lets you browse that ledger: blocks, transactions, addresses and more, both live and historically. Litecoin Space is both a mempool explorer and a block explorer.

## What is mining, and what are mining pools?

Mining is how unconfirmed transactions become confirmed. Miners select transactions from their mempools, arrange them into a candidate block, and race to find a block that satisfies the network's difficulty target. The miner who finds the next block collects all of that block's transaction fees (plus the block subsidy), so miners prioritise transactions paying higher fees. Mining pools are groups of miners that combine their hashing power to find blocks more regularly and share the rewards.

## What are virtual bytes (vB) and weight units (WU)?

Transaction and block sizes on Litecoin are measured in **virtual bytes (vB)** and **weight units (WU)**, where 1 vB = 4 WU. A transaction's size is set by technical factors (how many inputs, outputs and signatures it has, and whether it uses legacy or SegWit formats), not by how much Litecoin it moves. Block space is limited, so bigger transactions pay more in fees.

The maximum block weight is 4,000,000 WU, equivalent to 1,000,000 vB. Sizes used to be measured in plain bytes; vB and WU were introduced with SegWit to stay compatible with that older limit while giving witness data a discount.

## What is lit/vB?

A pending transaction's priority is decided by its **fee rate**, measured in **lit/vB**: litoshis per virtual byte. (On Bitcoin the same unit is sat/vB.) A higher lit/vB generally means faster confirmation. Fee rates change constantly with demand, so check the suggested rates on the Litecoin Space dashboard right before sending to avoid a stuck transaction.

## What Litecoin Space is not

The site only provides data about the Litecoin network. It cannot recover funds, fix a wallet or reverse a payment. For help with a particular transaction, contact whoever made it on your behalf: the wallet software, exchange or payment processor.

---
*Editor note. Snapshot of the "Basics" section of litecoinspace.org/docs/faq, condensed (the page is JavaScript-rendered, so it cannot be imported by the registry; the fetched text was used). Please re-check the 4,000,000 WU / 1,000,000 vB limit against Litecoin Core's consensus constants, since the FAQ text is inherited from mempool.space.*
