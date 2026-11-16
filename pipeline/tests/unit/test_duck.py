"""DuckDB connection settings (REQ-OPS-DUCK.1-3): memory share, threads, spill folder, cap, overrides, every call site."""

from __future__ import annotations

import re
from pathlib import Path

import duckdb
import pytest
from helpers import examples
from hypothesis import given, settings
from hypothesis import strategies as st

from undead311 import duck

PIPELINE = Path(__file__).resolve().parents[2]


def read(con, *names):
    q = ",".join("?" for _ in names)
    return dict(con.execute(f"select name, value from duckdb_settings() where name in ({q})", list(names)).fetchall())


def test_req_ops_duck_1_defaults_are_65_percent_of_ram_all_cpus_and_a_20gb_spill_cap(tmp_path):
    """REQ-OPS-DUCK.1."""
    s = duck.settings(env={}, temp_dir=tmp_path / "t", total=10 * 2**30)
    assert s["memory_limit"] == "6656MiB"  # 65% of 10 GiB
    assert s["threads"] == str(duck.cpu_count())
    assert s["temp_directory"] == str(tmp_path / "t")
    assert s["max_temp_directory_size"] == "20GB"


@settings(max_examples=examples(60), deadline=None)
@given(st.integers(min_value=1 << 28, max_value=1 << 46))
def test_req_ops_duck_1_the_memory_share_never_exceeds_65_percent(total):
    """REQ-OPS-DUCK.1: the limit stays under 65% of RAM (rounded down to a whole MiB) and above 0."""
    mib = int(duck.default_memory_limit(total).removesuffix("MiB"))
    assert 1 <= mib <= total * 0.65 / 2**20


def test_req_ops_duck_1_unknown_ram_leaves_duckdbs_own_memory_limit(tmp_path):
    """REQ-OPS-DUCK.1: with no readable RAM size the setting is omitted instead of guessed."""
    assert "memory_limit" not in duck.settings(env={}, temp_dir=tmp_path, total=0)
    assert duck.default_memory_limit(0) is None
    assert duck.default_memory_limit(None) is None


def test_req_ops_duck_2_environment_values_override_the_defaults(tmp_path):
    """REQ-OPS-DUCK.2."""
    env = {
        duck.ENV_MEMORY: "3GB", duck.ENV_THREADS: "3", duck.ENV_TEMP_DIR: str(tmp_path / "spill"), duck.ENV_MAX_TEMP: "5GB",
    }  # fmt: skip
    s = duck.settings(env=env, temp_dir=tmp_path / "ignored", total=64 * 2**30)
    assert s == {"memory_limit": "3GB", "threads": "3", "temp_directory": str(tmp_path / "spill"), "max_temp_directory_size": "5GB"}


def test_req_ops_duck_1_configure_sets_them_on_a_live_connection_and_creates_the_spill_folder(tmp_path):
    """REQ-OPS-DUCK.1: read the values back from DuckDB, in memory and in a file database."""
    env = {duck.ENV_MEMORY: "1GiB", duck.ENV_THREADS: "2", duck.ENV_MAX_TEMP: "4GiB"}
    for target in (":memory:", str(tmp_path / "x.duckdb")):
        spill = tmp_path / f"spill-{abs(hash(target))}"
        con = duckdb.connect(target)
        duck.configure(con, temp_dir=spill, env=env)
        got = read(con, "memory_limit", "threads", "temp_directory", "max_temp_directory_size")
        assert got["memory_limit"] == "1.0 GiB" and got["threads"] == "2"
        assert got["temp_directory"] == str(spill) and spill.is_dir()
        assert got["max_temp_directory_size"] == "4.0 GiB"
        con.close()


def test_req_ops_duck_1_the_spill_folder_defaults_under_data_dir_not_tmp(tmp_path, monkeypatch):
    """REQ-OPS-DUCK.1: `$DATA_DIR/tmp`, never the sandbox's wiped /tmp, and no stderr noise per connection."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for k in (duck.ENV_TEMP_DIR, duck.ENV_MEMORY, duck.ENV_THREADS, duck.ENV_MAX_TEMP):
        monkeypatch.delenv(k, raising=False)
    con = duck.connect()
    assert read(con, "temp_directory")["temp_directory"] == str(tmp_path.resolve() / "tmp")
    assert (tmp_path / "tmp").is_dir()


def test_req_ops_duck_1_a_read_only_connection_is_configured_too(tmp_path):
    """REQ-OPS-DUCK.3: build_sample opens the processed file read-only."""
    db = tmp_path / "ro.duckdb"
    duckdb.connect(str(db)).close()
    con = duck.connect(db, read_only=True, temp_dir=tmp_path / "s")
    assert read(con, "temp_directory")["temp_directory"] == str(tmp_path / "s")


def test_req_ops_duck_1_total_memory_uses_the_smaller_of_meminfo_and_the_cgroup_limit(tmp_path):
    """REQ-OPS-DUCK.1."""
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:       16000000 kB\nMemFree: 1 kB\n")
    cg = tmp_path / "memory.max"
    cg.write_text("max\n")
    assert duck.total_memory_bytes(meminfo, (cg,)) == 16000000 * 1024
    cg.write_text(str(4 * 2**30))
    assert duck.total_memory_bytes(meminfo, (cg,)) == 4 * 2**30
    assert duck.total_memory_bytes(tmp_path / "missing", (tmp_path / "none",)) is None


def test_req_ops_duck_3_no_pipeline_code_opens_duckdb_without_the_helper():
    """REQ-OPS-DUCK.3: every connection in pipeline/undead311 and pipeline/scripts goes through undead311.duck."""
    offenders = []
    for root in (PIPELINE / "undead311", PIPELINE / "scripts"):
        for path in root.rglob("*.py"):
            if path.name == "duck.py":
                continue
            for n, line in enumerate(path.read_text().splitlines(), 1):
                if re.search(r"\bduckdb\.connect\(", line) and not line.lstrip().startswith("#"):
                    offenders.append(f"{path.relative_to(PIPELINE)}:{n}")
    assert offenders == []


def test_req_ops_duck_3_the_atomic_writer_configures_its_connection(tmp_path, monkeypatch):
    """REQ-OPS-DUCK.3: write_duckdb_atomic (the full run's one persistent connection) reads its temp folder from the helper."""
    from undead311.export.writers import write_duckdb_atomic

    monkeypatch.setenv(duck.ENV_TEMP_DIR, str(tmp_path / "spill"))
    seen = {}

    def build(con):
        seen.update(read(con, "temp_directory"))
        con.execute("create table t(x int)")

    write_duckdb_atomic(tmp_path / "out" / "a.duckdb", build)
    assert seen["temp_directory"] == str(tmp_path / "spill")


@pytest.mark.parametrize("name", ["memory_limit", "threads", "temp_directory", "max_temp_directory_size"])
def test_req_ops_duck_1_settings_returns_every_name_but_memory_may_be_absent(name, tmp_path):
    """REQ-OPS-DUCK.1."""
    assert name in duck.settings(env={}, temp_dir=tmp_path, total=2**33)
