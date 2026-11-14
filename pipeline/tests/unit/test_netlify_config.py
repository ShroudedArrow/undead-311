"""Hosting config checks (REQ-OPS-HOST.1 to .4): netlify.toml and docs/DEPLOY.md.

The build must run in Netlify's image (Node and make, no uv), publish web/dist, build previews, carry no secret and not
repeat the headers the web build generates. DEPLOY.md must give the human steps and the secret-name mapping.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TOML = REPO / "netlify.toml"
DEPLOY = REPO / "docs" / "DEPLOY.md"


def config() -> dict:
    return tomllib.loads(TOML.read_text())


def make_recipe(target: str) -> str:
    """The recipe lines of a Makefile target."""
    lines = (REPO / "Makefile").read_text().splitlines()
    start = lines.index(f"{target}:")
    body = []
    for line in lines[start + 1:]:
        if not line.startswith("\t"):
            break
        body.append(line)
    return "\n".join(body)


def test_build_publishes_web_dist_with_make_build():
    """REQ-OPS-HOST.1: static files from web/dist, built by `make build`."""
    build = config()["build"]
    assert build["publish"] == "web/dist"
    assert "make build" in build["command"]


def test_build_command_needs_no_uv_or_python():
    """REQ-OPS-HOST.1, design.md Netlify step 2: the build image has no uv, so the command and `make build` are web-only."""
    cmd = config()["build"]["command"]
    assert "uv" not in re.findall(r"\w+", cmd)
    assert "python" not in cmd
    recipe = make_recipe("build")
    assert "uv" not in re.findall(r"\w+", recipe) and "python" not in recipe
    assert "npm" in recipe


def test_dependencies_install_from_web_before_the_build():
    """REQ-OPS-HOST.1: package.json is in web/, so the command installs there (Netlify only installs at the base)."""
    cmd = config()["build"]["command"]
    assert cmd.index("web ci") < cmd.index("make build")
    assert (REPO / "web" / "package-lock.json").exists()


def test_every_context_builds_the_same_way_and_previews_are_configured():
    """REQ-OPS-HOST.2: production and deploy previews use the same build command."""
    cfg = config()
    assert cfg["context"]["deploy-preview"]["command"] == cfg["build"]["command"]
    assert cfg["context"]["production"]["command"] == cfg["build"]["command"]


def test_headers_come_from_the_web_build_not_the_toml():
    """REQ-OPS-HOST.3: one source of truth (the `_headers` file the web build writes)."""
    assert "headers" not in config()


def test_toml_holds_no_secret_or_token():
    """REQ-OPS-HOST.4: no secret in the repo."""
    text = TOML.read_text()
    assert not re.search(r"(?i)(token|secret|password|api[_-]?key)\s*=", text)
    assert "NETLIFY_AUTH_TOKEN" not in text


def test_node_comes_from_nvmrc():
    """REQ-OPS-HOST.1: Netlify reads .nvmrc at the repo root, so no NODE_VERSION override can disagree with it."""
    assert (REPO / ".nvmrc").read_text().strip()
    assert "NODE_VERSION" not in TOML.read_text()


def test_deploy_guide_gives_the_human_steps():
    """REQ-OPS-HOST.4: click-by-click steps, secret names, production branch, previews, no paid plan."""
    text = DEPLOY.read_text()
    for needle in ("NETLIFY_AUTH_TOKEN", "NETLIFY_SITE_ID", "CHANNEL_TOKEN", "GITHUB_CHANNEL_TOKEN",
                   "Production branch", "Deploy Previews", "Branch deploys", "Free",
                   "ShroudedArrow/undead-311-data", "ShroudedArrow/undead-311-ops", "README.md"):
        assert needle in text, needle
    assert "secrets.CHANNEL_TOKEN" in text
    assert "main" in text


def test_deploy_guide_has_no_real_secret_values_and_balanced_markup():
    """REQ-OPS-HOST.4: no token-shaped strings, and no stray markdown markers (a typo found in review)."""
    text = DEPLOY.read_text()
    assert not re.search(r"\b(ghp_|github_pat_|nfp_)[A-Za-z0-9_]{10,}", text)
    assert text.count("`") % 2 == 0
    assert "**" not in re.sub(r"\*\*[^*\n]+\*\*", "", text)
