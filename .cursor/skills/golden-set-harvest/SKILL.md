---
name: golden-set-harvest
description: >-
  Turns knowledge-gap candidates, question logs, and thumbs-down feedback into
  a reviewed golden-set batch. Use when the user mentions the golden set,
  golden questions, knowledge gaps, question logs, or thumbs-down feedback
  and wants the eval set updated.
---

# Golden-set harvest

Promote real misses into `backend/tests/eval/golden_questions.yaml`. Classification lives in `backend/eval/golden_harvest.py`. Do not re-derive it.

## Run

From the repo root:

```bash
python scripts/harvest_golden_candidates.py
```

The script is read-only. It prints a JSON packet and does not edit the golden file or Mongo. If Mongo is unreachable, or `MONGO_DETAILS` / `MONGO_URI` is unset, stop. Do not invent candidates.

Those two variables are the connection, same fallback as `backend/dependencies.py`. When they are unset, the script fills them from `.env.docker.prod`, `.env.secrets`, `backend/.env`, then `.env`. A URI whose host is the Docker name `mongodb` only works where that name resolves.

## Review

Show one table: `proposed_id`, query, sources (`gap` / `log` / `feedback`), frequency, suggested behavior, citation needle or `must_not_contain`, `close_golden_id`, and note. Also show `slots_remaining` and `dropped`.

Wait. Change the golden file only for rows the user names.

Leave a row out of the batch when:

- `close_golden_id` is set, unless the user explicitly wants that paraphrase
- `yaml_ready` is false, until the missing piece is filled
- `suggested_behavior` is `needs_review`, until the user picks `answer`, `lookup`, `refuse`, `escalate`, or `abstain`

An open Litecoin gap (`category: abstain`, `expected_behavior: answer`, empty substrings) needs `must_not_contain` for the specific wrong claim, taken from the answer excerpt. Same shape as `gap-nonexistent-feature`. Leave it out when that phrase cannot be named. A CMS draft is not a citation needle. Set `expected_source_substrings` only for a published article, using the slug or a title word that appears in the first five chips.

Non-`answer` questions keep `expected_source_substrings: []`. The runner always uses an empty history and `skip_cache=True`. The packet already drops follow-ups, questions shorter than four words, cache hits, and queries that are already in the golden file.

## Write

Append the approved questions. Ids must stay unique. If the batch would pass `cap` (90, the ceiling in `backend/tests/test_eval_scaffold.py`), raise that ceiling in the same change and say the new number.

Then run:

```bash
pytest backend/tests/test_eval_scaffold.py backend/tests/test_golden_harvest.py -q
```

Mention the live eval, and run it only when the user asks. It calls the model:

```bash
EVAL_RETRIEVAL=1 pytest -m eval backend/tests/eval
```

Do not commit unless the user asks.
