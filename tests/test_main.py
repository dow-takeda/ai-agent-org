from __future__ import annotations

from unittest.mock import patch

import pytest

from src.main import main


@pytest.fixture
def source_dir(tmp_path):
    """Create a minimal source directory for --source."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "dummy.py").write_text("# dummy", encoding="utf-8")
    return str(src)


class TestRequestOption:
    def test_request_string(self, source_dir):
        with patch("src.pipeline.run_pipeline") as mock_pipeline:
            with patch(
                "sys.argv",
                ["prog", "--request", "テスト要求", "--source", source_dir],
            ):
                main()
            mock_pipeline.assert_called_once()
            assert mock_pipeline.call_args.kwargs["request"] == "テスト要求"

    def test_request_file(self, tmp_path, source_dir):
        req_file = tmp_path / "request.md"
        req_file.write_text("ファイルからの要求", encoding="utf-8")

        with patch("src.pipeline.run_pipeline") as mock_pipeline:
            with patch(
                "sys.argv",
                ["prog", "--request-file", str(req_file), "--source", source_dir],
            ):
                main()
            mock_pipeline.assert_called_once()
            assert mock_pipeline.call_args.kwargs["request"] == "ファイルからの要求"

    def test_request_directory(self, tmp_path, source_dir):
        req_dir = tmp_path / "requests"
        req_dir.mkdir()
        (req_dir / "01_overview.md").write_text("概要", encoding="utf-8")
        (req_dir / "02_details.md").write_text("詳細", encoding="utf-8")

        with patch("src.pipeline.run_pipeline") as mock_pipeline:
            with patch(
                "sys.argv",
                ["prog", "--request-file", str(req_dir), "--source", source_dir],
            ):
                main()
            mock_pipeline.assert_called_once()
            request_text = mock_pipeline.call_args.kwargs["request"]
            assert "# 01_overview.md\n概要" in request_text
            assert "# 02_details.md\n詳細" in request_text

    def test_both_options_error(self, tmp_path, source_dir):
        req_file = tmp_path / "request.md"
        req_file.write_text("要求", encoding="utf-8")

        with patch(
            "sys.argv",
            [
                "prog",
                "--request", "テスト",
                "--request-file", str(req_file),
                "--source", source_dir,
            ],
        ), pytest.raises(SystemExit, match="2"):
            main()

    def test_neither_option_error(self, source_dir):
        with patch("sys.argv", ["prog", "--source", source_dir]), pytest.raises(
            SystemExit, match="2"
        ):
            main()

    def test_nonexistent_file_error(self, source_dir):
        with patch(
            "sys.argv",
            ["prog", "--request-file", "/nonexistent/path.md", "--source", source_dir],
        ), pytest.raises(SystemExit, match="2"):
            main()

    def test_empty_directory_error(self, tmp_path, source_dir):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        with patch(
            "sys.argv",
            ["prog", "--request-file", str(empty_dir), "--source", source_dir],
        ), pytest.raises(SystemExit, match="2"):
            main()
