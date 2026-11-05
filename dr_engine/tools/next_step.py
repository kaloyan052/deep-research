"""What to do next in a study: ONE action, with the exact command.

Lighter models skip steps and take shortcuts. This reads the study folder, runs the same
checks as gate.py, and prints the FIRST unmet requirement in protocol order together with
the command that fixes it. Run it after every step, do exactly what it says, repeat until
it prints DONE. It never edits anything.

  python dr_engine/tools/next_step.py research/<dir> [--json]

Exit code: 0 = DONE, 1 = an action is needed, 2 = not a study folder.
Order: plan -> searches & evidence (E1-E9) -> corpus & claim ledger -> discovery
completeness (protocol 4.1) -> report draft -> report gate (R1-R13) -> blind claim audit ->
final gate -> copy to reports/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit as audit_mod  # noqa: E402
import gate as gate_mod  # noqa: E402
import screening as screening_mod  # noqa: E402
from evidence import ROOT, _jsonl, load_evidence, study_dir_error  # noqa: E402

T = "python dr_engine/tools/"
EVIDENCE_ORDER = ("E3", "E4", "E1", "E2", "E6", "E5", "E7", "E8", "E9", "E10")
COVERAGE_WORD_RE = re.compile(r"\b(coverage|saturat\w*|покрити\w*|насищ\w*)", re.I)
SCREENING_WORD_RE = re.compile(r"\b(screening|скрининг\w*)", re.I)

REPORT_ORDER = ("R1", "R14", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R13", "R11", "R15", "R16", "R10")
HELP = {
    "E10": ("Build and verify the Structural Causal Model (DAG) and counterfactual simulation",
            T + "causal.py init --dir {dir}  ->  add >= 4 nodes (add-node), >= 3 edges incl. a confounder/collider "
            "(add-edge), run " + T + "causal.py simulate --dir {dir} --intervene <node>=<val> --target <outcome>  "
            "and verify with " + T + "causal.py verify --dir {dir}"),
    "R15": ("Resolve dialectical conflicts and embed the Causal DAG / Dialectical Matrix in report.md",
            T + "dialectics.py build --dir {dir}  ->  " + T + "dialectics.py resolve --dir {dir} --id D### "
            "--synthesis \"...\" --partition-rule \"...\"  ->  paste " + T + "causal.py render --dir {dir} and "
            + T + "dialectics.py render --dir {dir} into report.md"),
    "R14": ("Expand the report to meet all volume and table quotas in quotas.json",
            "do NOT delete or truncate sections; add the missing table rows, complaint clusters, "
            "verbatim quotes (" + T + "evidence.py add-batch), calculations (" + T + "calc.py eval), "
            "and full Deep Dive sections until every threshold in {dir}/quotas.json is satisfied"),
    "E1": ("Restore the snapshot", T + "evidence.py fetch --dir {dir} --refresh <that source's URL>  "
           "(never edit sources/*.txt by hand)"),
    "E2": ("Replace the broken evidence record", T + "evidence.py retract --dir {dir} --id E### --reason "
           "\"<what is wrong>\"  then re-add it correctly: " + T + "evidence.py add --dir {dir} --source S### ... "
           "--quote \"<copied from evidence.py show>\"  (never edit evidence.jsonl by hand)"),
    "E2empty": ("Capture evidence", T + "evidence.py fetch --dir {dir} <url of a page a search returned>  ->  "
                + T + "evidence.py show --dir {dir} --source S### --grep \"<word>\"  ->  " + T + "evidence.py add "
                "--dir {dir} --source S### --sq SQn|Kn --tier T1..T5 --kind de_jure|de_facto|empirical|context "
                "--stance supports|contradicts|context --quote \"<copied from show>\" --claim \"<one sentence>\""),
    "E3": ("Complete plan.md and the searches per kill hypothesis",
           "plan.md needs >= 3 rows '| K1 | <how the thesis could be wrong> | ... |'; then for each Kn: "
           + T + "discover.py \"<query that would prove Kn true>\" --dir {dir} --purpose Kn  or  "
           + T + "evidence.py log-search --dir {dir} --purpose Kn --query \"...\" --opened <top result "
           "URLs> --channel web"),
    "E4": ("Search harder for evidence AGAINST the thesis, recording what each search returned",
           T + "discover.py \"<query that would prove Kn true>\" --dir {dir} --purpose Kn  |  "
           + T + "evidence.py log-search --dir {dir} --purpose Kn --query \"...\" --opened <top result "
           "URLs, even if irrelevant> --channel web|registry"),
    "E5": ("Answer the sub-question with quoted evidence",
           T + "corpus.py query --dir {dir} \"<SQ text>\" --log --purpose SQn  ->  " + T + "evidence.py add "
           "--dir {dir} --source S### --sq SQn --tier T1..T5 --kind de_jure|de_facto|empirical|context "
           "--stance supports|contradicts|context --quote \"<verbatim>\" --claim \"<one sentence>\"  "
           "(nothing found: say so in the report's Limitations)"),
    "E6": ("Correct the source tier", T + "evidence.py retract --dir {dir} --id E### --reason \"wrong tier\"  "
           "then re-add it with the right --tier (forums/social/Medium/Substack/personal GitHub = T5, "
           "Wikipedia/Investopedia-type explainers = T4)"),
    "E7dup": ("Withdraw the duplicate evidence record", T + "evidence.py retract --dir {dir} --id <the E### "
              "named first in WHY> --reason \"duplicate of E###\"  (one quote = one record with one stance)"),
    "E7": ("Add primary evidence", "find statutes, regulators' pages, official documents or peer-reviewed "
           "papers (" + T + "discover.py, registry sites) until >= 50% of evidence is T1-T3"),
    "E8": ("Fix the calculation", "re-run it: " + T + "calc.py eval --dir {dir} --label \"...\" --expr \"...\" "
           "--var x=... --cites E###  (never edit calculations.jsonl by hand)"),
    "E9": ("Finish the discovery-completeness checks", T + "screening.py bound --dir {dir}  and  "
           + T + "corpus.py stats --dir {dir} --save  (follow what they print)"),
    "R1": ("Fix the report structure", "add the missing sections / links from "
           ".agents/skills/deep-research/templates/report.md"),
    "R1urls": ("Paste the Sources table", T + "evidence.py sources --dir {dir} --report {dir}/report.md  "
               "-> paste its output under '## Sources' (citations count only when [E###] resolves to a URL)"),
    "R2": ("Cite the sentence", "add [E###] (or a verified [C###]) to the sentence on that line; if no "
           "evidence says it, find some (evidence.py add) or delete the sentence"),
    "R3": ("Bind the number to a quote", "cite the evidence whose quote contains that number, or compute "
           "it with " + T + "calc.py eval --dir {dir} ... and cite [C###]; never round or convert by eye "
           "(units.py / calc.py)"),
    "R4": ("Confront the contradicting evidence", "cite that E### in the body and say how the conflict "
           "is resolved"),
    "R5": ("Finish the kill-hypothesis section", "add a 'Kill hypotheses' section with each Kn's verdict "
           "(confirmed / refuted / unresolved) and evidence; set the same verdicts in plan.md"),
    "R6": ("Remove the self-assessment", "delete scores like '9/10' or 'rubric score'"),
    "R7": ("Remove the uncalibrated probability", "give n=... or compute it with calc.py, or delete it"),
    "R8": ("Fix the known-trap claim", "follow the message: the claim matches a refuted edge or a legal "
           "trap in dr_engine/tools/known_traps.json"),
    "R9": ("Register the inline calculations", "turn 'Calculation:' prose into " + T + "calc.py eval "
           "records and cite [C###]"),
    "R10": ("Lower the declared confidence", "set Overall Confidence to the formula.py ceiling "
            "(" + T + "formula.py {dir})"),
    "R11": ("Put the conflict in the Conflicts section", T + "claims.py conflicts --dir {dir}  ->  one "
            "row per conflict citing evidence from BOTH sides, with its axis"),
    "R13": ("Move the finding out of Sources/Verification", "state it in the body with [E###], or delete it"),
}


def _first(fails: list[str], order: tuple[str, ...]) -> str | None:
  for code in order:
    for f in fails:
      if f.split()[0] == code:
        return f
  return fails[0] if fails else None


def _step(action: str, command: str, why: str = "") -> dict:
  return {"status": "ACTION", "action": action, "command": command, "why": why}


def next_step(d: Path) -> dict:
  dir_s = d.as_posix()
  fill = lambda s: s.replace("{dir}", dir_s)  # noqa: E731

  # 1. plan
  plan_text = (d / "plan.md").read_text(encoding="utf-8")
  sqs, kills = gate_mod.parse_plan(plan_text)
  holders = gate_mod.placeholder_rows(plan_text)
  if not sqs or len(kills) < 3 or holders:
    return _step("Fill plan.md", f"edit {dir_s}/plan.md: the question, the decision, rows '| SQ1 | <sub-"
                 f"question> | ... |' and >= 3 rows '| K1 | <how the thesis could be wrong> | ... |'",
                 f"plan.md has {len(sqs)} sub-question(s) and {len(kills)} kill hypothesis/es"
                 + (f"; template placeholders still in rows {', '.join(holders)}" if holders else ""))

  # 2. searches and evidence (gate evidence stage)
  g = gate_mod.Gate(d)
  g.evidence_stage(12, 0.30)
  f = _first(g.fail, EVIDENCE_ORDER)
  if f:
    code = f.split()[0]
    if code == "E2" and "is empty" in f:
      code = "E2empty"
    elif code == "E7" and ("opposite stance" in f or "duplicate" in f):
      code = "E7dup"
    action, cmd = HELP.get(code, ("Fix this gate failure", "follow the message"))
    return _step(action, fill(cmd), f)

  index = _jsonl(d / "sources" / "index.jsonl")
  evidence = load_evidence(d)
  strict = gate_mod.study_is_strict(d)

  # 2b. Check pre-drafting evidence & calculation quotas if quotas.json exists
  q_path = d / "quotas.json"
  if q_path.exists():
    try:
      quotas = json.loads(q_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
      return _step("Fix syntax error in quotas.json", f"edit {dir_s}/quotas.json", str(e))
    min_ev = int(quotas.get("min_evidence", 0))
    if len(evidence) < min_ev:
      return _step(
          f"Collect more verified evidence ({len(evidence)}/{min_ev} required by quotas.json)",
          f"{T}evidence.py fetch --dir {dir_s} <urls...>  then  "
          f"{T}evidence.py add-batch --dir {dir_s} --file batch.jsonl",
          f"quotas.json requires >= {min_ev} evidence items before drafting; currently have {len(evidence)}",
      )
    min_calcs = int(quotas.get("min_calculations", 0))
    if len(g.calculations) < min_calcs:
      return _step(
          f"Register deterministic calculations ({len(g.calculations)}/{min_calcs} required by quotas.json)",
          f"{T}calc.py eval --dir {dir_s} --label \"...\" --expr \"...\" --cites E###",
          f"quotas.json requires >= {min_calcs} [C###] records before drafting; currently have {len(g.calculations)}",
      )

  # 3. corpus and claim ledger (v4)
  if len(index) > 15 and not (d / "corpus.sqlite").exists():
    return _step("Index the corpus and read by ranked passages",
                 f"{T}corpus.py build --dir {dir_s}  then  {T}corpus.py triage --dir {dir_s}",
                 f"{len(index)} sources: read passages, not whole pages")
  if len(evidence) >= 5 and not _jsonl(d / "claims.jsonl"):
    return _step("Log the load-bearing facts in the claim ledger",
                 f"{T}claims.py add --dir {dir_s} --subject <X> --attribute \"<what>\" --value <v> "
                 f"--unit \"<unit, e.g. USD RT or % p.a.>\" --scope \"<which plan/product>\" --eids E###"
                 f" --load-bearing   (repeat per fact; reuse wording from claims.py keys)",
                 "the report must be drafted from claims.py table, and R11 needs the ledger")

  # 4. discovery completeness (protocol 4.1)
  if strict:
    sdata = screening_mod.load(d)
    if not sdata:
      return _step("Audit the leads you did not fetch", f"{T}screening.py sample --dir {dir_s}  then "
                   f"judge each item in audit/screening_brief.md with screening.py record",
                   "protocol 4.1: the share of relevant leads discarded unread must be measured")
    s = screening_mod.summary(d, sdata)
    if s["pending"]:
      return _step("Judge the sampled leads", f"{T}screening.py record --dir {dir_s} --item {s['pending'][0]} "
                   f"--verdict relevant|irrelevant|duplicate|unreachable [--source S###] --note \"...\"",
                   f"{len(s['pending'])} unjudged: {', '.join(s['pending'][:6])}")
    cov = json.loads((d / "coverage.json").read_text(encoding="utf-8")) if (d / "coverage.json").exists() else None
    if not cov:
      return _step("Measure coverage and saturation", f"{T}corpus.py stats --dir {dir_s} --save",
                   "protocol 4.1: coverage of the relevant sources must be estimated")
    if cov.get("sources") != len(index):
      return _step("Re-measure coverage on the current corpus", f"{T}corpus.py stats --dir {dir_s} --save",
                   f"coverage.json counted {cov.get('sources')} sources, sources/ now has {len(index)}")
    report = d / "report.md"
    text = report.read_text(encoding="utf-8") if report.exists() else ""
    need_cov = cov.get("verdict") != "SATURATED" and not COVERAGE_WORD_RE.search(text)
    need_scr = s["cp_upper"] > screening_mod.MAX_LOSS and not SCREENING_WORD_RE.search(text)
    if report.exists() and (need_cov or need_scr):
      said = ([f"Coverage: {cov.get('verdict')}"] if need_cov else []) + (
          ["the screening audit leaves a high bound on relevant leads discarded unread"] if need_scr else [])
      why = ([f"coverage {cov.get('verdict')}: " + "; ".join(cov.get("reasons", [])[:2])] if need_cov else []) + (
          [f"screening loss bound {s['cp_upper']:.0%} > {screening_mod.MAX_LOSS:.0%}"] if need_scr else [])
      return _step("Continue discovery, or state the gap in Limitations",
                   f"follow the blind spots printed by {T}corpus.py stats --dir {dir_s} and fetch more of the "
                   f"discarded leads (back to discovery), or add this line to report.md Limitations (no numbers "
                   f"in it, so it needs no citation): '- {', and '.join(said)} (`corpus.py stats`, "
                   f"`screening.py bound`) - <why it could not be closed, in words>'", "; ".join(why))

  # 5. report draft
  report = d / "report.md"
  if not report.exists():
    return _step("Draft the report", f"copy .agents/skills/deep-research/templates/report.md to "
                 f"{dir_s}/report.md and fill it from {T}claims.py table --dir {dir_s}; every claim "
                 f"cites [E###]/[C###]", "no report.md yet")

  # 6. report gate without the audit, then the audit
  g.report_stage(report, 0.9)
  fails = [x for x in g.fail if not x.startswith("R12")]
  f = _first(fails, REPORT_ORDER)
  if f:
    code = f.split()[0]
    if code == "R1" and ("citation coverage" in f or "URL" in f or "domains" in f):
      code = "R1urls"
    action, cmd = HELP.get(code, ("Fix this gate failure", "follow the message"))
    return _step(action, fill(cmd), f)
  text = report.read_text(encoding="utf-8")
  data = audit_mod.load(d)
  if not data:
    return _step("Run the blind claim audit", f"{T}audit.py sample --dir {dir_s}  then give a FRESH "
                 f"verifier (a subagent that has not seen the research) ONLY audit/brief.md and "
                 f"sources/; it records each verdict with audit.py record", "required before delivery")
  s = audit_mod.summary(data)
  if s["pending"]:
    return _step("Have the verifier judge the sampled claims", f"{T}audit.py record --dir {dir_s} --item "
                 f"{s['pending'][0]} --verdict supported|partial|unsupported|wrong_number|misattributed "
                 f"--note \"...\"  (the verifier, not the author)", f"{len(s['pending'])} unjudged")
  problems = audit_mod.check_against_report(data, text)
  if problems:
    return _step("Fix the audited sentences, then re-sample", f"edit report.md at the lines below, then "
                 f"{T}audit.py sample --dir {dir_s} (fixed sentences go to a NEW blind verifier)",
                 "; ".join(problems[:3]))
  if s["upper_bound"] > 0.15:
    return _step("Fix and re-audit", f"fix the error sentences, then {T}audit.py sample --dir {dir_s}",
                 f"unsupported-claim bound {s['upper_bound']:.1%} > 15%")

  # 7. final gate and delivery
  sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
  delivered = [p for p in (ROOT / "reports").glob("*.md")
               if hashlib.sha256(p.read_bytes()).hexdigest() == sha]
  if not delivered:
    return _step("Run the final gate and deliver", f"{T}gate.py {dir_s} --live 5 --scorecard --require-audit"
                 f"  -> must print [PASS]; then copy report.md to reports/<TOPIC>_<YYYY-MM-DD>.md",
                 "report.md is not in reports/ yet")
  return {"status": "DONE", "action": "Nothing left", "command": "",
          "why": f"gate checks pass, audit bound {s['upper_bound']:.1%}, delivered as {delivered[0].name}"}


def main(argv: list[str] | None = None) -> int:
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
  ap.add_argument("dir", type=Path)
  ap.add_argument("--json", action="store_true")
  args = ap.parse_args(argv)
  err = study_dir_error(args.dir)
  if err:
    print(err)
    return 2
  res = next_step(args.dir)
  if args.json:
    print(json.dumps(res, ensure_ascii=False, indent=2))
  elif res["status"] == "DONE":
    print(f"DONE - {res['why']}")
  else:
    print(f"NEXT: {res['action']}\n  RUN: {res['command']}")
    why = re.sub(r"\s+", " ", res["why"])[:400]
    if why:
      print(f"  WHY: {why}")
    print("Then run next_step.py again.")
  return 0 if res["status"] == "DONE" else 1


if __name__ == "__main__":
  sys.exit(main())
