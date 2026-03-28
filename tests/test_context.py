import pytest

from src.context import load_source_context


def test_load_source_context_with_files(tmp_path):
    (tmp_path / "app.py").write_text("print('hello')")
    (tmp_path / "lib.py").write_text("x = 1")

    result = load_source_context(str(tmp_path))

    assert "=== ファイルツリー ===" in result
    assert "app.py" in result
    assert "lib.py" in result
    assert "print('hello')" in result


def test_load_source_context_skips_hidden_dirs(tmp_path):
    hidden = tmp_path / ".git"
    hidden.mkdir()
    (hidden / "config").write_text("secret")
    (tmp_path / "main.py").write_text("pass")

    result = load_source_context(str(tmp_path))

    assert "config" not in result
    assert "main.py" in result


def test_load_source_context_skips_non_source_files(tmp_path):
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    (tmp_path / "app.py").write_text("pass")

    result = load_source_context(str(tmp_path))

    assert "image.png" not in result
    assert "app.py" in result


def test_load_source_context_invalid_path():
    with pytest.raises(ValueError, match="ディレクトリではありません"):
        load_source_context("/nonexistent/path")


def test_load_source_context_empty_dir(tmp_path):
    result = load_source_context(str(tmp_path))
    assert "=== ファイルツリー ===" in result
