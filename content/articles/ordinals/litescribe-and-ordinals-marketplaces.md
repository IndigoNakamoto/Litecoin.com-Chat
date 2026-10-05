---
title: "Litescribe wallet and Litecoin Ordinals marketplaces"
category: Ordinals & Digital Artifacts
sourceTier: cms
reviewIntervalDays: 120
---

# Litescribe wallet and Litecoin Ordinals marketplaces

Running the `ord` command line against your own Litecoin node is the reference way to use Ordinals, but most people interact with Litecoin inscriptions through browser wallets and marketplaces. Several of these came out of Litecoin Foundation bounties and are listed on litecoin.com/projects.

## Litescribe wallet

**Litescribe** is a non-custodial browser-extension wallet for Litecoin Ordinals, forked from the UniSat wallet under a Foundation bounty ("Port Unisat to Litecoin"). It lets a user hold, transfer and create inscriptions **without running a full node**, by relying on a public indexer instead of a local `ord` index.

Features as described by the project:

- **Open source.** The code is published at github.com/LiteVerseHoldings/extension-ltc.
- **Non-custodial and hierarchical-deterministic.** Accounts derive from a Secret Recovery Phrase; private keys are encrypted on the user's device and the project states it never stores seed phrases, passwords or private information on its servers.
- **Privacy stance.** The wallet says it does not track personally identifiable information, account addresses or balances.
- **Functionality.** Storing, transferring and inscribing Ordinals, and managing LTC-20 inscriptions, plus importing single private keys (shown as "imported").
- **Marketplace.** Litescribe includes a trustless marketplace for Litecoin-native digital artifacts; the project funds continued development by reinvesting fees.

The official site is litescribe.io. As with any extension wallet, install only from the project's published links, verify the repository, and keep an ordinals wallet separate from a wallet holding your main Litecoin balance.

## OpenOrdEx on Litecoin

A second bounty funded a port of **OpenOrdEx**, an open-source, zero-fee, trustless ordinals marketplace. It works with **partially signed transactions (PSBTs)**: a seller signs a transaction that releases their inscription only if a matching payment output is present, a buyer completes and broadcasts it, and no intermediary ever holds either side's funds. This is the same trust model that trustless Bitcoin ordinals swaps use, applied to Litecoin.

## Stack Wallet

**Stack Wallet** is an open-source, non-custodial, multi-coin wallet whose Litecoin work is listed on the projects page. Its relevance to Ordinals is **coin control**: the wallet lets users see and choose individual outputs, which is what prevents an inscription from being spent accidentally as change or fee. Stack Wallet also enables its privacy features by default.

## Choosing between them

- To **create and hold** inscriptions with full sovereignty, run Ordinals Lite (`ord`) against your own `litecoind` node.
- To **collect and trade** without a node, a Litescribe-style extension wallet plus an indexer-backed marketplace is the usual path; understand that you are trusting the indexer's view of the chain.
- Whatever you use, the rule from the `ord` project applies: never spend from an ordinals wallet with software that does not understand inscriptions.

---
*Editor note. Sources: litecoin.com/projects/litescribe, litecoin.com/projects/bounty-port-unisat-to-litecoin-now-litescribe-wallet, litecoin.com/projects/bounty-port-openordex, litecoin.com/projects/stackwallet. Feature claims are the projects' own descriptions, not independent audits. The OpenOrdEx page is a 40-word stub; the PSBT trust-model description is from the upstream OpenOrdEx design. Please confirm Litescribe's current store availability and LTC-20 support before publishing.*
