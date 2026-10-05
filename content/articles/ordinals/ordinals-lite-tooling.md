---
title: "Ordinals Lite tooling: the ord-litecoin index, explorer and wallet"
category: Ordinals & Digital Artifacts
sourceTier: cms
reviewIntervalDays: 120
---

# Ordinals Lite tooling: the ord-litecoin index, explorer and wallet

**Ordinals Lite** is the Litecoin port of `ord`, the reference ordinals software. It is one program, `ord`, that plays three roles: an **index** that tracks every litoshi, a **block explorer** that renders inscriptions, and a **command-line wallet** for receiving, inscribing and sending. The source is at github.com/ynohtna92/ord-litecoin; the public explorer runs at ordinalslite.com. It is experimental software with no warranty.

## What you need

`ord` does not run on its own. It needs a fully synced **`litecoind`** (Litecoin Core) node started with **`-txindex`**, because building the litoshi index requires looking up arbitrary historical transactions. `ord` talks to the node over RPC. If `litecoind` runs locally under the same user with default settings, `ord` finds the cookie file and RPC port automatically; otherwise pass the node's RPC credentials:

```
ord --cookie-file /path/to/cookie/file server
ord --litecoin-rpc-username foo --litecoin-rpc-password bar server
```

or set `ORD_LITECOIN_RPC_USERNAME` / `ORD_LITECOIN_RPC_PASSWORD` in the environment.

Pre-built binaries are published on the repository's releases page, there is an `install.sh` script, and the project can be built from source with `cargo build --release`. Docker, Homebrew and Debian package routes are documented in the README.

## The index

`ord index` (or simply starting the server) walks the chain from genesis and records which litoshis sit in which outputs. The first index build is long because it processes every block Litecoin has ever produced. To track **rare litoshi locations** rather than only inscriptions, the index must be built with `--index-sats`, which uses considerably more disk space. Once built, the index is updated incrementally as new blocks arrive.

## The explorer

`ord server` serves a web explorer from the local index. It shows inscriptions, their content and provenance, individual litoshis by number or name, and the outputs that hold them. The same pages are available as JSON by sending `Accept: application/json`, which is how wallets and marketplaces query an indexer. ordinalslite.com is a public instance of this explorer for Litecoin.

## The wallet

The `ord wallet` commands are a wrapper around Litecoin Core's wallet RPC: Litecoin Core holds the keys and signs, while `ord` adds **litoshi control**, choosing exactly which litoshis and inscriptions go into each transaction.

Common commands:

- `ord wallet create` – create a new `ord` wallet (backed by a Litecoin Core descriptor wallet); `ord wallet restore --from mnemonic` restores one
- `ord wallet receive` – generate a receiving address
- `ord wallet inscribe --fee-rate <lit/vB> --file <FILE>` – create an inscription (add `--parent <ID>` for provenance, or `--batch` for several at once)
- `ord wallet inscriptions`, `ord wallet outputs`, `ord wallet sats` – list what the wallet holds (`sats` needs an `--index-sats` index)
- `ord wallet send --fee-rate <lit/vB> <ADDRESS> <INSCRIPTION_ID or sat name>` – send an inscription or a specific rare litoshi
- `ord wallet dump` – export the output descriptors, including private keys, for use in another descriptor-based wallet

## Safety rules from the project

The README is explicit about three things:

1. **Litecoin Core does not know about inscriptions and does not do litoshi control.** Spending from an `ord` wallet with `litecoin-cli` or other RPC tools can send an inscription away as change or as a fee and lose it.
2. **Keep ordinal and cardinal wallets separate.** Because `ord` can access any Litecoin Core wallet on the node, do not use it on wallets holding a material amount of ordinary funds.
3. **Wallet versions are not always compatible.** Older pre-alpha `ord` wallets must be migrated by sending their litoshis and inscriptions to addresses from a wallet created with the current version.

---
*Editor note. Source: the `ord-litecoin` README (Litecoin-worded) plus the wallet, explorer and sat-hunting guides in `docs/src/guides/` (Bitcoin-worded, adapted here). Command names and flags are taken from the current master branch; re-verify against the latest release before publishing, since the CLI changes between versions.*
