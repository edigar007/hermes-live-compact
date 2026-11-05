"""Where backups live, and the one-time move out of the plugin directory.

`hermes plugins update` runs a security scan over the installed plugin tree. Session
transcripts stored inside that tree (1.9 MB, all of `shadow/`) produced 80 findings and the
update was BLOCKED — the engine's own backups were blocking its own upgrade. Backups are
user data, so they now live under `$HERMES_HOME/compaction-spine/`, and anything written by
<=0.3.1 is moved there on first load.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STUB = Path(__file__).resolve().parent / "_hermes_stub"


def _ensure_hermes() -> None:
    try:
        import agent  # noqa: F401
        root = Path(agent.__file__).resolve().parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
    except Exception:
        if str(STUB) not in sys.path:
            sys.path.insert(0, str(STUB))


def _load_engine(plugin_dir: Path):
    """Execute a copy of the entry file as if it were installed at ``plugin_dir``."""
    _ensure_hermes()
    plugin_dir.mkdir(parents=True, exist_ok=True)
    entry = plugin_dir / "__init__.py"
    entry.write_bytes((ROOT / "__init__.py").read_bytes())
    module = types.ModuleType("live_compact_shadow_home")
    module.__file__ = str(entry)
    exec(compile(entry.read_text(encoding="utf-8"), str(entry), "exec"), module.__dict__)
    return module


@pytest.fixture()
def installed(tmp_path, monkeypatch):
    """A plugin installed at a realistic path: <home>/plugins/live_compact."""
    monkeypatch.delenv("LC_SHADOW_DIR", raising=False)
    monkeypatch.delenv("HERMES_DIR", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    plugin_dir = tmp_path / "home" / "plugins" / "live_compact"
    return _load_engine(plugin_dir), plugin_dir


def test_default_lives_under_hermes_home_not_the_plugin_dir(installed):
    module, plugin_dir = installed
    root = module.SHADOW_DIR
    assert root == plugin_dir.parent.parent / "compaction-spine" / "shadow"
    assert plugin_dir not in root.parents, "backups inside the plugin dir block updates"
    assert module.LOG_PATH.parent == root.parent, "runtime files stay out of the code dir"


def test_falls_back_to_the_plugins_parent_when_hermes_home_is_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("LC_SHADOW_DIR", raising=False)
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("HERMES_DIR", raising=False)
    plugin_dir = tmp_path / "home" / "plugins" / "live_compact"
    module = _load_engine(plugin_dir)
    assert module.SHADOW_DIR == tmp_path / "home" / "compaction-spine" / "shadow"


def test_config_shadow_dir_wins_over_the_default(installed):
    module, plugin_dir = installed
    custom = plugin_dir.parent.parent.parent / "custom-shadow"
    (plugin_dir / "config.json").write_text(
        '{"shadow_dir": "%s"}' % str(custom).replace("\\", "\\\\"), encoding="utf-8")
    reloaded = _load_engine(plugin_dir)
    assert reloaded.SHADOW_DIR == custom.resolve()


def test_env_override_wins_over_config(installed, monkeypatch):
    module, plugin_dir = installed
    (plugin_dir / "config.json").write_text('{"shadow_dir": "from-config"}', encoding="utf-8")
    monkeypatch.setenv("LC_SHADOW_DIR", str(plugin_dir.parent.parent / "env-shadow"))
    reloaded = _load_engine(plugin_dir)
    assert reloaded.SHADOW_DIR == (plugin_dir.parent.parent / "env-shadow").resolve()


def test_migration_moves_session_dirs_and_loose_files(tmp_path, lc):
    legacy = tmp_path / "plugin" / "shadow"
    target = tmp_path / "home" / "compaction-spine" / "shadow"
    (legacy / "sess-A").mkdir(parents=True)
    (legacy / "sess-A" / "lcdeadbeef.txt").write_text("原文一", encoding="utf-8")
    (legacy / "sess-A" / "raw-0123abcd.txt").write_text("工具输出", encoding="utf-8")
    (legacy / "lclegacy00001.txt").write_text("旧版顶层文件", encoding="utf-8")

    counts = lc.migrate_legacy_shadow(target=target, legacy=legacy)

    assert counts["moved"] == 3
    assert (target / "sess-A" / "lcdeadbeef.txt").read_text(encoding="utf-8") == "原文一"
    assert (target / "lclegacy00001.txt").read_text(encoding="utf-8") == "旧版顶层文件"
    assert not legacy.exists(), "the plugin dir must end up clean or the scan still fires"


def test_migration_dedupes_identical_and_never_overwrites_different(tmp_path, lc):
    legacy = tmp_path / "plugin" / "shadow"
    target = tmp_path / "home" / "compaction-spine" / "shadow"
    (legacy / "s").mkdir(parents=True)
    (target / "s").mkdir(parents=True)
    (legacy / "s" / "same.txt").write_text("同", encoding="utf-8")
    (target / "s" / "same.txt").write_text("同", encoding="utf-8")
    (legacy / "s" / "diff.txt").write_text("旧内容", encoding="utf-8")
    (target / "s" / "diff.txt").write_text("新内容", encoding="utf-8")

    counts = lc.migrate_legacy_shadow(target=target, legacy=legacy)

    assert counts["deduped"] == 1
    assert counts["kept"] >= 1, counts
    assert (target / "s" / "diff.txt").read_text(encoding="utf-8") == "新内容"
    assert (legacy / "s" / "diff.txt").is_file(), "a file we refuse to move must stay readable"


def test_migration_is_a_noop_without_a_legacy_dir(tmp_path, lc):
    target = tmp_path / "home" / "compaction-spine" / "shadow"
    counts = lc.migrate_legacy_shadow(target=target, legacy=tmp_path / "missing")
    assert counts == {"moved": 0, "deduped": 0, "kept": 0, "dirs": 0}
    assert not target.exists()


def test_migration_does_nothing_when_target_is_the_legacy_dir(tmp_path, lc):
    legacy = tmp_path / "shadow"
    (legacy / "s").mkdir(parents=True)
    (legacy / "s" / "a.txt").write_text("a", encoding="utf-8")
    counts = lc.migrate_legacy_shadow(target=legacy, legacy=legacy)
    assert counts["moved"] == 0
    assert (legacy / "s" / "a.txt").is_file()


def test_migration_also_rescues_the_old_debug_log(tmp_path, lc):
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "debug.jsonl").write_text('{"kind": "select"}\n', encoding="utf-8")
    target = tmp_path / "home" / "compaction-spine" / "shadow"

    counts = lc.migrate_legacy_shadow(target=target, legacy=plugin / "shadow")

    assert counts["moved"] == 1
    assert (target.parent / "debug.legacy.jsonl").is_file()
    assert not (plugin / "debug.jsonl").exists(), "the debug log is a scan finding too"


def test_cards_name_a_path_under_the_configured_shadow_dir(tmp_path, lc_nokeep):
    import _helpers as H

    lc_nokeep.SHADOW_DIR = tmp_path / "home" / "compaction-spine" / "shadow"
    projected, stats = lc_nokeep.project(H.conversation([H.BIG, H.BIG]), session="sess-A", seq=1)
    assert stats["cuts"] >= 1, stats["skips"]
    cards = [m for m in projected if "压缩摘录" in str(m.get("content"))]
    assert cards, "no card in the projection"
    for card in cards:
        assert str(lc_nokeep.SHADOW_DIR) in card["content"], "card points at the old location"
    assert (lc_nokeep.SHADOW_DIR / "sess-A").is_dir()
    assert not (lc_nokeep.PLUGIN_DIR / "shadow" / "sess-A").exists()
