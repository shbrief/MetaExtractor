import pytest

from metaextractor.keys import ApiKeyError, resolve_api_key


def test_literal_key_is_trimmed():
    assert resolve_api_key("  sk-ant-abc\n") == "sk-ant-abc"


def test_env_reference(monkeypatch):
    monkeypatch.setenv("MY_KEY", "sk-from-env")
    assert resolve_api_key("env:MY_KEY") == "sk-from-env"


def test_env_reference_missing(monkeypatch):
    monkeypatch.delenv("NOPE", raising=False)
    with pytest.raises(ApiKeyError):
        resolve_api_key("env:NOPE")


def test_file_reference(tmp_path):
    f = tmp_path / "key"
    f.write_text("sk-from-file\n", encoding="utf-8")
    assert resolve_api_key(f"file:{f}") == "sk-from-file"


def test_file_reference_first_nonempty_line(tmp_path):
    f = tmp_path / "key"
    f.write_text("\n  \nsk-real\nsomething-else\n", encoding="utf-8")
    assert resolve_api_key(f"file:{f}") == "sk-real"


def test_file_reference_missing(tmp_path):
    with pytest.raises(ApiKeyError):
        resolve_api_key(f"file:{tmp_path / 'absent'}")


def test_bare_path_to_existing_file_is_read(tmp_path):
    f = tmp_path / "keyfile"
    f.write_text("sk-ant-real\n", encoding="utf-8")
    # No 'file:' prefix — a bare path to an existing non-key file is read.
    assert resolve_api_key(str(f)) == "sk-ant-real"


def test_literal_key_not_treated_as_path(tmp_path, monkeypatch):
    # A value starting with 'sk-' is always literal, even if a like-named file exists.
    assert resolve_api_key("sk-ant-literal") == "sk-ant-literal"


def test_blank_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anthropic")
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    assert resolve_api_key("") == "sk-anthropic"
    assert resolve_api_key(None) == "sk-anthropic"


def test_no_key_anywhere(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    with pytest.raises(ApiKeyError):
        resolve_api_key(None)
