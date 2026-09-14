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
from brand.shell import masthead, footer
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


def stylesheet_href() -> str:
    """Use the estate sheet once; fingerprint the nearest supplied source sheet."""
    sheet = next((parent / "styles.css" for parent in HERE.parents
                  if (parent / "styles.css").is_file()), None)
    base = "https://ustechautomations.com/feeds/styles.css"
    return base + ("?v=" + hashlib.sha256(sheet.read_bytes()).hexdigest()[:10] if sheet else "")


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
    public_css = stylesheet_href()
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <meta name="referrer" content="no-referrer">
  <title>{html.escape(PRODUCT_NAME)} — your files</title>
  <link rel="stylesheet" href="{html.escape(public_css)}">
  <meta name="theme-color" media="(prefers-color-scheme: light)" content="#f9fafb">
  <meta name="theme-color" media="(prefers-color-scheme: dark)" content="#0d0f13">
  <style>
    /* Layout only. Colours and type come from styles.css. */
    .kit-cmd {{ overflow-x: auto; }}
    .kit-cmd pre {{
      margin: 0;
      padding: 1rem 1.125rem;
      white-space: pre-wrap;
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--surface-2);
      font-family: var(--mono);
      font-size: .9rem;
    }}
  </style>
</head>
<body data-family="{html.escape(FAMILY)}">
<a class="skip" href="#main">Skip to content</a>

{masthead("<span class=\"sep\">/</span>" + html.escape(PRODUCT_NAME))}

<section class="hero">
  <div class="wrap">
    <p class="eyebrow">Private page <span class="dot"></span> your files</p>
    <h1>{html.escape(PRODUCT_NAME)}</h1>
    <p class="lede">Every file below is inside this page. Click a name to save it. Nothing is fetched from our servers when you click, and the runner never sends anything to us.</p>
    <dl class="rail">
      <div><dt>Order</dt><dd class="stamp">{html.escape(ref)}</dd></div>
      <div><dt>Keep</dt><dd>Save these files for use on your machine. Keep your checkout confirmation private.</dd></div>
    </dl>
    <a class="btn btn-buy btn-lg" href="#files">Save your kit files</a>
  </div>
</section>

<main id="main" tabindex="-1">
  <div class="wrap">
    <section id="files">
      <h2>Your files</h2>
      <p class="note">Order reference {html.escape(ref)}. Click a file name to save it. Each link is the file itself, not a fetch from our servers.</p>
      <div class="evidence">
        <div class="evidence-head">
          <span>Kit files on this page</span>
          <span class="stamp">download · bytes inside the page</span>
        </div>
        <div class="scroll">
          <table>
            <thead><tr><th>File</th><th>Size</th><th>What it is</th><th>Checksum (first 12)</th></tr></thead>
            <tbody>
{chr(10).join(rows)}
            </tbody>
          </table>
        </div>
      </div>
    </section>
    <section>
      <h2>Quick start</h2>
      <div class="kit-cmd"><pre># offline demo first, no keys, spends nothing:
python3 silent_check.py --fixture fixtures/recorded_replies.json --tasks tasks.example.jsonl --prices prices.example.json --models anthropic:claude-fable-5-1,openai:gpt-6-astra --out demo_report.md --json demo.json

# then your own tasks with your own keys:
python3 silent_check.py --tasks my_tasks.jsonl --prices prices.example.json --models anthropic:claude-fable-5-1,openai:gpt-6-astra --out report.md --json summary.json</pre></div>
      <p class="note">Set your own keys in the environment first (the README names the variable for each provider). The runner reads them from your shell and never writes them anywhere.</p>
    </section>
    <section>
      <h2>README</h2>
      <div class="kit-cmd"><pre>{html.escape(readme)}</pre></div>
    </section>
    <section>
      <h2>What a finished report looks like</h2>
      <div class="kit-cmd"><pre>{html.escape(sample)}</pre></div>
      <p class="note">This is a measurement of the tasks you give it, on the day you run it. It is not a benchmark, not a ranking of models in general, and not a guarantee that any model will behave the same tomorrow.</p>
    </section>
  </div>
</main>

{footer("<p>A measurement you run yourself. Not a benchmark, model ranking or guarantee.</p>")}
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
