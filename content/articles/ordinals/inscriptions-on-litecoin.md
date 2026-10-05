---
title: "Inscriptions on Litecoin: how digital artifacts are created"
category: Ordinals & Digital Artifacts
sourceTier: cms
reviewIntervalDays: 180
---

# Inscriptions on Litecoin: how digital artifacts are created

An **inscription** attaches a piece of content to a single litoshi by writing that content into the Litecoin blockchain itself. Once inscribed, the content is permanent, lives entirely on-chain, and travels with its litoshi: whoever controls the output holding that litoshi owns the inscription. Inscriptions are the mechanism behind Litecoin-native digital artifacts, popularised on Litecoin by Ordinals Lite.

## What an inscription contains

An inscription has two parts: a **content type** (a MIME type such as `image/png`, `text/plain` or `text/html`) and the **content** itself, a byte string. Because the content type is recorded, an explorer or wallet knows how to render it. Anything a web browser can display can be inscribed, and the content is served by ordinals explorers directly from chain data.

## Where the content is stored

Inscription content is stored in the **witness** of a Taproot script-path spend. Taproot activated on Litecoin in 2022, in the same network upgrade that activated MWEB (Litecoin Core 0.21.2), which is what made the `ord` approach possible on Litecoin.

Inside the witness script the content is wrapped in an **envelope**: an `OP_FALSE OP_IF … OP_ENDIF` block containing data pushes. Because the `OP_IF` branch is never executed, the script remains valid no matter what is inside, so the envelope can hold arbitrary data without changing how the transaction is validated. Witness data also receives the SegWit discount, so inscription bytes cost less than the same bytes would in a transaction output.

## The commit and reveal transactions

A Taproot script can only be spent from an existing Taproot output, so inscribing takes two transactions:

1. **Commit.** A transaction creates a Taproot output that commits to a script containing the inscription content. Nothing is visible yet.
2. **Reveal.** A second transaction spends that output, and in doing so publishes the script, and therefore the content, to the chain.

By default the inscription is made on the **first litoshi of the first output** of the reveal transaction (the protocol also allows a *pointer* to choose a different litoshi). Ordinal theory then tracks that litoshi from output to output, so the inscription moves whenever its litoshi is sent.

## What inscribing costs

Inscriptions are ordinary transactions, so they pay ordinary fees: a rate in **lit/vB** (litoshis per virtual byte) multiplied by the transaction's size. Larger content means a larger reveal transaction and a larger fee. A small text inscription is cheap; a high-resolution image is not. The `ord` wallet exposes this directly: `ord wallet inscribe --fee-rate <lit/vB> --file <content>`. Fee estimates for the current mempool are shown on Litecoin Space.

Inscriptions also carry a small amount of Litecoin: the output that holds the inscribed litoshi must be above the dust limit. The `ord` software defaults to 10,000 litoshis of "postage" for this.

## Why "digital artifact" rather than "NFT"

The ordinals community uses the term **digital artifact** deliberately. A digital artifact must be complete (the content is on-chain, not a link to a server or IPFS), permissionless (no royalty or allow-list can block a transfer), uncensorable and immutable (there is no upgrade key). Many token-based NFTs fail one or more of these tests, so an inscription is better described as a digital artifact than as an NFT in the usual sense.

## Immutability and its consequences

Because the content is embedded in blocks that every full node stores, an inscription cannot be edited or removed. That is the source of its value and also a responsibility: inscribe only content you have the right to publish and are comfortable having on a public, permanent ledger. It also means inscriptions add to the data every archival node keeps, which is why their cost is tied to their size.

---
*Editor note. Sources: mechanics from the `ord-litecoin` documentation (`docs/src/inscriptions.md`, `docs/src/digital-artifacts.md`) and source (`TARGET_POSTAGE = 10,000`), rewritten with Litecoin units. Please confirm the Taproot activation detail (same upgrade as MWEB, Litecoin Core 0.21.2, May 2022) and the block height before publishing; the repo has no 0.21.2 release-notes file to cite.*
