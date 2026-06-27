#!/usr/bin/env python3
"""
Paper Miner — a configurable academic paper-mining pipeline
===========================================================

Mines research papers on ANY topic from OpenAlex (and, optionally, Semantic
Scholar), restricted to a curated set of important venues and a recent year
range, then writes the results to TSV + JSON.

The behavior is entirely config-driven (`config.yaml`): set your keywords,
venues, and year range to build a focused, venue-curated reading list for any
field. The shipped default config targets *diversity in recommender systems* as
a worked example — swap the keywords/venues to mine your own topic.

Strategy
--------
Venues are resolved to OpenAlex *source IDs* once (and cached to
`sources_cache.json`). Each keyword is then queried with a SERVER-SIDE venue
filter, so OpenAlex returns only papers from the important venues. This keeps
every query small and fast and avoids rate limiting.

Usage
-----
    pip install -r requirements.txt
    python miner.py --config config.yaml

    # Useful overrides:
    python miner.py --limit 50            # cap total papers (quick test run)
    python miner.py --no-venue-filter     # keep all venues (client-side only)
    python miner.py --refresh-sources     # re-resolve venue -> source IDs
    python miner.py --output-dir ./out2

Output fields (per paper)
-------------------------
    link, venue, year, citations, description, institutions, companies,
    title, authors, num_authors, doi, openalex_id, oa_pdf_url, is_open_access,
    oa_status, primary_topic, concepts, referenced_works_count, type,
    matched_keywords, abstract (full, JSON only)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
except ImportError:
    sys.exit("Missing dependency 'requests'. Run: pip install -r requirements.txt")

try:
    import yaml
except ImportError:
    sys.exit("Missing dependency 'PyYAML'. Run: pip install -r requirements.txt")


WORKS_URL = "https://api.openalex.org/works"
SOURCES_URL = "https://api.openalex.org/sources"
S2_BULK_URL = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
S2_FIELDS = ("title,abstract,year,venue,citationCount,referenceCount,externalIds,"
             "openAccessPdf,url,publicationTypes,fieldsOfStudy,authors")
SOURCE_IDS_PER_QUERY = 50  # max source IDs OR'd into a single works filter
MAX_BACKOFF_SECONDS = 30   # never sleep longer than this between retries
ABORT_RETRY_AFTER = 120    # if server asks to wait longer than this, give up (likely throttled/daily cap)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------
def load_config(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        sys.exit(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
# HTTP with retry / rate-limit handling
# ---------------------------------------------------------------------------
def _get_with_retry(
    session: requests.Session,
    url: str,
    params: Dict[str, Any],
    max_retries: int,
    delay: float,
) -> Optional[Dict[str, Any]]:
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, params=params, timeout=60)
        except requests.RequestException as exc:
            if attempt == max_retries:
                print(f"  ! request failed after {max_retries} attempts: {exc}", file=sys.stderr)
                return None
            time.sleep(delay * 2 * attempt)
            continue

        if resp.status_code == 200:
            return resp.json()

        if resp.status_code in (429, 500, 502, 503, 504):
            retry_after = resp.headers.get("Retry-After")
            backoff = delay * (2 ** attempt)
            if retry_after:
                try:
                    wanted = float(retry_after)
                except ValueError:
                    wanted = backoff  # HTTP-date or unparseable; ignore it
                if wanted > ABORT_RETRY_AFTER:
                    print(f"  ! server asked to wait {wanted:.0f}s (HTTP {resp.status_code}); "
                          f"likely rate-limited/daily cap. Giving up on this query.", file=sys.stderr)
                    return None
                backoff = max(backoff, wanted)
            backoff = min(backoff, MAX_BACKOFF_SECONDS)
            print(f"  . HTTP {resp.status_code}, retrying in {backoff:.1f}s "
                  f"(attempt {attempt}/{max_retries})", file=sys.stderr)
            time.sleep(backoff)
            continue

        print(f"  ! HTTP {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
        return None
    print(f"  ! exhausted {max_retries} retries for {url}", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# Venue -> OpenAlex source ID resolution (cached)
# ---------------------------------------------------------------------------
def _short_id(openalex_id: str) -> str:
    """https://openalex.org/S12345 -> S12345"""
    return (openalex_id or "").rsplit("/", 1)[-1]


def _find_source_ids(session: requests.Session, oa: Dict[str, Any], patterns: List[str]) -> List[str]:
    ids: List[str] = []
    seen = set()
    delay = oa.get("request_delay_seconds", 0.2)
    max_retries = oa.get("max_retries", 6)
    for pat in patterns:
        params: Dict[str, Any] = {
            "filter": f"display_name.search:{pat}",
            "per-page": 200,
            **_auth_params(oa),
        }
        data = _get_with_retry(session, SOURCES_URL, params, max_retries, delay)
        time.sleep(delay)
        if not data:
            continue
        for src in data.get("results", []):
            dn = (src.get("display_name") or "").lower()
            if pat.lower() in dn:
                sid = _short_id(src.get("id", ""))
                if sid and sid not in seen:
                    seen.add(sid)
                    ids.append(sid)
    return ids


def resolve_venue_sources(
    session: requests.Session,
    cfg: Dict[str, Any],
    cache_path: str,
    refresh: bool,
) -> Tuple[Dict[str, List[str]], Dict[str, str]]:
    """Return (venue_name -> [source_ids], source_id -> venue_name). Cached on disk."""
    venues_cfg = cfg.get("venues", [])
    oa = cfg["openalex"]

    cache: Dict[str, List[str]] = {}
    if os.path.exists(cache_path) and not refresh:
        try:
            with open(cache_path, "r", encoding="utf-8") as fh:
                cache = json.load(fh)
        except (json.JSONDecodeError, OSError):
            cache = {}

    venue_ids: Dict[str, List[str]] = {}
    id_to_name: Dict[str, str] = {}
    changed = False

    for v in venues_cfg:
        name = v["name"]
        patterns = v.get("patterns", [])
        key = name + "||" + "|".join(patterns)
        if key in cache and not refresh:
            ids = cache[key]
        else:
            print(f"  resolving venue source IDs: {name}")
            ids = _find_source_ids(session, oa, patterns)
            cache[key] = ids
            changed = True
        venue_ids[name] = ids
        for sid in ids:
            id_to_name.setdefault(sid, name)

    if changed:
        try:
            with open(cache_path, "w", encoding="utf-8") as fh:
                json.dump(cache, fh, indent=2)
        except OSError as exc:
            print(f"  ! could not write source cache: {exc}", file=sys.stderr)

    return venue_ids, id_to_name


def _chunk(items: List[str], size: int) -> List[List[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)] or [[]]


def load_results_cache(path: str, refresh: bool) -> Dict[str, List[Dict[str, Any]]]:
    """Load the per-query results cache (maps query key -> list of records)."""
    if refresh or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}


def save_results_cache(path: str, cache: Dict[str, List[Dict[str, Any]]]) -> None:
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False)
    except OSError as exc:
        print(f"  ! could not write results cache: {exc}", file=sys.stderr)


def build_keyword_groups(q: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize config into a list of {scope, keywords} groups.

    Supports the new `keyword_groups` form and the legacy single-group form
    (`keywords` + `search_scope`).
    """
    if q.get("keyword_groups"):
        groups = []
        for g in q["keyword_groups"]:
            groups.append({
                "scope": g.get("scope", "title_and_abstract"),
                "keywords": g.get("keywords", []),
                "venues": g.get("venues"),  # optional list of venue names; None = all venues
            })
        return groups
    return [{
        "scope": q.get("search_scope", "title_and_abstract"),
        "keywords": q.get("keywords", []),
        "venues": None,
    }]


def _auth_params(oa: Dict[str, Any]) -> Dict[str, Any]:
    """Common OpenAlex params: polite-pool email and optional premium API key."""
    params: Dict[str, Any] = {}
    if oa.get("mailto"):
        params["mailto"] = oa["mailto"]
    if oa.get("api_key"):
        params["api_key"] = oa["api_key"]
    return params


# ---------------------------------------------------------------------------
# OpenAlex works querying
# ---------------------------------------------------------------------------
def build_works_filter(
    from_year: int,
    to_year: int,
    scope: str,
    keyword: str,
    source_ids: Optional[List[str]],
) -> str:
    parts = [
        f"from_publication_date:{from_year}-01-01",
        f"to_publication_date:{to_year}-12-31",
    ]
    if scope == "title_and_abstract":
        parts.append(f"title_and_abstract.search:{keyword}")
    elif scope == "title":
        parts.append(f"title.search:{keyword}")
    if source_ids:
        parts.append("primary_location.source.id:" + "|".join(source_ids))
    return ",".join(parts)


def fetch_keyword(
    session: requests.Session,
    cfg: Dict[str, Any],
    keyword: str,
    source_ids: Optional[List[str]],
    scope: str,
) -> Tuple[List[Dict[str, Any]], bool]:
    """Fetch works for one keyword. Returns (works, success).

    success=False means a request failed/was rate-limited, so the result is
    incomplete and must NOT be cached (it should be retried on a later run).
    """
    oa = cfg["openalex"]
    q = cfg["query"]

    params: Dict[str, Any] = {
        "filter": build_works_filter(q["from_year"], q["to_year"], scope, keyword, source_ids),
        "per-page": oa.get("per_page", 200),
        "cursor": "*",
        **_auth_params(oa),
    }
    if scope == "fulltext":
        params["search"] = keyword

    cap = oa.get("max_records_per_keyword", 2000)
    delay = oa.get("request_delay_seconds", 0.2)
    max_retries = oa.get("max_retries", 6)

    collected: List[Dict[str, Any]] = []
    success = True
    while True:
        data = _get_with_retry(session, WORKS_URL, params, max_retries, delay)
        if data is None:
            success = False
            break
        results = data.get("results", [])
        collected.extend(results)
        next_cursor = data.get("meta", {}).get("next_cursor")
        if not results or not next_cursor or len(collected) >= cap:
            break
        params["cursor"] = next_cursor
        time.sleep(delay)

    return collected[:cap], success


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------
def reconstruct_abstract(inverted_index: Optional[Dict[str, List[int]]]) -> str:
    if not inverted_index:
        return ""
    positions: List[Tuple[int, str]] = []
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort(key=lambda p: p[0])
    return " ".join(word for _, word in positions)


def first_n_sentences(text: str, n: int) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(sentences[:n]).strip()


def venue_name_of(work: Dict[str, Any]) -> str:
    loc = work.get("primary_location") or {}
    source = loc.get("source") or {}
    return source.get("display_name") or ""


def source_id_of(work: Dict[str, Any]) -> str:
    loc = work.get("primary_location") or {}
    source = loc.get("source") or {}
    return _short_id(source.get("id", ""))


def match_venue_by_name(venue_name: str, venues_cfg: List[Dict[str, Any]]) -> Optional[str]:
    if not venue_name:
        return None
    low = venue_name.lower()
    for v in venues_cfg:
        for pat in v.get("patterns", []):
            if pat.lower() in low:
                return v["name"]
    return None


def resolve_label(
    work: Dict[str, Any],
    id_to_name: Dict[str, str],
    venues_cfg: List[Dict[str, Any]],
) -> Optional[str]:
    """Prefer exact source-ID match; fall back to venue-name substring match."""
    sid = source_id_of(work)
    if sid and sid in id_to_name:
        return id_to_name[sid]
    return match_venue_by_name(venue_name_of(work), venues_cfg)


def extract_institutions(work: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    all_inst: List[str] = []
    companies: List[str] = []
    seen = set()
    for authorship in work.get("authorships", []):
        for inst in authorship.get("institutions", []):
            name = inst.get("display_name")
            if not name or name in seen:
                continue
            seen.add(name)
            all_inst.append(name)
            if (inst.get("type") or "").lower() == "company":
                companies.append(name)
    return all_inst, companies


def best_link(work: Dict[str, Any]) -> str:
    doi = work.get("doi")
    if doi:
        return doi
    loc = work.get("primary_location") or {}
    landing = loc.get("landing_page_url")
    if landing:
        return landing
    return work.get("id", "")


def extract_record(work: Dict[str, Any], venue_label: str, desc_sentences: int) -> Dict[str, Any]:
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    all_inst, companies = extract_institutions(work)
    authors = [
        (a.get("author") or {}).get("display_name", "")
        for a in work.get("authorships", [])
    ]
    authors = [a for a in authors if a]
    oa = work.get("open_access") or {}
    primary_topic = (work.get("primary_topic") or {}).get("display_name", "")
    concepts = [c.get("display_name", "") for c in work.get("concepts", [])[:5]]

    return {
        "link": best_link(work),
        "venue": venue_label or venue_name_of(work),
        "year": work.get("publication_year"),
        "citations": work.get("cited_by_count", 0),
        "description": first_n_sentences(abstract, desc_sentences),
        "institutions": all_inst,
        "companies": companies,
        "title": work.get("title") or work.get("display_name") or "",
        "authors": authors,
        "num_authors": len(authors),
        "doi": work.get("doi") or "",
        "openalex_id": work.get("id", ""),
        "oa_pdf_url": oa.get("oa_url") or "",
        "is_open_access": oa.get("is_oa", False),
        "oa_status": oa.get("oa_status", ""),
        "primary_topic": primary_topic,
        "concepts": concepts,
        "referenced_works_count": work.get("referenced_works_count", 0),
        "type": work.get("type", ""),
        "source": "openalex",
        "matched_keywords": [],
        "abstract": abstract,
    }


# ---------------------------------------------------------------------------
# Semantic Scholar source (covers NeurIPS/ICML/ICLR, which OpenAlex under-indexes)
# ---------------------------------------------------------------------------
def _norm_title(t: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def canonical_key(rec: Dict[str, Any]) -> str:
    """Cross-source dedup key: DOI if present, else normalized title, else id."""
    doi = (rec.get("doi") or "").lower().strip()
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    if doi:
        return "doi::" + doi
    nt = _norm_title(rec.get("title"))
    if nt:
        return "title::" + nt
    return "id::" + (rec.get("openalex_id") or rec.get("link") or "")


def merge_record(
    bucket: Dict[str, Dict[str, Any]],
    kwmap: Dict[str, set],
    rec: Dict[str, Any],
    tags: set,
) -> None:
    """Insert rec or merge into an existing record sharing the same canonical key."""
    key = canonical_key(rec)
    if key not in bucket:
        bucket[key] = rec
        kwmap[key] = set()
    else:
        cur = bucket[key]
        # Backfill empty fields from the new record (prefers richer OpenAlex data).
        for f in ("description", "abstract", "oa_pdf_url"):
            if not cur.get(f) and rec.get(f):
                cur[f] = rec[f]
        if not cur.get("institutions") and rec.get("institutions"):
            cur["institutions"] = rec["institutions"]
    kwmap[key].update(tags)


def match_s2_venue(venue_str: str, s2_venues_cfg: List[Dict[str, Any]]) -> Optional[str]:
    if not venue_str:
        return None
    v = venue_str.lower()
    for ven in s2_venues_cfg:
        if any(e.lower() in v for e in ven.get("exclude", [])):
            continue
        if any(p.lower() in v for p in ven.get("match", [])):
            return ven["name"]
    return None


def _s2_get(
    session: requests.Session,
    url: str,
    params: Dict[str, Any],
    headers: Dict[str, str],
    max_retries: int,
    delay: float,
) -> Optional[Dict[str, Any]]:
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, params=params, headers=headers, timeout=60)
        except requests.RequestException as exc:
            if attempt == max_retries:
                print(f"  ! S2 request failed: {exc}", file=sys.stderr)
                return None
            time.sleep(delay * 2 * attempt)
            continue
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503, 504):
            backoff = min(delay * (2 ** attempt), MAX_BACKOFF_SECONDS)
            ra = resp.headers.get("Retry-After")
            if ra:
                try:
                    backoff = min(max(backoff, float(ra)), MAX_BACKOFF_SECONDS)
                except ValueError:
                    pass
            print(f"  . S2 HTTP {resp.status_code}, retrying in {backoff:.1f}s "
                  f"({attempt}/{max_retries})", file=sys.stderr)
            time.sleep(backoff)
            continue
        print(f"  ! S2 HTTP {resp.status_code}: {resp.text[:160]}", file=sys.stderr)
        return None
    return None


def fetch_s2_keyword(
    session: requests.Session,
    s2cfg: Dict[str, Any],
    keyword: str,
    venue_names: List[str],
    from_year: int,
    to_year: int,
) -> Tuple[List[Dict[str, Any]], bool]:
    """Fetch S2 papers for one keyword. Returns (papers, success); see fetch_keyword."""
    params: Dict[str, Any] = {
        "query": keyword,
        "year": f"{from_year}-{to_year}",
        "venue": ",".join(venue_names),
        "fields": S2_FIELDS,
    }
    headers: Dict[str, str] = {}
    if s2cfg.get("api_key"):
        headers["x-api-key"] = s2cfg["api_key"]
    cap = s2cfg.get("max_records_per_keyword", 1000)
    delay = s2cfg.get("request_delay_seconds", 1.0)
    max_retries = s2cfg.get("max_retries", 5)
    base = s2cfg.get("base_url", S2_BULK_URL)

    collected: List[Dict[str, Any]] = []
    success = True
    token = None
    while True:
        if token:
            params["token"] = token
        data = _s2_get(session, base, params, headers, max_retries, delay)
        if data is None:
            success = False
            break
        batch = data.get("data") or []
        collected.extend(batch)
        token = data.get("token")
        if not token or not batch or len(collected) >= cap:
            break
        time.sleep(delay)
    return collected[:cap], success


def extract_s2_record(paper: Dict[str, Any], venue_label: str, desc_sentences: int) -> Dict[str, Any]:
    abstract = paper.get("abstract") or ""
    ext = paper.get("externalIds") or {}
    doi = ext.get("DOI")
    doi_url = "https://doi.org/" + doi if doi else ""
    oa = paper.get("openAccessPdf") or {}
    authors = [a.get("name", "") for a in (paper.get("authors") or [])]
    authors = [a for a in authors if a]
    fos = paper.get("fieldsOfStudy") or []
    pub_types = paper.get("publicationTypes") or []

    return {
        "link": doi_url or paper.get("url") or oa.get("url") or "",
        "venue": venue_label or (paper.get("venue") or ""),
        "year": paper.get("year"),
        "citations": paper.get("citationCount") or 0,
        "description": first_n_sentences(abstract, desc_sentences),
        "institutions": [],   # not available from S2 bulk endpoint
        "companies": [],
        "title": paper.get("title") or "",
        "authors": authors,
        "num_authors": len(authors),
        "doi": doi_url,
        "openalex_id": "",
        "oa_pdf_url": oa.get("url") or "",
        "is_open_access": bool(oa.get("url")),
        "oa_status": "",
        "primary_topic": fos[0] if fos else "",
        "concepts": fos[:5],
        "referenced_works_count": paper.get("referenceCount") or 0,
        "type": ";".join(pub_types),
        "source": "semantic_scholar",
        "matched_keywords": [],
        "abstract": abstract,
    }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def run(cfg: Dict[str, Any], args: argparse.Namespace, cache_path: str) -> List[Dict[str, Any]]:
    filters = cfg.get("filters", {})
    venues_cfg = cfg.get("venues", [])
    out_cfg = cfg.get("output", {})
    desc_sentences = out_cfg.get("description_sentences", 5)

    require_venue = filters.get("require_venue_match", True) and not args.no_venue_filter
    min_citations = filters.get("min_citations", 0)
    allowed_types = set(t.lower() for t in filters.get("allowed_types", []))

    session = requests.Session()
    session.headers.update({"User-Agent": "paper-miner/1.1 (+https://github.com)"})

    id_to_name: Dict[str, str] = {}
    venue_ids: Dict[str, List[str]] = {}
    all_ids: List[str] = []
    if require_venue:
        print("Resolving venues to OpenAlex source IDs ...")
        venue_ids, id_to_name = resolve_venue_sources(session, cfg, cache_path, args.refresh_sources)
        all_ids = sorted({sid for ids in venue_ids.values() for sid in ids})
        print(f"  resolved {len(all_ids)} source IDs across {len(venue_ids)} venues")
        if not all_ids:
            print("  ! no source IDs resolved; falling back to client-side venue filtering",
                  file=sys.stderr)

    def chunks_for_group(group: Dict[str, Any]) -> List[Optional[List[str]]]:
        """Server-side source-ID chunks for a group, honoring an optional venue restriction."""
        if not require_venue or not all_ids:
            return [None]
        restrict = group.get("venues")
        if not restrict:
            return list(_chunk(all_ids, SOURCE_IDS_PER_QUERY))
        ids: set = set()
        for name in restrict:
            if name in venue_ids:
                ids.update(venue_ids[name])
            else:
                print(f"  ! group venue {name!r} not found in configured venues; ignored",
                      file=sys.stderr)
        if not ids:
            print("  ! group venue restriction resolved to 0 source IDs; using all venues",
                  file=sys.stderr)
            return list(_chunk(all_ids, SOURCE_IDS_PER_QUERY))
        return list(_chunk(sorted(ids), SOURCE_IDS_PER_QUERY))

    # Per-query results cache enables resume across budget windows: a query that
    # completed successfully on any prior run is reused (no API call); throttled
    # queries stay uncached and are retried next run. Output is the union of all
    # cached + freshly fetched queries, so it never shrinks on a partial run.
    results_cache_path = os.path.join(os.path.dirname(cache_path), "results_cache.json")
    cache = load_results_cache(results_cache_path, args.refresh)
    new_cache: Dict[str, List[Dict[str, Any]]] = {}
    stats = {"cache": 0, "fetched": 0, "failed": 0}

    from_year = cfg["query"]["from_year"]
    to_year = cfg["query"]["to_year"]

    bucket: Dict[str, Dict[str, Any]] = {}
    kw_match_map: Dict[str, set] = {}

    groups = build_keyword_groups(cfg["query"])
    total_kw = sum(len(g["keywords"]) for g in groups)
    counter = 0
    for group in groups:
        scope = group["scope"]
        restrict = group.get("venues")
        venues_sig = ",".join(sorted(restrict)) if restrict else "ALL"
        source_chunks = chunks_for_group(group)
        scope_note = scope if not restrict else f"{scope}, {len(restrict)} venues"
        for kw in group["keywords"]:
            counter += 1
            key = f"oa|{from_year}-{to_year}|{scope}|{venues_sig}|{kw}"
            if key in cache:
                recs = cache[key]
                new_cache[key] = recs
                stats["cache"] += 1
                print(f"[{counter}/{total_kw}] (cache) ({scope_note}) {kw!r} -> {len(recs)} records")
            else:
                works: List[Dict[str, Any]] = []
                ok = True
                for chunk in source_chunks:
                    w, cok = fetch_keyword(session, cfg, kw, chunk, scope)
                    works.extend(w)
                    ok = ok and cok
                recs = []
                for work in works:
                    if not work.get("id"):
                        continue
                    wtype = (work.get("type") or "").lower()
                    if allowed_types and wtype not in allowed_types:
                        continue
                    if work.get("cited_by_count", 0) < min_citations:
                        continue
                    label = resolve_label(work, id_to_name, venues_cfg)
                    if require_venue and label is None:
                        continue
                    recs.append(extract_record(work, label or "", desc_sentences))
                if ok:
                    new_cache[key] = recs
                    stats["fetched"] += 1
                    note = "fetched"
                else:
                    stats["failed"] += 1
                    note = "THROTTLED (will retry next run)"
                print(f"[{counter}/{total_kw}] ({scope_note}) {kw!r} -> {len(recs)} records [{note}]")

            for rec in recs:
                merge_record(bucket, kw_match_map, rec, {f"{kw} [{scope}]"})

    # Semantic Scholar pass for ML venues OpenAlex under-indexes (NeurIPS/ICML/ICLR)
    s2cfg = cfg.get("semantic_scholar", {})
    if s2cfg.get("enabled"):
        s2_venues = s2cfg.get("venues", [])
        s2_keywords = s2cfg.get("keywords", [])
        venue_param_names: List[str] = []
        for v in s2_venues:
            venue_param_names.extend(v.get("s2_names", [v["name"]]))
        s2_sig = ",".join(sorted(v["name"] for v in s2_venues))
        print(f"\nSemantic Scholar pass: {len(s2_keywords)} keywords across "
              f"{len(s2_venues)} venues ({', '.join(v['name'] for v in s2_venues)})")
        for i, kw in enumerate(s2_keywords, 1):
            key = f"s2|{from_year}-{to_year}|{s2_sig}|{kw}"
            if key in cache:
                recs = cache[key]
                new_cache[key] = recs
                stats["cache"] += 1
                print(f"[S2 {i}/{len(s2_keywords)}] (cache) {kw!r} -> {len(recs)} records")
            else:
                papers, ok = fetch_s2_keyword(session, s2cfg, kw, venue_param_names, from_year, to_year)
                recs = []
                for p in papers:
                    if (p.get("citationCount") or 0) < min_citations:
                        continue
                    if not p.get("title"):
                        continue
                    label = match_s2_venue(p.get("venue") or "", s2_venues)
                    if label is None:
                        continue
                    recs.append(extract_s2_record(p, label, desc_sentences))
                if ok:
                    new_cache[key] = recs
                    stats["fetched"] += 1
                    note = "fetched"
                else:
                    stats["failed"] += 1
                    note = "THROTTLED (will retry next run)"
                print(f"[S2 {i}/{len(s2_keywords)}] {kw!r} -> {len(recs)} records [{note}]")

            for rec in recs:
                merge_record(bucket, kw_match_map, rec, {f"{kw} [s2:{rec['venue']}]"})

    save_results_cache(results_cache_path, new_cache)
    print(f"\nQueries: {stats['cache']} from cache, {stats['fetched']} fetched, "
          f"{stats['failed']} throttled/failed (will retry next run).")
    if stats["failed"]:
        print("  -> Run again (fresh budget) to fill the throttled queries; "
              "cached results are preserved.")

    records = []
    for key, rec in bucket.items():
        rec["matched_keywords"] = sorted(kw_match_map.get(key, []))
        records.append(rec)

    records.sort(key=lambda r: (r.get("citations", 0), r.get("year") or 0), reverse=True)

    if args.limit:
        records = records[: args.limit]
    return records


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------
TSV_COLUMNS = [
    "link", "venue", "year", "citations", "description",
    "institutions", "companies", "title", "authors", "num_authors",
    "doi", "openalex_id", "oa_pdf_url", "is_open_access", "oa_status",
    "primary_topic", "concepts", "referenced_works_count", "type", "source",
    "matched_keywords",
]


def _tsv_cell(value: Any) -> str:
    if isinstance(value, list):
        value = "; ".join(str(v) for v in value)
    text = "" if value is None else str(value)
    return re.sub(r"\s+", " ", text.replace("\t", " ")).strip()


def write_tsv(records: List[Dict[str, Any]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\t".join(TSV_COLUMNS) + "\n")
        for rec in records:
            fh.write("\t".join(_tsv_cell(rec.get(col)) for col in TSV_COLUMNS) + "\n")


def write_json(records: List[Dict[str, Any]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Paper Miner — mine research papers on any topic from OpenAlex + Semantic Scholar.")
    p.add_argument("--config", default="config.yaml", help="Path to config YAML (default: config.yaml)")
    p.add_argument("--limit", type=int, default=None, help="Cap total papers in output (quick test)")
    p.add_argument("--output-dir", default=None, help="Override output directory")
    p.add_argument("--no-venue-filter", action="store_true", help="Keep all venues (client-side only)")
    p.add_argument("--refresh-sources", action="store_true", help="Re-resolve venue -> source IDs")
    p.add_argument("--refresh", action="store_true",
                   help="Ignore the per-query results cache and re-fetch everything")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    cfg = load_config(args.config)

    out_cfg = cfg.get("output", {})
    out_dir = args.output_dir or out_cfg.get("dir", "./output")
    os.makedirs(out_dir, exist_ok=True)
    cache_path = os.path.join(os.path.dirname(os.path.abspath(args.config)), "sources_cache.json")

    records = run(cfg, args, cache_path)

    tsv_path = os.path.join(out_dir, out_cfg.get("tsv", "papers.tsv"))
    json_path = os.path.join(out_dir, out_cfg.get("json", "papers.json"))
    write_tsv(records, tsv_path)
    write_json(records, json_path)

    print("\n" + "=" * 60)
    print(f"Done. {len(records)} unique papers written.")
    print(f"  TSV : {tsv_path}")
    print(f"  JSON: {json_path}")
    if records:
        venues: Dict[str, int] = {}
        for r in records:
            venues[r["venue"]] = venues.get(r["venue"], 0) + 1
        print("\nTop venues:")
        for v, n in sorted(venues.items(), key=lambda x: x[1], reverse=True)[:15]:
            print(f"  {n:4d}  {v}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
