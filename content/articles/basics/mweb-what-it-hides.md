---
title: What MWEB hides
category: Litecoin Basics
sourceTier: cms
reviewIntervalDays: 180
---

# What MWEB hides

Both. For a payment that stays inside MWEB, Litecoin hides the transaction amount and the addresses of the sender and the receiver. MWEB is MimbleWimble extension blocks, and it is opt-in. A normal Litecoin payment that never enters MWEB still shows the amount and the addresses on the public chain.

Amounts inside MWEB are hidden with confidential transactions. The amount is stored as a Pedersen commitment, so someone reading the extension block cannot tell how much LTC moved. A transparent output shows that number in the clear. An MWEB output does not.

Addresses are hidden on that same payment. An MWEB-to-MWEB transfer does not publish a transparent sender address or a transparent receiver address. The address a wallet shares starts with ltcmweb1. That string is a stealth address. The extension block does not store it the way an L…, M…, or ltc1 output is stored on the main chain. What the chain keeps is a commitment and a kernel, not a reusable public address tied to an amount.

A peg-in or a peg-out is the part that stays visible. Moving coins into MWEB is a peg-in. Moving them back out is a peg-out. Both are recorded on the transparent chain. Anyone can see that coins entered or left MWEB, and the amount of that peg is visible. Hiding applies to a later payment that stays inside MWEB, not to the peg itself.

---
*Editor note. Amounts: Pedersen commitments (confidential transactions), as in LIP-0003. Addresses: MWEB uses stealth addresses; the shareable form is the bech32m `ltcmweb1` prefix from the Litecoin Core MWEB address encoding, and the extension block does not store that string as a transparent output. Peg-in and peg-out amounts are visible on the canonical (HogEx / integration) transaction. Golden needles: stealth (hides-what), peg (pegin). Do not drop those words.*
