# Paper Miner

**A configurable research-paper mining pipeline — build focused, venue-curated reading lists on any topic from [OpenAlex](https://openalex.org) + [Semantic Scholar](https://www.semanticscholar.org).**

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Dependencies](https://img.shields.io/badge/deps-requests%20%2B%20PyYAML-lightgrey)
![API key](https://img.shields.io/badge/API%20key-not%20required-success)

Point it at a topic — *LLM evaluation, graph neural networks, recommender
systems, RLHF, anything* — and it returns a clean, de-duplicated, analysis-ready
**TSV + JSON** of the relevant papers from the venues you care about. It's a
lightweight tool for **automated literature review**, **systematic literature
search**, and **building a reading list** without paywalls or API keys.

> 🔎 Mine any field by editing one file (`config.yaml`). The repo ships with a
> working example config for *diversity in recommender systems*; swap the
> keywords to make it yours. See `output/diversity_audit.md` for an example of
> what you can build on top of the data.

---

## Why Paper Miner?

- **Topic-agnostic & config-driven** — no code changes to mine a new field; just
  edit keywords + venues in `config.yaml`.
- **No API key required** — uses the free tiers of OpenAlex and Semantic Scholar.
- **Venue-curated & precise** — whitelist the conferences/journals that matter
  (e.g. NeurIPS, SIGIR, KDD, ACL) and filter **server-side** so results stay
  on-topic, not a noisy keyword dump.
- **Two sources, merged & de-duplicated** — OpenAlex for breadth, Semantic
  Scholar for the ML conferences OpenAlex under-indexes (NeurIPS / ICML / ICLR).
- **Budget-tolerant & resumable** — per-query caching lets a large mine resume
  across daily rate-limit windows without losing data.
- **Rich, structured output** — citations, abstracts, affiliations (with an
  industry/company signal), open-access PDFs, topics, and more — ready for
  pandas, a spreadsheet, or an LLM.

## Who is this for?

- **Researchers & students** running a literature review or staying current in a
  field.
- **Engineers & applied scientists** scouting productionizable ideas from recent
  top-venue papers.
- **Research/ML teams** building curated, refreshable reading lists or paper
  digests.
- **Anyone** who wants a reproducible, scriptable alternative to manually
  searching Google Scholar.

## Table of contents

- [Quick start](#quick-start)
- [Configure it for your own topic](#configure-it-for-your-own-topic)
- [Usage](#usage)
- [Configuration reference](#configuration-reference)
- [Output schema](#output-schema)
- [Design](#design)
- [Caching & resumable runs](#caching--resumable-runs)
- [Troubleshooting](#troubleshooting)
- [Suggested GitHub topics](#suggested-github-topics)
- [Contributing](#contributing)
- [License](#license)

## Quick start

Requires Python 3.9+.

```bash
git clone <your-repo-url> paper_miner
cd paper_miner

python3 -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt

# (recommended) set your email for OpenAlex's faster "polite pool"
#   edit config.yaml -> openalex.mailto

python miner.py --config config.yaml
```

Quick smoke test (caps total papers, finishes in seconds):

```bash
python miner.py --limit 50
```

Outputs land in `output/papers.tsv` and `output/papers.json`.

## Configure it for your own topic

Mining a different field takes ~2 minutes — edit `config.yaml`:

1. **Set the keywords** under `query.keyword_groups`. Use specific phrases for
   precision, e.g. for retrieval-augmented generation:
   ```yaml
   query:
     keyword_groups:
       - scope: title_and_abstract
         keywords:
           - "retrieval augmented generation"
           - "retrieval-augmented generation"
           - "RAG large language model"
           - "dense passage retrieval"
   ```
2. **Pick your venues** under `venues` (and the optional `semantic_scholar`
   section for NeurIPS/ICML/ICLR). Each venue maps a label to lowercase
   substrings found in the OpenAlex venue name, e.g.:
   ```yaml
   venues:
     - name: "ACL"
       patterns: ["annual meeting of the association for computational linguistics"]
     - name: "EMNLP"
       patterns: ["empirical methods in natural language processing"]
   ```
3. **Set the year range** under `query.from_year` / `to_year`.
4. Re-resolve venues and run:
   ```bash
   python miner.py --refresh-sources
   ```

That's it — no code changes.

## Usage

```
python miner.py [options]

--config PATH         path to the config YAML (default: config.yaml)
--limit N             cap total papers in the output (quick test)
--output-dir DIR      write outputs somewhere other than config's output.dir
--no-venue-filter     keep all venues, ignore the curated whitelist
--refresh             ignore the per-query results cache and re-fetch everything
--refresh-sources     re-resolve venue names -> OpenAlex source IDs
```

Common recipes:

```bash
# Mine a different topic: edit config.yaml keywords, then
python miner.py

# Re-resolve venues after editing the `venues:` list
python miner.py --refresh-sources

# Full clean re-fetch (e.g. after changing filters)
python miner.py --refresh

# Write to a scratch dir
python miner.py --output-dir ./out_experiment
```

## Configuration reference

Everything is driven by `config.yaml`. Key sections:

### `query`
| Key | Meaning |
|-----|---------|
| `from_year` / `to_year` | Inclusive publication-year range. |
| `keyword_groups` | List of groups, each with a `scope`, optional `venues`, and `keywords`. A paper is kept if it matches **any** keyword in **any** group (logical OR). |

Per-group fields:
- `scope`: `title` (most precise), `title_and_abstract` (balanced), or
  `fulltext` (broadest, noisiest).
- `venues` *(optional)*: restrict this group to specific curated venue names;
  omit to search all venues. Use this to keep generic words (`novel`, `diverse`)
  from matching unrelated papers in broad venues.
- `keywords`: phrases passed to the source's phrase search.

> The legacy single-group form (`query.keywords` + `query.search_scope`) is still
> supported for backward compatibility.

### `openalex`
| Key | Meaning |
|-----|---------|
| `mailto` | Your email → OpenAlex "polite pool" (faster, more reliable). |
| `api_key` | Optional premium key for a higher daily budget. Blank = free tier. |
| `per_page` | Page size (200 max). |
| `max_records_per_keyword` | Safety cap per keyword query. |
| `request_delay_seconds` | Politeness delay between calls. |
| `max_retries` | Retries on 429/5xx before giving up. |

### `semantic_scholar`
Supplementary source for NeurIPS / ICML / ICLR. Set `enabled: false` to skip.
Each venue entry has `s2_names` (spellings sent to the S2 `venue` filter),
`match` (lowercase substrings to verify the returned venue), and optional
`exclude` (guard against near-name collisions, e.g. ICMLA vs ICML).

### `filters`
| Key | Meaning |
|-----|---------|
| `require_venue_match` | Keep only papers in the curated venue whitelist (toggle with `--no-venue-filter`). |
| `min_citations` | Drop papers below this citation count. |
| `allowed_types` | Keep only these OpenAlex work types (e.g. `article`, `proceedings-article`). |

### `venues`
The curated whitelist. Each entry has a `name` (the label shown in output) and
`patterns` — lowercase substrings matched against the OpenAlex venue display
name. Add a venue by adding an entry with discriminative patterns.

### `output`
| Key | Meaning |
|-----|---------|
| `dir`, `tsv`, `json` | Output location and filenames. |
| `description_sentences` | Leading abstract sentences used for the `description` column. |

## Output schema

One row per unique paper. The TSV contains all columns below except
`abstract`; the JSON additionally includes the full reconstructed `abstract`.

| Field | Description |
|-------|-------------|
| `link` | DOI link (or landing page) to the paper |
| `venue` | Curated venue label (e.g. *NeurIPS*, *SIGIR*) |
| `year` | Publication year |
| `citations` | Citation count (`cited_by_count`) |
| `description` | First few abstract sentences |
| `institutions` | All author affiliations |
| `companies` | Affiliations OpenAlex classifies as companies (industry signal) |
| `title`, `authors`, `num_authors` | Basic metadata |
| `doi`, `openalex_id`, `oa_pdf_url` | Identifiers + open-access PDF when available |
| `is_open_access`, `oa_status` | Open-access signals |
| `primary_topic`, `concepts` | Topical tags for filtering/clustering |
| `referenced_works_count`, `type` | Extra signal fields |
| `source` | `openalex` or `semantic_scholar` |
| `matched_keywords` | Which configured keywords matched (with `[scope]` tag) |
| `abstract` | Full reconstructed abstract (**JSON only**) |

> Note: the Semantic Scholar bulk endpoint does not expose author affiliations,
> so `institutions`/`companies` are empty for S2-sourced rows.

## Design

The pipeline is a single file (`miner.py`) organized as a linear, cache-backed
flow: **resolve venues → query each keyword → extract & filter → merge/dedup →
write**. For the full architecture, data-flow diagram, caching model, and
extension points, see **[DESIGN.md](DESIGN.md)**.

## Caching & resumable runs

Two caches (written next to `config.yaml`, both gitignored):

- **`sources_cache.json`** — venue name → OpenAlex source IDs, resolved once.
  Rebuild after editing `venues:` with `--refresh-sources`.
- **`results_cache.json`** — per-query results, keyed by year range + scope +
  venue scoping + keyword. A query that **succeeded** on any prior run is reused
  (no API call); a query that was **throttled** is *not* cached and is retried
  next run. Output is the union of all cached + freshly fetched queries, so a
  partial run never overwrites earlier data.

This makes large mines budget-tolerant: run, let some queries throttle, wait for
the budget to reset, run again — only the missing queries are fetched until the
run reports `throttled/failed = 0`. Each run prints, e.g.:

```
Queries: 18 from cache, 11 fetched, 4 throttled/failed (will retry next run).
```

Force a full re-fetch with `--refresh`. Changing `filters`
(`min_citations`/`allowed_types`) also requires `--refresh`, since those don't
change the cache key.

## Troubleshooting

### `Rate limit exceeded` / `Insufficient budget` (HTTP 429)
OpenAlex enforces a small **daily budget** on the free tier that **resets at
midnight UTC**. The run aborts gracefully (it never sleeps for hours) and logs
`server asked to wait ... likely rate-limited/daily cap`. Options:

1. **Wait** until after midnight UTC and re-run — cached queries are preserved.
2. **Add an API key** ([openalex.org/pricing](https://openalex.org/pricing)) under
   `openalex.api_key` for a higher budget.
3. **Reduce load** while testing with `--limit` and fewer keywords.

### No results / very few results
- Confirm your venue `patterns` actually match OpenAlex display names (try
  `--no-venue-filter` to see if venue filtering is the cause).
- Broaden a group's `scope` from `title` to `title_and_abstract`.
- Re-resolve sources after editing `venues:` with `--refresh-sources`.

### Semantic Scholar rows have empty institutions
Expected — the S2 bulk endpoint omits affiliations. Disable S2 with
`semantic_scholar.enabled: false` if you only need OpenAlex.

## Suggested GitHub topics

To help others discover this when they search GitHub, add these **topics** in
your repo settings (Repo → About → ⚙️ → Topics):

```
research-papers  literature-review  systematic-literature-review
openalex  semantic-scholar  academic-search  paper-scraper
citation-analysis  bibliometrics  reading-list  research-tools
scholarly  paper-mining  python
```

Recommended repo **description** (Repo → About):

> Configurable pipeline to mine research papers on any topic from OpenAlex &
> Semantic Scholar — venue-curated, no API key, resumable. For literature
> reviews and reading lists.

## Contributing

Issues and PRs welcome. The whole pipeline is one readable file; good first
contributions include adding venues, new output formats (CSV/Parquet), or
additional data sources behind the same merge/dedup interface (see
[DESIGN.md](DESIGN.md)).

When proposing changes, please keep the single-file, dependency-light design and
run a `--limit 50` smoke test before submitting.

## License

[MIT](LICENSE) © 2026 Senthil Rajagopalan
