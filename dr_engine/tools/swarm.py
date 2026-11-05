"""Autonomous 5-Phase Subagent Swarm Orchestrator (v5.0).

Eliminates context rot and write-contention across multi-agent research runs by:
  1. Generating zero-context, self-contained task packets (`swarm/packets/<role>_<id>.md`)
     for each subagent phase (Planner -> Parallel Scouts -> Quant/Causal Extractor ->
     Section Synthesizers -> Fresh-Context Blind Auditor).
  2. Sharding parallel Scout outputs (`swarm/shards/scout_<id>.jsonl`) and atomically
     merging them into `evidence.jsonl` via `evidence.py add-batch`.
  3. Tracking state transitions in `swarm/manifest.json`.

Usage:
  python dr_engine/tools/swarm.py init --dir D
  python dr_engine/tools/swarm.py status --dir D
  python dr_engine/tools/swarm.py emit-packets --dir D --phase scouts|extractor|synthesizers|auditor
  python dr_engine/tools/swarm.py merge-shards --dir D
  python dr_engine/tools/swarm.py assemble-report --dir D

Stdlib only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence as ev_mod  # noqa: E402
import gate as gate_mod  # noqa: E402
from evidence import _jsonl, study_dir_error  # noqa: E402


def _swarm_dir(d: Path) -> Path:
  p = Path(d) / "swarm"
  (p / "packets").mkdir(parents=True, exist_ok=True)
  (p / "shards").mkdir(parents=True, exist_ok=True)
  (p / "sections").mkdir(parents=True, exist_ok=True)
  return p


def load_manifest(d: Path) -> dict[str, Any]:
  mpath = _swarm_dir(d) / "manifest.json"
  if not mpath.exists():
    return {"phase": "planner", "updated_at": "", "tasks": {}}
  return json.loads(mpath.read_text(encoding="utf-8"))


def save_manifest(d: Path, manifest: dict[str, Any]) -> None:
  manifest["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
  mpath = _swarm_dir(d) / "manifest.json"
  mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def emit_scout_packets(d: Path) -> list[Path]:
  """Creates isolated prompt packets for parallel Scout subagents (1 per SQ and 1 per Kill)."""
  plan_text = (d / "plan.md").read_text(encoding="utf-8")
  sqs, kills = gate_mod.parse_plan(plan_text)
  sdir = _swarm_dir(d)
  packets: list[Path] = []
  manifest = load_manifest(d)
  dir_posix = d.as_posix()

  all_targets = [(sq, "SQ", "primary/peer-reviewed & marketplace VoC") for sq in sqs] + [
      (k, "KILL", "hostile disconfirmation & failure mode") for k in kills
  ]

  for tid, kind, focus in all_targets:
    shard_file = f"{dir_posix}/swarm/shards/scout_{tid}.jsonl"
    pkt_path = sdir / "packets" / f"scout_{tid}.md"
    pkt_body = (
        f"# Subagent Task Packet: Parallel Scout `{tid}` ({kind})\n\n"
        f"**Study Folder:** `{dir_posix}`\n\n"
        f"**Assigned Target:** `{tid}` ({focus})\n\n"
        f"**Isolation Rule:** Do NOT edit `evidence.jsonl` directly. Write extracted quotes to `{shard_file}`.\n\n"
        f"## Context From `plan.md`\n\n"
        f"```markdown\n{plan_text[:3000]}\n```\n\n"
        f"## Mandatory Execution Steps\n\n"
        f"1. Run discovery for `{tid}`:\n"
        f"   `python dr_engine/tools/discover.py \"<query>\" --dir {dir_posix} --purpose {tid}`\n"
        f"   or web search logged via:\n"
        f"   `python dr_engine/tools/evidence.py log-search --dir {dir_posix} --purpose {tid} --query \"...\" --opened <urls>`\n\n"
        f"2. Fetch all primary pages into `sources/`:\n"
        f"   `python dr_engine/tools/evidence.py fetch --dir {dir_posix} <url1> <url2> ...`\n\n"
        f"3. Inspect verbatim text with `evidence.py show --dir {dir_posix} --source S### --grep \"...\"`.\n\n"
        f"4. Write verified JSONL records to `{shard_file}`, one JSON object per line:\n"
        f"   `{{\"source\": \"S001\", \"sq\": \"{tid}\", \"tier\": \"T1\", \"kind\": \"empirical\", "
        f"\"stance\": \"supports\", \"quote\": \"<verbatim>\", \"claim\": \"<paraphrase>\", \"sample_period\": \"2024-2025\"}}`\n"
    )
    pkt_path.write_text(pkt_body, encoding="utf-8")
    packets.append(pkt_path)
    manifest.setdefault("tasks", {})[f"scout_{tid}"] = {
        "phase": "scouts", "packet": str(pkt_path), "shard": shard_file, "status": "ready"
    }

  manifest["phase"] = "scouts"
  save_manifest(d, manifest)
  return packets


def emit_extractor_packet(d: Path) -> list[Path]:
  sdir = _swarm_dir(d)
  dir_posix = d.as_posix()
  pkt_path = sdir / "packets" / "extractor_quant.md"
  pkt_body = (
      f"# Subagent Task Packet: Quant, Ledger & Causal Extractor\n\n"
      f"**Study Folder:** `{dir_posix}`\n\n"
      f"## Mandatory Execution Steps\n\n"
      f"1. Build and triage the passage corpus:\n"
      f"   `python dr_engine/tools/corpus.py build --dir {dir_posix}`\n"
      f"   `python dr_engine/tools/corpus.py triage --dir {dir_posix}`\n\n"
      f"2. Populate the normalized claim ledger (`claims.jsonl`) and generate dialectical conflict briefs:\n"
      f"   `python dr_engine/tools/claims.py add --dir {dir_posix} ... --load-bearing`\n"
      f"   `python dr_engine/tools/dialectics.py build --dir {dir_posix}`\n\n"
      f"3. Compute all deterministic AST math & decision matrices (`calculations.jsonl`):\n"
      f"   `python dr_engine/tools/calc.py eval --dir {dir_posix} ...`\n"
      f"   `python dr_engine/tools/calc.py decision --dir {dir_posix} ...`\n\n"
      f"4. Build and simulate the Structural Causal Model (`causal_dag.json`):\n"
      f"   `python dr_engine/tools/causal.py init --dir {dir_posix}`\n"
      f"   (add >= 4 nodes, >= 3 edges incl. 1 confounder/collider, and run `causal.py simulate`)\n\n"
      f"5. Complete screening and saturation checks:\n"
      f"   `python dr_engine/tools/screening.py sample --dir {dir_posix} ...`\n"
      f"   `python dr_engine/tools/corpus.py stats --dir {dir_posix} --save`\n\n"
      f"6. Verify `python dr_engine/tools/gate.py {dir_posix} --stage evidence`.\n"
  )
  pkt_path.write_text(pkt_body, encoding="utf-8")
  manifest = load_manifest(d)
  manifest["phase"] = "extractor"
  manifest.setdefault("tasks", {})["extractor_quant"] = {
      "phase": "extractor", "packet": str(pkt_path), "status": "ready"
  }
  save_manifest(d, manifest)
  return [pkt_path]


def emit_synthesizer_packets(d: Path) -> list[Path]:
  """Splits report drafting across 4 section writers to guarantee zero truncation."""
  sdir = _swarm_dir(d)
  dir_posix = d.as_posix()
  sections = [
      ("01_executive_and_causal", "Executive Decision Card, Bottom Line, Causal DAG & Counterfactual Physics"),
      ("02_sq_analysis_and_matrices", "Exhaustive Sub-Question Analysis SQ1..SQn with Full Candidate Matrices"),
      ("03_deep_dives", "Top 5 Product / Investment Deep Dives (all mandatory candidate profiles)"),
      ("04_kills_dialectics_tail", "Kill Hypotheses Table, Dialectical Synthesis Matrix, Base/Bear/Stress & Verification"),
  ]
  packets: list[Path] = []
  manifest = load_manifest(d)
  for sec_slug, desc in sections:
    out_sec = f"{dir_posix}/swarm/sections/{sec_slug}.md"
    pkt = sdir / "packets" / f"synth_{sec_slug}.md"
    pkt.write_text(
        f"# Subagent Task Packet: Section Synthesizer `{sec_slug}`\n\n"
        f"**Output File:** `{out_sec}`\n"
        f"**Scope:** {desc}\n\n"
        f"## Strict Grounding Rules\n"
        f"- Every number, percentage, date, or currency amount MUST cite inline `[E###]` or `[C###]`.\n"
        f"- Table rows are validated by row-scope union: place all `[E###]` in the cell or notes column.\n"
        f"- Never summarize or omit rows requested in `{dir_posix}/quotas.json`.\n",
        encoding="utf-8",
    )
    packets.append(pkt)
    manifest.setdefault("tasks", {})[f"synth_{sec_slug}"] = {
        "phase": "synthesizers", "packet": str(pkt), "output": out_sec, "status": "ready"
    }
  manifest["phase"] = "synthesizers"
  save_manifest(d, manifest)
  return packets


def emit_auditor_packet(d: Path) -> list[Path]:
  sdir = _swarm_dir(d)
  dir_posix = d.as_posix()
  pkt = sdir / "packets" / "blind_auditor.md"
  pkt.write_text(
      f"# Subagent Task Packet: Adversarial Blind Verifier (Zero-Context Audit)\n\n"
      f"**Study Folder:** `{dir_posix}`\n\n"
      f"## STRICT EPISTEMIC FIREWALL\n"
      f"You are a hostile external verifier. You are FORBIDDEN from reading `report.md`, "
      f"`plan.md`, `evidence.jsonl`, or `claims.jsonl`. You may ONLY read:\n"
      f"1. `{dir_posix}/audit/brief.md`\n"
      f"2. `{dir_posix}/sources/index.jsonl` and `{dir_posix}/sources/S###.txt`\n\n"
      f"For every item `A##` in `audit/brief.md`, verify whether the verbatim snapshot text supports "
      f"the exact scope, qualifiers, sample period, and numbers of the claim.\n"
      f"Record every verdict via:\n"
      f"`python dr_engine/tools/audit.py record --dir {dir_posix} --id A## --verdict supported|error --note \"...\"`\n",
      encoding="utf-8",
  )
  manifest = load_manifest(d)
  manifest["phase"] = "auditor"
  manifest.setdefault("tasks", {})["blind_auditor"] = {
      "phase": "auditor", "packet": str(pkt), "status": "ready"
  }
  save_manifest(d, manifest)
  return [pkt]


def merge_shards(d: Path) -> int:
  """Merges all `swarm/shards/*.jsonl` into `evidence.jsonl` using `evidence.py add-batch`."""
  shard_dir = _swarm_dir(d) / "shards"
  shards = sorted(shard_dir.glob("*.jsonl"))
  if not shards:
    print("No shard files found in swarm/shards/.")
    return 0
  combined_items: list[dict] = []
  for sh in shards:
    combined_items.extend(_jsonl(sh))
  if not combined_items:
    print("All shard files are empty.")
    return 0

  merged_file = _swarm_dir(d) / "merged_batch.jsonl"
  with merged_file.open("w", encoding="utf-8", newline="\n") as f:
    for item in combined_items:
      f.write(json.dumps(item, ensure_ascii=False) + "\n")

  ns = argparse.Namespace(dir=str(d), file=str(merged_file))
  return ev_mod.cmd_add_batch(ns)


def assemble_report(d: Path) -> int:
  sec_dir = _swarm_dir(d) / "sections"
  parts = sorted(sec_dir.glob("*.md"))
  if not parts:
    print("ERROR: no drafted section files in swarm/sections/*.md")
    return 1
  blocks = [p.read_text(encoding="utf-8").strip() for p in parts]
  out = d / "report.md"
  out.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
  print(f"Assembled {len(parts)} sections into {out} ({len(out.read_text(encoding='utf-8').split())} words)")
  return 0


def main(argv: list[str] | None = None) -> int:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
  sub = ap.add_subparsers(dest="cmd", required=True)

  p = sub.add_parser("init"); p.add_argument("--dir", required=True)
  p = sub.add_parser("status"); p.add_argument("--dir", required=True)
  p = sub.add_parser("emit-packets"); p.add_argument("--dir", required=True)
  p.add_argument("--phase", choices=("scouts", "extractor", "synthesizers", "auditor"), required=True)
  p = sub.add_parser("merge-shards"); p.add_argument("--dir", required=True)
  p = sub.add_parser("assemble-report"); p.add_argument("--dir", required=True)

  args = ap.parse_args(argv)
  d = Path(args.dir)
  err = study_dir_error(d)
  if err:
    print(err)
    return 2

  if args.cmd == "init":
    _swarm_dir(d)
    save_manifest(d, {"phase": "planner", "tasks": {}})
    print(f"Initialized swarm workspace in {d / 'swarm'}")
    return 0
  if args.cmd == "status":
    print(json.dumps(load_manifest(d), ensure_ascii=False, indent=2))
    return 0
  if args.cmd == "emit-packets":
    fn = {
        "scouts": emit_scout_packets,
        "extractor": emit_extractor_packet,
        "synthesizers": emit_synthesizer_packets,
        "auditor": emit_auditor_packet,
    }[args.phase]
    pkts = fn(d)
    for p in pkts:
      print(f"EMITTED  {p}")
    return 0
  if args.cmd == "merge-shards":
    return merge_shards(d)
  if args.cmd == "assemble-report":
    return assemble_report(d)
  return 0


if __name__ == "__main__":
  sys.exit(main())
