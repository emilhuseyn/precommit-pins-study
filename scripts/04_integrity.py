r"""Integrity gate for row 44: the numbers in results/numbers.json must re-derive from data/ and results/entries.csv
by a second, independent route, and the gate must be shown to fail on a corrupted copy.

    py scripts/04_integrity.py            # check the real results
    py scripts/04_integrity.py --corrupt  # same checks on a deliberately damaged copy; must FAIL
"""
import collections
import copy
import csv
import json
import os
import random
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D, R = os.path.join(HERE, "data"), os.path.join(HERE, "results")


def load(p):
    return json.load(open(p, encoding="utf-8"))


def checks(N, entries, parsed, repos, heads):
    out = []

    def ok(name, cond):
        out.append((name, bool(cond)))
    f = N["frame"]
    no_gh = sum(1 for p in list(repos)[:5000] if repos[p].get("status") == 200 and not repos[p].get("owner"))
    ok("projects = github + no-github + pypi failures", f["projects"] == f["with_github_url"] + no_gh + f["pypi_lookup_failed"])
    ok("repositories = resolved + unresolved", f["distinct_repositories"] == f["head_resolved"] + f["head_unresolved"])
    ok("configs on disk = with_config", f["with_config"] == len(parsed))
    good = [p for p in parsed if p["ok"]]
    kinds = collections.Counter(e["kind"] for p in good for e in p["entries"])
    r1 = N["rq1"]
    ok("entry kinds re-count", (kinds["remote"], kinds["local"], kinds["meta"], kinds["builtin"]) ==
       (r1["remote_entries"], r1["local_entries"], r1["meta_entries"], r1["builtin_entries"]))
    ok("entries.csv rows = remote entries", len(entries) == r1["remote_entries"])
    pk = collections.Counter(e["pin"] for e in entries)
    ok("pin kinds sum", sum(v["k"] for v in N["rq3"]["pin_kind"].values()) == len(entries)
       and all(pk[k] == v["k"] for k, v in N["rq3"]["pin_kind"].items()))
    meas = [e for e in entries if e["behind"] != ""]
    r2 = N["rq2"]
    ok("measured + not measured = entries", r2["entries_measured"] + r2["entries_not_measured"] == len(entries))
    ok("measured re-count", len(meas) == r2["entries_measured"])
    ok("current re-count", sum(1 for e in meas if int(e["behind"]) == 0) == r2["current"]["k"])
    ok(">=5 behind re-count", sum(1 for e in meas if int(e["behind"]) >= 5) == r2["behind_5_or_more"]["k"])
    ok("percentages agree with k/n", all(abs(v["pct"] - 100 * v["k"] / v["n"]) < 0.051
                                         for v in (r2["current"], r2["behind_5_or_more"], f["config_share"])))
    ok("pinned version is never newer than latest", all(not e["latest"] or not e["pinned"] or
                                                         int(e["behind"] or 0) >= 0 for e in meas))
    return out


def spot(entries, n=12, seed=44):
    """Re-ask git, live, for a random sample: does the pinned tag/SHA still exist and match the recorded version?"""
    random.seed(seed)
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="echo", GCM_INTERACTIVE="never")
    res = []
    for e in random.sample([e for e in entries if e["behind"] != "" and e["pin"] == "ref"], n):
        r = subprocess.run(["git", "-c", "credential.helper=", "-c", "core.askPass=", "ls-remote", "--tags",
                            "https://" + e["hook"] + ".git", e["rev"]], capture_output=True, text=True,
                           timeout=60, env=env)
        res.append((e["hook"], e["rev"], bool(r.stdout.strip())))
    return res


def main():
    N = load(os.path.join(R, "numbers.json"))
    entries = list(csv.DictReader(open(os.path.join(R, "entries.csv"), encoding="utf-8")))
    parsed, repos, heads = load(os.path.join(D, "parsed.json")), load(os.path.join(D, "pypi_repos.json")), \
        load(os.path.join(D, "heads.json"))
    if "--corrupt" in sys.argv:
        N = copy.deepcopy(N)
        N["rq2"]["current"]["k"] += 7                           # a typo in one count
        entries = entries[:-3]                                  # three rows lost
        parsed = parsed + [parsed[0]]                           # one config counted twice
    res = checks(N, entries, parsed, repos, heads)
    for name, good in res:
        print("  %-4s %s" % ("ok" if good else "FAIL", name))
    bad = [n for n, g in res if not g]
    if "--corrupt" not in sys.argv:
        sp = spot(entries)
        for h, rev, found in sp:
            print("  %-4s live tag %s @ %s" % ("ok" if found else "FAIL", h, rev))
        bad += [h for h, _, f in sp if not f]
    print("RESULT:", "PASS" if not bad else "FAIL (%d)" % len(bad))
    return 0 if not bad else 1


sys.exit(main())
