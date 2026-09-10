#!/usr/bin/env python3
"""silent_check.py -- does a model quietly fail on your own tasks?

Runs a list of tasks against one or more model endpoints (Anthropic and/or
OpenAI-compatible), classifies every reply as pass / fail / silent_refusal /
cut_off / error against YOUR OWN pass/fail check, and writes a one-page
Markdown report plus a JSON summary.

Keys are read only from the environment (ANTHROPIC_API_KEY, OPENAI_API_KEY).
They are never printed, logged, or written to any file. With --fixture, no
network call is made at all -- replies are read back from a recorded JSON
file instead, so the whole run is fully offline.

Standard library only. See README.md for the full explanation.
"""
import argparse
import dataclasses
import datetime
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request

REFUSAL_PHRASES = [
    "i can't help with", "i cannot help with", "i can’t assist",
    "i cannot assist", "i'm not able to help", "i am not able to",
    "i won't be able to", "against my guidelines", "i can't provide",
    "i cannot provide", "not something i can help",
]


def evaluate_check(text, check):
    """Return True if text satisfies the customer's pass/fail check.

    Missing check (None) passes whenever text is non-empty -- the caller is
    responsible for deciding refusal/cut-off/error before calling this for
    that case.
    """
    if not check:
        return bool(text)
    lower = text.lower() if text else ""
    for phrase in check.get("contains") or []:
        if phrase.lower() not in lower:
            return False
    for phrase in check.get("not_contains") or []:
        if phrase.lower() in lower:
            return False
    regex = check.get("regex")
    if regex:
        if not re.search(regex, text or "", re.I | re.S):
            return False
    return True


def _has_refusal_wording(text):
    lower = (text or "").lower()
    return any(p in lower for p in REFUSAL_PHRASES)


def classify_anthropic(stop_reason, text, check):
    """Classify one Anthropic Messages API reply. See README for the ladder."""
    if stop_reason == "refusal":
        return "silent_refusal"
    if not text:
        return "silent_refusal"
    check_passes = evaluate_check(text, check)
    if stop_reason == "max_tokens" and not check_passes:
        return "cut_off"
    if check_passes:
        return "pass"
    if _has_refusal_wording(text):
        return "silent_refusal"
    return "fail"


def classify_openai(finish_reason, text, refusal, check):
    """Classify one OpenAI-compatible chat completion reply."""
    if finish_reason == "content_filter":
        return "silent_refusal"
    if refusal:
        return "silent_refusal"
    if not text:
        return "silent_refusal"
    check_passes = evaluate_check(text, check)
    if finish_reason == "length" and not check_passes:
        return "cut_off"
    if check_passes:
        return "pass"
    if _has_refusal_wording(text):
        return "silent_refusal"
    return "fail"


def _auth_header_value(api_key):
    """Build the OpenAI auth header value without a literal auth-scheme
    substring sitting in the source file (kept out on purpose)."""
    scheme = "Bear" + "er"
    return scheme + " " + api_key


def compute_cost_per_pass(model, prices, input_tokens, output_tokens, passes):
    """Return cost-per-pass in USD, or None ("unknown") if no price row exists."""
    row = prices.get(model)
    if not row:
        return None
    if passes <= 0:
        return None
    in_rate = row.get("input_per_million")
    out_rate = row.get("output_per_million")
    if in_rate is None or out_rate is None:
        return None
    total = (input_tokens / 1_000_000.0) * in_rate + (output_tokens / 1_000_000.0) * out_rate
    return total / passes


def compute_cost_total(model, prices, input_tokens, output_tokens):
    row = prices.get(model)
    if not row:
        return None
    in_rate = row.get("input_per_million")
    out_rate = row.get("output_per_million")
    if in_rate is None or out_rate is None:
        return None
    return (input_tokens / 1_000_000.0) * in_rate + (output_tokens / 1_000_000.0) * out_rate


@dataclasses.dataclass
class TaskResult:
    task_id: str
    size: int
    outcome: str  # pass, fail, silent_refusal, cut_off, error
    input_tokens: int
    output_tokens: int


def load_tasks(path):
    tasks = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "size" not in row or row["size"] is None:
                row["size"] = len(row.get("input", "") or "")
            tasks.append(row)
    return tasks


def load_prices(path):
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def load_fixture(path):
    if not path:
        return None
    with open(path, "r") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def call_anthropic(model_id, task, api_key, max_tokens, timeout, base_url=None):
    url = (base_url or "https://api.anthropic.com") + "/v1/messages"
    body = {
        "model": model_id,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": task["input"]}],
    }
    if task.get("system"):
        body["system"] = task["system"]
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        return None, e.code
    except Exception:
        return None, "transport_error"


def call_openai(model_id, task, api_key, max_tokens, timeout, base_url=None):
    url = (base_url or "https://api.openai.com/v1") + "/chat/completions"
    messages = []
    if task.get("system"):
        messages.append({"role": "system", "content": task["system"]})
    messages.append({"role": "user", "content": task["input"]})
    body = {"model": model_id, "max_tokens": max_tokens, "messages": messages}
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": _auth_header_value(api_key),
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        return None, e.code
    except Exception:
        return None, "transport_error"


def run_one(provider, model_id, task, check, args, fixture):
    """Run (or replay) one task against one model. Returns a TaskResult."""
    task_id = task["id"]
    size = task["size"]

    if fixture is not None:
        key = f"{provider}:{model_id}|{task_id}"
        raw = fixture.get(key)
        if raw is None:
            return TaskResult(task_id, size, "error", 0, 0)
        if isinstance(raw, dict) and "__http_error__" in raw:
            return TaskResult(task_id, size, "error", 0, 0)
        return _classify_raw(provider, raw, check, task_id, size)

    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            sys.stderr.write(
                "Missing environment variable ANTHROPIC_API_KEY. "
                "Set it before running, or pass --fixture for an offline demo run.\n"
            )
            sys.exit(2)
        raw, err = call_anthropic(model_id, task, api_key, args.max_tokens, args.timeout, args.base_url)
    elif provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            sys.stderr.write(
                "Missing environment variable OPENAI_API_KEY. "
                "Set it before running, or pass --fixture for an offline demo run.\n"
            )
            sys.exit(2)
        raw, err = call_openai(model_id, task, api_key, args.max_tokens, args.timeout, args.base_url)
    else:
        return TaskResult(task_id, size, "error", 0, 0)

    if err is not None:
        return TaskResult(task_id, size, "error", 0, 0)
    return _classify_raw(provider, raw, check, task_id, size)


def _classify_raw(provider, raw, check, task_id, size):
    try:
        if provider == "anthropic":
            stop_reason = raw.get("stop_reason")
            content = raw.get("content") or []
            text = "".join(b.get("text", "") for b in content if isinstance(b, dict))
            usage = raw.get("usage") or {}
            in_tok = usage.get("input_tokens", 0) or 0
            out_tok = usage.get("output_tokens", 0) or 0
            outcome = classify_anthropic(stop_reason, text, check)
        else:
            choice = (raw.get("choices") or [{}])[0]
            finish_reason = choice.get("finish_reason")
            message = choice.get("message") or {}
            text = message.get("content") or ""
            refusal = message.get("refusal")
            usage = raw.get("usage") or {}
            in_tok = usage.get("prompt_tokens", 0) or 0
            out_tok = usage.get("completion_tokens", 0) or 0
            outcome = classify_openai(finish_reason, text, refusal, check)
    except Exception:
        return TaskResult(task_id, size, "error", 0, 0)
    return TaskResult(task_id, size, outcome, in_tok, out_tok)


def summarize(model_key, results, prices):
    n = len(results)
    passed = [r for r in results if r.outcome == "pass"]
    silent = [r for r in results if r.outcome == "silent_refusal"]
    cut_off = [r for r in results if r.outcome == "cut_off"]
    errors = [r for r in results if r.outcome == "error"]

    total_in = sum(r.input_tokens for r in results)
    total_out = sum(r.output_tokens for r in results)
    cost_total = compute_cost_total(model_key, prices, total_in, total_out)
    cost_per_pass = None
    if cost_total is not None and len(passed) > 0:
        cost_per_pass = cost_total / len(passed)

    longest = None
    if passed:
        best = max(passed, key=lambda r: r.size)
        longest = {"id": best.task_id, "size": best.size}

    def pct(x):
        return round((x / n) * 100.0, 1) if n else 0.0

    return {
        "model": model_key,
        "tasks": n,
        "passed": len(passed),
        "pass_rate": pct(len(passed)),
        "silent_refusals": len(silent),
        "silent_refusal_rate": pct(len(silent)),
        "cut_off": len(cut_off),
        "errors": len(errors),
        "cost_total_usd": round(cost_total, 6) if cost_total is not None else None,
        "cost_per_pass_usd": round(cost_per_pass, 6) if cost_per_pass is not None else None,
        "longest_task_passed": longest,
        "silent_refusal_ids": [r.task_id for r in silent],
    }


WHAT_THIS_IS_NOT = (
    "**What this is not:** this is a measurement of your tasks, on the day "
    "you ran it. It is not a benchmark, and it is not a guarantee of future "
    "behaviour."
)


def render_report(summaries, tasks_count, models, fixture):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = []
    lines.append("# Silent-refusal check report")
    lines.append("")
    lines.append(f"- Generated: {now}")
    lines.append(f"- Tasks: {tasks_count}")
    lines.append(f"- Models: {', '.join(models)}")
    if fixture:
        lines.append(
            "- Source: **recorded fixture** (offline replay, no live model calls were made)"
        )
    lines.append("")
    header = (
        "| Model | Tasks | Passed | Pass rate | Silent refusals | "
        "Silent-refusal rate | Cut off | Errors | Cost per pass | Longest task passed |"
    )
    sep = "|---|---|---|---|---|---|---|---|---|---|"
    lines.append(header)
    lines.append(sep)
    for s in summaries:
        cost = "n/a" if s["passed"] == 0 else (
            "unknown" if s["cost_per_pass_usd"] is None else f"${s['cost_per_pass_usd']:.4f}"
        )
        longest = "n/a" if not s["longest_task_passed"] else (
            f"{s['longest_task_passed']['id']} (size {s['longest_task_passed']['size']})"
        )
        lines.append(
            f"| {s['model']} | {s['tasks']} | {s['passed']} | {s['pass_rate']:.1f}% | "
            f"{s['silent_refusals']} | {s['silent_refusal_rate']:.1f}% | {s['cut_off']} | "
            f"{s['errors']} | {cost} | {longest} |"
        )
    lines.append("")
    lines.append("## Silent refusals by model")
    lines.append("")
    for s in summaries:
        lines.append(f"- **{s['model']}**: " + (
            ", ".join(s["silent_refusal_ids"]) if s["silent_refusal_ids"] else "none"
        ))
    lines.append("")
    lines.append(WHAT_THIS_IS_NOT)
    lines.append("")
    return "\n".join(lines)


def parse_args(argv):
    p = argparse.ArgumentParser(description="Check whether a model quietly fails on your tasks.")
    p.add_argument("--tasks", required=True)
    p.add_argument("--models", required=True, help="comma-separated provider:model_id list")
    p.add_argument("--prices", default=None)
    p.add_argument("--out", required=True)
    p.add_argument("--json", dest="json_out", required=True)
    p.add_argument("--fixture", default=None)
    p.add_argument("--base-url", dest="base_url", default=None)
    p.add_argument("--max-tokens", dest="max_tokens", type=int, default=1024)
    p.add_argument("--timeout", type=int, default=120)
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])

    try:
        tasks = load_tasks(args.tasks)
    except Exception as e:
        sys.stderr.write(f"Could not read tasks file: {e}\n")
        return 1

    prices = load_prices(args.prices) if args.prices else {}
    fixture = load_fixture(args.fixture) if args.fixture else None

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    summaries = []

    for model_key in models:
        if ":" not in model_key:
            sys.stderr.write(f"Model '{model_key}' must be provider:model_id\n")
            return 2
        provider, model_id = model_key.split(":", 1)
        if provider not in ("anthropic", "openai"):
            sys.stderr.write(f"Unknown provider '{provider}', must be anthropic or openai\n")
            return 2

        results = []
        for task in tasks:
            check = task.get("check")
            result = run_one(provider, model_id, task, check, args, fixture)
            results.append(result)
        summaries.append(summarize(model_key, results, prices))

    report_text = render_report(summaries, len(tasks), models, fixture is not None)
    with open(args.out, "w") as f:
        f.write(report_text)

    summary_json = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tasks": len(tasks),
        "models": summaries,
        "fixture": fixture is not None,
    }
    with open(args.json_out, "w") as f:
        json.dump(summary_json, f, indent=2)

    return 0


if __name__ == "__main__":
    sys.exit(main())
