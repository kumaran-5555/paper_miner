# Diversity Papers Audit — for Reels Recommendation Ranking

Audited `papers.tsv` (583 papers). Ranked for: **(1) productionizable at scale, (2) industry-focused, (3) high impact**, with a 4th lens of **Reels-fit** (short-video / feed / ranking & re-ranking stages).

## TL;DR audit findings
- Only **~89 of 583** papers are genuinely about recommendation *diversity* (the rest are generic recsys that the miner tagged loosely on the broad "diverse recommendations" keyword — e.g. cross-domain matching, knowledge distillation, multi-view clustering, KG embedding). The list needs cleaning.
- The corpus is **academic-skewed**: only ~26 of the on-topic papers carry any industry affiliation, and very few report online A/B results at scale. Venues lean theory (AAAI/TKDE/TOIS) over applied (KDD/RecSys/WWW).
- **Gap**: the canonical *productionized* diversity papers are missing entirely (see "Missing canonical references" at bottom). Add these — they're more directly usable than most of what's in the list.
- Best directly-applicable cluster for Reels: **DPP / diversified re-ranking**, **calibration**, **filter-bubble & popularity-bias mitigation**, and **multi-interest** modeling — ideally the short-video ones (Kuaishou/micro-video).

---

## Tier 1 — Read first (most productionizable + Reels-relevant)

| # | Paper | Why it matters for Reels | Signal |
|---|-------|--------------------------|--------|
| 1 | **CIRS: Bursting Filter Bubbles by Counterfactual Interactive Recommender System** (Kuaishou, TOIS 2023) | From a **direct short-video peer**. Models overexposure/boredom and de-biases via causal user model — exactly the filter-bubble problem in an endless Reels feed. | industry✓ short-video✓ 85 cit. https://doi.org/10.1145/3594871 |
| 2 | **Feature-aware Diversified Re-ranking with Disentangled Representations for Relevant Recommendation** (KDD 2022) | Re-ranking-stage diversity with disentangled item reps — drops into the final ranking stage of the stack. Applied KDD work. | re-rank✓ 29 cit. https://doi.org/10.1145/3534678.3539130 |
| 3 | **Determinantal Point Processes Guided Crowd-wise Mixture-of-Experts for Recommendation in Alipay** (RecSys 2024) | **Productionized DPP** at Alipay scale. DPP is the canonical diversity re-ranking primitive; this shows a scaled MoE variant. | industry✓ production✓ DPP. https://doi.org/10.1145/3691357 |
| 4 | **Enhancing Recommendation Diversity by Re-ranking with Large Language Models** (RecSys 2024) | Modern LLM-based diversity re-ranking; relevant if you're exploring LLM re-rankers in the stack. | re-rank✓ 31 cit. https://doi.org/10.1145/3700604 |
| 5 | **Multi-interest Diversification for End-to-end Sequential Recommendation** (Alibaba, TOIS 2021) | Ties multi-interest retrieval to list diversity in sequential setting — maps to candidate-gen + ranking. | industry✓ 42 cit. https://doi.org/10.1145/3475768 |
| 6 | **A Hybrid Bandit Framework for Diversified Recommendation** (Alibaba US, AAAI 2021) | Exploration/bandit approach to diversity; deployable for cold/long-tail and exploration in feed. | industry✓ 23 cit. https://doi.org/10.1609/aaai.v35i5.16524 |

## Tier 2 — Strong techniques (applicable, mostly academic but high-impact)

| # | Paper | Angle | Signal |
|---|-------|-------|--------|
| 7 | **Determinantal Point Process Likelihoods for Sequential Recommendation** (SIGIR 2022) | DPP integrated into sequential model objective. | DPP, 14 cit. https://doi.org/10.1145/3477495.3531965 |
| 8 | **Popularity Bias is not Always Evil: Disentangling Benign and Harmful Bias** (TKDE 2022) | Nuanced popularity-bias framing — avoids over-correcting; directly informs feed exposure policy. | 103 cit. https://doi.org/10.1109/tkde.2022.3218994 |
| 9 | **Co-training Disentangled Domain Adaptation for Leveraging Popularity Bias** (Alibaba, SIGIR 2022) | Popularity de-bias for long-tail exposure. | industry✓ 47 cit. https://doi.org/10.1145/3477495.3531952 |
| 10 | **User-controllable Recommendation Against Filter Bubbles** (SIGIR 2022) | User-controllable diversity knobs — product-friendly lever. | 58 cit. https://doi.org/10.1145/3477495.3532075 |
| 11 | **Mitigating the Filter Bubble While Maintaining Relevance** (SIGIR 2022) | Diversity↔relevance trade-off management. | 28 cit. https://doi.org/10.1145/3477495.3531890 |
| 12 | **Relieving Popularity Bias in Interactive Recommendation: Diversity-Novelty-Aware RL** (TOIS 2023) | RL policy balancing diversity/novelty in interactive feed. | 29 cit. https://doi.org/10.1145/3618107 |
| 13 | **Understanding Diversity in Session-based Recommendation** (TOIS 2023) | Session-level diversity analysis — Reels sessions analog. | 17 cit. https://doi.org/10.1145/3600226 |

## Tier 3 — Short-video / slate specific (closest domain match)

| # | Paper | Angle | Signal |
|---|-------|-------|--------|
| 14 | **Relative Advantage Debiasing for Watch-Time Prediction in Short-Video Recommendation** (AAAI 2026) | Watch-time debiasing in short-video — adjacent to diversity, directly Reels. | short-video✓. https://doi.org/10.1609/aaai.v40i18.38555 |
| 15 | **Deconfounding Duration Bias in Watch-time Prediction for Video Recommendation** (Kuaishou, KDD 2022) | Watch-time duration bias from a short-video peer; informs the ranking objective diversity sits on top of. | industry✓ short-video✓ 82 cit. https://doi.org/10.1145/3534678.3539092 |
| 16 | **Don't Get Bored: Enhancing Scalability and Diversity in Session-Based Slate Recommendation** (RecSys 2025) | Slate-level diversity at scale — feed = slate. | slate✓. https://doi.org/10.1145/3733241 |
| 17 | **Modeling High-order Interactions across Multi-interests for Micro-video Recommendation** (AAAI 2021) | Micro-video multi-interest (short abstract). | micro-video✓. https://doi.org/10.1609/aaai.v35i18.17969 |
| 18 | **Balancing the Diversity-Coverage Trade-off in Graph-based Recommendations for Cold-Start Industrial Applications** (RecSys 2026) | Industrial cold-start diversity/coverage trade-off. | industry✓. https://doi.org/10.1145/3796509 |

## Tier 4 — Grounding: surveys & measurement (use to frame metrics/eval)

| Paper | Use | Link |
|-------|-----|------|
| **Result Diversification in Search and Recommendation: A Survey** (Microsoft, TKDE 2024) | Best landscape of methods/metrics. | https://doi.org/10.1109/tkde.2024.3382262 |
| **Calibrated Recommendations: Survey and Future Directions** (RecSys 2026) | Calibration (topic/genre proportionality) — high-leverage, cheap to ship in re-ranking. | https://doi.org/10.1145/3789266 |
| **Bias and Debias in Recommender System: A Survey** (TOIS 2022, 607 cit) | Foundational bias taxonomy. | https://doi.org/10.1145/3564284 |
| **Assessing the Impact of Music Recommendation Diversity on Listeners: A Longitudinal Study** (RecSys 2023) | Causal evidence that diversity improves long-term engagement — useful to justify the investment. | https://doi.org/10.1145/3608487 |
| **Diversity Vs Relevance: A Practical Multi-objective Study (Luxury Fashion)** (SIGIR 2022) | Practical multi-objective diversity/relevance tuning. | https://doi.org/10.1145/3477495.3531866 |

---

## Missing canonical references (add these — they're the productionized standards)
The mined list omits the industry papers most teams actually build on:
- **Practical Diversified Recommendations on YouTube with Determinantal Point Processes** — Wilhelm et al., Google/YouTube, CIKM 2018. *The* reference for DPP diversity in a video feed at scale.
- **Calibrated Recommendations** — H. Steck, Netflix, RecSys 2018. The origin of calibration; trivially applicable to Reels topic mix.
- **Managing Diversity in Airbnb Search** — KDD 2020. Production diversity in a ranking stack with online results.
- Pinterest / Instagram Explore diversity & "feed blending" write-ups (engineering blogs / KDD applied track).

## Suggested next step
Full ranked output of all 583 with scores is saved at `papers_ranked.tsv` (columns: rank, score, topic, industry, production, impact, reels_fit, ...). The Tier-1 list above is the practical starting set; I'd prototype **DPP/feature-aware diversified re-ranking (#2, #3, #7)** + **calibration** in the re-ranking stage first, since those are the cheapest to A/B in an existing stack.
