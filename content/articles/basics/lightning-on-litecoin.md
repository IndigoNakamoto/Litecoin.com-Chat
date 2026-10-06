---
title: Lightning Network on Litecoin
category: Litecoin Basics
sourceTier: cms
reviewIntervalDays: 180
---

# Lightning Network on Litecoin

Yes. Litecoin can be used on the Lightning Network. Lightning is a layer of payment channels on top of the base chain. Two parties lock LTC in a shared output on Litecoin, update the balance between them off-chain as they pay each other, and settle back to the Litecoin blockchain only when they close the channel or need the chain to enforce the latest state. Payments can also be routed across other people's channels, so the sender and receiver do not have to open a channel with each other directly.

Lightning on Litecoin depends on SegWit. The channel transactions use SegWit features, including a transaction format that fixes malleability, so Litecoin could support Lightning once SegWit was active on the network. Lightning does not replace Litecoin. The coins in a channel are still LTC, and the security of the channel comes from the ability to publish the latest state as an ordinary Litecoin transaction. If the other party cheats, the honest party has a window, defined by the channel's timelocks, to publish the penalty transaction on the Litecoin chain.

Using Lightning is optional. A normal on-chain Litecoin payment does not go through a channel, and MWEB confidential payments are a separate feature of the base layer. Wallets that support Lightning on Litecoin keep channel state in addition to ordinary keys. A user still needs a Litecoin balance to open a channel, and routing can fail when no path has enough capacity. This article does not rank wallets and does not claim that every Litecoin wallet speaks Lightning.

Lightning is not a second coin and it does not change the 84 million supply cap. Capacity locked in channels is LTC that already exists. Fees on a routed payment are set by the operators of the channels along the path, in litoshis, and they are distinct from the on-chain fee a user pays to open or close a channel.

---
*Editor note. States that Litecoin can be used on Lightning because SegWit is active, channels lock LTC, and settlement is an on-chain transaction. Does not name a wallet, a capacity figure, or a launch-day lightning transaction. Please confirm the malleability sentence is the level of detail we want; the golden needle is the word "lightning".*
