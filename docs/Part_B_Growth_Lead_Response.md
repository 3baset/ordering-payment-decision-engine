# Part B – Business Acumen: Prioritisation

## 1. The Call

**Hypothesis:** I would fix **Availability** first because customers cannot buy what is not available, and availability failures destroy conversion, trust, retention, and operational efficiency simultaneously.

### Why Availability First?

Availability sits at the intersection of demand generation and fulfillment execution.

A business can survive temporarily with:
- Imperfect pricing
- Limited assortment
- Less-than-perfect delivery speed

But if customers repeatedly encounter out-of-stock products, the purchase journey ends immediately.

Availability is also the lever most likely to unlock the value of the other three:

| Lever | Impact from Improving Availability |
|---------|---------|
| Assortment | Existing assortment becomes more productive before expanding catalog breadth. |
| Affordability | Promotional spend becomes more efficient because advertised products can actually be purchased. |
| DiFOT | Better inventory positioning reduces last-minute substitutions and delivery exceptions. |

### What Improves?

- Search-to-cart conversion
- Cart completion rate
- Repeat purchase rate
- Basket size
- Supplier planning accuracy
- Demand forecasting quality

### What May Regress?

- Working capital requirements may increase.
- Inventory holding costs may increase.
- Obsolescence risk may increase.
- Assortment expansion may slow while inventory accuracy is stabilized.

### What Becomes Unblocked?

Once availability is reliable, the business can accurately evaluate:
- Whether pricing is competitive.
- Which assortment gaps actually matter.
- Which delivery failures are logistics problems versus stock problems.

---

## Availability vs. Assortment, Affordability, and DiFOT

### Assortment

**Pros**
- Attracts more customers.
- Increases basket completion.
- Creates differentiation.

**Cons**
- More SKUs increase forecasting complexity.
- Long-tail SKUs often create inventory fragmentation.
- Broader assortment frequently reduces availability.

### Availability

**Pros**
- Directly impacts conversion.
- Reduces substitution and abandonment.
- Improves customer trust.
- Benefits both new and repeat customers.

**Cons**
- Requires inventory investment.
- Forecasting mistakes become expensive.
- Operationally difficult across multiple fulfillment nodes.

### Affordability

What it likely means:

Not simply lowest price.

It includes:
- Relative price competitiveness.
- Perceived value.
- Promotions.
- Delivery fees.
- Substitution economics.
- Total basket affordability.

**Pros**
- Immediate demand stimulation.
- Strong acquisition lever.
- Easy for customers to understand.

**Cons**
- Can destroy margin.
- Competitors can easily copy.
- May attract low-loyalty customers.

### DiFOT (Delivery in Full, On Time)

**Pros**
- Major retention driver.
- Strong NPS impact.
- Improves trust and reliability.

**Cons**
- Often expensive to improve.
- Logistics investments may not increase demand directly.
- Benefits are limited if products are unavailable in the first place.

---

## 2. Data Required

### Demand-Side
- Search → Cart conversion
- Cart → Checkout conversion
- Out-of-stock product views
- Substitution acceptance rate
- New vs. returning customer behavior

### Supply-Side
- In-stock rate by SKU and node
- Inventory accuracy
- Supplier fill rate
- Supplier lead time
- Picker accuracy
- DiFOT by route

### Competitive / Market
- Price index vs. top three competitors
- Assortment gaps weighted by demand
- Share of search on unavailable products

### Unit Economics
- Contribution margin per order
- Cost-to-serve by fulfillment path
- Inventory carrying cost
- Discount depth vs. incremental volume

### Customer Behavior
- Repeat purchase rate
- NPS by failure mode
- Churn after first stockout event
- Churn after first DiFOT failure

---

## 3. Sequencing & Trade-Offs

### Example Trade-Off

Improving availability by increasing safety stock:

**Benefit**
- Fewer stockouts.
- Higher conversion.
- Better retention.

**Cost**
- Higher inventory carrying cost.
- More working capital.
- Greater risk of dead stock.

### 30-Day Validation

### Leading Indicator

Primary metric:
- Out-of-stock rate on top-decile demand SKUs

Supporting metrics:
- Search-to-cart conversion
- Basket completion rate
- Substitution rate

### Kill Criterion

I would consider the decision wrong if after 30 days:

- Top-SKU availability improves materially (e.g. >10 percentage points),
- But search-to-cart conversion improves less than 2%,
- And repeat purchase behavior remains unchanged.

That would indicate availability was not the primary constraint and that affordability, assortment, or DiFOT is the larger growth bottleneck.

---

## Priority Matrix

| Impact | Effort | Priority |
|----------|----------|----------|
| Availability | Medium-High | P1 |
| DiFOT | High | P2 |
| Affordability | Medium | P3 |
| Assortment Expansion | High | P4 |

Rationale:

1. Fix Availability first.
2. Improve DiFOT once inventory reliability exists.
3. Optimize Affordability after supply constraints are understood.
4. Expand Assortment last, once operational foundations are stable.

---

## Appendix: ODA — Operational Foundation Enabling the Growth Agenda

The Ordering Decisioning Agent addresses a constraint that blocks all four growth levers: manual order approval delays and inconsistent credit decisions that slow GMV, damage rep morale, and increase credit loss exposure.

### What ODA Produces

| Decision Tier | Threshold | Share of Orders | Action |
|---|---|---|---|
| AUTO_APPROVE | composite ≥ 0.70 | ~60% | Instant fulfillment, zero rep time |
| MANUAL_REVIEW | 0.40 – 0.69 | ~28% | Escalated to rep with pre-scored context |
| DECLINE | composite < 0.40 | ~12% | Rejected with reason code, rep notified |

Composite score = `0.40 × LTV tier + 0.35 × (1 − fraud) + 0.25 × payment × basket-risk`

### Business Impact

**Credit loss reduction.** Systematic DECLINE on high-risk orders (fraud + payment profile + basket spike) replaces gut-feel decisions. The ~12% decline tier targets the cohort most likely to default or dispute — removing them from the fulfillment queue before cost is incurred.

**Rep capacity.** Auto-approving ~60% of order volume frees each rep from routine review and redirects their time to the 28% MANUAL_REVIEW queue — orders worth investigating — and to field sales, customer success, and availability issue resolution. This directly supports the availability-first strategy: reps who are not bottlenecked on order approval can focus on supplier-side interventions.

**Availability feedback loop.** Order-level data enriched with segment, payment method, fraud score, and basket deviation creates a structured signal for demand planning. High-value customers (AUTO_APPROVE tier) placing anomalous baskets trigger MANUAL_REVIEW rather than silent fulfillment — reducing over-commitment on constrained SKUs.

### Live Validation

The ODA pipeline is deployed in AWS `us-east-1`. 100 orders seeded from simulation output produced 105 action-log entries (full chain: DynamoDB Streams → Decision Lambda → Action Lambda → audit log). Scores ranged 0.503 – 0.941 with all three routing tiers active.
