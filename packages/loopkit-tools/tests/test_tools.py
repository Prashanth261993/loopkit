"""Tests for loopkit-tools: read tools really work; destructive tools obey the
LoopKit registry's dry-run / allow-list safety gate."""

from __future__ import annotations

from pathlib import Path

from loopkit import ToolRegistry
from loopkit_tools import ALL_FACTORIES, fs, register_all


def test_register_all_registers_every_family() -> None:
    reg = ToolRegistry(allow_writes=None)
    register_all(reg)
    names = {t["name"] for t in reg.specs()}
    assert names == {
        "fs.read",
        "fs.list",
        "fs.write",
        "proc.run",
        "git.status",
        "git.diff",
        "git.commit",
        "git.apply",
        "http.get",
    }
    assert len(ALL_FACTORIES) == len(names)


def test_read_and_list_are_real(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    reg = ToolRegistry(allow_writes=None)
    register_all(reg)

    r = reg.execute("fs.read", {"path": str(tmp_path / "a.txt")})
    assert r.ok and not r.dry_run and r.output == "hello"

    r = reg.execute("fs.list", {"path": str(tmp_path)})
    assert r.ok and r.output == ["a.txt"]


def test_write_is_dry_run_unless_allow_listed(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"

    gated = ToolRegistry(allow_writes=None)
    gated.register(fs.write_file())
    r = gated.execute("fs.write", {"path": str(target), "content": "x"})
    assert r.ok and r.dry_run
    assert not target.exists(), "dry-run must not touch the filesystem"

    allowed = ToolRegistry(allow_writes=["fs.write"])
    allowed.register(fs.write_file())
    r = allowed.execute("fs.write", {"path": str(target), "content": "x"})
    assert r.ok and not r.dry_run
    assert target.read_text(encoding="utf-8") == "x"


def test_destructive_tools_are_flagged_in_safety_config() -> None:
    reg = ToolRegistry(allow_writes=["fs.write"])
    register_all(reg)
    cfg = reg.safety_config()
    assert set(cfg["destructive_tools"]) == {
        "fs.write",
        "proc.run",
        "git.commit",
        "git.apply",
    }
    assert cfg["allow_writes"] == ["fs.write"]


def test_proc_run_dry_runs_without_allow_list() -> None:
    reg = ToolRegistry(allow_writes=None)
    register_all(reg)
    r = reg.execute("proc.run", {"cmd": ["echo", "hi"]})
    assert r.ok and r.dry_run
    assert "would execute" in r.output
