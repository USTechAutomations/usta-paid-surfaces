"""silent-refusal-kit: deliver the downloadable report kit after a $199 one-off payment.

The buyer receives one private page that carries every kit file as a download
link (the bytes are inside the page itself, so nothing is fetched from anywhere
else and nothing of the buyer's is uploaded). The kit runs on the buyer's own
machine with the buyer's own model keys; we never see their tasks or keys.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import sys
from pathlib import Path

FAMILY = "silent-refusal-kit"
LINK_ID_ENV_OR_CATALOG = "silent-refusal-kit"
PRODUCT_NAME = "Model silent-failure report kit"
ETA_MINUTES = 15

HERE = Path(__file__).resolve().parent
KIT_DIR = HERE / "kit"
# Every file the buyer gets, in the order it is shown. The kit folder is the
# single source: the page is built from these bytes at delivery time.
KIT_FILES = (
    ("silent_check.py", "text/x-python", "The runner. One file, Python 3.10 or newer, no packages to install."),
    ("README.md", "text/markdown", "How to run it, what each number means, and what it does not measure."),
    ("tasks.example.jsonl", "application/jsonl", "Example task file. Replace the rows with your own tasks and expected outputs."),
    ("prices.example.json", "application/json", "Example price table for cost per pass. Edit the numbers to your contract prices."),
    ("sample_report.md", "text/markdown", "A report the runner produced from recorded replies, so you can see the shape before you run it."),
    ("fixtures/recorded_replies.json", "application/json", "The recorded example replies behind the sample report. Save it in a folder named fixtures next to the runner to try the offline demo in the README before spending any model credit."),
)
NEVER_IN_KIT = ("sk_live", "sk_test", "rk_live", "sk-ant-", "sk-proj-", "hf_", "Bearer ")


def kit_bytes(name: str) -> bytes:
    return (KIT_DIR / name).read_bytes()


def kit_manifest() -> list[dict]:
    """Name, size, sha256 and purpose of every kit file (no contents)."""
    out = []
    for name, mime, purpose in KIT_FILES:
        data = kit_bytes(name)
        out.append({"name": name, "mime": mime, "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(), "purpose": purpose})
    return out


def check_kit() -> list[str]:
    """Reasons the kit must not ship. Empty list means it may."""
    problems = []
    for name, _mime, _purpose in KIT_FILES:
        p = KIT_DIR / name
        if not p.is_file():
            problems.append(f"missing kit file {name}")
            continue
        text = p.read_text(errors="replace")
        for marker in NEVER_IN_KIT:
            if marker in text:
                problems.append(f"{name} contains a key-like string ({marker!r})")
        if not text.strip():
            problems.append(f"{name} is empty")
    return problems


def data_url(name: str, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(kit_bytes(name)).decode('ascii')}"


def render_delivery(session_id: str) -> str:
    """The private page: one h1, the file list with download links, the README inline."""
    manifest = kit_manifest()
    readme = kit_bytes("README.md").decode("utf-8", errors="replace")
    sample = kit_bytes("sample_report.md").decode("utf-8", errors="replace")
    rows = []
    for m, (name, mime, purpose) in zip(manifest, KIT_FILES):
        rows.append(
            "<tr><td><a download=\"{dl}\" href=\"{u}\">{n}</a></td><td>{kb} KB</td>"
            "<td>{p}</td><td><code>{h}</code></td></tr>".format(
                n=html.escape(name), dl=html.escape(name.rsplit("/", 1)[-1]), u=data_url(name, mime), kb=max(1, m["bytes"] // 1024),
                p=html.escape(purpose), h=m["sha256"][:12]))
    ref = hashlib.sha256(session_id.encode()).hexdigest()[:12]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{html.escape(PRODUCT_NAME)} — your files</title>
<style>
body{{margin:0;padding:1.5rem 1rem;font:16px/1.5 system-ui,sans-serif;max-width:60rem;margin-inline:auto;color:#111;background:#fff}}
h1{{font-size:1.5rem;margin:0 0 .5rem}} h2{{font-size:1.15rem;margin:1.75rem 0 .5rem}}
table{{border-collapse:collapse;width:100%;font-size:.95rem}} th,td{{text-align:left;padding:.4rem .5rem;border-bottom:1px solid #ddd;vertical-align:top}}
.scroll{{overflow-x:auto}} pre{{white-space:pre-wrap;background:#f6f6f6;padding:1rem;border-radius:6px;font-size:.9rem}}
.muted{{color:#555}}
@media (prefers-color-scheme: dark){{body{{color:#eee;background:#111}} th,td{{border-color:#333}} pre{{background:#1b1b1b}}}}
</style>
</head>
<body>
<main id="main">
<h1>{html.escape(PRODUCT_NAME)}</h1>
<p class="muted">Order reference {ref}. Save this page or the files now; the link that opened it stops working later.</p>
<p>Every file below is inside this page. Click a name to save it. Nothing is fetched from our servers when you click, and the runner never sends anything to us.</p>
<h2>Your files</h2>
<div class="scroll"><table>
<thead><tr><th>File</th><th>Size</th><th>What it is</th><th>Checksum (first 12)</th></tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody></table></div>
<h2>Quick start</h2>
<pre># offline demo first, no keys, spends nothing:
python3 silent_check.py --fixture fixtures/recorded_replies.json --tasks tasks.example.jsonl --prices prices.example.json --models anthropic:claude-fable-5-1,openai:gpt-6-astra --out demo_report.md --json demo.json

# then your own tasks with your own keys:
python3 silent_check.py --tasks my_tasks.jsonl --prices prices.example.json --models anthropic:claude-fable-5-1,openai:gpt-6-astra --out report.md --json summary.json</pre>
<p class="muted">Set your own keys in the environment first (the README names the variable for each provider). The runner reads them from your shell and never writes them anywhere.</p>
<h2>README</h2>
<pre>{html.escape(readme)}</pre>
<h2>What a finished report looks like</h2>
<pre>{html.escape(sample)}</pre>
<p class="muted">This is a measurement of the tasks you give it, on the day you run it. It is not a benchmark, not a ranking of models in general, and not a guarantee that any model will behave the same tomorrow.</p>
</main>
</body>
</html>
"""


def fulfil(session) -> str | None:
    """Return the private page for a paid session, or None when the session is unusable."""
    sid = (session or {}).get("session_id") or (session or {}).get("id")
    if not sid:
        return None
    problems = check_kit()
    if problems:
        raise RuntimeError("kit not shippable: " + "; ".join(problems))
    return render_delivery(str(sid))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--check" in argv:
        problems = check_kit()
        print("\n".join(problems) if problems else "kit ok: " + ", ".join(f"{m['name']} {m['bytes']}B" for m in kit_manifest()))
        return 1 if problems else 0
    if "--manifest" in argv:
        print(json.dumps(kit_manifest(), indent=1))
        return 0
    out = fulfil({"session_id": "cs_local_preview"})
    sys.stdout.write(out or "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
