from __future__ import annotations

import random
import uuid

import numpy as np

from engines.elasticity_engine import get_demand_class
from engines.inventory_engine import (
    compute_eoq,
    compute_initial_stock,
    compute_reorder_point,
    compute_safety_stock,
)

# ── Category registry ──────────────────────────────────────────────────────────
CATEGORY_REGISTRY: dict[str, dict] = {
    "BEV": {"weight": 0.25, "subcats": {
        "CSD": {"mean_log": 6.00, "sigma": 0.40, "weight": 0.25},
        "WAT": {"mean_log": 5.20, "sigma": 0.35, "weight": 0.20},
        "JUI": {"mean_log": 6.10, "sigma": 0.45, "weight": 0.15},
        "HOT": {"mean_log": 6.32, "sigma": 0.50, "weight": 0.10},
        "ENE": {"mean_log": 6.52, "sigma": 0.55, "weight": 0.10},
        "MLK": {"mean_log": 6.22, "sigma": 0.40, "weight": 0.20},
    }},
    "FOD": {"weight": 0.22, "subcats": {
        "STA": {"mean_log": 5.92, "sigma": 0.50, "weight": 0.15},
        "OIL": {"mean_log": 6.42, "sigma": 0.45, "weight": 0.12},
        "SNK": {"mean_log": 5.82, "sigma": 0.50, "weight": 0.15},
        "BIS": {"mean_log": 5.92, "sigma": 0.50, "weight": 0.12},
        "CHO": {"mean_log": 6.22, "sigma": 0.60, "weight": 0.10},
        "CND": {"mean_log": 5.72, "sigma": 0.55, "weight": 0.08},
        "DAI": {"mean_log": 6.02, "sigma": 0.45, "weight": 0.12},
        "SAU": {"mean_log": 6.12, "sigma": 0.50, "weight": 0.08},
        "SPE": {"mean_log": 5.92, "sigma": 0.55, "weight": 0.08},
    }},
    "CLN": {"weight": 0.18, "subcats": {
        "LDY": {"mean_log": 6.42, "sigma": 0.45, "weight": 0.25},
        "DSH": {"mean_log": 5.92, "sigma": 0.40, "weight": 0.20},
        "SUR": {"mean_log": 6.02, "sigma": 0.45, "weight": 0.20},
        "DIS": {"mean_log": 6.12, "sigma": 0.50, "weight": 0.20},
        "IND": {"mean_log": 6.92, "sigma": 0.50, "weight": 0.15},
    }},
    "PER": {"weight": 0.12, "subcats": {
        "HAR": {"mean_log": 6.12, "sigma": 0.55, "weight": 0.25},
        "SKN": {"mean_log": 5.92, "sigma": 0.50, "weight": 0.20},
        "ORL": {"mean_log": 6.12, "sigma": 0.45, "weight": 0.20},
        "DED": {"mean_log": 6.12, "sigma": 0.50, "weight": 0.20},
        "RAZ": {"mean_log": 6.32, "sigma": 0.55, "weight": 0.15},
    }},
    "PAP": {"weight": 0.13, "subcats": {
        "TIS": {"mean_log": 6.22, "sigma": 0.45, "weight": 0.25},
        "TLT": {"mean_log": 6.42, "sigma": 0.40, "weight": 0.25},
        "DIS": {"mean_log": 6.12, "sigma": 0.50, "weight": 0.20},
        "PKG": {"mean_log": 6.22, "sigma": 0.55, "weight": 0.15},
        "OFF": {"mean_log": 6.62, "sigma": 0.40, "weight": 0.15},
    }},
    "HOR": {"weight": 0.07, "subcats": {
        "CNT": {"mean_log": 6.82, "sigma": 0.50, "weight": 0.18},
        "BAK": {"mean_log": 6.62, "sigma": 0.50, "weight": 0.18},
        "RIC": {"mean_log": 6.72, "sigma": 0.45, "weight": 0.18},
        "COK": {"mean_log": 7.02, "sigma": 0.40, "weight": 0.18},
        "CSM": {"mean_log": 6.42, "sigma": 0.50, "weight": 0.14},
        "STO": {"mean_log": 6.92, "sigma": 0.60, "weight": 0.14},
    }},
    "STA": {"weight": 0.03, "subcats": {
        "WRI": {"mean_log": 5.72, "sigma": 0.55, "weight": 0.50},
        "FIL": {"mean_log": 5.82, "sigma": 0.50, "weight": 0.30},
        "GEN": {"mean_log": 5.62, "sigma": 0.60, "weight": 0.20},
    }},
}

BRAND_CODES: dict[str, list[str]] = {
    "CSD": ["COKE", "PEPSI", "7UP", "SPRT", "MIRN", "FANT", "KLCH", "SPRO"],
    "WAT": ["BRAK", "NPURL", "SAFI", "AQSIW", "DASN"],
    "JUI": ["JUHY", "BYTI", "CAPP", "ENJOY", "VITA"],
    "HOT": ["NSCF", "AHMD", "LIPT", "JCBS", "TWIG"],
    "ENE": ["RBULL", "PWRHS", "BOOM", "STNG"],
    "MLK": ["JUHY", "BRAK", "BYTI", "ALMA", "DINF"],
    "STA": ["ELWD", "NILB", "EGRC", "BRIL", "PNZN"],
    "OIL": ["AFIA", "ALRB", "SANA", "CRSC", "IDEL"],
    "SNK": ["CHPY", "DRTS", "PRNG", "CHES", "EDTA"],
    "BIS": ["BSCO", "TRIN", "OREO", "LU", "RING"],
    "CHO": ["KTKT", "GLXY", "SNCR", "CDBY", "BNTY"],
    "CND": ["CHCL", "ORBT", "MNTS", "HLLS", "TRID"],
    "DAI": ["KIRI", "PUCK", "PRSD", "NSCM", "ANCR"],
    "SAU": ["HNZ", "VITRC", "AMRC", "DLMT", "KNOR"],
    "SPE": ["KNOR", "MAGG", "LCLS", "ELRS"],
    "LDY": ["ARIL", "PRSL", "TIDE", "OMO", "BNUX"],
    "DSH": ["BREF", "FARY", "PRIL", "DTTL"],
    "SUR": ["DMST", "HRPC", "AJAX", "MRPH"],
    "DIS": ["DMST", "SLNX", "DTTL"],
    "IND": ["HRPC", "DMST", "JHNSON"],
    "HAR": ["HDS", "PNTN", "DOVE", "CLPT", "NIVEA"],
    "SKN": ["NIVEA", "LUX", "DOVE", "VSLNE"],
    "ORL": ["ORALB", "COLGT", "SENSDN"],
    "DED": ["DOVE", "COLT", "SGNL", "AXE"],
    "RAZ": ["GLLTE", "SCHK"],
    "TIS": ["FINE", "KLNX"],
    "TLT": ["FINE", "DART", "DBLA"],
    "PKG": ["NAVG", "DART", "IKPL"],
    "OFF": ["FINE", "NAVG"],
    "CNT": ["KNORPRO", "HNZ", "SAFI"],
    "BAK": ["ANCR", "ELVR", "SAFINS"],
    "RIC": ["MNFI", "SUNRC", "ELWD"],
    "COK": ["AFIA10L", "ALRB", "CRSCPRO"],
    "CSM": ["DART", "PURT"],
    "STO": ["KNORPRO", "MAGG"],
    "WRI": ["BIC", "FBER", "PTLOT"],
    "FIL": ["NAVG", "FINE"],
    "GEN": ["PVT"],
}

SIZE_CODES: list[str] = ["250ML12", "500ML24", "1L6", "330CAN24", "2L6", "5KG", "10KG", "1KG12"]


def generate_skus(n: int, avg_daily_demand_range: tuple[float, float] = (0.5, 10.0)) -> list[dict]:
    """Generate n SKU records with full inventory metadata."""
    cat_names = list(CATEGORY_REGISTRY.keys())
    cat_weights = [CATEGORY_REGISTRY[c]["weight"] for c in cat_names]

    skus: list[dict] = []
    used_ids: set[str] = set()

    for _ in range(n):
        cat = random.choices(cat_names, weights=cat_weights, k=1)[0]
        subcats = CATEGORY_REGISTRY[cat]["subcats"]
        subcat_names = list(subcats.keys())
        subcat_weights = [subcats[s]["weight"] for s in subcat_names]
        subcat = random.choices(subcat_names, weights=subcat_weights, k=1)[0]
        brands = BRAND_CODES.get(subcat, BRAND_CODES.get(cat, ["PVT"]))
        brand = random.choice(brands)
        size = random.choice(SIZE_CODES)

        # Build unique SKU ID
        base_id = f"{cat}-{subcat}-{brand}-{size}"
        sku_id = base_id
        suffix = 0
        while sku_id in used_ids:
            suffix += 1
            sku_id = f"{base_id}-{suffix:02d}"
        used_ids.add(sku_id)

        # Unit price from log-normal
        params = subcats[subcat]
        unit_price = float(np.random.lognormal(params["mean_log"], params["sigma"]))

        # Demand parameters
        avg_demand = np.random.uniform(*avg_daily_demand_range)
        demand_std = avg_demand * np.random.uniform(0.2, 0.6)
        lead_time = random.choices([3, 5, 7, 10, 14], weights=[20, 30, 25, 15, 10], k=1)[0]
        demand_class = get_demand_class(cat, subcat)

        reorder_pt = compute_reorder_point(avg_demand, lead_time, demand_std)
        safety = compute_safety_stock(lead_time, demand_std)
        eoq = compute_eoq(avg_demand * 365)
        initial = compute_initial_stock(reorder_pt, demand_std)

        skus.append({
            "sku_id": sku_id,
            "category": cat,
            "subcategory": subcat,
            "brand_code": brand,
            "unit_price": round(unit_price, 2),
            "avg_daily_demand": round(avg_demand, 3),
            "demand_std": round(demand_std, 3),
            "lead_time": lead_time,
            "demand_class": demand_class,
            "reorder_point": round(reorder_pt, 1),
            "safety_stock": round(safety, 1),
            "eoq": eoq,
            "initial_stock": initial,
        })

    return skus
