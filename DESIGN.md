# Design

This document explains how Paper Miner is put together: the architecture, the
data flow, the caching model, and where to extend it. For usage and config, see
[README.md](README.md).

## Goals & constraints

The design optimizes for three things, in order:

1. **Precision** — return papers that are actually on-topic and at venues that
   matter, not a noisy keyword dump.
2. **Budget tolerance** — public APIs (OpenAlex free tier especially) impose a
   small daily budget. A large mine must survive being throttled partway and
   resume later without losing work.
3. **Simplicity** — one readable file, two dependencies (`requests`, `PyYAML`),
   no database, no framework. All behavior lives in `config.yaml`.

## High-level architecture

```
                         ┌──────────────┐
                         │  config.yaml │
                         └──────┬───────┘
                                │ load_config()
                                ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                          run()                                │
   │                                                               │
   │  1. resolve_venue_sources()    venue names → source IDs       │
   │         │  (cached: sources_cache.json)                       │
   │         ▼                                                      │
   │  2. for each keyword group / keyword:                         │
   │         ├─ fetch_keyword()      OpenAlex /works  (cursor)     │
   │         │     │  server-side filter: years + phrase + sources │
   │         │     ▼                                               │
   │         ├─ filter: type, min_citations, venue label           │
   │         ├─ extract_record()     normalize fields + abstract   │
   │         └─ merge_record()       dedup by DOI/title            │
   │                                                               │
   │  3. (optional) Semantic Scholar pass for NeurIPS/ICML/ICLR    │
   │         └─ fetch_s2_keyword() → extract_s2_record() → merge   │
   │                                                               │
   │     (every query cached: results_cache.json)                 │
   │                                                               │
   │  4. attach matched_keywords, sort by citations/year, limit    │
   └─────────────────────────────┬─────────────────────────────-──┘
                                  ▼
                    write_tsv()  +  write_json()
                                  ▼
                     output/papers.tsv / papers.json
```

## Data flow, step by step

### 1. Venue resolution (`resolve_venue_sources`)
Each configured venue name (e.g. *ACM RecSys*) is resolved to one or more
OpenAlex **source IDs** by searching the `/sources` endpoint with the venue's
`patterns`. This happens **once** and is cached in `sources_cache.json` keyed by
`name + patterns`. Resolving to IDs lets later queries filter **server-side**
(`primary_location.source.id:S1|S2|...`), which is the key to keeping each query
small and within budget.

Source IDs are chunked (`SOURCE_IDS_PER_QUERY = 50`) because a single filter can
only OR so many IDs before the URL gets unwieldy; each chunk is a separate query
and the results are concatenated.

### 2. Keyword querying (`fetch_keyword`)
For each keyword in each group, `build_works_filter` assembles an OpenAlex filter:

```
from_publication_date:<from>-01-01,
to_publication_date:<to>-12-31,
title_and_abstract.search:<keyword>,     # or title.search, per group scope
primary_location.source.id:<chunk>       # when venue filtering is on
```

Results are paged with **cursor pagination** up to `max_records_per_keyword`.
The function returns `(records, success)` — `success=False` signals a
throttled/failed query whose (incomplete) result must **not** be cached.

### 3. Filtering & extraction
Each returned work is filtered by `allowed_types`, `min_citations`, and — if
`require_venue_match` — by whether it resolves to a curated venue label
(`resolve_label`: exact source-ID match first, then venue-name substring as a
fallback). Survivors go through `extract_record`, which:

- reconstructs the abstract from OpenAlex's `abstract_inverted_index`
  (`reconstruct_abstract`),
- trims a short `description` (`first_n_sentences`),
- pulls affiliations and flags company affiliations as an industry signal,
- normalizes identifiers, open-access status, topics, and concepts.

### 4. Merge & dedup (`merge_record`, `canonical_key`)
All records flow into a single bucket keyed by a **canonical key**: DOI if
present, else a normalized title, else the OpenAlex/link id. When the same paper
arrives from multiple keywords or sources, records are merged: empty fields are
backfilled (preferring richer OpenAlex data), and the set of `matched_keywords`
accumulates. This is what lets one paper show *all* the keywords it matched.

### 5. Semantic Scholar supplement
OpenAlex severely under-indexes NeurIPS/ICML/ICLR (most of their papers are
attributed to arXiv instead). When `semantic_scholar.enabled`, the pipeline runs
a second pass against the S2 bulk search API for those venues, verifies the
returned venue string (`match`/`exclude`), and merges results into the *same*
bucket via the same `canonical_key` — so cross-source duplicates collapse
automatically. S2 rows are tagged `source = semantic_scholar`.

### 6. Output
Records get their final `matched_keywords`, are sorted by `(citations, year)`
descending, optionally truncated by `--limit`, and written to TSV (flat columns)
and JSON (adds full `abstract`).

## Caching model

Two independent, on-disk caches make runs fast and resumable. Both live next to
`config.yaml` and are gitignored.

| Cache | Keyed by | Purpose | Invalidate with |
|-------|----------|---------|-----------------|
| `sources_cache.json` | venue name + patterns | Avoid re-resolving venue→source IDs every run | `--refresh-sources` |
| `results_cache.json` | `source \| years \| scope \| venues \| keyword` | Skip already-fetched queries; enable resume | `--refresh` |

**Resume semantics** (the important part): on each run, the output is the
**union** of every query result — whether reused from cache or freshly fetched.
Only queries that *succeeded* are written back to the cache; throttled ones are
left out and naturally retried next run. So you can complete a large mine across
several daily-budget windows, and the dataset only ever grows until the run
reports `throttled/failed = 0`.

Because the cache key encodes the year range, scope, venue scoping, and keyword,
editing any of those creates new keys automatically. Editing `filters`
(`min_citations`, `allowed_types`) does **not** change the key, so use
`--refresh` after changing filters.

## HTTP & rate-limit handling

`_get_with_retry` (OpenAlex) and `_s2_get` (Semantic Scholar) implement
exponential backoff on `429/5xx`, honor a `Retry-After` header when present, and
**abort gracefully** if the server asks to wait longer than `ABORT_RETRY_AFTER`
(120s) — the signature of a daily-cap exhaustion. Backoff is capped at
`MAX_BACKOFF_SECONDS` (30s) so the process never hangs for hours. The `mailto`
param opts into OpenAlex's faster "polite pool".

## Extension points

- **Add a venue** — add an entry under `venues:` with discriminative lowercase
  `patterns`, then `--refresh-sources`.
- **Add or change keywords** — edit `query.keyword_groups`; use group `venues`
  scoping to keep generic words precise.
- **Add a data source** — implement `fetch_*` + `extract_*_record` returning the
  standard record dict, then feed records through `merge_record` with the same
  `canonical_key`. Dedup against existing sources is automatic.
- **Add an output format** — add a `write_*` function alongside `write_tsv` /
  `write_json` and call it from `main`. Keep `TSV_COLUMNS` as the canonical flat
  schema.

## Why these choices

- **Server-side venue filtering over client-side** — without it, broad keywords
  return tens of thousands of works and blow the daily budget. Resolving venues
  to source IDs once and filtering on the server is the single biggest budget
  saver.
- **Per-query caching over a single result file** — makes runs idempotent and
  resumable at the finest useful granularity (one keyword × scope × venue set).
- **Canonical-key merge over post-hoc dedup** — accumulates `matched_keywords`
  and cross-source backfill in one pass, with no separate dedup stage.
- **Single file, two deps** — this is a research/analysis tool meant to be read,
  forked, and tweaked, not deployed as a service.
