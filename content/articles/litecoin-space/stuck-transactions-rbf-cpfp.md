---
title: "Stuck Litecoin transactions: why they happen and how RBF and CPFP help"
category: Fees, Payments & Everyday Use
sourceUrl: https://litecoinspace.org/docs/faq
sourceTier: pinned
reviewIntervalDays: 180
---

# Stuck Litecoin transactions: why they happen and how RBF and CPFP help

## Why isn't my transaction confirming?

If a transaction has been waiting a while, it is almost always because its **fee rate** (lit/vB) is low compared with the other transactions currently in the mempool. Miners fill blocks with the highest-paying transactions first, so a low-fee transaction keeps being passed over while better-paying ones arrive.

There is no need to panic. A Litecoin transaction always ends in one of two states: fully confirmed, or dropped from mempools and never confirmed, in which case the coins are still yours. As long as you have the **transaction ID (txid)** you can look it up on Litecoin Space and see exactly where the funds are.

Litecoin Space only shows network data. To act on a transaction, use the tool that created it: your wallet software, exchange or payment processor.

## How can I get a transaction confirmed faster?

You have to raise its **effective fee rate**. There are two standard ways:

### Replace-by-fee (RBF)

If the transaction was created with RBF enabled (BIP 125 opt-in), your wallet can broadcast a **replacement** that spends the same inputs with a higher fee. Nodes and miners accept the replacement and drop the original. Not all wallets support RBF; the transaction page on Litecoin Space shows whether a transaction signalled it, and the Mempool Analysis filters can highlight RBF-enabled transactions.

### Child-pays-for-parent (CPFP)

If you control one of the stuck transaction's **outputs** (for example the change output, or the payment if you are the recipient), you can spend that output in a new "child" transaction with a high fee. Miners who want the child's fee must include the parent too, so the pair is evaluated by its combined, or *effective*, fee rate. On a Litecoin Space transaction page a CPFP relationship appears as the transaction's effective fee rate, with links to its ancestor or descendant transactions.

If you are not sure how to do either, work with the wallet or service that made the transaction; most modern wallets offer "bump fee" or "speed up" buttons that perform RBF or CPFP for you.

## How can I avoid stuck transactions?

- Pay a fee rate that matches how soon you need confirmation. Litecoin Space's dashboard shows High, Medium, Low and No-priority estimates computed from the current projected blocks.
- Use a wallet that supports **RBF**, so you can raise the fee later if the mempool becomes busier than expected.
- When the mempool is full (see the "purging" fee rate on the dashboard), set a rate above the purge threshold or your transaction may be evicted by nodes before a miner sees it.

## What "effective fee rate" means

The rate a transaction *declares* is not always the rate that gets it mined. A 1 lit/vB parent with a high-fee child is mined at the pair's combined rate; that is why Litecoin Space shows a block's fee range in effective terms and why a block can appear to contain transactions paying less than its displayed minimum. Litecoin Core also measures rates per *adjusted* vsize, which penalises transactions with unusually many signature operations.

---
*Editor note. Snapshot of the "Help! My transaction is stuck" and related "Advanced" answers on litecoinspace.org/docs/faq, condensed and merged with the existing RBF/CPFP vocabulary in the Hub. The source page is JavaScript-rendered and cannot be imported automatically. Our fee card already pulls the live estimates this article describes.*
