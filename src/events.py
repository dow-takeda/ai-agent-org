from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field

OnEvent = Callable[["PipelineEvent"], None] | None


@dataclass
class PipelineEvent:
    type: str
    agent: str | None = None
    data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_sse(self) -> str:
        payload = {
            "type": self.type,
            "agent": self.agent,
            "data": self.data,
            "timestamp": self.timestamp,
        }
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
