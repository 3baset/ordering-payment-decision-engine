from __future__ import annotations

import random

# Category co-occurrence weights (lift > 1.5 for top pairs)
CATEGORY_AFFINITY: dict[str, dict[str, float]] = {
    "BEV": {"FOD": 2.5, "PER": 1.2, "CLN": 1.0, "PAP": 1.1, "HOR": 0.8, "STA": 0.5},
    "FOD": {"BEV": 2.5, "CLN": 1.8, "PAP": 1.5, "PER": 1.0, "HOR": 1.3, "STA": 0.4},
    "CLN": {"PAP": 2.8, "FOD": 1.8, "BEV": 1.0, "PER": 1.6, "HOR": 0.7, "STA": 0.3},
    "PAP": {"CLN": 2.8, "HOR": 2.2, "FOD": 1.5, "BEV": 1.1, "PER": 1.0, "STA": 0.5},
    "PER": {"CLN": 1.6, "BEV": 1.2, "FOD": 1.0, "PAP": 1.0, "HOR": 0.5, "STA": 0.4},
    "HOR": {"PAP": 2.2, "FOD": 1.3, "CLN": 0.7, "BEV": 0.8, "PER": 0.5, "STA": 0.3},
    "STA": {"PAP": 0.5, "BEV": 0.5, "FOD": 0.4, "CLN": 0.3, "PER": 0.4, "HOR": 0.3},
}


def get_affinity_weight(anchor_category: str, candidate_category: str) -> float:
    return CATEGORY_AFFINITY.get(anchor_category, {}).get(candidate_category, 1.0)


def sample_basket_skus(
    anchor_sku_id: str,
    all_sku_ids: list[str],
    sku_categories: dict[str, str],
    n_lines: int,
) -> list[str]:
    """Sample n_lines SKUs weighted by category affinity from the anchor SKU."""
    if n_lines <= 0:
        return []

    anchor_cat = sku_categories.get(anchor_sku_id, "BEV")
    weights = []
    for sku in all_sku_ids:
        cat = sku_categories.get(sku, "BEV")
        weights.append(get_affinity_weight(anchor_cat, cat))

    total = sum(weights)
    if total <= 0:
        weights = [1.0] * len(all_sku_ids)
        total = len(all_sku_ids)
    norm_weights = [w / total for w in weights]

    chosen = random.choices(all_sku_ids, weights=norm_weights, k=min(n_lines, len(all_sku_ids)))
    # deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for s in chosen:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique
