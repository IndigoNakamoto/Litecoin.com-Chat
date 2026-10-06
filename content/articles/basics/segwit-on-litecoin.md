---
title: SegWit on Litecoin
category: Litecoin Basics
sourceTier: cms
reviewIntervalDays: 180
---

# SegWit on Litecoin

Yes. Litecoin supports SegWit, short for segregated witness. SegWit is a consensus upgrade that moves the signatures (the witness) out of the traditional transaction body and into a separate witness structure. Litecoin activated it on the network in May 2017, before Bitcoin did. Once it activated, every node enforcing those rules accepts SegWit transactions, and wallets may pay to native SegWit addresses that start with ltc1.

Segregated witness fixes transaction malleability. Before SegWit, a third party could tweak a signature encoding and change a transaction's identifier without changing who was paid. That made it unsafe to build a later transaction that spent an unconfirmed parent by its identifier. With the witness segregated, the identifier of a SegWit transaction commits in a way that signature tweaks do not change it. Lightning payment channels rely on that property, which is why Litecoin's Lightning support followed SegWit.

SegWit also counts witness bytes at a discount when measuring how full a block is. Litecoin, like Bitcoin, limits a block to 4,000,000 weight units, which is 1,000,000 virtual bytes. A byte of witness data weighs less than a byte of output data, so a SegWit transaction consumes less of the block than the same payment in a legacy format and typically pays a lower fee for the same number of inputs. The discount does not make witness data free, and it does not raise the 84 million supply cap.

SegWit is optional for spenders in the sense that legacy addresses (L… and M…) still work. A payer can send to a legacy address or to an ltc1 address. Coins already in a legacy output stay there until the owner spends them. Spending them in a SegWit transaction is a choice the wallet makes when it builds the payment. SegWit is not MWEB: it does not hide amounts. It changes where signatures sit and how block weight is counted.

---
*Editor note. Activation stated as May 2017, before Bitcoin, which is the commonly cited Litecoin SegWit lock-in/activation window. Please confirm the exact activation date and height (often given as 10 May 2017) against Litecoin Core release notes before publishing. Block weight 4,000,000 WU matches the Litecoin Space basics article. Golden needles: segwit, segregated witness.*
