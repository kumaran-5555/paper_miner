# Cohort Prediction-Quality Papers Audit — for Reels Recommendation Ranking

Audited `output_cohort_prediction_quality/papers.tsv` (266 papers). Ranked for: **(1) productionizable at scale, (2) industry-focused, (3) high impact**, with a 4th lens of **Reels-fit** (short-video / feed / ranking & re-ranking stages).

Scope of this corpus: **model prediction quality across user-item cohorts** — measuring and closing per-cohort/per-slice NE, AUC, and calibration gaps (worst-group / group-DRO optimization, multicalibration, subgroup calibration, cold-start cohort prediction).

## TL;DR audit findings
- Of 266, only **~46 carry industry affiliation** and the corpus splits into two camps: **(a) foundational ML theory** (multicalibration, group-DRO, invariant learning — mostly NeurIPS/ICML/ICLR, no online results) and **(b) applied recsys/CTR** (KDD/SIGIR/WWW/TOIS, some with production signals). The applied camp is where the directly-shippable work lives.
- **Only 6 papers** are *directly* about cohort/worst-case/subgroup prediction quality in recommendation (see Tier 1). The rest are either generic CTR/cold-start, fairness-as-parity (a different objective than closing accuracy gaps), or pure ML calibration theory.
- The **single best Reels-fit paper** is Google's *Distributionally-robust Recommendations for Improving Worst-case User Experience* (WWW 2022) — it optimizes worst-cohort user experience, which is exactly the "NE/AUC gap on under-served cohorts" framing.
- **Calibration** is the cheapest win: Google's *Scale Calibration of Deep Ranking Models* (KDD 2022) is a production-grade method for fixing miscalibration in a ranking stack, and **multicalibration** (Tier 4) is the principled way to guarantee calibration *simultaneously across many overlapping cohorts*.
- **Gap**: the canonical productionized references (Meta DLRM calibration, Google's multitask MMoE, slice-based "Overton"/model-patching) are largely absent — added at the bottom.

---

## Tier 1 — Read first (directly on-topic: cohort/worst-case prediction quality + Reels-relevant)

| # | Paper | Why it matters for Reels | Signal |
|---|-------|--------------------------|--------|
| 1 | **Distributionally-robust Recommendations for Improving Worst-case User Experience** (Google, WWW 2022) | *The* paper for this brief. Group-DRO over user cohorts so the model doesn't sacrifice tail/under-served cohorts for average metrics — maps straight onto "close NE/AUC gaps across user-item cohorts" in ranking. | industry✓ DRO✓ 39 cit. https://doi.org/10.1145/3485447.3512255 |
| 2 | **Scale Calibration of Deep Ranking Models** (Google, KDD 2022) | Production method to calibrate a deep ranker's scores at scale — the cheapest cohort-gap fix to A/B in an existing Reels ranking stack. | industry✓ production✓ calibration✓ 20 cit. https://doi.org/10.1145/3534678.3539072 |
| 3 | **Temporally and Distributionally Robust Optimization for Cold-Start Recommendation** (AAAI 2024) | DRO over time *and* distribution for cold cohorts — directly addresses prediction quality where exposure is thin. | DRO✓ cold-start✓ 18 cit. https://doi.org/10.1609/aaai.v38i8.28721 |
| 4 | **Model-Agnostic Causal Embedding Learning for Counterfactually Group-Fair Recommendation** (Huawei, IEEE TKDE 2024) | Model-agnostic layer to equalize prediction quality across groups — pluggable into an existing embedding-based ranker. | industry✓ group-fair✓ 12 cit. https://doi.org/10.1109/tkde.2024.3424906 |
| 5 | **Relative Advantage Debiasing for Watch-Time Prediction in Short-Video Recommendation** (AAAI 2026) | Short-video watch-time debiasing — the most Reels-native paper; debiasing improves per-cohort prediction quality of the core ranking objective. | short-video✓ watch-time✓ new. https://doi.org/10.1609/aaai.v40i18.38555 |

## Tier 2 — Cold-start / under-exposed cohort prediction (applied, deployable)

| # | Paper | Angle | Signal |
|---|-------|-------|--------|
| 6 | **Enhancing CTR Prediction with Context-Aware Feature Representation Learning** (MSRA, SIGIR 2022) | Context-aware features lift CTR prediction quality — helps thin-data cohorts. | industry✓ 41 cit. https://doi.org/10.1145/3477495.3531970 |
| 7 | **Improving Item Cold-start Recommendation via Model-agnostic Conditional VAE** (Tencent, SIGIR 2022) | Model-agnostic generative warm-up for cold cohorts — pluggable. | industry✓ 53 cit. https://doi.org/10.1145/3477495.3531902 |
| 8 | **Alleviating Cold-start Problem in CTR Prediction with a Variational Embedding Learning Framework** (JD, WWW 2022) | Variational embeddings for cold IDs — closes the cold-cohort CTR gap at the embedding layer. | industry✓ 27 cit. https://doi.org/10.1145/3485447.3512048 |
| 9 | **RESUS: Warm-up Cold Users via Meta-learning Residual User Preferences in CTR Prediction** (Tencent, TOIS 2022) | Meta-learning residuals for cold *users* — the user-cohort low-exposure case in CTR. | industry✓ meta-learn✓ 8 cit. https://doi.org/10.1145/3564283 |
| 10 | **A Unified Framework for Multi-Domain CTR Prediction via LLMs** (Huawei, TOIS 2024) | Multi-domain CTR = per-cohort heads; relevant if cohorts ≈ domains/surfaces. | industry✓ multi-domain✓ 21 cit. https://doi.org/10.1145/3698878 |

## Tier 3 — Calibration across cohorts (the NE/calibration-gap lens)

| # | Paper | Angle | Signal |
|---|-------|-------|--------|
| 11 | **MBCT: Tree-Based Feature-Aware Binning for Individual Uncertainty Calibration** (Alibaba, WWW 2022) | Feature-aware (per-segment) calibration — calibrate by cohort, not globally. | industry✓ 9 cit. https://doi.org/10.1145/3485447.3512096 |
| 12 | **Rating Distribution Calibration for Selection Bias Mitigation** (WWW 2022) | Calibrates predicted distribution under selection bias — fixes cohort skew from exposure. | 29 cit. https://doi.org/10.1145/3485447.3512078 |
| 13 | **Uncertainty Calibration for Counterfactual Propensity Estimation in Recommendation** (IEEE TKDE 2025) | Calibrated propensities → unbiased per-cohort estimation. | new. https://doi.org/10.1109/tkde.2025.3552658 |

## Tier 4 — Foundations: multicalibration & robust optimization (the principled toolbox)

These are the ML-theory primitives behind "no cohort left behind." Not plug-and-play, but they define the right objective.

| Paper | Use | Link |
|-------|-----|------|
| **When is Multicalibration Post-Processing Necessary?** (NeurIPS 2024) | Practical guidance on *whether/when* multicalibration helps — read before investing. | https://doi.org/10.48550/arXiv.2406.06487 |
| **Bridging Multicalibration and OOD Generalization Beyond Covariate Shift** (NeurIPS 2024) | Links multicalibration to robustness — why it closes cohort gaps. | https://doi.org/10.48550/arXiv.2406.00661 |
| **Bridging Jensen Gap for Max-Min Group Fairness Optimization in Recommendation** (ICLR 2025) | Max-min (worst-group) objective specialized to recommendation. | https://doi.org/10.48550/arXiv.2502.09319 |
| **DORO: Distributional and Outlier Robust Optimization** (Bosch, ICML 2021) | Stabilizes group-DRO against outliers — important for noisy production data. | http://proceedings.mlr.press/v139/zhai21a/zhai21a.pdf |
| **Environment Inference for Invariant Learning** (Apple, ICML 2021) | Infers cohorts/environments when labels are unknown — useful when cohorts aren't predefined. | http://proceedings.mlr.press/v139/creager21a/creager21a.pdf |
| **Should Fairness be a Metric or a Model?** (Microsoft, TOIS 2024) | Framework for *measuring* bias/gaps across a pipeline — frames the audit/eval. | https://doi.org/10.1145/3641276 |

---

## Missing canonical references (add these — the productionized standards)
The mined list omits the industry papers most teams build on for cohort prediction quality:
- **Recommending What Video to Watch Next (YouTube MMoE)** — Zhao et al., Google, RecSys 2019. Multi-gate mixture-of-experts is how production systems give cohorts/objectives their own capacity; the standard lever for per-cohort quality.
- **Multicalibration** (origin) — Hébert-Johnson et al., ICML 2018. The foundational definition; Tier 4 builds on it.
- **Distributionally Robust Optimization / Group-DRO** — Sagawa et al., ICLR 2020. The canonical worst-group training reference behind #1, #3.
- **Model Patching / Slice-based learning ("Overton", Snorkel)** — Ré et al., for discovering and fixing underperforming slices in production.
- **Meta DLRM calibration & calibration-in-ranking** engineering write-ups (KDD applied / eng blogs) — closest to a Reels-stack baseline.

## Suggested next step
For Reels, the fastest path is **calibration first, DRO second**:
1. **Prototype Scale Calibration (#2) + per-cohort calibration (#11)** in the re-ranking/scoring stage — cheapest to A/B, directly measurable as per-cohort calibration error (ECE) and NE.
2. **Layer worst-case DRO (#1, #3)** into training to lift NE/AUC on the worst user-item cohorts without tanking average metrics.
3. **Adopt multicalibration (Tier 4)** as the eval contract — guarantee calibration across many overlapping Reels cohorts (creator tier, topic, new-user, country) simultaneously, and read #11-Tier4 ("when is it necessary") before investing.

Full corpus with all columns is at `output_cohort_prediction_quality/papers.tsv` (266 rows; `companies` column flags the 46 industry papers).
