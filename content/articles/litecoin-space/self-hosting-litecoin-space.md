---
title: "Self-hosting Litecoin Space"
category: Build on Litecoin
sourceUrl: https://litecoinspace.org/docs/faq
sourceTier: pinned
reviewIntervalDays: 180
---

# Self-hosting Litecoin Space

## Who runs litecoinspace.org?

Litecoin Space is operated by the **Litecoin Foundation**. The software is a fork of mempool.space, released under AGPLv3+ and MIT, and the Litecoin fork is published at github.com/litecoin-foundation/ltcspace. Because it is open source you can run your own instance, which gives you a private explorer that trusts only your own node.

## What a Litecoin Space instance needs

An instance has three parts:

1. a fully synced **Litecoin Core** node (`litecoind`) that the backend queries over RPC;
2. an **Electrum-protocol server** indexing the chain, which the backend uses for address lookups;
3. the **Litecoin Space backend and frontend** (Node.js services plus a database), which build the mempool view, projected blocks and web UI.

Address history is the expensive part, which is why the choice of Electrum server matters (see below).

## Installation routes

The project's README describes a spectrum from one-click installs to production deployments:

- **One-click on a Raspberry Pi full-node distribution.** The upstream mempool project ships on Umbrel, RaspiBlitz, myNode, RoninDojo and StartOS. The Litecoin Space FAQ lists the same distributions, but the repository README currently marks one-click installation as "being worked on" with the list commented out, so check the repository for the current status before relying on this route.
- **Docker.** Docker images and a `docker/` directory with compose instructions are provided for anyone comfortable running containers.
- **Manual install.** The `backend/` and `frontend/` directories carry developer-oriented instructions, and `production/` documents a higher-performance deployment intended for serious instances. The project recommends these only for people with server-administration experience.

Block audits and block health are **not** available on self-hosted instances; they depend on resources and uptime that only the official instance provides.

## Why do some address lookups fail on my instance?

Almost always because of the Electrum server backend. Litecoin Space can use any implementation of the Electrum server protocol, but they differ in capability:

- **romanz/electrs**: the common default on Pi distributions because it is light on resources. It handles ordinary queries well but struggles with heavy ones, such as addresses with thousands of transactions, especially on low-power hardware.
- **Fulcrum**: needs more resources than electrs but still fits a Raspberry Pi and handles heavy queries far better. The first thing to try if electrs times out.
- **electrs-ltc**: the backend behind litecoinspace.org itself, a Litecoin fork of Blockstream's Esplora/electrs, aimed at maximum performance and large deployments. Appropriate for strong hardware.

## Where to get help

The FAQ, the repository's issue tracker and the Litecoin community channels are the support routes. Remember that an explorer only reads chain data; it cannot recover funds or repair wallets.

---
*Editor note. Snapshot of the "Self-Hosting" section of litecoinspace.org/docs/faq combined with the ltcspace repository README (v3.3.x). Discrepancy flagged in the text: the FAQ advertises one-click installers but the README has that section commented out as in progress. The page is JavaScript-rendered and cannot be imported by the registry; the README is imported separately as "Litecoin Space: Litecoin Space".*
