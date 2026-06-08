from __future__ import annotations
from typing import Literal, Optional
import yaml
from pydantic import BaseModel, model_validator


class DateWindow(BaseModel):
    anchor: str = "latest"
    days: int = 90


class JoinConfig(BaseModel):
    parent: str
    key: str


class TableConfig(BaseModel):
    name: str
    filter: Optional[Literal["date_window"]] = None
    join: Optional[JoinConfig] = None
    static: bool = False
    split_anchor: bool = False

    @model_validator(mode="after")
    def check_exclusions(self) -> "TableConfig":
        if self.static and self.join is not None:
            raise ValueError(f"'{self.name}': static tables cannot have a join")
        if self.static and self.split_anchor:
            raise ValueError(f"'{self.name}': static tables cannot be split_anchor")
        return self


class SampleConfig(BaseModel):
    name: str
    split: Literal["even", "odd"]


class SamplerConfig(BaseModel):
    source_dir: str
    output_dir: str
    random_seed: int = 42
    date_window: DateWindow
    stratify_by: list[str]
    # Total rows across ALL tables per sample (orders + all joined tables combined).
    # When set, target_rows is ignored and the sampler proportionally trims after joining.
    total_records_per_sample: Optional[int] = None
    # Legacy per-orders cap (used only when total_records_per_sample is None)
    target_rows: Optional[int] = None
    tolerance: float = 0.10
    samples: list[SampleConfig]
    tables: list[TableConfig]

    @model_validator(mode="after")
    def exactly_one_split_anchor(self) -> "SamplerConfig":
        anchors = [t for t in self.tables if t.split_anchor]
        if len(anchors) != 1:
            raise ValueError(
                f"Exactly one table must have split_anchor=true, "
                f"got {len(anchors)}: {[t.name for t in anchors]}"
            )
        return self


def load_config(path: str) -> SamplerConfig:
    with open(path) as f:
        raw = yaml.safe_load(f)
    return SamplerConfig.model_validate(raw)
