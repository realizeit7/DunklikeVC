"""Screening-policy registry (v2.2): which version is ACTIVE is decided only by a user-confirmed activation row.

* A policy file's own `declared_state` never activates it.
* `activate()` requires the exact sha256 of the file and an explicit user flag. It is exposed as a CLI command for the
  user; agents and LLM stages must not call it. Nothing in the analysis pipeline calls it.
* `state()` returns 'active' only when an activation row matches the version AND the file's current hash. Editing a
  policy file after activation therefore makes it 'proposed' again.
* screening_policy_v1 keeps its legacy route (`ack-policy`); this module governs v1_2 and later.
* `actor='user'` in policy_activations is a PROVENANCE LABEL, not proof of authorization. The CLI therefore also
  requires an interactive terminal and a typed hash prefix (see cli.py). No analysis code imports `activate`.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from .core import Ctx

POLICY_DIR = Path(__file__).parent / "policies"
FILES = {"screening_policy_v1_2": POLICY_DIR / "screening_policy_v1_2_PROPOSED.yaml",
         "screening_policy_v1_3": POLICY_DIR / "screening_policy_v1_3_PROPOSED.yaml"}
# v1_2 is immutable and declares no compatible classifiers. Its v2.2 results predate predicate checks, so even if v1_2
# were activated they never become approval-eligible.
LEGACY_COMPATIBLE = {"screening_policy_v1_2": []}


def compatible_classifiers(version: str) -> list[str]:
    if version in LEGACY_COMPATIBLE:
        return LEGACY_COMPATIBLE[version]
    return list(load(version).get("compatible_classifiers") or [])


def approval_eligible(ctx: Ctx, version: str, policy_sha256: str, classifier: str) -> tuple[bool, str]:
    """An analysis result can support an approval only if (1) the policy version is ACTIVE (user activation row
    matching the current file hash), (2) the analysis was assessed under that same hash, and (3) its classifier is one
    the policy declares compatible. Activating a policy never makes older or incompatible analyses eligible."""
    if version not in FILES:
        return False, f"unknown policy {version}"
    if state(ctx, version) != "active":
        return False, f"{version} is not active (PROPOSED policies cannot be used for approval)"
    if policy_sha256 != sha(version):
        return False, f"analysis assessed under a different {version} hash ({policy_sha256[:12]}...)"
    if classifier not in compatible_classifiers(version):
        return False, f"classifier {classifier} is not compatible with {version}"
    return True, "eligible"


def sha(version: str) -> str:
    return hashlib.sha256(FILES[version].read_bytes()).hexdigest()


def load(version: str) -> dict:
    d = yaml.safe_load(FILES[version].read_text())
    d["_sha256"] = sha(version)
    d["_rules"] = {r["id"]: r for r in d["rules"]}
    return d


def state(ctx: Ctx, version: str) -> str:
    if version not in FILES:
        return "unknown"
    row = ctx.con.execute("SELECT 1 FROM policy_activations WHERE policy_kind='screening' AND policy_version=? AND "
                          "policy_sha256=?", (version, sha(version))).fetchone()
    return "active" if row else "proposed"


def activate(ctx: Ctx, version: str, sha256: str, statement: str, i_am_the_user: bool) -> int:
    if not i_am_the_user:
        raise PermissionError("activation must be performed by the user (--i-am-the-user)")
    if version not in FILES or sha256 != sha(version):
        raise ValueError(f"sha256 does not match the current file for {version} ({sha(version) if version in FILES else 'unknown'})")
    if len(statement.strip()) < 20:
        raise ValueError("write a statement of what you accept (at least 20 characters)")
    cur = ctx.con.execute("INSERT INTO policy_activations(policy_kind, policy_version, policy_sha256, activated_utc, statement, "
                          "actor, user_confirmed) VALUES ('screening',?,?,?,?, 'user', 1)", (version, sha256, ctx.now(), statement))
    ctx.con.commit()
    return cur.lastrowid
