from __future__ import annotations

from unittest.mock import patch

import pytest

from src.schemas import TalkMessage, TalkResponse
from src.talk import ROLE_DISPLAY_NAMES, TalkAgent


class TestTalkAgent:
    def test_init_with_valid_role(self):
        agent = TalkAgent(role="pm")
        assert agent.role == "pm"
        assert agent.personality is None
        assert agent.tone is None

    def test_init_all_roles(self):
        for role in ROLE_DISPLAY_NAMES:
            agent = TalkAgent(role=role)
            assert agent.role == role

    def test_init_with_personality_and_tone(self):
        agent = TalkAgent(role="pm", personality_id="visionary", tone_id="onee")
        assert agent.personality is not None
        assert agent.personality.id == "visionary"
        assert agent.tone is not None
        assert agent.tone.id == "onee"

    def test_init_invalid_role_raises(self):
        with pytest.raises(ValueError, match="Invalid role"):
            TalkAgent(role="nonexistent")

    def test_system_prompt_includes_talk_prompt(self):
        agent = TalkAgent(role="pm")
        assert "談話室" in agent.system_prompt

    def test_system_prompt_includes_personality(self):
        agent = TalkAgent(role="pm", personality_id="visionary")
        assert "パーソナリティ" in agent.system_prompt
        assert "ビジョナリー" in agent.system_prompt

    def test_system_prompt_includes_tone(self):
        agent = TalkAgent(role="pm", tone_id="onee")
        assert "## 口調" in agent.system_prompt
        assert "おネエ" in agent.system_prompt


class TestChat:
    def test_chat_requires_user_as_last_message(self):
        agent = TalkAgent(role="pm")
        with pytest.raises(ValueError, match="Last message"):
            agent.chat([TalkMessage(role="assistant", content="hi")])

    def test_chat_rejects_empty_messages(self):
        agent = TalkAgent(role="pm")
        with pytest.raises(ValueError, match="Last message"):
            agent.chat([])

    def test_chat_single_message(self):
        agent = TalkAgent(role="pm")
        with patch("src.agents.base.call_llm") as mock_llm:
            mock_llm.return_value = (
                TalkResponse(reply="こんにちは！"),
                {"input_tokens": 10, "output_tokens": 5},
            )
            result, _ = agent.chat([TalkMessage(role="user", content="やあ")])
        assert result.reply == "こんにちは！"
        call_kwargs = mock_llm.call_args.kwargs
        assert call_kwargs["user_message"] == "やあ"

    def test_chat_with_history_includes_context(self):
        agent = TalkAgent(role="engineer")
        history = [
            TalkMessage(role="user", content="こんにちは"),
            TalkMessage(role="assistant", content="こんばんは"),
            TalkMessage(role="user", content="最近どう？"),
        ]
        with patch("src.agents.base.call_llm") as mock_llm:
            mock_llm.return_value = (
                TalkResponse(reply="元気だよ"),
                {"input_tokens": 20, "output_tokens": 5},
            )
            agent.chat(history)
        user_message = mock_llm.call_args.kwargs["user_message"]
        assert "こんにちは" in user_message
        assert "こんばんは" in user_message
        assert "最近どう？" in user_message
