from __future__ import annotations

from unittest.mock import patch

import pytest

from src.config import PipelineConfig, load_config


class TestPipelineConfig:
    def test_default_values(self):
        with patch.dict("os.environ", {}, clear=True):
            config = PipelineConfig()
        assert config.max_rollback_attempts == 3
        assert config.max_discussion_rounds == 2
        assert config.pm_count == 1
        assert config.engineer_count == 1
        assert config.reviewer_count == 1

    def test_custom_values(self):
        env = {
            "MAX_ROLLBACK_ATTEMPTS": "5",
            "MAX_DISCUSSION_ROUNDS": "4",
            "ENGINEER_COUNT": "2",
            "REVIEWER_COUNT": "2",
        }
        with patch.dict("os.environ", env, clear=True):
            config = PipelineConfig()
        assert config.max_rollback_attempts == 5
        assert config.max_discussion_rounds == 4
        assert config.engineer_count == 2
        assert config.reviewer_count == 2

    def test_invalid_engineer_count(self):
        with (
            patch.dict("os.environ", {"ENGINEER_COUNT": "8"}, clear=True),
            pytest.raises(ValueError, match="ENGINEER_COUNT"),
        ):
            PipelineConfig()

    def test_invalid_reviewer_count(self):
        with (
            patch.dict("os.environ", {"REVIEWER_COUNT": "0"}, clear=True),
            pytest.raises(ValueError, match="REVIEWER_COUNT"),
        ):
            PipelineConfig()

    def test_load_config(self):
        with patch.dict("os.environ", {}, clear=True):
            config = load_config()
        assert isinstance(config, PipelineConfig)
