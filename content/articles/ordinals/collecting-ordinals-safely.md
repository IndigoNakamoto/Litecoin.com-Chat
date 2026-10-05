---
title: "Collecting Litecoin Ordinals and hunting rare litoshis safely"
category: Ordinals & Digital Artifacts
sourceTier: cms
reviewIntervalDays: 180
---

# Collecting Litecoin Ordinals and hunting rare litoshis safely

Ordinals turn individual litoshis into things that can be owned, found and lost. The protocol itself is simple; most losses come from treating an ordinals wallet like a normal Litecoin wallet. This article covers the habits that keep inscriptions and rare litoshis safe.

## Use a dedicated wallet

Ordinary wallet software picks inputs and builds change outputs without any idea that one particular litoshi matters. Sending from a wallet that holds inscriptions with such software can place the inscribed litoshi into a change output you do not expect, or spend it as part of the fee, after which it belongs to the miner. The `ord` project's rule is therefore to keep **ordinal** wallets (holding inscriptions and rare litoshis) strictly separate from **cardinal** wallets (holding spendable Litecoin), and to never use `litecoin-cli` or other RPC tools on an `ord` wallet.

## Understand litoshi control

Wallets built for ordinals (`ord`, Litescribe, Stack Wallet with coin control) show individual outputs and let you choose exactly which ones a transaction spends. Before sending, check:

- the inscription or rare litoshi you intend to send is the one selected;
- the output carrying it keeps enough "postage" above the dust limit (`ord` uses 10,000 litoshis by default);
- the fee is paid from a different, plain output, not from the output that carries the inscription.

If the transaction's outputs are reordered or merged, ordinal theory's first-in, first-out rule decides where the litoshi lands, so always inspect the result on an explorer such as ordinalslite.com after it confirms.

## Hunting rare litoshis

Rare litoshis (the first of a block, difficulty period, halving epoch or cycle) can be identified only by an indexer that tracks every litoshi. With Ordinals Lite:

1. Run `ord --index-sats server` against a `litecoind` node with `-txindex`; the sat index is large and the first build takes a long time.
2. `ord wallet sats` lists any rare litoshis in the wallet's outputs.
3. To scan a wallet that is not an `ord` wallet, export its output descriptors and import them into Litecoin Core as a watch-only wallet, then run `ord wallet --name <name> sats`.
4. Send a specific rare litoshi with `ord wallet send <ADDRESS> <sat name> --fee-rate <lit/vB>`; `ord` picks the output containing it.

Litecoin's parameters make some rarities more common than on Bitcoin: a new uncommon litoshi every 2.5 minutes, a rare one every 2,016 blocks, an epic one every 840,000 blocks, and a legendary one every three halvings (2,520,000 blocks).

## Buying and selling

- Verify the **inscription ID** (the reveal transaction ID followed by `i` and an index) on an independent explorer before paying; the same image can be inscribed many times and only the ID is unique.
- Prefer **PSBT-based trustless swaps**, where the trade either completes atomically or not at all, over sending funds first and hoping the seller delivers.
- Check **provenance**: child inscriptions can declare a parent, which is how collections prove authenticity. An inscription without that link is not part of the collection, whatever its content looks like.
- Marketplaces and indexers are services. If one goes offline your inscriptions are still on-chain, but you need a working indexer to see and move them.

## Scams to expect

- Sites or extensions that ask for your **seed phrase** to "verify" or "sync" inscriptions. No legitimate tool needs it.
- Fake marketplace or wallet downloads impersonating Litescribe or Ordinals Lite; install only from the projects' published repositories.
- "Free mint" pages that ask you to sign a transaction you cannot read; a signature can move every inscription in the wallet.
- Offers to buy at a premium if you send the inscription first.

If you believe you have been targeted, do not send anything further and report it through the channels listed by the Litecoin Foundation.

---
*Editor note. Sources: `ord-litecoin` README safety notes and the `docs/src/guides/sat-hunting.md`, `wallet.md` and `inscriptions/provenance.md` guides (Bitcoin-worded, adapted); `TARGET_POSTAGE` from source. The scam list is general good practice, not a record of specific incidents. Consider linking the Foundation's scam-reporting page that the safety router already uses.*
