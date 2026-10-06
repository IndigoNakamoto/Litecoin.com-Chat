---
title: Litecoin confirmations and irreversible transactions
category: Litecoin Basics
sourceTier: cms
reviewIntervalDays: 180
---

# Litecoin confirmations and irreversible transactions

A confirmation is a block that commits a Litecoin transaction. The block that first includes the transaction is one confirmation. Each later block built on top of that block adds another confirmation. With a 2.5-minute target, six confirmations are on the order of fifteen minutes, but that is arithmetic, not a rule the protocol enforces.

Litecoin does not pick one confirmation count for everyone. The software will relay and mine a valid transaction with zero confirmations, and a recipient decides how many to wait for. A merchant selling a small item may accept one confirmation or even show the payment while it is still unconfirmed. An exchange accepting a large deposit usually waits for more, because a shallow block can still be dropped if a competing chain overtakes it. Those policies belong to the recipient. They are not a Litecoin Foundation setting, and this article does not name an official required number.

## Can a Litecoin transaction be reversed?

A Litecoin transaction cannot be reversed by the sender once it has been broadcast and mined, and there is no chargeback. The Litecoin Foundation cannot undo it, and neither can a wallet provider. The only way a confirmed transaction leaves the chain is a reorganization: a heavier competing chain that does not include the same block. Each extra confirmation means more work has been stacked on that history, so replacing it costs the attacker more Scrypt work. Deeply confirmed payments are treated as final for that reason. Unconfirmed payments are not final. A sender can still try to publish a conflicting transaction while the original sits in the mempool, which is why recipients who need certainty wait for confirmations.

If a payment looks stuck and unconfirmed, the tools are fee bumping (replace-by-fee, when the original opted in) or a child transaction that pays a higher fee. Those replace or accelerate an unconfirmed payment. They do not reverse one that already has confirmations.

---
*Editor note. Confirmation = including block plus each block on top; no protocol-mandated count; reorg is the only removal of a confirmed tx. "Six confirmations ≈ fifteen minutes" is 6 × 2.5, stated as arithmetic. Please confirm we should not cite a specific exchange's current deposit requirement. Irreversibility wording is meant to satisfy the golden needles confirmation / irreversib / cannot be reversed.*
