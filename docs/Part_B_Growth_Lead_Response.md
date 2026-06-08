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
