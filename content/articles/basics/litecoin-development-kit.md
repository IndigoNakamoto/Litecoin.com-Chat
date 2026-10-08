---
title: What is the Litecoin Development Kit?
category: Litecoin Basics
sourceTier: cms
reviewIntervalDays: 180
---

# What is the Litecoin Development Kit?

The Litecoin Development Kit is the Litecoin port of Bitcoin Dev Kit (BDK). It is a set of libraries for building a descriptor-based wallet. A descriptor is the text that names which keys and scripts the wallet will spend, so two programs that share one descriptor agree on the same coins. The libraries keep their bdk names. Where that code says bitcoin, the port points those types at Litecoin, and the same wallet shape then works for LTC.

Ordinary Litecoin addresses, the legacy and SegWit ones, can sync through an Electrum or Esplora server, or through a Litecoin node. MimbleWimble Extension Blocks are a separate path in the same dev kit. Wallet code can scan for private coins and build a peg between the transparent chain and that private path.

That funds path is a public prototype. It has not had an independent audit, and it has not been independently reviewed. A wallet built from it can move real LTC. A mistake in a funds path that nobody outside the project has reviewed can lose those coins. Do not put coins you cannot afford to lose into a wallet built from this kit until that review exists.

<!-- retrieval-questions
What is the Litecoin Development Kit?
-->

---
*Editor note. Sources: LitecoinDevKit/bdk README (litecoin branch) and the LitecoinDevKit org profile. Facts limited to the BDK port, descriptors, Electrum/Esplora or node sync, and a public prototype whose funds path has not been independently reviewed. Do not add "is production-ready", "fully audited", or "has been audited". Golden needles: dev kit, descriptor, bdk, prototype, audit.*
