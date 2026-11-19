r"""Write every number the manuscript prints as a LaTeX macro (build/numbers.tex) and every table as a .tex file
(build/tables/), from results/numbers.json and results/*.csv. The text never types a number by hand.

    py scripts/06_tables.py
"""
import collections
import csv
import json
import os
import statistics
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R, B = os.path.join(HERE, "results"), os.path.join(HERE, "build")
T = os.path.join(B, "tables")
os.makedirs(T, exist_ok=True)
N = json.load(open(os.path.join(R, "numbers.json"), encoding="utf-8"))
E = list(csv.DictReader(open(os.path.join(R, "entries.csv"), encoding="utf-8")))
H = list(csv.DictReader(open(os.path.join(R, "rq1_hook_repositories.csv"), encoding="utf-8")))
DR = list(csv.DictReader(open(os.path.join(R, "rq4_drift.csv"), encoding="utf-8")))


def num(x, d=0):
    if x is None:
        return "--"
    s = f"{x:,.{d}f}" if isinstance(x, float) or d else f"{int(x):,}"
    return s.replace(",", "{,}")


def p(v):
    return num(v["pct"], 1) + r"\%"


def ci(v):
    return "[" + num(v["ci95"][0], 1) + ", " + num(v["ci95"][1], 1) + "]"


M = {}
f, r1, r2, r3, r4 = N["frame"], N["rq1"], N["rq2"], N["rq3"], N["rq4"]
M.update(nProjects=num(f["projects"]), nWithGitHub=num(f["with_github_url"]), nRepos=num(f["distinct_repositories"]),
         nResolved=num(f["head_resolved"]), nUnresolved=num(f["head_unresolved"]), nConfigs=num(f["with_config"]),
         pConfigs=p(f["config_share"]), ciConfigs=ci(f["config_share"]), nUnparseable=num(f["config_unparseable"]),
         nPypiFail=num(f["pypi_lookup_failed"]), dumpDate=f["top_dump_last_update"][:10],
         snapFirst=f["snapshot_first"][:16].replace("T", " "), snapLast=f["snapshot_last"][11:16],
         nRemote=num(r1["remote_entries"]), nLocal=num(r1["local_entries"]), nMeta=num(r1["meta_entries"]),
         nBuiltin=num(r1["builtin_entries"]), nHookRepos=num(r1["distinct_hook_repositories"]),
         medRemote=num(r1["median_remote_per_config"]), nZeroRemote=num(r1["configs_with_zero_remote"]),
         nUnmappedRepos=num(r1["unmapped_hook_repositories"]), nUnmappedEntries=num(r1["entries_in_unmapped_hook_repos"]),
         nMeasured=num(r2["entries_measured"]), nNotMeasured=num(r2["entries_not_measured"]),
         pCurrent=p(r2["current"]), ciCurrent=ci(r2["current"]), medBehind=num(r2["median_behind"]),
         pBehindFive=p(r2["behind_5_or_more"]), ciBehindFive=ci(r2["behind_5_or_more"]),
         nDays=num(r2["days_behind"]["entries"]), medDays=num(r2["days_behind"]["median"]),
         pOverYear=p(r2["days_behind"]["over_365"]), ciOverYear=ci(r2["days_behind"]["over_365"]))
a = r2["automation"]
mw = a["mann_whitney"]
M.update(nAutoConfigs=num(a["configs"]), pAuto=p(a["any_indicator"]), nAuto=num(a["any_indicator"]["k"]),
         nNoAuto=num(a["configs"] - a["any_indicator"]["k"]), nCiSection=num(a["ci_section"]),
         nDependabot=num(a["dependabot"]), nRenovate=num(a["renovate"]),
         medWith=num(a["median_mean_behind_with"], 1), medWithout=num(a["median_mean_behind_without"], 1),
         pAllCurrentWith=p(a["all_current_with"]), pAllCurrentWithout=p(a["all_current_without"]),
         mwU=num(mw["U"]), mwZ=num(mw["z"], 2), mwR=num(mw["rank_biserial"], 2),
         mwP=r"<0.001" if mw["p"] < 0.001 else num(mw["p"], 3))
pk = r3["pin_kind"]
mv = r3["moved"]
M.update(pRef=p(pk["ref"]), nRef=num(pk["ref"]["k"]), pSha=p(pk["sha"]), nSha=num(pk["sha"]["k"]),
         ciSha=ci(pk["sha"]), nMissingRev=num(pk.get("missing", {"k": 0})["k"]),
         pFrozen=p(r3["sha_with_frozen_comment"]), nRefNotTag=num(r3["ref_not_a_tag"]),
         nShaUnmatched=num(r3["sha_unmatched"]), nUnresolvableRepos=num(r3["unresolvable_hook_repositories"]),
         nUnresolvableEntries=num(r3["entries_in_unresolvable"]), nMovedRepos=num(mv["hook_repositories"]),
         pMovedEntries=p(mv["entries"]), nMovedEntries=num(mv["entries"]["k"]), pMovedConfigs=p(mv["configs"]),
         nMovedConfigs=num(mv["configs"]["k"]), ciMovedConfigs=ci(mv["configs"]),
         nFormerOwners=num(mv["former_owner_accounts"]), nFormerMissing=num(mv["former_owner_missing"]))
M.update(nPairs=num(r4["repo_tool_pairs"]), nUnpinnedPairs=num(r4["unpinned_in_project"]),
         nConstrained=num(r4["constrained"]), pDisagree=p(r4["disagree"]), nDisagree=num(r4["disagree"]["k"]),
         ciDisagree=ci(r4["disagree"]))
for cat, v in r1["category_repo_share"].items():
    M["pCat" + "".join(w.capitalize() for w in cat.split())] = p(v)
# security scanners: code scanners versus workflow/secret scanners (configurations)
sec = collections.defaultdict(set)
for e in E:
    if e["category"] == "security scanner":
        sec[e["hook"]].add(e["repo"])
CODE = {"github.com/pycqa/bandit", "github.com/semgrep/pre-commit"}
all_sec = set().union(*sec.values()) if sec else set()
code_sec = set().union(*(s for h, s in sec.items() if h in CODE)) if any(h in CODE for h in sec) else set()
M.update(nSecConfigs=num(len(all_sec)), nSecCode=num(len(code_sec)), nSecOther=num(len(all_sec - code_sec)))
# disagreements that involve an exact (==) pin
dis = collections.defaultdict(list)
for d in DR:
    if d["state"] == "disagrees":
        dis[(d["repo"], d["tool"])].append(d["specifier"])
M.update(nDisagreeExact=num(sum(1 for v in dis.values() if any(s.startswith("==") for s in v))))
with open(os.path.join(B, "numbers.tex"), "w", encoding="utf-8", newline="\n") as fh:
    fh.write("% generated by scripts/06_tables.py from results/numbers.json - do not edit\n")
    for k, v in M.items():
        fh.write("\\newcommand{\\%s}{%s}\n" % (k, v))

# Table: categories
rows = sorted(r1["category_repo_share"].items(), key=lambda kv: -kv[1]["k"])
with open(os.path.join(T, "categories.tex"), "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\\begin{tabular}{@{}lrrr@{}}\n\\toprule\nHook category & Configurations & Share & 95\\% CI\\\\\n\\colrule\n")
    for c, v in rows:
        fh.write(f"{c[0].upper() + c[1:]} & {num(v['k'])} & {p(v)} & {ci(v)}\\\\\n")
    fh.write("\\botrule\n\\end{tabular}\n")

# Table: the ten most used hook repositories
by = collections.defaultdict(list)
for e in E:
    by[e["hook"]].append(e)
with open(os.path.join(T, "top_hooks.tex"), "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\\begin{tabular}{@{}lrrrr@{}}\n\\toprule\nHook repository & Configs & Current & Median behind & SHA-pinned\\\\\n\\colrule\n")
    for h in H[:10]:
        es = by[h["hook_repo"]]
        m = [int(e["behind"]) for e in es if e["behind"] != ""]
        cur = sum(1 for x in m if x == 0)
        sha = sum(1 for e in es if e["pin"] == "sha")
        name = h["hook_repo"].replace("github.com/", "").replace("_", "\\_")
        fh.write(f"\\texttt{{{name}}} & {num(int(h['configs_using']))} & {num(100 * cur / len(m), 1)}\\% & "
                 f"{num(statistics.median(m), 1 if statistics.median(m) % 1 else 0)} & {num(100 * sha / len(es), 1)}\\%\\\\\n")
    fh.write("\\botrule\n\\end{tabular}\n")

# Table: drift by tool (tools with at least 10 constrained pairs)
with open(os.path.join(T, "drift.tex"), "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\\begin{tabular}{@{}lrrr@{}}\n\\toprule\nTool & Pairs with a project pin & Disagree & 95\\% CI\\\\\n\\colrule\n")
    for t, v in sorted(r4["by_tool"].items(), key=lambda kv: -kv[1]["n"]):
        if v["n"] >= 10:
            fh.write(f"{t} & {num(v['n'])} & {p(v)} & {ci(v)}\\\\\n")
    fh.write(f"\\colrule\nAll tools & {num(r4['constrained'])} & {p(r4['disagree'])} & {ci(r4['disagree'])}\\\\\n")
    fh.write("\\botrule\n\\end{tabular}\n")
src = collections.Counter(d["source"].split(":")[0] for d in DR if d["state"] == "disagrees")
print("macros:", len(M), "| tables: categories, top_hooks, drift | disagree sources:", dict(src))
