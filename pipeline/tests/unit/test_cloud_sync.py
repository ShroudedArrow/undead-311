"""Cloud copies must equal the repo copies on main (scripts/cloud_sync.py, preflight G3)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
import cloud_sync


def make_repo(tmp: Path) -> Path:
    root = tmp / "repo"
    for d in cloud_sync.DIRS:
        (root / ".kiro" / d).mkdir(parents=True)
        (root / ".kiro" / d / "a.txt").write_text(f"{d} a\n")
    run = lambda *a: subprocess.run(["git", *a], cwd=root, check=True, capture_output=True)
    run("init", "-q", "-b", "main")
    run("add", "-A")
    run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x")
    return root


def make_cloud(tmp: Path) -> Path:
    cloud = tmp / "cloud"
    for d in cloud_sync.DIRS:
        (cloud / d).mkdir(parents=True)
        (cloud / d / "a.txt").write_text(f"{d} a\n")
    return cloud


def test_identical_copies_pass(tmp_path):
    root, cloud = make_repo(tmp_path), make_cloud(tmp_path)
    assert not any(cloud_sync.compare(cloud, "main", root).values())


def test_changed_file_fails(tmp_path):
    root, cloud = make_repo(tmp_path), make_cloud(tmp_path)
    (cloud / "steering" / "a.txt").write_text("stale\n")
    assert cloud_sync.compare(cloud, "main", root)["steering"] == [
        "steering/a.txt: differs (repo {}, cloud {})".format(
            cloud_sync.hashlib.sha256(b"steering a\n").hexdigest()[:8],
            cloud_sync.hashlib.sha256(b"stale\n").hexdigest()[:8],
        )
    ]


def test_file_on_one_side_only_fails(tmp_path):
    root, cloud = make_repo(tmp_path), make_cloud(tmp_path)
    (cloud / "agents" / "old.json").write_text("{}")
    (cloud / "hooks" / "a.txt").unlink()
    result = cloud_sync.compare(cloud, "main", root)
    assert any("old.json: in the cloud copy, not in the repo" in p for p in result["agents"])
    assert any("a.txt: in the repo, not in the cloud copy" in p for p in result["hooks"])


def test_compares_the_ref_not_the_working_tree(tmp_path):
    root, cloud = make_repo(tmp_path), make_cloud(tmp_path)
    (root / ".kiro" / "workflows" / "a.txt").write_text("uncommitted edit\n")
    assert not any(cloud_sync.compare(cloud, "main", root).values())
    assert cloud_sync.compare(cloud, None, root)["workflows"]


def test_cli_exit_codes(tmp_path, monkeypatch, capsys):
    """Exit codes of cloud_sync.main, independent of the sandbox: no real cloud-cache folder is ever read.

    The default cache folders and CLOUD_CONFIG_DIR are cleared, so only temporary folders under tmp_path can be found.
    """
    monkeypatch.setattr(cloud_sync, "CLOUD_CANDIDATES", ())
    monkeypatch.delenv("CLOUD_CONFIG_DIR", raising=False)
    cloud = make_cloud(tmp_path)

    assert cloud_sync.main(["--cloud", str(tmp_path / "none")]) == 2  # no cache found
    assert "cloud-cache folder not found" in capsys.readouterr().out

    monkeypatch.setenv("CLOUD_CONFIG_DIR", str(cloud))  # the env var is found too
    assert cloud_sync.find_cloud_dir() == cloud
    monkeypatch.delenv("CLOUD_CONFIG_DIR")

    (cloud / "hooks" / "a.txt").write_text("changed\n")
    assert cloud_sync.main(["--cloud", str(cloud), "--working-tree"]) == 1
    assert "RE-SYNC NEEDED" in capsys.readouterr().out
