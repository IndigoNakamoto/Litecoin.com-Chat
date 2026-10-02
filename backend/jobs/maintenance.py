"""
Scheduled maintenance jobs (ARQ cron). The worker executes these; the admin
API can also enqueue any of them on demand.

    flag_stale_articles     nightly   review-window report -> Mongo + Discord
    run_golden_eval         nightly   golden set through the pipeline, diff vs last run
    cluster_gap_candidates  daily     collapse repeated gaps into one CMS draft each
    reconcile_embeddings    weekly    re-embed published docs missing from the vector store
    ingest_doc_sources      weekly    refresh Core / MWEB / Space / litecoin.com drafts

Every job is wrapped by `_run` which records status (Redis + Mongo) and never
lets bookkeeping or alerting failures mask the job's own result.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from backend.jobs.status import get_last_run, record_job_finish, record_job_start

logger = logging.getLogger(__name__)

STALE_DEFAULT_INTERVAL_DAYS = int(os.getenv("STALE_DEFAULT_REVIEW_INTERVAL_DAYS", "180"))
GAP_CLUSTER_SIMILARITY = float(os.getenv("GAP_CLUSTER_SIMILARITY", "0.85"))
# First night at >=2 produced junk drafts ("Live Agent", a debit-card question). Require real
# demand, a recognised topic, and a question the safety router would actually answer.
GAP_CLUSTER_MIN_FREQUENCY = int(os.getenv("GAP_CLUSTER_MIN_FREQUENCY", "3"))
GAP_CLUSTER_MAX_DRAFTS_PER_RUN = int(os.getenv("GAP_CLUSTER_MAX_DRAFTS_PER_RUN", "5"))
GAP_CLUSTER_MIN_QUESTION_WORDS = int(os.getenv("GAP_CLUSTER_MIN_QUESTION_WORDS", "4"))


def _draftable_question(question: str, topic: Optional[str]) -> Optional[str]:
    """Return None if the cluster representative is worth a CMS draft, else the reason it is not."""
    q = (question or "").strip()
    if len(q.split()) < GAP_CLUSTER_MIN_QUESTION_WORDS:
        return "too_short"
    if not topic:
        return "no_topic_cluster"
    try:
        from backend.services.safety_router import classify_safety
        from backend.utils.litecoin_vocabulary import is_litecoin_related

        intent, category = classify_safety(q)
        if intent is not None:
            return f"safety_{intent}_{category}"
        if not is_litecoin_related(q):
            return "off_topic"
    except Exception as e:  # noqa: BLE001
        logger.debug("draftable check fell back: %s", e)
    return None


async def _alert(title: str, description: str, level: str = "info", fields: Optional[List[Dict[str, Any]]] = None) -> None:
    try:
        from backend.monitoring.discord_alerts import send_ops_alert

        await send_ops_alert(title, description, level=level, fields=fields)
    except Exception as e:  # noqa: BLE001
        logger.debug("ops alert failed: %s", e)


async def _run(name: str, fn: Callable[[str], Awaitable[Dict[str, Any]]]) -> Dict[str, Any]:
    run_id = await record_job_start(name)
    try:
        summary = await fn(run_id)
        await record_job_finish(name, run_id, "success", summary=summary)
        logger.info("[job %s] success: %s", name, summary)
        return summary
    except Exception as e:  # noqa: BLE001
        logger.error("[job %s] failed: %s", name, e, exc_info=True)
        await record_job_finish(name, run_id, "error", error=str(e)[:1000])
        await _alert(f"Job failed: {name}", str(e)[:1500], level="error")
        raise


async def _mongo_db():
    from backend.dependencies import MONGO_DATABASE_NAME, get_mongo_client

    client = await get_mongo_client()
    if client is None:
        raise ConnectionError("MongoDB unavailable")
    return client[MONGO_DATABASE_NAME]


def _vector_collection_name() -> str:
    return os.getenv("MONGO_COLLECTION_NAME", "litecoin_docs")


def _as_dt(v: Any) -> Optional[datetime]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# --------------------------------------------------------------------------- 1) stale docs


async def _flag_stale_articles(run_id: str) -> Dict[str, Any]:
    db = await _mongo_db()
    coll = db[_vector_collection_name()]
    now = datetime.now(timezone.utc)

    pipeline = [
        {"$match": {"metadata.payload_id": {"$exists": True}, "metadata.status": "published"}},
        {
            "$group": {
                "_id": "$metadata.payload_id",
                "title": {"$first": "$metadata.doc_title"},
                "slug": {"$first": "$metadata.slug"},
                "updated_at": {"$max": "$metadata.updated_at"},
                "last_reviewed_at": {"$max": "$metadata.last_reviewed_at"},
                "review_interval_days": {"$first": "$metadata.review_interval_days"},
                "source_tier": {"$first": "$metadata.source_tier"},
                "chunks": {"$sum": 1},
            }
        },
    ]
    stale: List[Dict[str, Any]] = []
    total = 0
    async for row in coll.aggregate(pipeline):
        total += 1
        interval = row.get("review_interval_days")
        try:
            interval = int(interval) if interval not in (None, "") else STALE_DEFAULT_INTERVAL_DAYS
        except (TypeError, ValueError):
            interval = STALE_DEFAULT_INTERVAL_DAYS
        if interval <= 0:
            continue
        anchor = _as_dt(row.get("last_reviewed_at")) or _as_dt(row.get("updated_at"))
        if anchor is None:
            continue
        age_days = (now - anchor).days
        if age_days > interval:
            stale.append(
                {
                    "payload_id": row["_id"],
                    "title": row.get("title"),
                    "slug": row.get("slug"),
                    "tier": row.get("source_tier") or "cms",
                    "age_days": age_days,
                    "review_interval_days": interval,
                    "last_reviewed_at": (_as_dt(row.get("last_reviewed_at")) or anchor).isoformat(),
                }
            )
    stale.sort(key=lambda r: -r["age_days"])

    # Fold in thumbs-down pressure so the Friday review reads one list.
    try:
        fb = db[os.getenv("ANSWER_FEEDBACK_COLLECTION_NAME", "answer_feedback")]
        since = now - timedelta(days=30)
        downs: Dict[str, int] = {}
        async for row in fb.aggregate(
            [
                {"$match": {"verdict": "down", "timestamp": {"$gte": since}}},
                {"$unwind": "$source_payload_ids"},
                {"$group": {"_id": "$source_payload_ids", "n": {"$sum": 1}}},
            ]
        ):
            downs[str(row["_id"])] = int(row["n"])
        for s in stale:
            s["thumbs_down_30d"] = downs.get(str(s["payload_id"]), 0)
    except Exception as e:  # noqa: BLE001
        logger.debug("stale report: feedback join skipped: %s", e)

    await db["stale_doc_reports"].insert_one({"run_id": run_id, "ran_at": now, "total_published": total, "stale": stale})

    summary = {"total_published": total, "stale_count": len(stale), "top": [s["title"] for s in stale[:10]]}
    if stale:
        fields = [
            {"name": f"{s['title'] or s['payload_id']}", "value": f"{s['age_days']}d old (window {s['review_interval_days']}d), {s.get('thumbs_down_30d', 0)} 👎", "inline": False}
            for s in stale[:10]
        ]
        await _alert(
            f"Stale-doc report: {len(stale)} of {total} published articles past review window",
            "Re-date or fix these in the CMS (set lastReviewedAt). Source chips already show them as 'needs review'.",
            level="warning",
            fields=fields,
        )
    return summary


async def flag_stale_articles(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await _run("flag_stale_articles", _flag_stale_articles)


# --------------------------------------------------------------------------- 2) golden eval


async def _run_golden_eval(run_id: str) -> Dict[str, Any]:
    from backend.eval.golden_runner import eval_enabled, report_to_dict, run_golden_eval

    if not eval_enabled():
        return {"skipped": True, "reason": "GOLDEN_EVAL_ENABLED=false"}

    from backend.main import rag_pipeline_instance  # worker already imports main for other jobs

    previous = await get_last_run("run_golden_eval", status="success")
    prev_per_q = ((previous or {}).get("summary") or {}).get("per_question") or {}

    report = await run_golden_eval(rag_pipeline_instance, run_id=run_id, previous_per_question=prev_per_q)
    payload = report_to_dict(report)

    db = await _mongo_db()
    await db["eval_runs"].insert_one({"run_id": run_id, "ran_at": datetime.now(timezone.utc), **payload})

    if report.should_alert:
        fields = []
        if report.regressions:
            fields.append({"name": "Regressions (passed last run, failed now)", "value": ", ".join(report.regressions)[:1000], "inline": False})
        if report.behavior_failures:
            fields.append({"name": "Behavior failures (abstain/refuse/lookup wrong)", "value": ", ".join(report.behavior_failures)[:1000], "inline": False})
        if report.citation_misses:
            fields.append({"name": "Citation misses", "value": ", ".join(report.citation_misses)[:1000], "inline": False})
        await _alert(
            f"Golden set: {report.passed}/{report.total} passed",
            f"{len(report.regressions)} regression(s), {len(report.behavior_failures)} behavior failure(s), {len(report.citation_misses)} citation miss(es). Fixed since last run: {len(report.fixed)}.",
            level="error" if report.regressions else "warning",
            fields=fields,
        )
    return report.summary()


async def run_golden_eval_job(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await _run("run_golden_eval", _run_golden_eval)


# --------------------------------------------------------------------------- 3) gap clustering


def _cosine(a: List[float], b: List[float]) -> float:
    import numpy as np

    va, vb = np.asarray(a, dtype="float32"), np.asarray(b, dtype="float32")
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(va @ vb / denom) if denom else 0.0


async def _cluster_gap_candidates(run_id: str) -> Dict[str, Any]:
    """Collapse pending candidates whose questions embed within GAP_CLUSTER_SIMILARITY into one
    representative, then draft a CMS article for clusters with enough demand."""
    from backend.dependencies import get_knowledge_candidates_collection

    coll = await get_knowledge_candidates_collection()
    pending: List[Dict[str, Any]] = []
    async for doc in coll.find({"status": "pending"}).sort("timestamp", 1).limit(1000):
        pending.append(doc)

    clusters: List[List[Dict[str, Any]]] = []
    for cand in pending:
        emb = cand.get("question_embedding")
        placed = False
        if emb:
            for cluster in clusters:
                rep_emb = cluster[0].get("question_embedding")
                if rep_emb and len(rep_emb) == len(emb) and _cosine(emb, rep_emb) >= GAP_CLUSTER_SIMILARITY:
                    cluster.append(cand)
                    placed = True
                    break
        if not placed:
            clusters.append([cand])

    merged = 0
    drafted = 0
    drafted_titles: List[str] = []
    skipped: Dict[str, int] = {}
    for cluster in clusters:
        rep = max(cluster, key=lambda c: (int(c.get("question_frequency") or 1), len(c.get("generated_answer") or "")))
        others = [c for c in cluster if c["_id"] != rep["_id"]]
        total_freq = sum(int(c.get("question_frequency") or 1) for c in cluster)

        if others:
            await coll.update_many(
                {"_id": {"$in": [c["_id"] for c in others]}},
                {"$set": {"status": "merged", "merged_into": str(rep["_id"]), "reviewed_at": datetime.now(timezone.utc), "reviewed_by": "cluster_job"}},
            )
            await coll.update_one(
                {"_id": rep["_id"]},
                {
                    "$set": {"question_frequency": total_freq},
                    "$addToSet": {"similar_candidate_ids": {"$each": [str(c["_id"]) for c in others]}},
                    "$push": {"question_variants": {"$each": [c.get("user_question") for c in others if c.get("user_question")], "$slice": -20}},
                },
            )
            merged += len(others)

        if total_freq >= GAP_CLUSTER_MIN_FREQUENCY and not rep.get("payload_article_id") and drafted < GAP_CLUSTER_MAX_DRAFTS_PER_RUN:
            reason = _draftable_question(rep.get("user_question") or "", rep.get("topic_cluster"))
            if reason:
                skipped[reason] = skipped.get(reason, 0) + 1
                logger.info("cluster job: not drafting %r (%s)", (rep.get("user_question") or "")[:60], reason)
                continue
            try:
                from backend.services.article_draft_generator import create_payload_draft

                variants = [c.get("user_question") for c in others if c.get("user_question")]
                answer = rep.get("generated_answer") or ""
                if variants:
                    answer += "\n\n## Questions this should also answer\n" + "\n".join(f"- {v}" for v in variants[:10])
                article_id = await create_payload_draft(
                    question=rep.get("user_question") or "Untitled gap",
                    answer=answer,
                    topic=rep.get("topic_cluster"),
                    grounding_sources=rep.get("grounding_sources") or [],
                    publish_status="draft",
                )
                await coll.update_one(
                    {"_id": rep["_id"]},
                    {"$set": {"payload_article_id": article_id, "admin_notes": f"Auto-drafted by cluster job {run_id} (freq={total_freq}). Review in CMS before publishing."}},
                )
                drafted += 1
                drafted_titles.append((rep.get("user_question") or "")[:80])
            except Exception as e:  # noqa: BLE001
                logger.warning("cluster job: draft failed for %s: %s", rep.get("_id"), e)

    summary = {"pending_seen": len(pending), "clusters": len(clusters), "merged": merged, "drafted": drafted, "drafted_titles": drafted_titles, "skipped": skipped}
    if drafted or merged:
        await _alert(
            f"Gap queue: {len(clusters)} clusters from {len(pending)} pending ({merged} merged, {drafted} new drafts)",
            "Drafts are in the CMS as `draft`. Monday review: approve, rewrite, or reject.",
            level="info",
            fields=[{"name": "New drafts", "value": "\n".join(drafted_titles) or "none", "inline": False}],
        )
    return summary


async def cluster_gap_candidates(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await _run("cluster_gap_candidates", _cluster_gap_candidates)


# --------------------------------------------------------------------------- 4) reconcile


async def _payload_published_docs() -> List[Dict[str, Any]]:
    import httpx

    from backend.services.article_draft_generator import _get_payload_url, _payload_headers

    base = _get_payload_url()
    headers = _payload_headers()
    docs: List[Dict[str, Any]] = []
    page = 1
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            resp = await client.get(
                f"{base}/api/articles",
                params={"where[status][equals]": "published", "limit": 100, "page": page, "depth": 0, "locale": "en"},
                headers=headers,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Payload list failed: {resp.status_code} {resp.text[:200]}")
            data = resp.json()
            docs.extend(data.get("docs") or [])
            if not data.get("hasNextPage"):
                break
            page += 1
    return docs


async def _reconcile_embeddings(run_id: str) -> Dict[str, Any]:
    from backend.jobs.enqueue import enqueue_delete, enqueue_ingest

    db = await _mongo_db()
    coll = db[_vector_collection_name()]

    published = await _payload_published_docs()
    published_by_id = {str(d.get("id")): d for d in published}

    indexed: Dict[str, Optional[datetime]] = {}
    async for row in coll.aggregate(
        [
            {"$match": {"metadata.payload_id": {"$exists": True}}},
            {"$group": {"_id": "$metadata.payload_id", "updated_at": {"$max": "$metadata.updated_at"}}},
        ]
    ):
        indexed[str(row["_id"])] = _as_dt(row.get("updated_at"))

    missing = [pid for pid in published_by_id if pid not in indexed]
    stale_ids = [
        pid
        for pid, d in published_by_id.items()
        if pid in indexed and indexed[pid] is not None and (_as_dt(d.get("updatedAt")) or indexed[pid]) > indexed[pid] + timedelta(minutes=1)
    ]
    orphans = [pid for pid in indexed if pid not in published_by_id]

    re_embedded = 0
    for pid in missing + stale_ids:
        doc = published_by_id[pid]
        try:
            await enqueue_ingest(doc, "update")
            re_embedded += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("reconcile: enqueue ingest failed for %s: %s", pid, e)
    removed = 0
    for pid in orphans:
        try:
            await enqueue_delete(pid, "unpublish")
            removed += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("reconcile: enqueue delete failed for %s: %s", pid, e)

    summary = {
        "published": len(published_by_id),
        "indexed": len(indexed),
        "missing": len(missing),
        "stale": len(stale_ids),
        "orphans": len(orphans),
        "re_embed_enqueued": re_embedded,
        "delete_enqueued": removed,
    }
    if missing or stale_ids or orphans:
        await _alert(
            f"Embedding reconcile: {len(missing)} missing, {len(stale_ids)} stale, {len(orphans)} orphaned",
            f"Enqueued {re_embedded} re-embeds and {removed} deletes. These are webhook deliveries that were lost; no action needed unless it repeats.",
            level="warning" if (missing or orphans) else "info",
        )
    return summary


async def reconcile_embeddings(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await _run("reconcile_embeddings", _reconcile_embeddings)


async def _reingest_all_published(run_id: str) -> Dict[str, Any]:
    """Re-ingest every published article from Payload.

    Unlike `reindex_vectors` (which only re-embeds the chunks already in Mongo), this
    re-runs chunking + metadata, so new Article fields (sourceUrl, sourceTier, review
    dates) reach the vector store. One-shot after schema changes; not on the cron.
    """
    from backend.jobs.enqueue import enqueue_ingest

    published = await _payload_published_docs()
    enqueued = 0
    for doc in published:
        try:
            await enqueue_ingest(doc, "update")
            enqueued += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("reingest: enqueue failed for %s: %s", doc.get("id"), e)
    summary = {"published": len(published), "enqueued": enqueued}
    await _alert(
        f"Re-ingest queued for {enqueued} published articles",
        "Each article is re-chunked and re-embedded with current metadata. Press 'Reload index into API' once the worker is idle.",
        level="info",
    )
    return summary


async def reingest_all_published(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await _run("reingest_all_published", _reingest_all_published)


# --------------------------------------------------------------------------- 5) doc sources


async def _ingest_doc_sources(run_id: str) -> Dict[str, Any]:
    from backend.data_ingestion.doc_sources import run_all

    apply = os.getenv("DOC_SOURCES_APPLY", "true").lower() == "true"
    reports = await run_all(apply=apply)
    summary = {"apply": apply, "sources": [r.summary() for r in reports]}
    created = sum(len(r.created) for r in reports)
    updated = sum(len(r.updated) for r in reports)
    errors = sum(len(r.errors) for r in reports)
    if created or errors:
        await _alert(
            f"Reference docs refreshed: {created} new drafts, {updated} updated, {errors} errors",
            "New drafts wait in the CMS for review. Errors usually mean an upstream path moved; check doc_sources.yaml.",
            level="warning" if errors else "info",
            fields=[{"name": r.source_id, "value": f"fetched {len(r.fetched)}, created {len(r.created)}, updated {len(r.updated)}, errors {len(r.errors)}", "inline": False} for r in reports],
        )
    return summary


async def ingest_doc_sources(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return await _run("ingest_doc_sources", _ingest_doc_sources)


JOB_FUNCTIONS: Dict[str, Callable[..., Awaitable[Dict[str, Any]]]] = {
    "flag_stale_articles": flag_stale_articles,
    "run_golden_eval": run_golden_eval_job,
    "cluster_gap_candidates": cluster_gap_candidates,
    "reconcile_embeddings": reconcile_embeddings,
    "ingest_doc_sources": ingest_doc_sources,
    "reingest_all_published": reingest_all_published,
}
