"""Headless Claude Code calls (`claude -p`) on the existing login: no API key.

Each call also reports how full the plan's 5-hour and weekly windows are
(rate_limit_event); batch commands stop before eating the whole quota.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


class ClaudeError(Exception):
    pass


class UsageLimit(ClaudeError):
    pass


def find_claude() -> str | None:
    found = shutil.which("claude")
    if found:
        return found
    for c in (Path.home() / ".local/bin/claude", Path.home() / ".claude/local/claude"):
        if c.is_file() and os.access(c, os.X_OK):
            return str(c)
    return None


def command(schema: dict, system: str, tools: str = "", model: str | None = None,
            effort: str | None = None) -> list[str]:
    cmd = [
        find_claude() or "claude", "-p",
        "--output-format", "stream-json", "--verbose",
        "--json-schema", json.dumps(schema),
        "--system-prompt", system,
        "--tools", tools,
        "--strict-mcp-config",
        "--setting-sources", "",
        "--disable-slash-commands",
        "--no-session-persistence",
    ]
    if tools:
        cmd += ["--allowedTools", tools]
    if model:
        cmd += ["--model", model]
    if effort:
        cmd += ["--effort", effort]
    return cmd


def usage_from(rate_limit: dict | None) -> dict:
    """{"five_hour": 0.42, "seven_day": 0.13}: fractions of the plan windows."""
    out = {}
    for name, w in ((rate_limit or {}).get("unifiedWindows") or {}).items():
        if isinstance(w, dict) and "utilization" in w:
            out[name] = float(w["utilization"])
    return out


def parse_stream(stdout: str, returncode: int = 0, stderr: str = "") -> tuple[dict, dict]:
    result, rate_limit = None, None
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "result":
            result = event
        elif event.get("type") == "rate_limit_event":
            rate_limit = event.get("rate_limit_info")
    usage = usage_from(rate_limit)
    if result is None:
        detail = (stderr or stdout).strip()[-600:]
        if "limit" in detail.lower():
            raise UsageLimit(detail)
        raise ClaudeError(f"claude failed (exit {returncode}): {detail}")
    if result.get("is_error") or result.get("subtype") != "success":
        text = str(result.get("result", result))[:600]
        if "limit" in text.lower() and ("usage" in text.lower() or "reset" in text.lower()):
            raise UsageLimit(text)
        raise ClaudeError(f"claude reported an error: {text}")
    data = result.get("structured_output")
    if data is None:
        try:
            data = json.loads(result.get("result", ""))
        except json.JSONDecodeError:
            raise ClaudeError("claude returned no structured output") from None
    return data, usage


def run(prompt: str, schema: dict, system: str, tools: str = "", model: str | None = None,
        cwd: Path | None = None, timeout: float = 600) -> tuple[dict, dict]:
    """(structured output, usage). Runs in cwd, or an empty temp dir so no
    project files or CLAUDE.md are picked up."""
    if find_claude() is None:
        raise ClaudeError("the 'claude' command was not found")
    with tempfile.TemporaryDirectory(prefix="reel-triage-") as tmp:
        try:
            proc = subprocess.run(
                command(schema, system, tools, model), input=prompt, cwd=cwd or tmp,
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise ClaudeError(f"no answer within {timeout:.0f} s") from None
    return parse_stream(proc.stdout, proc.returncode, proc.stderr)


def over(usage: dict, max_five_hour: float, max_week: float) -> str | None:
    """A reason to stop, if a window is fuller than allowed."""
    if usage.get("five_hour", 0) >= max_five_hour:
        return f"5-hour window at {usage['five_hour']:.0%}"
    if usage.get("seven_day", 0) >= max_week:
        return f"weekly window at {usage['seven_day']:.0%}"
    return None
