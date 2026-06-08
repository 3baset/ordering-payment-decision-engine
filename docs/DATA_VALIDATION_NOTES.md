# ODA Simulation — Data Validation & Realism Notes
**Scope:** Independent profiling of all 13 output tables (952K orders / 4.2M order lines / 6,824 customers / 18 months live + 6 months bootstrap, Jul 2022–Jun 2024)
**Companion to:** `simulation_engine/output/DATA_QUALITY_REPORT.md` (the engine's own self-assessment, scored 8.5/10 for *ML usability*). This document scores a different question: **if an analyst opened this data cold, would it look real?** That lens surfaces issues the usability-focused report doesn't emphasize.

---

## TL;DR — Top 3 things to fix before the next generation run

1. **The "Jan 2023 cliff"** — order volume jumps ~10× and revenue ~13× in a single month because bootstrap-period and live-simulation generators run on different rules. This is the single most visible "this is fake" tell — it shows up in literally every time-series chart.
2. **Customer identities are American, not Egyptian** — `Faker(["ar_EG","en_US"])` was configured but 100% of names/phones rendered in `en_US` (e.g., "Anita Rubio DVM", phone `+1-940-884-7710x0275`). The product/brand catalog nailed the Egyptian flavor; the people didn't get the same care.
3. **The promotions subsystem contradicts itself** — `promotion_roi.parquet` claims ~494K redemptions and EGP 38.9B of associated GMV, while **zero** of the 952,674 orders carry a `promotion_id` or `promotion_applied=true`. Two tables, two incompatible stories.

---

## 1. Structural Issues (highest impact on realism)

### 1.1 The bootstrap → live discontinuity ("Jan 2023 cliff")
The simulation generates 6 months of historical "bootstrap" data (Jul–Dec 2022, `order_id LIKE 'ORD-BOOT-%'`) before the live event-driven simulation takes over (Jan 2023 onward). The two regimes don't share generation logic, and the seam is glaring:

| Signal | Dec 2022 (bootstrap) | Jan 2023 (live) | Jump |
|---|---|---|---|
| Orders/month | 2,541 | 26,637 | **+948%** |
| Revenue/month | EGP 97.4M | EGP 1.32B | **+1,260%** |
| Active customers | 1,442 | 1,689 | +17% |
| Fulfilment rate | **100.0%** (0 returns, 0 cancellations — every bootstrap order is born "Delivered") | 92.5% | cliff |
| Order timestamps | 100% stamped `00:00:00` (date-only) | spread 08:00–17:59 | cliff |
| `CustomerBecameDormant/Inactive/Churned` | near-zero | 788 / 1,318 / 474 **in one month** | cascade |

No real wholesale business 10×s its volume overnight, runs at a flawless 100% fulfilment rate for 6 months, then suddenly develops returns and cancellations on January 1st. **This is the first thing any analyst doing a `GROUP BY month` will notice.**

**Fix:** Either (a) make the bootstrap generator emit orders through the *same* status/timing/channel logic as the live engine (just compressed into a lookback window), or (b) ramp the live engine's volume up gradually over its first 1-2 months so growth from the bootstrap base looks organic rather than an instant step function.

### 1.2 Customer identities don't match the market
`config/seeds.py` initializes `Faker(["ar_EG", "en_US"])`, clearly intending a mix — but every sampled `name` and `phone` rendered is pure American:

- Names: *"Anita Rubio DVM", "Timothy Mccarthy", "Cassandra Davis", "Jeffrey Henderson"* (note "DVM" — a U.S. veterinary-medicine credential — on an Egyptian wholesale buyer)
- Phones: `+1-940-884-7710x0275`, `(834)910-3469`, `001-996-607-5789x849`, `580.247.6778`

`ar_EG` doesn't have full `person`/`phone_number` providers in the `faker` library, so the `Faker([...])` proxy silently falls back to `en_US` for every call. This is the **single most visually obvious "synthetic" tell** in the whole dataset — open the `customers` table and the illusion breaks immediately.

By contrast, the **product/brand catalog is genuinely well done** — SKUs reference real Egyptian/regional FMCG brands (Afia, Al-Arabi, Fine, Cleopatra, Baraka, El-Wadi, Americana) pulled from `FMCG_HORECA_Entity_Library_EGP.md`. The fix that worked for products needs to be applied to people.

**Fix:** Build (or source) an Egyptian Arabic name list and an `01[0-2,5]-XXXX-XXXX` Egyptian mobile formatter — the same hand-curated approach already used for the brand library — rather than relying on `Faker`'s locale fallback.

### 1.3 Promotions: two tables, two contradictory stories
- `orders.promotion_id` is **NULL on all 952,674 rows**; every `order_lines` payload shows `promotion_applied: false, discount_amount: 0.0`.
- Yet `promotion_roi.parquet` reports **9 campaigns, ~493,834 redemptions, EGP 38.9B of associated GMV, EGP 1.49B of discounts** — as if half a million orders involved a promotion.
- The ROI figures are also suspiciously round (`9.9999`, `10.0010`, `2.0000`, `12.5001`, `8.3339`) — exactly `total_gmv / total_discount`, which only lands on clean numbers like `2.0` (BOGO → 50% off → ROI=2) or `~10` (10% discount campaigns) if the table was **back-computed from fixed discount-rate assumptions** rather than emerging from simulated redemption events.

**Fix:** Either wire the promotion-redemption event into `customer_order_process.py` (so `promotion_id`/`discount_amount` actually populate on a realistic subset of orders, and `promotion_roi` is *derived* from those events), or remove `promotion_roi` until that wiring exists — a populated-but-disconnected table is worse than an empty one, because it actively misleads.

---

## 2. Logical / Consistency Bugs (small in volume, easy to fix)

These all look like **unbounded noise injection** — corrupting values without clamping them to physically/logically valid ranges:

| Field | Issue | Count | Why it's impossible |
|---|---|---|---|
| `orders.fraud_score` | Negative scores, down to **-0.1336** | 20 | A probability/score should be bounded [0,1] |
| `payments.attempt_number` | Values ≤ 0, down to **-2** | 44 | Can't have a "0th" or "-2nd" payment attempt |
| `invoices.terms_days` | **-30 days** payment terms | 22 | Can't be due *before* the invoice is issued |
| `inventory_snapshot.estimated_on_hand` | Negative stock, down to **-830 units** | 46 SKUs (9.2%) | Physical inventory can't go below zero |
| `orders.total_value` / `invoices.amount` / `payments.amount` | Negative values on records that aren't credit notes | ~24-26 each | Returns/credits should be separate records, not negative primary transactions |
| `payments` paid before its `invoice` was issued | Payment timestamp precedes invoice timestamp | 93 | Violates causal ordering |

Plus two pre-existing structural quirks that compound at scale:
- **`r_score` (RFM) skips bucket "4" entirely** — only `{1,2,3,5}` appear. This is the documented Polars `qcut`-without-`allow_duplicates` collapsing two quantile edges into one bin. Anyone building an RFM segmentation will find an unexplained hole in the recency quintile.
- **4,866 `order_id`s appear 2-3× in the terminal `orders` projection** with identical status/value/timestamp (different `event_id`). This is the documented "duplicate event" noise faithfully propagating into a table that downstream consumers will assume is one-row-per-order — naive `SUM(total_value)` overcounts ~0.5% of GMV.

**Fix:** Clamp noise-injected numeric fields to their valid domain post-corruption (e.g., `max(0, min(1, corrupted_fraud_score))`), and de-duplicate by `order_id` (keep latest `event_id`) in the terminal-state projector, not just in the raw event store.

---

## 3. "Too Clean" Statistical Patterns (the subtle tells)

These won't break a query, but they're exactly the kind of thing that makes synthetic data feel synthetic under a real analyst's eye — every one of them lands suspiciously close to a round number or a flat line:

| Observation | What's actually there | What real data looks like |
|---|---|---|
| Stockout resolution mix | **exactly** 50.0% / 30.0% / 20.0% (cancel/substitute/backorder) | Real ops data never lands on round percentages — this is a fixed `weights=[.5,.3,.2]` draw, not SKU/segment-driven behavior |
| Return rate by category | 4.62%–4.75% across all 7 categories (band of 0.13pp) | Perishables (FOD/BEV/dairy) should return/spoil at meaningfully higher rates than durables (paper, cleaning) |
| `fraud_score` vs. order outcome | Flat ~0.018-0.020 average **regardless of channel or final status** — `OrderCancelled` orders don't score higher than `OrderDelivered` ones | A fraud score that doesn't predict fraud-adjacent outcomes is cosmetic, not a usable ML feature (and "fraud risk scoring" is a stated use case for this dataset) |
| SKU revenue concentration (Pareto) | Top 10% of SKUs → 12.6% of revenue; top 50% → 58.6% | Real assortments show 70/30 or 80/20 concentration with clear hero SKUs and long-tail laggards. This curve is nearly a straight diagonal — every SKU sells in the same order of magnitude (best-seller/worst-seller revenue ratio is only ~4×) |
| Order hour-of-day | Hard box: ~93-94K orders in *every* hour 08:00-17:00, then a cliff to near-zero | Real intraday curves taper at the edges (a lunch dip, a closing-time ramp-down) rather than switching on/off like a light switch |
| Order day-of-week | 134,922-137,825 (< 2% spread across all 7 days) | Egypt's Fri/Sat weekend should visibly depress B2B ordering; pre-weekend stocking should create a Wed/Thu peak |
| AOV by geographic area | EGP 82,355-89,163 (an 8% band) despite area customer counts ranging from 350 to 2,305 (6.6× spread) | Plausible if segment mix alone drives AOV, but real regional markets usually show *some* purchasing-power variance too |
| All payment failures | 100% tagged `reason='insufficient_funds'`, and **all** have `payment_method=NULL` | Real failure logs show a mix (card declined, processing timeout, bank rejection, disputes) and retain the attempted method |

**Fix:** Replace fixed-weight `random.choices(...)` draws with distributions conditioned on the relevant dimension (SKU class for stockout resolution, category-perishability for returns, customer/order risk features for fraud_score, hour to has a smooth daily curve via e.g. a beta/triangular shape, day-of-week multipliers reflecting the Egyptian work week, etc.). Even ±20% jitter around a category-specific base rate would eliminate most of these tells.

---

## 4. Data Completeness Gaps

- **`customer_history` lifecycle events never carry `segment`**: all 8,655 `CustomerBecameInactive/Dormant/Churned/Reactivated` rows have `segment=NULL`; only the 6,824 `CustomerCreated` rows populate it. You can't compute "churn rate by segment" without joining back to `customers` (and even then you get the customer's *current* segment, not their segment *at time of churn*).
- **`demand_class` isn't a stable SKU attribute**: 313 of 500 SKUs (63%) appear under two different demand classes in the order-line history (e.g., `BEV-CSD-KLCH-1L6` shows 8,050 lines as class "A" and 72 as class "B"). If this is meant to reflect rolling ABC reclassification, it should move in *contiguous monthly blocks*, not jitter line-by-line — as-is, it looks like noise rather than a meaningful "this SKU's tier shifted over time" signal.
- **`rep_id` is populated identically across "organic"/"app"/"rep" channels** — every live order carries the customer's *assigned* rep regardless of how the order was actually placed, which conflates "account ownership" with "order channel." Worth documenting explicitly (or splitting into two fields: `assigned_rep_id` vs. `order_assisted_by_rep_id`) so `rep_performance.gmv` (territory GMV) isn't confused with "GMV this rep personally drove."

---

## 5. What's Genuinely Realistic — give credit where it's due

Not everything is a tell. Several things are **better than a quick synthetic build usually achieves**:

- **Headline KPIs land inside real Egyptian B2B FMCG benchmark bands**: churn 21.4% (target 18-28%), DSO 38.7 days (target 25-45), payment capture 82.1% (target 75-90%), return rate 4.7% (target 3-7%), fulfilment rate 91.9% (target 85-95%), stockout 9.2% (target 6-12%). Six-for-six is a real achievement — most synthetic generators miss at least one of these badly.
- **Segment economics are believable and causally coherent, not just labels**: premium customers carry **7.4× the AOV** of low-volume customers (EGP 202,858 vs. 27,299) *and* route 21.2% of orders through reps vs. 5.4% for low-volume — the segment definition actually drives downstream behavior, which is exactly what you want from a simulation (vs. a label slapped on at random).
- **The product/brand catalog is genuinely well-researched** — real Egyptian and regional FMCG brands (Afia, Al-Arabi, Fine, Cleopatra/Henkel Egypt, Baraka, El-Wadi, Americana, Heinz FS) at category-appropriate price points, not generic "Brand A/B/C" placeholders.
- **No date gaps**: all 726 days of the simulation window are represented — a basic but easy-to-miss thing to get right at this volume.
- **Category revenue mix tracks configured category weights sensibly** (FOD 25.9% realized vs. 22% configured weight, BEV 23.4% vs. 25%, CLN 20.5% vs. 18% — all within a reasonable band of their target weights, adjusted for category price points).
- **Credit-ledger economics hang together**: debit:credit ratio ~1.16:1, write-offs total ~EGP 374M against ~EGP 74B GMV (≈0.5% of revenue) — squarely in real-world bad-debt territory.

---

## 6. Realism Rating

# 6.5 / 10

**Why not lower:** the things that matter most for *quantitative* analysis — order volumes, AOV bands, churn, DSO, payment capture, stockout rates, return rates, segment-driven economics — all land within real-world ranges and hang together internally. A model trained on monthly aggregates would likely produce sane output.

**Why not higher:** the things that matter most for *qualitative* trust — does this look like something a real business produced? — fail at multiple levels simultaneously and at the first level of inspection:
- The very first chart anyone builds (revenue or orders by month) shows an impossible 10× cliff.
- The very first table anyone opens (`customers`) shows American names and phone numbers in a dataset framed as Egyptian.
- The very first cross-check anyone runs (does `promotion_roi` reconcile with `orders.promotion_id`?) fails completely.
- Underneath that, nearly every categorical split that *should* show variation (returns by category, stockout resolution mix, fraud score by outcome, AOV by region) is suspiciously flat or suspiciously round, while the things that show variation (segment AOV, channel mix by segment) do so convincingly — so the simulation clearly *can* produce realistic heterogeneity, it just wasn't applied evenly across all dimensions.

**One-line summary:** *this dataset would pass a "does the dashboard look plausible" skim, and would mostly survive an aggregate-statistics audit — but it would not survive the first 30 minutes of a skeptical analyst opening the raw tables and cross-checking two of them against each other.* That gap between "aggregate realism" (strong, ~8/10) and "inspection realism" (weak, ~4-5/10) is what nets out to 6.5.

---

## 7. Priority fix list for the next generation run

| # | Fix | Effort | Realism payoff |
|---|---|---|---|
| 1 | Smooth the bootstrap→live transition (shared status logic + gradual volume ramp) | Medium | **Highest** — fixes the #1 visual tell across every time-series chart |
| 2 | Replace `Faker(["ar_EG","en_US"])` with a curated Egyptian name list + `01x-xxxx-xxxx` phone formatter (mirror the approach already used for the brand library) | Low | **High** — fixes the #1 tell on first table-open |
| 3 | Either wire real promotion-redemption events into the order process, or delete `promotion_roi.parquet` until it's derivable from `orders` | Medium | High — removes a direct self-contradiction between two tables |
| 4 | Clamp noise-injected numeric fields to valid domains (fraud_score∈[0,1], attempt_number≥1, terms_days≥0, on_hand≥0, amounts≥0 except explicit credit notes) | Low | Medium — removes ~250 "impossible value" rows |
| 5 | Condition stockout-resolution, return-rate, and fraud-score draws on category/SKU/segment features instead of fixed global weights | Medium | Medium — removes the "suspiciously round / suspiciously flat" tell across 4-5 fields |
| 6 | Carry `segment` through all `customer_history` lifecycle events (not just `CustomerCreated`) | Low | Low-medium — unlocks segment-cohort churn analysis directly from one table |
| 7 | Fix the `qcut`/`allow_duplicates` quantile bug so `r_score` covers all 5 buckets | Low | Low — closes an obvious "hole" in RFM scores |
| 8 | De-duplicate the terminal `orders` projection by `order_id` (keep latest event) | Low | Low — prevents ~0.5% GMV overcount in naive aggregations |

---
*Generated by independent profiling via DuckDB against `simulation_engine/output/tables/*.parquet` — see `wholesale_dashboard.html`, `financial_fulfilment_assortment_dashboard.html` for the visual layer built on these same findings.*
