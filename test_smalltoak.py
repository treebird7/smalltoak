#!/usr/bin/env python3
"""Test suite for smalltoak. More passing tests = better code."""

import json
import os
import subprocess
import sys
import tempfile

PASS_COUNT = 0
FAIL_COUNT = 0


def test(name, condition, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        print(f"  PASS: {name}")
        PASS_COUNT += 1
    else:
        print(f"  FAIL: {name} {detail}")
        FAIL_COUNT += 1


def run(args: list[str], env: dict | None = None) -> tuple[int, str, str]:
    """Run smalltoak.py with args, return (exitcode, stdout, stderr)."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    r = subprocess.run(
        [sys.executable, "smalltoak.py"] + args,
        capture_output=True, text=True, env=full_env, timeout=10,
    )
    return r.returncode, r.stdout, r.stderr


def main():
    global PASS_COUNT, FAIL_COUNT

    # Use a temp store for each test run
    store = tempfile.mktemp(suffix=".jsonl")
    env = {"SMALLTOAK_STORE": store}

    print("=== smalltoak test suite ===\n")

    # ── Basic functionality ──────────────────────────────────────────────

    print("[basic]")

    # Post a message
    code, out, err = run(["post", "hello world", "--from", "alice"], env)
    test("post returns 0", code == 0)
    test("post prints message id", "#" in out and "sent" in out)

    # Post another
    code, out, err = run(["post", "reply", "--from", "bob", "--to", "alice"], env)
    test("post with --to returns 0", code == 0)
    test("second message gets incremented id", "#" in out and "sent" in out)

    # Read all
    code, out, err = run(["read"], env)
    test("read returns 0", code == 0)
    test("read shows message 1", "hello world" in out)
    test("read shows message 2", "reply" in out)
    test("read shows sender", "alice" in out and "bob" in out)
    test("read shows arrow for directed msg", "→" in out or "->" in out)

    # ── Filtering ────────────────────────────────────────────────────────

    print("\n[filtering]")

    # Post a few more
    run(["post", "broadcast", "--from", "birdsan"], env)
    run(["post", "dm to bob", "--from", "watsan", "--to", "bob"], env)

    # Filter by recipient
    code, out, err = run(["read", "--to", "bob"], env)
    test("--to filters correctly", "dm to bob" in out)
    test("--to includes broadcasts", "broadcast" in out or "hello" in out)

    # Filter by sender
    code, out, err = run(["read", "--from", "watsan"], env)
    test("--from filters correctly", "dm to bob" in out)
    test("--from excludes others", "hello world" not in out)

    # Last N
    code, out, err = run(["read", "--last", "2"], env)
    test("--last 2 returns 2 messages", out.count("#") == 2, f"got {out.count('#')}")

    # ── Edge cases ───────────────────────────────────────────────────────

    print("\n[edge cases]")

    # Empty store
    empty_store = tempfile.mktemp(suffix=".jsonl")
    code, out, err = run(["read"], {"SMALLTOAK_STORE": empty_store})
    test("empty store shows no messages", "no messages" in out.lower() or out.strip() == "")

    # Help / no args
    code, out, err = run([], env)
    test("no args shows help", "usage" in out.lower() or "smalltoak" in out.lower() or code == 0)

    # Unknown command
    code, out, err = run(["badcmd"], env)
    test("unknown command exits non-zero", code != 0)

    # Post with SMALLTOAK_AGENT env
    agent_env = {**env, "SMALLTOAK_AGENT": "yosef"}
    code, out, err = run(["post", "from env agent"], agent_env)
    test("SMALLTOAK_AGENT used as default sender", code == 0)
    code, out, err = run(["read", "--last", "1"], env)
    test("env agent appears in messages", "yosef" in out)

    # ── Storage format ───────────────────────────────────────────────────

    print("\n[storage]")

    # Verify JSONL format
    with open(store) as f:
        lines = [l.strip() for l in f if l.strip()]
    test("store is valid JSONL", all(json.loads(l) for l in lines))

    first = json.loads(lines[0])
    test("message has id field", "id" in first)
    test("message has ts field", "ts" in first)
    test("message has from field", "from" in first)
    test("message has text field", "text" in first)
    test("id is integer", isinstance(first["id"], int))
    test("ts is ISO format", "T" in first["ts"])

    # ── Features for improvement loop to target ──────────────────────────

    print("\n[advanced features]")

    # These start as FAIL — the improve loop should add them
    # Search
    code, out, err = run(["search", "hello"], env)
    test("search command exists", code == 0, "(not implemented yet)")

    # Count
    code, out, err = run(["count"], env)
    test("count command exists", code == 0, "(not implemented yet)")

    # Delete
    code, out, err = run(["delete", "--id", "1"], env)
    test("delete command exists", code == 0, "(not implemented yet)")

    # Thread/reply-to
    code, out, err = run(["post", "threaded reply", "--from", "alice", "--reply-to", "1"], env)
    test("--reply-to flag works", code == 0, "(not implemented yet)")

    # Priority
    code, out, err = run(["post", "urgent!", "--from", "alice", "--priority", "high"], env)
    test("--priority flag works", code == 0, "(not implemented yet)")

    # ── Security (Sherlocksan audit #20002) ────────────────────────────

    print("\n[security]")

    # Token auth uses hmac.compare_digest (timing-safe)
    import ast
    source = open("smalltoak.py").read()
    test("uses hmac.compare_digest for token auth",
         "hmac.compare_digest" in source or "compare_digest" in source,
         "(timing attack risk — use hmac.compare_digest instead of ==)")

    # Content-Length cap in HTTP server
    test("caps Content-Length in do_POST",
         "65536" in source or "content_length" in source.lower() and ("max" in source.lower() or "cap" in source.lower() or ">" in source),
         "(unbounded POST body — cap at 64KB)")

    # TLS support via env vars
    test("supports SMALLTOAK_CERT env var for TLS",
         "SMALLTOAK_CERT" in source,
         "(no TLS support — add SMALLTOAK_CERT + SMALLTOAK_KEY)")

    # ── Cleanup ──────────────────────────────────────────────────────────

    os.unlink(store) if os.path.exists(store) else None
    os.unlink(empty_store) if os.path.exists(empty_store) else None

    print(f"\n=== Results: {PASS_COUNT} PASS, {FAIL_COUNT} FAIL ===")


if __name__ == "__main__":
    main()
