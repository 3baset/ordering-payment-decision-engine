from __future__ import annotations
from typing import Literal, Optional, Union
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
    limit_rows: Optional[int] = None
    limit_mb: Optional[float] = None

    @model_validator(mode="after")
    def check_exclusions(self) -> "TableConfig":
        if self.limit_rows is not None and self.limit_mb is not None:
            raise ValueError(f"'{self.name}': limit_rows and limit_mb are mutually exclusive")
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
