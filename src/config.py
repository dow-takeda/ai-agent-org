from __future__ import annotations

import os


class PipelineConfig:
    """Pipeline configuration loaded from environment variables."""

    def __init__(self) -> None:
        self.max_rollback_attempts: int = int(os.getenv("MAX_ROLLBACK_ATTEMPTS", "3"))
        self.max_discussion_rounds: int = int(os.getenv("MAX_DISCUSSION_ROUNDS", "2"))
        self.pm_count: int = 1
        self.engineer_count: int = int(os.getenv("ENGINEER_COUNT", "1"))
        self.reviewer_count: int = int(os.getenv("REVIEWER_COUNT", "1"))

        if not 1 <= self.engineer_count <= 2:
            raise ValueError(f"ENGINEER_COUNT must be 1 or 2, got {self.engineer_count}")
        if not 1 <= self.reviewer_count <= 2:
            raise ValueError(f"REVIEWER_COUNT must be 1 or 2, got {self.reviewer_count}")


def load_config() -> PipelineConfig:
    return PipelineConfig()
