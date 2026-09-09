from __future__ import annotations
from dataclasses import dataclass, field, asdict
import hashlib
from typing import Any


@dataclass
class Signal:
    kind: str
    symbols: list[str]
    direction: str
    timeframe: str
    asof: str
    event_key: str
    reasons: list[str]
    metrics: dict[str, Any] = field(default_factory=dict)
    caution: str = "Pattern hypothesis, not a calibrated probability. News and fundamentals NOT checked."
    priority: str = "WATCH"
    horizon: str = "5-20 sessions; research hypothesis"

    @property
    def signal_id(self) -> str:
        raw = "|".join(["v2", self.kind, *self.symbols, self.direction, self.event_key])
        return hashlib.sha256(raw.encode()).hexdigest()[:20]

    @property
    def cooldown_key(self) -> str:
        return "|".join([self.kind, *self.symbols, self.direction])

    def to_dict(self) -> dict:
        return {**asdict(self), "signal_id": self.signal_id, "cooldown_key": self.cooldown_key}
