# Spec: ODA Simulation Data — Generation Run v2

**Source of truth for findings:** `DATA_VALIDATION_NOTES.md` (independent profiling of the v1 dataset — 952K orders / 4.2M lines / 6,824 customers, Jul 2022–Jun 2024, rated **6.5/10** for realism)
**This document turns that audit's §7 fix list into a scoped, phased build plan for the next generation run.**

---

## Problem Statement

The v1 synthetic dataset is *quantitatively* solid — all six headline KPIs (churn, DSO, payment capture, return rate, fulfilment rate, stockout rate) land inside real Egyptian B2B FMCG benchmark bands, and segment economics behave causally rather than as random labels. But it fails *qualitative* inspection immediately: the first chart anyone builds shows an impossible 10× volume cliff, the first table anyone opens (`customers`) shows American names ("Anita Rubio DVM") in a dataset framed as Egyptian, and the first cross-check anyone runs (does `promotion_roi` reconcile with `orders`?) contradicts itself outright. Anyone using this data for analytics demos, ML training, or stakeholder review — the stated use cases — risks the entire dataset being dismissed as "obviously fake" within 30 minutes, which undermines trust in the whole case-study deliverable, not just the flawed tables.

**Net effect today:** "aggregate realism" ≈ 8/10, "inspection realism" ≈ 4-5/10, blending to 6.5/10 overall.

---

## Goals

1. **Eliminate the three "first 5 minutes" tells** — bootstrap→live cliff, American customer identities, promotions self-contradiction — since these are what determines whether a skeptical reader trusts anything else in the dataset.
2. **Move the realism rating from 6.5/10 to ≥ 8/10**, measured by re-running the same independent profiling pass that produced `DATA_VALIDATION_NOTES.md` against the v2 output.
3. **Drive "impossible value" rows to zero** (currently ~250: negative fraud scores, negative inventory, sub-zero payment terms, etc.) so no downstream consumer has to defensively clean data before trusting an aggregate.
4. **Close the two completeness gaps that block specific analyses** — `segment` missing from lifecycle events (blocks segment-cohort churn analysis) and `demand_class` jitter (makes ABC reclassification look like noise instead of signal).
5. **Don't regress what already works** — the 6/6 KPI bands, causally-coherent segment economics, and the well-researched Egyptian FMCG brand catalog are genuine wins; v2 should preserve them while fixing the rest.

---

## Non-Goals

1. **Rewriting the simulation engine architecture.** The SimPy/DuckDB/Polars event-sourcing core works (62 files, 27 passing tests). This is a tuning-and-content pass on top of a working foundation, not a rebuild.
2. **Adding new tables, schemas, or analytical dimensions.** The 13 output tables are sufficient in shape; the work is making their *contents* internally consistent and realistic, not expanding what's measured.
3. **Architectural change toward live/streaming generation.** Stays a batch run that exports to Parquet.
4. **Chasing 10/10 "indistinguishable from real data."** That's not the bar (and may not be achievable for synthetic data under sufficiently deep inspection). The bar is "survives a skeptical analyst's first 30 minutes" — which is the specific gap between 6.5 and 8+.
5. **Re-auditing dimensions the v1 profiling already cleared.** The brand/product catalog, credit-ledger economics, category revenue mix, and date-coverage were rated as genuinely realistic — no need to re-litigate them; just don't break them while fixing everything else.

---

## User Stories

The "users" here are the people who will open and rely on the generated dataset:

- As an **analyst evaluating this case-study dataset**, I want every monthly time-series chart to show organic month-over-month growth (not a 10× overnight jump), so that I don't flag the data as fabricated on the first chart I build.
- As an **analyst opening the `customers` table for the first time**, I want to see Egyptian names and `01x-xxxx-xxxx` phone numbers, so the dataset matches the market it claims to represent.
- As an **analyst cross-checking the promotions tables**, I want `promotion_roi` to reconcile with `orders.promotion_id` (or for only one of them to exist), so the two tables tell one consistent story instead of contradicting each other.
- As a **data scientist building an ML feature set**, I want numeric fields (`fraud_score`, `estimated_on_hand`, `terms_days`, transaction amounts) to fall within physically valid ranges, so I don't have to write defensive clamping code before trusting any aggregate built on them.
- As a **business analyst segmenting customers by cohort**, I want `segment` populated on every `customer_history` lifecycle row — not just `CustomerCreated` — so I can compute "churn rate by segment at time of churn" directly from one table, without joining back and losing the historical segment value.
- As a **stakeholder reviewing dashboards built on this data**, I want categorical splits (returns by category, stockout-resolution mix, fraud score by outcome) to show the natural variation real operations data has, so the visuals read as "a real business," not "a uniform random draw with extra steps."

---

## Requirements

### P0 — Must-have (the three "first 5 minutes" tells; blocks the 6.5→8+ goal)

**1. Smooth the bootstrap → live transition**
Today, Dec 2022 (bootstrap) → Jan 2023 (live) shows orders +948%, revenue +1,260%, fulfilment rate jumping from a flawless 100% to 92.5%, and order timestamps switching overnight from all-`00:00:00` to an 08:00–17:59 spread. Fix by either making the bootstrap generator share the live engine's status/timing/channel logic (compressed into the lookback window), or ramping live volume up gradually over its first 1–2 months.
*Acceptance:* month-over-month deltas in orders/revenue/fulfilment-rate/timestamp-distribution at the Dec'22→Jan'23 seam are continuous — no single-month change exceeds what's plausible for organic B2B growth (rule of thumb: <50%, tunable during implementation).

**2. Replace the broken `Faker(["ar_EG","en_US"])` locale fallback**
`ar_EG` lacks full `person`/`phone_number` providers, so 100% of names/phones silently render as American ("Timothy Mccarthy", `+1-940-884-7710x0275`). Mirror the approach that *already worked* for the brand catalog (`FMCG_HORECA_Entity_Library_EGP.md` — hand-curated, not Faker-generated): build or source a curated Egyptian Arabic name list and an `01[0-2,5]-XXXX-XXXX` mobile-number formatter.
*Acceptance:* 0% of sampled customer names/phones show `en_US` artifacts (no Western surnames, no professional-credential suffixes like "DVM", no `+1-`/`(xxx)xxx-xxxx` phone patterns); 100% match Egyptian naming and `01x-xxxx-xxxx` phone conventions.

**3. Reconcile (or remove) the promotions subsystem**
`orders.promotion_id` is NULL on all 952,674 rows and every `order_lines` payload shows `promotion_applied: false` — yet `promotion_roi.parquet` claims 9 campaigns, ~494K redemptions, and suspiciously-round ROI figures (`9.9999`, `2.0000`) that look back-computed from fixed discount-rate assumptions rather than emergent from real redemption events. Either (a) wire a real promotion-redemption event into `customer_order_process.py` so `promotion_id`/`discount_amount` populate on a realistic subset of orders and `promotion_roi` derives from those events, or (b) delete `promotion_roi.parquet` until that wiring exists.
*Acceptance:* either `COUNT(orders WHERE promotion_id IS NOT NULL)` is consistent with `promotion_roi`'s redemption count (reconciled path), or `promotion_roi.parquet` does not exist in the output (removal path) — no contradiction state under any circumstance.

### P1 — Should-have (meaningfully improves trust; not launch-blocking)

**4. Clamp noise-injected numeric fields to valid domains**
~250 rows currently violate physical/logical bounds: `fraud_score` as low as -0.1336 (should be [0,1]), `attempt_number` down to -2 (should be ≥1), `terms_days` at -30 (should be ≥0), `estimated_on_hand` down to -830 units on 46 SKUs (should be ≥0), and ~24-26 each of negative `total_value`/`amount` on records that aren't credit notes.
*Acceptance:* zero rows violate documented domain bounds for these fields; legitimate negative values (credit notes, refunds) remain distinguishable as their own record type rather than negative primary transactions.

**5. Condition fixed-weight random draws on relevant features**
Several categorical splits currently look like a single global `random.choices(weights=[...])` draw rather than SKU/segment/category-driven behavior: stockout resolution lands on *exactly* 50.0%/30.0%/20.0% (cancel/substitute/backorder), return rates band within 0.13pp across all 7 categories regardless of perishability, and `fraud_score` averages a flat ~0.018-0.020 *regardless of channel or final order status* (so it can't predict the fraud-adjacent outcomes it's supposedly scoring). Replace fixed global weights with distributions conditioned on category-perishability (returns), SKU class (stockouts), and order/customer risk features (fraud score) — even ±20% jitter around a category-specific base rate would remove most of these tells.
*Acceptance:* stockout-resolution mix and category return rates show feature-driven variation (no exact round numbers, spread > current <0.2pp bands); `OrderCancelled` orders show measurably higher average `fraud_score` than `OrderDelivered` orders.

**6. Carry `segment` through every `customer_history` lifecycle event**
Today only the 6,824 `CustomerCreated` rows populate `segment`; all 8,655 `CustomerBecameInactive/Dormant/Churned/Reactivated` rows have `segment=NULL` (44% coverage overall) — making "churn rate by segment at time of churn" impossible without a join that only returns the customer's *current* segment.
*Acceptance:* 100% of `customer_history` rows have non-null `segment`, reflecting the customer's segment *at the time of that event* (not their current segment).

**7. Fix the `qcut`/`allow_duplicates` RFM bucket bug**
`r_score` skips bucket "4" entirely — only `{1,2,3,5}` appear — because Polars' `qcut` without `allow_duplicates` handling collapses two quantile edges together (a documented, known issue in this codebase).
*Acceptance:* `r_score` distribution covers all 5 buckets `{1,2,3,4,5}`.

### P2 — Future considerations (lower payoff or already addressed; design for, don't block on)

**8. ~~De-duplicate the terminal `orders` projection by `order_id`~~ — already resolved.**
This was originally fix #8 in the v1 audit (4,866 `order_id`s appeared 2-3× due to "duplicate event" noise propagating downstream, overcounting GMV by ~0.5%). **It's now moot**: this session removed the "duplicate events" noise type at its source (along with "missing events" noise, which was separately producing orphan orders that violated the engine's own `C1-no-orphan-orders` check). With that noise type gone, duplicate `order_id`s can no longer be generated — verified on a fresh 30-day run (0 duplicates, 0 orphans, vs. 4,866 and ~1% respectively before). No generation-time fix needed; the existing `kpi_validator.py` checks now simply pass instead of needing a workaround. Worth adding an explicit "no duplicate order_ids" regression check to the validator so this stays caught if anything regresses it.

**9. Split `rep_id` into `assigned_rep_id` vs. `order_assisted_by_rep_id`**
Every live order currently carries the customer's *assigned* rep regardless of actual order channel (organic/app/rep), conflating "account ownership" with "who drove this order." Document the distinction even if the schema split waits for a future round — `rep_performance.gmv` (territory GMV) shouldn't be read as "GMV this rep personally drove" until this is fixed.

**10. Make `demand_class` move in contiguous monthly blocks**
63% of SKUs (313/500) currently flicker between two demand classes line-by-line in the order history, which reads as noise rather than the "rolling ABC reclassification" signal it's presumably meant to represent. Low priority — fix once the higher-payoff items land.

---

## Success Metrics

**Leading indicators** (read directly off the v2 output via the same DuckDB-against-Parquet profiling methodology used for `DATA_VALIDATION_NOTES.md`):

| Metric | v1 (baseline) | v2 target |
|---|---|---|
| Bootstrap→live month-over-month order/revenue jump | +948% / +1,260% | < 50% / < 50% |
| Sampled customer names/phones reading as Egyptian | ~0% | 100% |
| Promotions self-contradiction | 494K redemptions vs. 0 linked orders | reconciled, or table removed |
| "Impossible value" rows (fraud_score, inventory, terms_days, amounts) | ~250 | 0 |
| `customer_history` rows with populated `segment` | 6,824 / 15,479 (44%) | 15,479 / 15,479 (100%) |
| Duplicate `order_id`s in terminal `orders` table | 4,866 | 0 *(already achieved this session)* |
| `r_score` buckets represented | 4 of 5 (`{1,2,3,5}`) | 5 of 5 |

**Lagging indicator (the actual target this whole effort serves):**
Re-run the same independent profiling pass that produced `DATA_VALIDATION_NOTES.md` against the v2 dataset and produce a v2 ratings write-up. **Target: realism rating ≥ 8/10**, with the "inspection realism" sub-score (currently ~4-5/10) closing most of the gap to the "aggregate realism" sub-score (currently ~8/10) — i.e., the two scores should converge rather than one masking the other.

---

## Open Questions

- **[Founder — blocking for scoping fix #3]** Is a populated, fully-reconciled `promotion_roi` table a hard requirement for the case study's analytical narrative (e.g., does a downstream dashboard or storyline depend on showing promotions ROI)? If not, *deleting* the table is the Low-effort path; if so, *wiring real redemption events* is a Medium-effort path. This single answer changes the cost of fix #3 substantially.
- **[Engineering — non-blocking, resolve during implementation of #1]** What "organic ramp" curve should the bootstrap→live transition follow — a fixed linear ramp over N months, or a curve fit to the live regime's actual early growth rate? Either works; pick during implementation.
- **[Engineering — non-blocking, resolve during implementation of #2]** Is there a ready-made Egyptian Arabic name/phone reference list to adapt (the way `FMCG_HORECA_Entity_Library_EGP.md` already exists for brands), or does one need to be hand-curated from scratch? Affects the actual effort behind the "Low" estimate.
- **[Founder — non-blocking, but worth deciding before kickoff]** Once v2's code changes land, should the full 365-day regeneration run (~4M events, multi-minute operation) happen automatically, or only on your explicit go-ahead? (Recommendation: explicit go-ahead — it's long-running and you'll want to choose the moment.)

---

## Timeline Considerations

- **No hard deadline.** This is a quality-improvement pass on an already-functional, already-usable dataset — not a blocker for other workstreams. Sequence it whenever bandwidth allows.
- **Dependency order:** Fixes #1 (bootstrap smoothing) and #2 (Egyptian identities) touch the generators/bootstrap engine and `config/seeds.py` — land both *before* running a full regeneration, since every other fix's "did it actually work" check depends on having a clean run to inspect. Fix #3 (promotions) is independent and can proceed in parallel.
- **Recommended phasing:** Ship the three P0 fixes as "v2.0," then re-run the validation profiling *before* committing to P1. If the three first-5-minutes tells are gone, the rating may already clear 8/10 — making P1/P2 optional polish rather than required follow-through. This avoids over-investing in fixes #4-7 if #1-3 alone close the gap.
- **Cost to budget for:** each full validation cycle requires a complete 365-day regeneration (~4M events). Plan for at least two cycles — one after P0 lands, and a second only if the re-validation shows the rating still short of 8/10.

---
*Built from `DATA_VALIDATION_NOTES.md` §7's prioritized fix list (8 items) plus the orphan/duplicate findings in §2 — cross-referenced against the noise-injector change shipped this session, which already resolved one of the eight items at the source.*
