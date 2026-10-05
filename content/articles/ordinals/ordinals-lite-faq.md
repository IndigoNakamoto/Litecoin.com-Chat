---
title: "Ordinals Lite FAQ"
category: Ordinals & Digital Artifacts
sourceTier: cms
reviewIntervalDays: 180
---

# Ordinals Lite FAQ

## Does ordinal theory require a side chain, a token or changes to Litecoin?

No. Ordinal theory works on Litecoin as it is today. It assigns numbers to litoshis and tracks them with a first-in, first-out rule; both are conventions applied by an indexer to the ordinary blockchain. The only asset involved is Litecoin itself. Litecoin Core does not need to know about it, and nodes that ignore it are unaffected.

## Did Litecoin have to upgrade for inscriptions?

Inscriptions store content in Taproot witness data, so Taproot had to be active. Litecoin activated Taproot in 2022 as part of the same upgrade that activated MWEB (Litecoin Core 0.21.2). No further change was required; Ordinals Lite was ported in February 2023 by using what the network already supported.

## Are Litecoin Ordinals NFTs?

They are usually called **digital artifacts** instead. The difference is deliberate: an inscription's content is entirely on-chain (not a link to a server), it can be transferred without anyone's permission or a royalty, it cannot be censored or altered, and it has no upgrade key. Many NFTs on smart-contract platforms fail one or more of those tests. If you need a quick analogy, "on-chain, immutable NFT" is close; the project prefers the more precise term.

## What is a litoshi, and why does ordinal theory care about it?

A litoshi is one hundred-millionth of a litecoin, the smallest unit the protocol can represent. Ordinal theory numbers every litoshi in the order it was mined and follows each one through transactions. An inscription is attached to one specific litoshi, which is how a piece of content can be owned and transferred.

## How is Ordinals Lite different from Bitcoin Ordinals?

The protocol is the same; the parameters are Litecoin's. Blocks arrive every 2.5 minutes instead of ten, halvings happen every 840,000 blocks, and a rarity "cycle" is three halvings (2,520,000 blocks) rather than six. The unit is the litoshi rather than the satoshi. Inscription IDs, envelopes, provenance and the explorer work the same way, so tools and knowledge from Bitcoin ordinals carry over.

## Do inscriptions make Litecoin fees higher?

Inscriptions are transactions and compete for block space like any other, paying a fee proportional to their size. When many large inscriptions are broadcast at once, the mempool fills and fee rates rise for everyone until the backlog clears. Litecoin's fast blocks and historically low fees mean this effect has been milder than on Bitcoin, but during inscription waves users have seen higher-than-usual fee estimates. Litecoin Space shows the current fee market and mempool depth.

## Do inscriptions bloat the blockchain?

Yes, in the sense that inscription content is stored permanently in blocks and every archival node keeps it. Witness data is cheaper per byte than other transaction data because of the SegWit discount, but it is still data. The cost of inscribing scales with content size, which is the protocol's built-in limit on how much is added.

## Who runs the index?

Anyone can. `ord` is open source and any Litecoin node with `-txindex` can build the full litoshi index. ordinalslite.com is a public explorer run by the Ordinals Lite project; Litescribe and marketplaces run their own indexers. Because the rules are deterministic, independent indexers agree.

## Can an inscription be deleted or changed?

No. Once the reveal transaction is confirmed the content is part of the chain. Inscriptions can be transferred, and the protocol supports *provenance* (child inscriptions pointing to a parent) and *delegation* (an inscription that displays another's content), but the original bytes are immutable.

## What is LTC-20?

LTC-20 is an experimental, community-defined convention for fungible tokens written as JSON text inscriptions, modelled on Bitcoin's BRC-20. It is not part of the `ord` protocol or of Litecoin, has no consensus enforcement, and depends entirely on off-chain indexers agreeing on the rules. Litescribe lists LTC-20 management among its features. The Knowledge Hub does not currently hold a Litecoin-specific reference for the LTC-20 rules, so treat any specifics as unverified.

## Is this safe for my main Litecoin wallet?

Keep them apart. Ordinary wallets do not know which litoshi carries an inscription and can spend it as change or fee. Use a wallet that understands inscriptions for ordinals, and a separate wallet for everyday Litecoin.

---
*Editor note. Sources: `ord-litecoin` documentation (`faq.md`, `digital-artifacts.md`, `inscriptions.md`, `inscriptions/provenance.md`, `inscriptions/delegate.md`) adapted to Litecoin; project history from litecoin.com/projects. The Taproot/MWEB activation statement should be confirmed against Litecoin Core 0.21.2 release notes. The fee-impact paragraph is qualitative; replace with measured figures if we have them.*
