# FMCG & HORECA Seeded Entity Library — Egyptian Market
## For the Synthetic Wholesale Commerce Simulation Engine

**Version:** 2.0 (Egyptian Market)  
**Currency:** EGP (Egyptian Pound / جنيه مصري)  
**Simulation period:** 2023-01-01 → 2023-12-31  
**Exchange rate basis:** 2023 average 30.6 EGP/USD  
  → lognormal param conversion: `mean_log_EGP = mean_log_USD + ln(30.6) = mean_log_USD + 3.42`  
**Inflation basis:** Egypt 2023 annual wholesale FMCG ~30%  
  → `DAILY_INFLATION = (1.30) ** (1/365) = 1.000724`  
  (replaces the 3% global default in `MacroProcess`)  
**Connects to:** §B7 (Generator Layer), §B1 (Macro), §A2, §A15, §A1

---

## 0. Key Egyptian Market Parameters (Plug Into `MacroProcess`)

```python
# processes/macro_process.py — Egypt 2023 overrides

# Replace the original 3% global constant
DAILY_INFLATION  = (1.30) ** (1 / 365)   # 30% wholesale annual — Egypt 2023
EGP_USD_RATE_2023 = 30.6                 # for reference; all prices already in EGP

# Egypt-specific seasonality (supplements §8.1 global multipliers)
# Key: summer CSD/water spike much stronger than generic; Ramadan is a major driver
SEASONALITY = {
    1: 0.85,   # January  – post-holiday slow
    2: 0.90,   # February
    3: 1.20,   # March    – Ramadan 2023 starts 22 Mar → +20% base
    4: 1.30,   # April    – Ramadan + Eid al-Fitr peak
    5: 1.00,   # May      – post-Eid normalisation
    6: 1.20,   # June     – summer heat starts, beverages surge
    7: 1.40,   # July     – peak summer Egypt (40°C+), water/CSD dominant
    8: 1.45,   # August   – peak summer continues
    9: 1.30,   # September – back to school
    10: 1.05,  # October
    11: 0.95,  # November
    12: 1.00,  # December – mild Xmas bump for HORECA only
}

# Ramadan 2023 exact window (for targeted category boosts in MacroProcess)
RAMADAN_2023 = ("2023-03-22", "2023-04-21")
```

---

## 1. Product Taxonomy (EGP-calibrated)

### Lognormal parameter key

`(mean_log, sigma_log)` → `exp(mean_log)` ≈ median **wholesale case/unit price in EGP**.  
Sigma unchanged from USD version (price variability is relative, not absolute).

---

#### CATEGORY: `BEV` — Beverages

| Subcat | Name | Class | `(mean_log, sigma)` | Median price | Representative brands |
|---|---|---|---|---|---|
| `CSD` | Carbonated Soft Drinks | A | **(6.00, 0.40)** | ~403 EGP | Coca-Cola, Pepsi, 7Up, Sprite, Mirinda, Fanta, Kola Champagne, Spiro Spathis |
| `WAT` | Water | A | **(5.20, 0.35)** | ~181 EGP | Baraka ★, Nestlé Pure Life, Safi, Aqua Siwa, Siwa Oasis, Dasani |
| `JUI` | Juice & Nectar | B | **(6.10, 0.45)** | ~445 EGP | Juhayna ★, Beyti, Cappy, Enjoy, Vita (Juhayna), Rani, Donald |
| `HOT` | Hot Beverages | B | **(6.32, 0.50)** | ~554 EGP | Nescafé ★, Ahmad Tea ★, Lipton, Jacobs, Karak Tea, Twinings |
| `ENE` | Energy & Sport | C | **(6.52, 0.55)** | ~678 EGP | Red Bull, Power Horse, Boom, Sting, Monster |
| `MLK` | UHT Milk & Cream | B | **(6.22, 0.40)** | ~502 EGP | Juhayna ★, Baraka, Beyti, Almarai, Dina Farms, Président |

★ = dominant Egyptian-market brand; prioritise in weighted random selection

```python
BEV_PACK_SIZES = {
    "CSD": [("330ml can",  24), ("500ml PET",  24), ("1.5L PET", 6),
            ("2L PET",      6), ("250ml can",  24)],
    "WAT": [("500ml PET",  24), ("1.5L PET",  12), ("330ml PET", 24),
            ("5L gallon",   4)],
    "JUI": [("200ml carton",24), ("1L carton", 12), ("330ml can", 24)],
    "HOT": [("100g jar",   12), ("200g jar",  12), ("500g tin",   6),
            ("25-bag box", 24), ("100-bag box",12)],
    "ENE": [("250ml can",  24), ("500ml can", 24)],
    "MLK": [("200ml carton",24), ("1L carton", 12), ("200ml cream",24)],
}

# Brand weights for Egypt market (index matches brand list above)
BEV_BRAND_WEIGHTS = {
    "CSD": {"Coca-Cola": 0.32, "Pepsi": 0.28, "7Up": 0.10, "Sprite": 0.10,
            "Mirinda": 0.08, "Fanta": 0.08, "Kola Champagne": 0.02, "Spiro Spathis": 0.02},
    "WAT": {"Baraka": 0.45, "Nestlé Pure Life": 0.25, "Safi": 0.15,
            "Aqua Siwa": 0.10, "Dasani": 0.05},
    "JUI": {"Juhayna": 0.35, "Beyti": 0.20, "Cappy": 0.20, "Enjoy": 0.10,
            "Vita": 0.10, "Donald": 0.05},
    "HOT": {"Nescafé": 0.35, "Ahmad Tea": 0.30, "Lipton": 0.20, "Jacobs": 0.08, "Twinings": 0.07},
    "ENE": {"Red Bull": 0.40, "Power Horse": 0.30, "Boom": 0.20, "Sting": 0.10},
    "MLK": {"Juhayna": 0.35, "Baraka": 0.20, "Beyti": 0.20, "Almarai": 0.15, "Dina Farms": 0.10},
}
```

---

#### CATEGORY: `FOD` — Food & Dry Goods

| Subcat | Name | Class | `(mean_log, sigma)` | Median price | Representative brands |
|---|---|---|---|---|---|
| `STA` | Dry Staples | A | **(5.92, 0.50)** | ~372 EGP | El-Wadi ★, Nile Best, Egyptian Rice (Menofi), Barilla, Panzani, El-Mokhtar |
| `OIL` | Cooking Oils | A | **(6.42, 0.45)** | ~615 EGP | Afia ★, Al-Arabi ★, Sana, Crisco, Ideal, Mazola |
| `SNK` | Snacks & Crisps | B | **(5.82, 0.50)** | ~337 EGP | Chipsy ★ (Lay's Egypt), Doritos, Pringles, Cheetos, Elitess, Edita Bake Rollz |
| `BIS` | Biscuits & Crackers | B | **(5.92, 0.50)** | ~372 EGP | BISCO MISR ★ (Casio, Digestive), Trianon ★, Oreo, LU, Ringo, Petite Beurre |
| `CHO` | Chocolate & Confectionery | C | **(6.22, 0.60)** | ~502 EGP | KitKat ★, Galaxy, Snickers, Cadbury, Bounty, Molto (Edita), HoHos |
| `CND` | Candy & Gum | C | **(5.72, 0.55)** | ~305 EGP | Chiclets ★, Orbit, Mentos, Halls, Trident, Dentyne |
| `DAI` | Dairy (ambient) | B | **(6.02, 0.45)** | ~412 EGP | Kiri ★, Puck, President, Nestlé Sweetened Condensed, Anchor cream |
| `SAU` | Sauces & Pastes | B | **(6.12, 0.50)** | ~455 EGP | Heinz, Vitrac ★ (tomato paste), Americana, Del Monte, Knorr, Maggi |
| `SPE` | Spices & Stock Cubes | B | **(5.92, 0.55)** | ~372 EGP | Knorr cubes ★, Maggi ★, local bulk spices, el-Rashidi el-Mizan |

```python
FOD_PACK_SIZES = {
    "STA": [("1kg",     12), ("2kg",     6), ("5kg",     4), ("25kg sack", 1)],
    "OIL": [("1L PET",  12), ("2L PET",  6), ("5L",      4), ("20L drum",  1)],
    "SNK": [("40g",     24), ("85g",    12), ("160g",   12), ("200g",      6)],
    "BIS": [("150g",    12), ("250g",   12), ("500g",    6), ("24-count box",1)],
    "CHO": [("50g",     24), ("100g",   12), ("200g",    6), ("24-count box",1)],
    "CND": [("100-count",6), ("30g tube",24), ("25-count blister",12)],
    "DAI": [("170g tin",24), ("400g tin",12), ("1kg tub",  6)],
    "SAU": [("340g glass",12),("500g",  12), ("1kg",     6), ("5kg institutional",1)],
    "SPE": [("10g sachet",100),("50g box",24),("200g pack",12),("1kg bulk",6)],
}
```

---

#### CATEGORY: `CLN` — Cleaning & Household Chemicals

| Subcat | Name | Class | `(mean_log, sigma)` | Median price | Representative brands |
|---|---|---|---|---|---|
| `LDY` | Laundry & Fabric Care | A | **(6.42, 0.45)** | ~615 EGP | Ariel ★, Persil ★, Tide, OMO, Bonux, Bref |
| `DSH` | Dish & Kitchen | A | **(5.92, 0.40)** | ~372 EGP | Fairy ★, Pril ★, Sunlight, Vim, Ajax |
| `SUR` | Surface, Floor & Bathroom | B | **(6.02, 0.45)** | ~412 EGP | Dettol ★, Domestos, Harpic, Mr. Muscle, Flash, Clorox |
| `DIS` | Disinfectants & Sanitisers | B | **(6.12, 0.50)** | ~455 EGP | Dettol ★, Savlon, Lifebuoy sanitiser, Purell |
| `IND` | Industrial / HORECA Concentrates | C | **(6.92, 0.50)** | ~1009 EGP | Diversey, Ecolab, Holchem, Henkel Professional |

```python
CLN_PACK_SIZES = {
    "LDY": [("1kg powder",12),("3kg powder",4),("10kg powder",1),
            ("1L liquid", 12),("3L liquid",  4),("5L liquid",  2)],
    "DSH": [("500ml",     12),("1L",         6),("5L",         2)],
    "SUR": [("500ml spray",12),("1L",        12),("5L",         2)],
    "DIS": [("500ml",     12),("1L",          6),("5L",         2)],
    "IND": [("5L concentrate",2),("10L",      1),("20L drum",   1)],
}
```

---

#### CATEGORY: `PER` — Personal Care

| Subcat | Name | Class | `(mean_log, sigma)` | Median price | Representative brands |
|---|---|---|---|---|---|
| `HAR` | Hair Care | B | **(6.12, 0.55)** | ~455 EGP | Head & Shoulders ★, Pantene, Dove, Sunsilk, Garnier, Palmolive |
| `SKN` | Skin & Body Care | B | **(5.92, 0.50)** | ~372 EGP | Dove ★, Nivea, Lux, Cleopatra ★ (Henkel Egypt), Lifebuoy, Fa |
| `ORL` | Oral Care | B | **(6.12, 0.45)** | ~455 EGP | Colgate ★, Signal, Oral-B, Sensodyne, Close-Up |
| `DED` | Deodorant | C | **(6.12, 0.50)** | ~455 EGP | Dove, Rexona, Nivea, Fa, Axe |
| `RAZ` | Razors & Shaving | C | **(6.32, 0.55)** | ~554 EGP | Gillette ★, Bic, Wilkinson |

```python
PER_PACK_SIZES = {
    "HAR": [("200ml",12),("400ml",6),("1L salon",6)],
    "SKN": [("90g bar x6",4),("125g bar x6",4),("250ml gel",12),("500ml lotion",6)],
    "ORL": [("75ml",12),("100ml",12),("150ml",6),("12-tube case",1)],
    "DED": [("150ml aerosol",6),("50ml roll-on",12)],
    "RAZ": [("10-blade disposable",6),("refill x8",6)],
}
```

---

#### CATEGORY: `PAP` — Paper, Tissue & Disposables

| Subcat | Name | Class | `(mean_log, sigma)` | Median price | Representative brands |
|---|---|---|---|---|---|
| `TIS` | Facial Tissue & Paper Towel | A | **(6.22, 0.45)** | ~502 EGP | Fine ★, Kleenex, Tempo, Softy, Carrefour |
| `TLT` | Toilet Paper | A | **(6.42, 0.40)** | ~615 EGP | Fine ★, Kleenex, Scott, Softy, jumbo industrial |
| `DIS` | Disposable Cups / Plates / Cutlery | A | **(6.12, 0.50)** | ~455 EGP | Dart ★, Solo, Falcon, Comet, generic branded |
| `PKG` | Food Packaging & Foil | B | **(6.22, 0.55)** | ~502 EGP | Fine, Glad, Alcan, commercial generic |
| `OFF` | Office & Copy Paper | B | **(6.62, 0.40)** | ~748 EGP | Double A ★, Navigator, IK Plus, HP Paper, Hammermill |

```python
PAP_PACK_SIZES = {
    "TIS": [("200-sheet box x12",1),("100-sheet box x24",1),("pocket 6-roll x10",2)],
    "TLT": [("4-roll x12",1),("12-roll x4",1),("24-roll case",1),("jumbo 6-roll",1)],
    "DIS": [("4oz cup x50",6),("8oz cup x50",4),("12oz cup x25",6),
            ("7in plate x50",4),("9in plate x25",4),("500-spork set",1)],
    "PKG": [("30m foil x12",1),("50m cling x6",1),("parchment 50m x6",1)],
    "OFF": [("500-sheet ream x5",2),("500-sheet ream x10",1)],
}
```

---

#### CATEGORY: `HOR` — HORECA-Specific Ingredients & Supplies

*Primary channel: hotels, restaurants, catering companies, institutional kitchens.*

| Subcat | Name | Class | `(mean_log, sigma)` | Median price | Representative brands |
|---|---|---|---|---|---|
| `CNT` | Institutional Condiments | B | **(6.82, 0.50)** | ~916 EGP | Heinz FS, Hellmann's, Americana ketchup, American Garden, Vitrac |
| `BAK` | Baking & Pastry Ingredients | B | **(6.62, 0.50)** | ~748 EGP | Anchor, Elle & Vire, Saf-Instant yeast, Puratos, Zeelandia, Dawn |
| `RIC` | Rice & Grain (bulk) | A | **(6.72, 0.45)** | ~826 EGP | Egyptian Premium Menofi ★, SunRice FS, Al Wadi, Jasmine grade A |
| `COK` | Cooking Fats & Oils (bulk) | A | **(7.02, 0.40)** | ~1122 EGP | Afia 10L ★, Al-Arabi drum, Crisco Professional, Palm shortening |
| `CSM` | HORECA Consumables | B | **(6.42, 0.50)** | ~615 EGP | Fine interfolded, PE gloves, Sysco napkins, commercial cling wrap |
| `STO` | Stock, Bases & Flavourings | C | **(6.92, 0.60)** | ~1009 EGP | Knorr Professional ★, Maggi Professional, Nestlé Professional |

```python
HOR_PACK_SIZES = {
    "CNT": [("5kg bucket",2),("10kg bucket",1),("3L bag-in-box",4),("1L squeeze x6",1)],
    "BAK": [("500g sachet x10",1),("1kg x10",1),("25kg sack",1),("1L liquid x12",1)],
    "RIC": [("5kg",4),("10kg",2),("25kg sack",1)],
    "COK": [("5L tin",4),("10L tin",2),("20L drum",1),("15kg shortening",1)],
    "CSM": [("500-napkin x10",1),("PE glove M x100 x10",1)],
    "STO": [("1kg pouch x10",1),("500ml x6",1),("1L base x4",1)],
}
```

---

#### CATEGORY: `STA` — Stationery & Office Supplies (limited)

| Subcat | Name | Class | `(mean_log, sigma)` | Median price | Brands |
|---|---|---|---|---|---|
| `WRI` | Writing Instruments | B | **(5.72, 0.60)** | ~305 EGP | Bic ★, Staedtler, Pilot, Pentel |
| `FIL` | Filing & Organisation | C | **(5.92, 0.60)** | ~372 EGP | Leitz, Esselte, Avery |

---

### 1.1 Consolidated Category Registry

```python
# generators/product_generator.py

CATEGORY_REGISTRY = {
    "BEV": {
        "name": "Beverages",
        "subcategories": ["CSD", "WAT", "JUI", "HOT", "ENE", "MLK"],
        "demand_class_weights": {"A": 0.50, "B": 0.35, "C": 0.15},
        "lognormal_params": (6.00, 0.50),
        "margin_range": (0.10, 0.18),   # tighter in Egypt — high competition
        "lead_time_weights": [0.30, 0.35, 0.20, 0.10, 0.05],
    },
    "FOD": {
        "name": "Food & Dry Goods",
        "subcategories": ["STA", "OIL", "SNK", "BIS", "CHO", "CND", "DAI", "SAU", "SPE"],
        "demand_class_weights": {"A": 0.30, "B": 0.45, "C": 0.25},
        "lognormal_params": (6.02, 0.55),
        "margin_range": (0.12, 0.22),
        "lead_time_weights": [0.20, 0.30, 0.25, 0.15, 0.10],
    },
    "CLN": {
        "name": "Cleaning & Household Chemicals",
        "subcategories": ["LDY", "DSH", "SUR", "DIS", "IND"],
        "demand_class_weights": {"A": 0.35, "B": 0.40, "C": 0.25},
        "lognormal_params": (6.22, 0.50),
        "margin_range": (0.13, 0.24),
        "lead_time_weights": [0.20, 0.30, 0.25, 0.15, 0.10],
    },
    "PER": {
        "name": "Personal Care",
        "subcategories": ["HAR", "SKN", "ORL", "DED", "RAZ"],
        "demand_class_weights": {"A": 0.10, "B": 0.55, "C": 0.35},
        "lognormal_params": (6.12, 0.50),
        "margin_range": (0.16, 0.28),
        "lead_time_weights": [0.25, 0.30, 0.25, 0.15, 0.05],
    },
    "PAP": {
        "name": "Paper & Disposables",
        "subcategories": ["TIS", "TLT", "DIS", "PKG", "OFF"],
        "demand_class_weights": {"A": 0.40, "B": 0.40, "C": 0.20},
        "lognormal_params": (6.22, 0.45),
        "margin_range": (0.10, 0.20),
        "lead_time_weights": [0.25, 0.30, 0.20, 0.15, 0.10],
    },
    "HOR": {
        "name": "HORECA Ingredients & Supplies",
        "subcategories": ["CNT", "BAK", "RIC", "COK", "CSM", "STO"],
        "demand_class_weights": {"A": 0.30, "B": 0.45, "C": 0.25},
        "lognormal_params": (6.72, 0.50),
        "margin_range": (0.08, 0.18),   # bulk staples compressed margin
        "lead_time_weights": [0.15, 0.25, 0.30, 0.20, 0.10],
    },
    "STA": {
        "name": "Stationery & Office",
        "subcategories": ["WRI", "FIL"],
        "demand_class_weights": {"A": 0.05, "B": 0.45, "C": 0.50},
        "lognormal_params": (5.82, 0.60),
        "margin_range": (0.18, 0.36),
        "lead_time_weights": [0.30, 0.30, 0.20, 0.15, 0.05],
    },
}
```

---

## 2. SKU Naming Convention (Egypt market)

### 2.1 Format

```
{CATEGORY}-{SUBCAT}-{BRAND_CODE}-{SIZE_CODE}
```

**Local examples:**
- `BEV-CSD-COKE-330CAN24`    → Coca-Cola 330ml can case of 24
- `BEV-WAT-BRAK-500PET24`    → Baraka 500ml PET case of 24
- `BEV-HOT-AHMD-100BAG12`    → Ahmad Tea 100-bag case of 12
- `FOD-OIL-AFIA-5L4`         → Afia cooking oil 5L case of 4
- `FOD-SNK-CHPY-85G12`       → Chipsy 85g case of 12
- `CLN-LDY-ARIL-3KGPOW4`     → Ariel 3kg powder case of 4
- `PAP-TIS-FINE-200SH12`     → Fine 200-sheet tissue case of 12
- `HOR-RIC-MNFI-25KGSACK1`   → Menofi Egyptian rice 25kg sack

### 2.2 Egyptian Brand Codes

```python
BRAND_CODES = {
    # Beverages
    "Coca-Cola": "COKE",   "Pepsi": "PEPSI",      "7Up": "7UP",
    "Sprite": "SPRT",      "Mirinda": "MIRN",      "Fanta": "FANT",
    "Kola Champagne": "KLCH", "Spiro Spathis": "SPRO",
    "Baraka": "BRAK",      "Nestlé Pure Life": "NPURL", "Safi": "SAFI",
    "Aqua Siwa": "AQSIW",
    "Juhayna": "JUHY",     "Beyti": "BYTI",        "Cappy": "CAPP",
    "Enjoy": "ENJOY",      "Vita": "VITA",
    "Nescafé": "NSCF",     "Ahmad Tea": "AHMD",    "Lipton": "LIPT",
    "Jacobs": "JCBS",
    "Red Bull": "RBULL",   "Power Horse": "PWRHS", "Boom": "BOOM",
    # Food
    "Chipsy": "CHPY",      "Lay's": "LAYS",        "Doritos": "DRIT",
    "Edita Bake Rollz": "BKRZ", "Elitess": "ELTSS",
    "BISCO MISR": "BSCO",  "Trianon": "TRIN",      "Oreo": "OREO",
    "Ringo": "RING",
    "Vitrac": "VTRC",      "Americana": "AMRC",    "Heinz": "HNZ",
    "Afia": "AFIA",        "Al-Arabi": "ALRB",     "Sana": "SANA",
    "Knorr": "KNOR",       "Maggi": "MAGG",
    "Egyptian Menofi": "MNFI", "El-Wadi": "ELWD",
    "Kiri": "KIRI",        "Puck": "PUCK",
    # Cleaning
    "Ariel": "ARIL",       "Persil": "PRSL",       "Tide": "TIDE",
    "OMO": "OMO",          "Bonux": "BNUX",        "Bref": "BREF",
    "Fairy": "FARY",       "Pril": "PRIL",
    "Dettol": "DTTL",      "Domestos": "DMST",     "Harpic": "HRPC",
    # Personal Care
    "Head & Shoulders": "HDS", "Pantene": "PNTN",  "Dove": "DOVE",
    "Cleopatra": "CLPT",   "Nivea": "NIVEA",       "Lux": "LUX",
    "Colgate": "COLT",     "Signal": "SGNL",       "Oral-B": "ORALB",
    # Paper
    "Fine": "FINE",        "Kleenex": "KLNX",      "Dart": "DART",
    "Double A": "DBLA",    "Navigator": "NAVG",    "IK Plus": "IKPL",
    # HORECA
    "Knorr Professional": "KNORPRO", "Saf-Instant": "SAFINS",
    "Elle & Vire": "ELVIRE", "Puratos": "PURT",
    "Anchor": "ANCR",
    # Generic
    "Private Label": "PVT",
}
```

---

## 3. Customer Universe (Egyptian B2B Wholesale)

### 3.1 Faker Locale Setup

Egypt has bilingual business names — use both locales:

```python
from faker import Faker

fake = Faker(["ar_EG", "en_US"])   # bilingual — very realistic for Egyptian B2B
Faker.seed(42)
fake.add_provider(WholesaleFMCGProviderEGP)
```

### 3.2 Customer Type Registry (EGP credit limits)

```python
CUSTOMER_TYPES = {
    "HORECA_hotel_premium": {
        "templates_en": [
            "{adj} {name} Hotel & Resort", "{name} Palace Hotel",
            "Le {name} Hotel", "Four Points by {name}", "{name} Hilton",
            "{name} Marriott", "Kempinski {name}",
        ],
        "templates_ar": [
            "فندق {name} الكبير", "فندق قصر {name}", "فندق {name} البلاتيني",
        ],
        "segment":                "Premium",
        "order_size_multiplier":   1.6,
        "horeca_sku_affinity":     0.70,
        "avg_credit_limit_egp":    1_500_000,
        "payment_method_weights":  {"bank_transfer": 0.60, "cheque": 0.35, "cash": 0.05},
    },
    "HORECA_hotel_regular": {
        "templates_en": [
            "{name} Hotel", "{name} Inn & Suites", "{name} Suites",
            "{city} View Hotel", "Hotel {name}",
        ],
        "templates_ar": [
            "فندق {name}", "فندق {city}", "سويتس {name}",
        ],
        "segment":                "Regular",
        "order_size_multiplier":   1.2,
        "horeca_sku_affinity":     0.55,
        "avg_credit_limit_egp":    600_000,
        "payment_method_weights":  {"cheque": 0.55, "bank_transfer": 0.30, "cash": 0.15},
    },
    "HORECA_restaurant_premium": {
        "templates_en": [
            "{name} Restaurant & Grill", "{name} Fine Dining",
            "Brasserie {name}", "{name} Steakhouse", "{name} Rooftop",
        ],
        "templates_ar": [
            "مطعم {name} الفاخر", "مطعم {name} للمأكولات البحرية",
        ],
        "segment":                "Premium",
        "order_size_multiplier":   1.4,
        "horeca_sku_affinity":     0.65,
        "avg_credit_limit_egp":    1_200_000,
        "payment_method_weights":  {"cheque": 0.50, "bank_transfer": 0.40, "cash": 0.10},
    },
    "HORECA_restaurant_regular": {
        "templates_en": [
            "{name} Restaurant", "Café {name}", "{name} Grill & Rotisserie",
            "{name} Bistro", "{name} Kitchen",
        ],
        "templates_ar": [
            "مطعم {name}", "كافيه {name}", "مطعم {name} للكشري",
            "مطعم {name} للفول والطعمية", "مطبخ {name}",
        ],
        "segment":                "Regular",
        "order_size_multiplier":   1.0,
        "horeca_sku_affinity":     0.50,
        "avg_credit_limit_egp":    600_000,
        "payment_method_weights":  {"cheque": 0.45, "cash": 0.40, "bank_transfer": 0.15},
    },
    "HORECA_catering": {
        "templates_en": [
            "{name} Catering & Events", "{name} Catering Services",
            "{name} Food & Banqueting", "{name} Corporate Catering",
        ],
        "templates_ar": [
            "شركة {name} للتموين", "{name} للأفراح والمناسبات", "مؤسسة {name} للضيافة",
        ],
        "segment":                "Regular",
        "order_size_multiplier":   1.8,
        "horeca_sku_affinity":     0.60,
        "avg_credit_limit_egp":    900_000,
        "payment_method_weights":  {"cheque": 0.60, "bank_transfer": 0.35, "cash": 0.05},
    },
    "HORECA_school_canteen": {
        "templates_en": [
            "{name} International School", "{name} British School",
            "{name} Language School", "{name} Academy",
        ],
        "templates_ar": [
            "مدرسة {name} الدولية", "مدرسة {name} الخاصة", "أكاديمية {name}",
        ],
        "segment":                "Regular",
        "order_size_multiplier":   0.9,
        "horeca_sku_affinity":     0.35,
        "avg_credit_limit_egp":    450_000,
        "payment_method_weights":  {"cheque": 0.50, "bank_transfer": 0.40, "cash": 0.10},
    },
    "RETAIL_supermarket_large": {
        "templates_en": [
            "{name} Hypermarket", "Carrefour Market {city}",
            "Spinneys {name}", "{name} Seoudi Market", "Metro {name}",
        ],
        "templates_ar": [
            "هايبر {name}", "سوبرماركت {name} الكبير",
        ],
        "segment":                "Premium",
        "order_size_multiplier":   2.0,
        "horeca_sku_affinity":     0.03,
        "avg_credit_limit_egp":    1_800_000,
        "payment_method_weights":  {"bank_transfer": 0.65, "cheque": 0.30, "cash": 0.05},
    },
    "RETAIL_supermarket_mid": {
        "templates_en": [
            "{name} Superstore", "{name} Grocery", "{name} Market",
            "Spar {name}", "{name} Fresh Market",
        ],
        "templates_ar": [
            "سوبر ماركت {name}", "محلات {name}", "بقالة {name} الكبيرة",
        ],
        "segment":                "Regular",
        "order_size_multiplier":   1.2,
        "horeca_sku_affinity":     0.03,
        "avg_credit_limit_egp":    540_000,
        "payment_method_weights":  {"cheque": 0.55, "cash": 0.30, "bank_transfer": 0.15},
    },
    "RETAIL_minimarket": {
        "templates_en": [
            "{name} Mini Market", "Al {name} Store", "{name} Corner Shop",
            "{name} Quick Stop",
        ],
        "templates_ar": [
            "دكان {name}", "بقالة {name}", "ميني ماركت {name}",
            "محل {name} للبقالة", "بقالة أبو {name}",
        ],
        "segment":                "Low volume",
        "order_size_multiplier":   0.5,
        "horeca_sku_affinity":     0.05,
        "avg_credit_limit_egp":    150_000,
        "payment_method_weights":  {"cash": 0.70, "cheque": 0.25, "bank_transfer": 0.05},
    },
    "RETAIL_pharmacy": {
        "templates_en": [
            "{name} Pharmacy", "Ezzaby {city}", "Dr. {name} Pharmacy",
            "{name} Medical Supplies",
        ],
        "templates_ar": [
            "صيدلية {name}", "صيدلية د. {name}", "صيدلية {city} المركزية",
        ],
        "segment":                "Regular",
        "order_size_multiplier":   0.8,
        "horeca_sku_affinity":     0.02,
        "avg_credit_limit_egp":    360_000,
        "payment_method_weights":  {"cheque": 0.50, "cash": 0.35, "bank_transfer": 0.15},
    },
    "HORECA_cafe_small": {
        "templates_en": [
            "Café {name}", "{name} Coffee Shop", "{name} Espresso Bar",
            "{name} Kafe",
        ],
        "templates_ar": [
            "كافيه {name}", "قهوة {name}", "كافيه {city}",
        ],
        "segment":                "Low volume",
        "order_size_multiplier":   0.4,
        "horeca_sku_affinity":     0.45,
        "avg_credit_limit_egp":    120_000,
        "payment_method_weights":  {"cash": 0.60, "cheque": 0.30, "bank_transfer": 0.10},
    },
    "HORECA_bakery_small": {
        "templates_en": [
            "{name} Bakery", "{name} Patisserie", "Boulangerie {name}",
        ],
        "templates_ar": [
            "فرن {name}", "محل {name} للحلويات", "بيكري {name}",
        ],
        "segment":                "Low volume",
        "order_size_multiplier":   0.5,
        "horeca_sku_affinity":     0.30,
        "avg_credit_limit_egp":    135_000,
        "payment_method_weights":  {"cash": 0.55, "cheque": 0.35, "bank_transfer": 0.10},
    },
}

CUSTOMER_TYPE_WEIGHTS = {
    "HORECA_hotel_premium":       0.04,
    "HORECA_hotel_regular":       0.07,
    "HORECA_restaurant_premium":  0.06,
    "HORECA_restaurant_regular":  0.14,
    "HORECA_catering":            0.06,
    "HORECA_school_canteen":      0.04,
    "RETAIL_supermarket_large":   0.04,
    "RETAIL_supermarket_mid":     0.10,
    "RETAIL_minimarket":          0.18,
    "RETAIL_pharmacy":            0.07,
    "HORECA_cafe_small":          0.12,
    "HORECA_bakery_small":        0.08,
}
```

### 3.3 Egyptian Name Token Pool

```python
NAME_TOKENS = {
    "adj": [
        "Golden", "Royal", "Grand", "Premier", "Classic", "Elite",
        "Diamond", "Blue Nile", "Platinum", "Crown", "Heritage",
        # Arabic-flavoured adjectives (written in Latin for template use)
        "Al-Masri", "Al-Azhar", "Al-Ahram", "Al-Nile",
    ],
    "name": [
        # Egyptian geography (commercial use)
        "Nile", "Pyramids", "Sphinx", "Luxor", "Aswan", "Sinai", "Suez",
        "Alexandria", "Pharaoh", "Lotus", "Oasis", "Delta",
        # Common Egyptian family names
        "Hassan", "Ibrahim", "Khalil", "Mansour", "Nasser", "Omar",
        "Saleh", "Farouk", "Gamal", "Amr", "Karim", "Sherif",
        "Mostafa", "Tarek", "Hossam", "Walid", "Ayman", "Essam",
        # Brand-style names
        "Metro", "Central", "Orient", "Riviera", "Palms",
    ],
    "city": [
        "Zamalek", "Maadi", "Heliopolis", "Dokki", "Mohandiseen",
        "Nasr City", "New Cairo", "Sheikh Zayed", "6th October",
        "Downtown", "Garden City", "Rehab", "Katameya", "Tagamoa",
        "Obour", "Badr", "10th of Ramadan",   # industrial cities
        "Alex", "Port Said", "Ismailia", "Suez",
        "Hurghada", "Sharm", "Luxor",          # Red Sea / tourism
        "Tanta", "Mansoura", "Zagazig",         # Delta cities
        "Asyut", "Minya", "Sohag",              # Upper Egypt
    ],
}
```

---

## 4. Sales Territory Map (Egyptian Governorates)

Used to assign customers to `SalesRepresentatives` and to `area_income_band`
(which feeds the `AOV` multiplier in §A23.3).

```python
SALES_AREAS = [
    {
        "area_id": "AREA-GCR",
        "name": "Greater Cairo",
        "governorates": ["Cairo", "Giza"],
        "districts": ["Zamalek", "Maadi", "Heliopolis", "Nasr City", "Dokki",
                      "Mohandiseen", "New Cairo", "Sheikh Zayed", "6th October",
                      "Obour", "Shorouk"],
        "income_band": "high",
        "aov_multiplier": 1.20,
        "horeca_concentration": "high",
        "rep_count_range": (8, 14),
    },
    {
        "area_id": "AREA-ALX",
        "name": "Alexandria & North Coast",
        "governorates": ["Alexandria", "Beheira coastal"],
        "districts": ["Smouha", "Miami", "Sidi Gaber", "Montaza", "Agami"],
        "income_band": "high",
        "aov_multiplier": 1.15,
        "horeca_concentration": "medium",
        "rep_count_range": (5, 8),
    },
    {
        "area_id": "AREA-DLT",
        "name": "Delta Region",
        "governorates": ["Gharbia", "Dakahlia", "Sharqia", "Menoufia", "Beheira", "Kafr El-Sheikh"],
        "districts": ["Tanta", "Mansoura", "Zagazig", "Damanhour", "Shibin El-Kom"],
        "income_band": "mid",
        "aov_multiplier": 1.00,
        "horeca_concentration": "low",
        "rep_count_range": (6, 10),
    },
    {
        "area_id": "AREA-CNL",
        "name": "Canal Zone",
        "governorates": ["Suez", "Ismailia", "Port Said"],
        "districts": ["Port Said Downtown", "Ismailia Centre", "Suez Ataka"],
        "income_band": "mid",
        "aov_multiplier": 1.05,
        "horeca_concentration": "medium",
        "rep_count_range": (3, 5),
    },
    {
        "area_id": "AREA-RED",
        "name": "Red Sea & South Sinai",
        "governorates": ["Red Sea", "South Sinai"],
        "districts": ["Hurghada", "Marsa Alam", "Sharm El-Sheikh", "Dahab"],
        "income_band": "high",
        "aov_multiplier": 1.30,    # tourism — premium HORECA
        "horeca_concentration": "very high",
        "rep_count_range": (3, 5),
    },
    {
        "area_id": "AREA-UPP",
        "name": "Upper Egypt",
        "governorates": ["Minya", "Asyut", "Sohag", "Qena", "Luxor", "Aswan", "Beni Suef"],
        "districts": ["Minya Centre", "Asyut Centre", "Sohag Centre", "Luxor City", "Aswan City"],
        "income_band": "low",
        "aov_multiplier": 0.80,    # lower purchasing power
        "horeca_concentration": "low",
        "rep_count_range": (4, 7),
    },
    {
        "area_id": "AREA-FAY",
        "name": "Fayoum & South Giza",
        "governorates": ["Fayoum", "South Giza"],
        "income_band": "low",
        "aov_multiplier": 0.75,
        "horeca_concentration": "very low",
        "rep_count_range": (2, 4),
    },
]
```

---

## 5. Supplier Registry (Egypt-based)

```python
SUPPLIER_ARCHETYPES_TIER1 = [
    # Direct manufacturers — shortest lead time, highest daily capacity
    {
        "name": "Coca-Cola Egypt Bottling Company (CCEP)",
        "categories": ["BEV-CSD", "BEV-WAT", "BEV-JUI"],
        "avg_lead_time": 2,
        "daily_capacity": 20000,
        "on_time_rate": 0.97,
        "tier": 1,
        "location": "Obour Industrial City",
    },
    {
        "name": "PepsiCo Egypt (PEPSICO Beverages Egypt)",
        "categories": ["BEV-CSD", "BEV-WAT", "BEV-JUI", "FOD-SNK"],
        "avg_lead_time": 2,
        "daily_capacity": 18000,
        "on_time_rate": 0.96,
        "tier": 1,
        "location": "6th October Industrial Zone",
    },
    {
        "name": "Juhayna Food Industries",
        "categories": ["BEV-MLK", "BEV-JUI", "FOD-DAI"],
        "avg_lead_time": 3,
        "daily_capacity": 12000,
        "on_time_rate": 0.94,
        "tier": 1,
        "location": "Badr City",
    },
    {
        "name": "Nestlé Egypt S.A.E.",
        "categories": ["BEV-HOT", "FOD-DAI", "FOD-CHO", "BEV-MLK", "HOR-STO"],
        "avg_lead_time": 4,
        "daily_capacity": 10000,
        "on_time_rate": 0.95,
        "tier": 1,
        "location": "10th of Ramadan City",
    },
    {
        "name": "Edita Food Industries",
        "categories": ["FOD-SNK", "FOD-BIS", "FOD-CHO"],
        "avg_lead_time": 2,
        "daily_capacity": 9000,
        "on_time_rate": 0.93,
        "tier": 1,
        "location": "10th of Ramadan City",
    },
    {
        "name": "BISCO MISR (Mondelez Egypt)",
        "categories": ["FOD-BIS", "FOD-CHO", "FOD-CND"],
        "avg_lead_time": 3,
        "daily_capacity": 7000,
        "on_time_rate": 0.92,
        "tier": 1,
        "location": "Shoubra El-Kheima",
    },
    {
        "name": "Unilever Mashreq Egypt",
        "categories": ["CLN-LDY", "CLN-DSH", "PER-HAR", "PER-SKN", "BEV-HOT"],
        "avg_lead_time": 4,
        "daily_capacity": 11000,
        "on_time_rate": 0.95,
        "tier": 1,
        "location": "6th October City",
    },
    {
        "name": "Procter & Gamble Egypt",
        "categories": ["CLN-LDY", "PER-HAR", "PER-ORL", "PER-DED"],
        "avg_lead_time": 5,
        "daily_capacity": 8000,
        "on_time_rate": 0.94,
        "tier": 1,
        "location": "Obour City",
    },
    {
        "name": "Fine Hygienic Holding (Egypt)",
        "categories": ["PAP-TIS", "PAP-TLT", "PAP-DIS"],
        "avg_lead_time": 3,
        "daily_capacity": 9000,
        "on_time_rate": 0.95,
        "tier": 1,
        "location": "Borg Al Arab, Alexandria",
    },
    {
        "name": "Henkel Egypt (Persil / Cleopatra)",
        "categories": ["CLN-LDY", "CLN-DSH", "PER-SKN"],
        "avg_lead_time": 4,
        "daily_capacity": 6000,
        "on_time_rate": 0.93,
        "tier": 1,
        "location": "Obour Industrial City",
    },
]

# Tier 2 & 3 name templates (programmatic, seeded)
SUPPLIER_NAME_TEMPLATES_T2 = [
    "{name} Trading & Distribution Co.",
    "{name} Food Import & Export S.A.E.",
    "{name} General Trading L.L.C.",
    "{city} FMCG Distributors",
    "{name} Commercial Agency",
    "مؤسسة {name} للتجارة والتوزيع",
    "شركة {name} للاستيراد والتصدير",
    "{name} Brothers Trading",
    "Al-{name} Commercial Agents",
    "{name} Group — Supply Division",
]

SUPPLIER_PERFORMANCE_TIERS = {
    1: {"on_time_rate_range": (0.92, 0.98), "delay_days_range": (0, 2)},
    2: {"on_time_rate_range": (0.78, 0.92), "delay_days_range": (1, 8)},
    3: {"on_time_rate_range": (0.60, 0.80), "delay_days_range": (3, 20)},
}
```

---

## 6. Egyptian Seasonal Demand Overlays

### 6.1 Category-Level Modifiers

```python
CATEGORY_SEASONAL_MULTIPLIERS = {
    # Egypt summer (June-August): 40°C+, extreme beverage demand
    "BEV-CSD": {6: 1.5, 7: 1.65, 8: 1.65, 9: 1.25, 12: 1.0, 1: 0.8},
    "BEV-WAT": {6: 1.7, 7: 1.90, 8: 1.90, 9: 1.40, 12: 0.85, 1: 0.75},
    "BEV-ENE": {6: 1.3, 7: 1.40, 8: 1.40, 9: 1.10},
    # Winter hot beverages boost
    "BEV-HOT": {11: 1.25, 12: 1.40, 1: 1.35, 2: 1.20, 6: 0.70, 7: 0.60},
    # Ramadan 2023 (22 Mar – 21 Apr): food and staples surge
    "FOD-STA": {3: 1.55, 4: 1.60, 8: 1.10},       # Ramadan bulk buying + summer
    "FOD-OIL": {3: 1.50, 4: 1.55},
    "FOD-CHO": {3: 1.30, 4: 1.80, 2: 1.40, 12: 1.2},  # Ramadan + Valentines
    "FOD-BIS": {3: 1.45, 4: 1.40, 9: 1.10},
    "FOD-DAI": {3: 1.35, 4: 1.40},
    # Baking peaks for Ramadan iftars and Eid baking
    "HOR-BAK": {3: 1.60, 4: 1.50, 12: 1.20},
    "HOR-CNT": {3: 1.30, 4: 1.40, 6: 1.20, 7: 1.25},
    # Back-to-school (September) — stationery and office
    "PAP-OFF": {8: 1.45, 9: 1.60},
    "STA-WRI": {8: 1.50, 9: 1.70},
    # HORECA disposables peak: Ramadan events + summer tourism
    "PAP-DIS": {3: 1.40, 4: 1.35, 7: 1.30, 8: 1.30},
}
```

### 6.2 Ramadan & Eid Events (hardcoded for 2023)

```python
EGYPTIAN_CALENDAR_EVENTS_2023 = [
    {
        "name": "Ramadan 2023",
        "window": ("2023-03-22", "2023-04-21"),
        "category_boosts": {
            "FOD-STA": 1.55, "FOD-OIL": 1.50, "BEV-JUI": 1.55,
            "FOD-BIS": 1.45, "FOD-DAI": 1.35, "HOR-BAK": 1.60,
            "PAP-DIS": 1.40, "BEV-MLK": 1.30, "HOR-CNT": 1.30,
        },
        "note": "Largest annual demand event in Egypt. Wholesalers pre-stock heavily.",
    },
    {
        "name": "Eid al-Fitr 2023",
        "window": ("2023-04-21", "2023-04-24"),
        "category_boosts": {
            "FOD-CHO": 2.0, "FOD-BIS": 1.8, "BEV-JUI": 1.6,
            "PAP-DIS": 1.5,
        },
        "note": "Short but very intense. Gifts (chocolate, biscuits) peak hard.",
    },
    {
        "name": "Eid al-Adha 2023",
        "window": ("2023-06-28", "2023-07-02"),
        "category_boosts": {
            "FOD-SAU": 1.6, "HOR-CNT": 1.5, "FOD-SPE": 1.7,
            "PAP-DIS": 1.4,
        },
        "note": "Meat-cooking season — condiments and spices surge.",
    },
    {
        "name": "Back-to-School 2023",
        "window": ("2023-08-15", "2023-09-30"),
        "category_boosts": {
            "PAP-OFF": 1.60, "STA-WRI": 1.70, "STA-FIL": 1.50,
            "BEV-JUI": 1.20,   # school canteens re-stock
        },
    },
    {
        "name": "Summer Peak (Beverages)",
        "window": ("2023-06-01", "2023-08-31"),
        "category_boosts": {
            "BEV-WAT": 1.90, "BEV-CSD": 1.65, "BEV-ENE": 1.40,
            "BEV-JUI": 1.30,
        },
        "note": "Egypt averages 40°C+ in summer — single largest seasonal driver.",
    },
]
```

---

## 7. Egyptian Payment Behaviour (overrides §12.2)

Egypt B2B wholesale operates heavily on **post-dated cheques (PDC)** — a legal
instrument where a buyer gives a cheque with a future date. This is culturally
embedded and affects fraud detection, collection logic, and risk scoring.

```python
EGYPTIAN_PAYMENT_METHODS = {
    "post_dated_cheque": {
        "weight_by_segment": {"Premium": 0.40, "Regular": 0.55, "Low volume": 0.25},
        "typical_term_days": 30,        # cheque date = delivery date + 30
        "bounce_rate": {                # specific to Egypt 2023
            "risk_low":    0.04,        # low-risk customer: 4% bounce rate
            "risk_medium": 0.12,
            "risk_high":   0.30,
        },
        "note": "PDC bounce (return) triggers 'PaymentFailed' event and credit freeze.",
    },
    "bank_transfer": {
        "weight_by_segment": {"Premium": 0.45, "Regular": 0.25, "Low volume": 0.10},
        "typical_lag_days": 2,          # CBE RTGS same-day but small ops take 1-2 days
    },
    "cash_on_delivery": {
        "weight_by_segment": {"Premium": 0.05, "Regular": 0.20, "Low volume": 0.65},
        "note": "High for informal minimarkets. No credit risk, but operational cost.",
    },
}

# Egyptian-specific payment risk overrides for §12.2
# Replace default success probabilities with Egypt-calibrated values
EGYPT_PAYMENT_SUCCESS_PROB = {
    # (risk_score_band): (PDC, bank_transfer, cash)
    "low":    {"post_dated_cheque": 0.96, "bank_transfer": 0.99, "cash": 0.99},
    "medium": {"post_dated_cheque": 0.88, "bank_transfer": 0.97, "cash": 0.98},
    "high":   {"post_dated_cheque": 0.70, "bank_transfer": 0.90, "cash": 0.95},
}
```

---

## 8. Basket Affinity Matrix (Egyptian context)

```python
AFFINITY_GROUPS = [
    # --- Iftar / Ramadan Bundle (strongest Egyptian-specific signal) ---
    {
        "name": "iftar_bundle",
        "anchor": "BEV-JUI",
        "partners": [
            ("FOD-DAI",  2.0),   # yoghurt/cream for Ramadan
            ("FOD-BIS",  1.8),   # biscuits for iftar table
            ("PAP-DIS",  1.6),   # disposable cups
            ("BEV-MLK",  1.5),
        ],
        "active_during": ["Ramadan 2023"],   # matches EGYPTIAN_CALENDAR_EVENTS_2023
        "segment_amplifier": {"Premium": 1.0, "Regular": 1.4, "Low volume": 1.2},
    },
    # --- Hot Beverage Bundle (café / hotel all-year) ---
    {
        "name": "hot_beverage_bundle",
        "anchor": "BEV-HOT",
        "partners": [
            ("FOD-STA",  1.9),   # sugar
            ("PAP-DIS",  2.1),   # disposable cups
            ("BEV-MLK",  1.7),   # creamer / UHT milk
        ],
        "channel_amplifier": {"HORECA": 1.5},
    },
    # --- Summer Cold Beverage + Snack (convenience / kiosk) ---
    {
        "name": "summer_cold_bundle",
        "anchor": "BEV-CSD",
        "partners": [
            ("FOD-SNK",  2.2),
            ("BEV-WAT",  1.6),
            ("FOD-CHO",  1.3),
        ],
        "active_during": ["Summer Peak (Beverages)"],
        "segment_amplifier": {"Low volume": 1.5, "Regular": 1.1},
    },
    # --- Cooking Bundle (staples) ---
    {
        "name": "cooking_bundle",
        "anchor": "FOD-STA",
        "partners": [
            ("FOD-OIL",  2.6),
            ("FOD-SAU",  1.9),   # tomato paste / sauces
            ("FOD-SPE",  1.7),   # spices / Knorr
            ("HOR-STO",  1.5),
        ],
    },
    # --- Bakery / HORECA Bundle ---
    {
        "name": "bakery_bundle",
        "anchor": "HOR-BAK",
        "partners": [
            ("FOD-STA",  2.3),   # flour + sugar
            ("FOD-OIL",  2.0),
            ("HOR-COK",  1.8),
            ("BEV-MLK",  1.6),
        ],
        "channel_amplifier": {"HORECA": 1.7},
    },
    # --- Laundry Bundle ---
    {
        "name": "laundry_bundle",
        "anchor": "CLN-LDY",
        "partners": [
            ("CLN-DSH",  1.8), ("CLN-SUR", 1.6), ("CLN-DIS", 1.4),
        ],
    },
    # --- Tissue Triple (hygiene routine) ---
    {
        "name": "tissue_bundle",
        "anchor": "PAP-TIS",
        "partners": [
            ("PAP-TLT",  2.4), ("CLN-DSH", 1.4), ("PAP-DIS", 1.5),
        ],
    },
    # --- HORECA Service Bundle ---
    {
        "name": "horeca_service_bundle",
        "anchor": "PAP-DIS",
        "partners": [
            ("PAP-TIS",  2.0), ("HOR-CSM", 2.1), ("BEV-HOT", 1.5),
        ],
        "channel_amplifier": {"HORECA": 2.0},
    },
    # --- Condiment Set ---
    {
        "name": "condiment_bundle",
        "anchor": "HOR-CNT",
        "partners": [
            ("FOD-SAU",  1.9), ("FOD-OIL",  1.4), ("FOD-SPE", 1.5),
        ],
        "channel_amplifier": {"HORECA": 1.6},
    },
    # --- Water + Juice (hotel buffet / tourist HORECA) ---
    {
        "name": "buffet_hydration",
        "anchor": "BEV-WAT",
        "partners": [
            ("BEV-JUI",  1.8), ("BEV-CSD",  1.5),
        ],
        "channel_amplifier": {"HORECA": 1.8, "RETAIL_supermarket_large": 1.3},
    },
]
```

---

## 9. Egyptian Fraud Patterns (extends §A5)

Egypt-specific patterns on top of the generic FMCG fraud signatures.

```python
FRAUD_PATTERNS_EGYPT = [
    {
        "name": "pdc_bust_out",
        "description": "Customer issues post-dated cheques against rising orders then "
                       "stops answering — classic Egyptian bust-out using PDC.",
        "triggers": {
            "payment_method": ("==", "post_dated_cheque"),
            "open_cheques_count": (">", 4),
            "order_frequency_spike_7d": (">", 3.0),   # 3× normal rate
            "customer_tenure_days": ("<", 90),
        },
        "fraud_score_boost": 0.45,
    },
    {
        "name": "ramadan_overstock_flip",
        "description": "Bulk-buying essentials at wholesale during Ramadan then "
                       "reselling at retail — common margin arbitrage that inflates order sizes.",
        "triggers": {
            "sku_category": ("in", ["FOD-STA", "FOD-OIL", "BEV-JUI"]),
            "order_qty_ratio_vs_30d_avg": (">", 6),
            "active_event": ("==", "Ramadan 2023"),
            "customer_type": ("in", ["RETAIL_minimarket", "HORECA_cafe_small"]),
        },
        "fraud_score_boost": 0.25,
        "note": "Flag for review; not always fraudulent — genuine stockpiling is common.",
    },
    {
        "name": "new_account_credit_escalation",
        "description": "Customer starts with small COD orders, switches to PDC, "
                       "rapidly escalates order size near credit limit.",
        "triggers": {
            "customer_tenure_days": ("<", 60),
            "payment_method_change": ("cod_to_pdc", True),
            "credit_utilisation_pct": (">", 0.85),
            "order_total_growth_30d": (">", 4.0),
        },
        "fraud_score_boost": 0.40,
    },
    {
        "name": "cleaning_chemical_diversion",
        "description": "Large CLN-IND order from non-institutional customer "
                       "(minimarket / small café) — possible diversion or resale.",
        "triggers": {
            "sku_subcategory": ("==", "CLN-IND"),
            "customer_type": ("in", ["RETAIL_minimarket", "HORECA_cafe_small"]),
            "order_qty_ratio_vs_segment_norm": (">", 8),
        },
        "fraud_score_boost": 0.38,
    },
]
```

---

## 10. Custom Faker Provider: `WholesaleFMCGProviderEGP`

```python
# generators/wholesale_fmcg_provider_egp.py

from faker.providers import BaseProvider
import numpy as np
import re

class WholesaleFMCGProviderEGP(BaseProvider):
    """
    Egyptian-market FMCG/HORECA Faker provider. All prices in EGP.
    
    Usage:
        from faker import Faker
        from generators.wholesale_fmcg_provider_egp import WholesaleFMCGProviderEGP

        fake = Faker(["ar_EG", "en_US"])
        Faker.seed(42)
        fake.add_provider(WholesaleFMCGProviderEGP)

        sku         = fake.wholesale_sku()
        company     = fake.b2b_company_name(segment="Regular", language="ar")
        price_egp   = fake.wholesale_base_price_egp("BEV", "CSD")
    """

    # ── Product ──────────────────────────────────────────────────────────────

    def wholesale_sku(
        self,
        category: str | None = None,
        subcategory: str | None = None,
        brand: str | None = None,
    ) -> str:
        if category is None:
            category = self.random_element(list(CATEGORY_REGISTRY.keys()))
        if subcategory is None:
            subcategory = self.random_element(CATEGORY_REGISTRY[category]["subcategories"])
        if brand is None:
            brand = self._pick_brand(category, subcategory)
        brand_code = BRAND_CODES.get(brand, brand[:4].upper())
        pack = self.random_element(_pack_sizes_for(category, subcategory))
        size_code = re.sub(r"[^A-Z0-9]", "", pack[0].upper())[:9]
        qty_code  = str(pack[1])
        return f"{category}-{subcategory}-{brand_code}-{size_code}{qty_code}"

    def wholesale_base_price_egp(
        self, category: str, subcategory: str | None = None
    ) -> float:
        """Return a wholesale unit/case price in EGP."""
        mean_log, sigma = CATEGORY_REGISTRY[category]["lognormal_params"]
        price = float(np.random.lognormal(mean=mean_log, sigma=sigma))
        return round(max(50.0, min(price, 15_000.0)), 2)   # EGP bounds

    def wholesale_unit_cost_egp(self, base_price_egp: float, category: str) -> float:
        lo, hi = CATEGORY_REGISTRY[category]["margin_range"]
        margin = self.generator.random.uniform(lo, hi)
        return round(base_price_egp * (1 - margin), 2)

    def wholesale_demand_class(self, category: str) -> str:
        w = CATEGORY_REGISTRY[category]["demand_class_weights"]
        return self.random_element(
            list(w.keys()), weights=list(w.values())
        )

    # ── Customer ─────────────────────────────────────────────────────────────

    def b2b_company_name(
        self, segment: str = "Regular", language: str = "en"
    ) -> str:
        type_pool = [k for k, v in CUSTOMER_TYPES.items() if v["segment"] == segment]
        if not type_pool:
            type_pool = list(CUSTOMER_TYPES.keys())
        chosen_type = self.random_element(type_pool)
        ct = CUSTOMER_TYPES[chosen_type]
        key = "templates_ar" if language == "ar" else "templates_en"
        template = self.random_element(ct.get(key, ct["templates_en"]))
        return template.format(
            adj=self.random_element(NAME_TOKENS["adj"]),
            name=self.random_element(NAME_TOKENS["name"]),
            city=self.random_element(NAME_TOKENS["city"]),
        )

    def b2b_credit_limit_egp(self, segment: str) -> float:
        """Draw a credit limit in EGP with ±20–50% variability."""
        segment_base = {
            "Premium":    1_500_000,
            "Regular":      600_000,
            "Low volume":   150_000,
        }
        base = segment_base.get(segment, 600_000)
        variability = {
            "Premium": (0.80, 1.20),
            "Regular": (0.70, 1.30),
            "Low volume": (0.50, 1.50),
        }[segment]
        factor = self.generator.random.uniform(*variability)
        return round(base * factor, -3)   # round to nearest 1000 EGP

    # ── Supplier ─────────────────────────────────────────────────────────────

    def supplier_name(self, tier: int = 2) -> str:
        if tier == 1:
            return self.random_element(
                [s["name"] for s in SUPPLIER_ARCHETYPES_TIER1]
            )
        template = self.random_element(SUPPLIER_NAME_TEMPLATES_T2)
        return template.format(
            name=self.random_element(NAME_TOKENS["name"]),
            city=self.random_element(NAME_TOKENS["city"]),
        )

    # ── Private ──────────────────────────────────────────────────────────────

    def _pick_brand(self, category: str, subcategory: str) -> str:
        key = (category, subcategory)
        weights_map = BEV_BRAND_WEIGHTS.get(subcategory) if category == "BEV" else None
        if weights_map:
            brands = list(weights_map.keys())
            weights = list(weights_map.values())
            return self.random_element(brands, weights=weights)
        return self.random_element(_brands_for(category, subcategory))
```

---

## 11. Integration Checklist

```
generators/
├── wholesale_fmcg_provider_egp.py   ← this library's provider class
├── product_generator.py
│     fake.add_provider(WholesaleFMCGProviderEGP)
│     sku_id      = fake.wholesale_sku(category, subcategory)
│     base_price  = fake.wholesale_base_price_egp(category, subcategory)   # EGP
│     unit_cost   = fake.wholesale_unit_cost_egp(base_price, category)     # EGP
│     demand_class = fake.wholesale_demand_class(category)
│
├── customer_generator.py
│     fake.add_provider(WholesaleFMCGProviderEGP)
│     company_name  = fake.b2b_company_name(segment, language="ar")  # bilingual
│     credit_limit  = fake.b2b_credit_limit_egp(segment)             # EGP
│
└── supplier_generator.py
      fake.add_provider(WholesaleFMCGProviderEGP)
      name = fake.supplier_name(tier=tier)

processes/macro_process.py
      DAILY_INFLATION  = (1.30) ** (1/365)   # 30% annual — Egypt 2023
      SEASONALITY      = { ... }              # use Egypt dict from Section 0

engines/affinity_engine.py
      import AFFINITY_GROUPS from this library

engines/fraud_engine.py
      import FRAUD_PATTERNS_EGYPT and merge with FRAUD_PATTERNS_FMCG

store/shared_state.py (InvoiceProcess)
      import EGYPT_PAYMENT_METHODS for payment_method selection
      import EGYPT_PAYMENT_SUCCESS_PROB to replace §12.2 defaults
```

---

*End of FMCG & HORECA Entity Library v2.0 — Egyptian Market (EGP)*
