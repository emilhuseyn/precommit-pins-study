r"""Answer RQ1-RQ4 of plan/analysis_plan.md from data/. Every number the manuscript uses is written to
results/numbers.json; tables go to results/*.csv. Nothing is typed by hand.

    py scripts/03_analyse.py
"""
import collections
import csv
import datetime
import json
import math
import os
import re
import sys
import tomllib

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA, RES, FILES = (os.path.join(HERE, x) for x in ("data", "results", os.path.join("data", "files")))
N = {}


def load(name):
    return json.load(open(os.path.join(DATA, name), encoding="utf-8"))


def wilson(k, n, z=1.959964):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(100 * (c - h), 1), round(100 * (c + h), 1)]


def pct(k, n):
    return {"k": k, "n": n, "pct": round(100 * k / n, 1) if n else None, "ci95": wilson(k, n)}


def ver(tag):
    t = re.sub(r"^(v|release-|rel-|version-)", "", tag.strip(), flags=re.I)
    try:
        return Version(t)
    except InvalidVersion:
        return None


def mannwhitney(a, b):
    """Two-sided Mann-Whitney U with normal approximation and tie correction; rank-biserial r = 1 - 2U/(n1 n2)."""
    n1, n2 = len(a), len(b)
    allv = sorted([(x, 0) for x in a] + [(x, 1) for x in b])
    ranks, i = [0.0] * len(allv), 0
    ties = 0
    while i < len(allv):
        j = i
        while j + 1 < len(allv) and allv[j + 1][0] == allv[i][0]:
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[k] = r
        t = j - i + 1
        ties += t ** 3 - t
        i = j + 1
    r1 = sum(r for r, (_, g) in zip(ranks, allv) if g == 0)
    u1 = r1 - n1 * (n1 + 1) / 2
    nn = n1 + n2
    sd = math.sqrt(n1 * n2 / 12 * ((nn + 1) - ties / (nn * (nn - 1))))
    z = (u1 - n1 * n2 / 2) / sd if sd else 0.0
    p = math.erfc(abs(z) / math.sqrt(2))
    return {"n1": n1, "n2": n2, "U": u1, "z": round(z, 3), "p": p, "rank_biserial": round(1 - 2 * u1 / (n1 * n2), 3)}


def median(xs):
    s = sorted(xs)
    n = len(s)
    return None if not n else s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def poetry_to_pep440(c):
    c = c.strip()
    m = re.fullmatch(r"\^(\d+)(?:\.(\d+))?(?:\.(\d+))?", c)
    if m:
        a, b, d = (int(x) if x else 0 for x in m.groups())
        lo = f"{a}.{b}.{d}"
        hi = f"{a + 1}.0.0" if a > 0 else (f"0.{b + 1}.0" if b > 0 else f"0.0.{d + 1}")
        return f">={lo},<{hi}"
    m = re.fullmatch(r"~(\d+)(?:\.(\d+))?(?:\.(\d+))?", c)
    if m:
        a, b, d = (int(x) if x else 0 for x in m.groups())
        return f">={a}.{b}.{d},<{a}.{b + 1}.0" if m.group(2) else f">={a}.0.0,<{a + 1}.0.0"
    if re.fullmatch(r"\d+(\.\d+)*", c):
        return "==" + c
    return "" if c in ("*", "") else c


def project_specs(key):
    """tool name (PyPI, lower-case) -> list of (source, specifier string) from the repo's own dev pins."""
    folder = os.path.join(FILES, key.replace("/", "__"))
    out = collections.defaultdict(list)

    def add(src, req):
        try:
            r = Requirement(req)
        except InvalidRequirement:
            return
        out[r.name.lower().replace("_", "-")].append((src, str(r.specifier)))
    p = os.path.join(folder, "pyproject.toml")
    if os.path.exists(p):
        try:
            d = tomllib.load(open(p, "rb"))
        except Exception:  # noqa: BLE001
            d = {}
        for grp in (d.get("project", {}).get("optional-dependencies") or {}).values():
            for req in grp if isinstance(grp, list) else []:
                if isinstance(req, str):
                    add("pyproject:optional-dependencies", req)
        for grp in (d.get("dependency-groups") or {}).values():
            for req in grp if isinstance(grp, list) else []:
                if isinstance(req, str):
                    add("pyproject:dependency-groups", req)
        tool = d.get("tool", {})
        poetry = tool.get("poetry", {}) if isinstance(tool, dict) else {}
        groups = [g.get("dependencies", {}) for g in (poetry.get("group") or {}).values() if isinstance(g, dict)]
        groups.append(poetry.get("dev-dependencies") or {})
        for g in groups:
            for name, spec in (g or {}).items():
                s = spec if isinstance(spec, str) else (spec.get("version", "") if isinstance(spec, dict) else "")
                add("pyproject:poetry", f"{name}{poetry_to_pep440(s)}" if s else name)
        for g in ((tool.get("uv", {}) or {}).get("dev-dependencies") or [],
                  *((tool.get("pdm", {}) or {}).get("dev-dependencies") or {}).values()):
            for req in g if isinstance(g, list) else []:
                if isinstance(req, str):
                    add("pyproject:uv/pdm", req)
    for root, _, files in os.walk(folder):
        for f in files:
            if f.endswith(".txt") and "requirement" in os.path.join(root, f).lower():
                for line in open(os.path.join(root, f), encoding="utf-8", errors="replace"):
                    line = line.split("#")[0].strip()
                    if line and not line.startswith(("-", "git+", "http")):
                        add("requirements", line)
    return out


def main():
    os.makedirs(RES, exist_ok=True)
    top, repos, heads = load("top_dump.json"), load("pypi_repos.json"), load("heads.json")
    idx, parsed, tags = load("files_index.json"), load("parsed.json"), load("hook_tags.json")
    rel, mirrors = load("tool_releases.json"), load("mirrors.json")
    cats = {r["hook_repo"]: r["category"] for r in csv.DictReader(open(os.path.join(HERE, "research",
                                                                                       "hook_categories.csv"),
                                                                          encoding="utf-8"))}
    # ---- frame -----------------------------------------------------------------------------------------
    projects = [r["project"] for r in top["rows"][:5000]]
    with_gh = [p for p in projects if repos.get(p, {}).get("owner")]
    pypi_fail = [p for p in projects if repos.get(p, {}).get("status") != 200]
    keys = sorted({f"{repos[p]['owner']}/{repos[p]['repo']}" for p in with_gh})
    resolved = [k for k in keys if heads.get(k, {}).get("sha")]
    cfg_err = sum(1 for k in resolved for f in (".pre-commit-config.yaml", ".pre-commit-config.yml")
                  if idx.get(f"{k}|{f}") not in (200, 404, 410, None))
    ok = [r for r in parsed if r["ok"]]
    snap = sorted(v["at"] for v in heads.values() if v.get("at"))
    N["frame"] = {"top_dump_last_update": top.get("last_update"), "projects": len(projects),
                  "pypi_lookup_failed": len(pypi_fail), "with_github_url": len(with_gh),
                  "distinct_repositories": len(keys), "head_resolved": len(resolved),
                  "head_unresolved": len(keys) - len(resolved), "config_fetch_errors": cfg_err,
                  "with_config": len(parsed), "config_unparseable": len(parsed) - len(ok),
                  "config_share": pct(len(parsed), len(resolved)), "snapshot_first": snap[0] if snap else None,
                  "snapshot_last": snap[-1] if snap else None,
                  "yml_variant": sum(1 for r in parsed if r["file"].endswith(".yml"))}
    # ---- RQ1 -------------------------------------------------------------------------------------------
    remote = [(r["key"], e) for r in ok for e in r["entries"] if e["kind"] == "remote"]
    local = sum(1 for r in ok for e in r["entries"] if e["kind"] == "local")
    meta = sum(1 for r in ok for e in r["entries"] if e["kind"] == "meta")
    builtin = sum(1 for r in ok for e in r["entries"] if e["kind"] == "builtin")
    use = collections.Counter(e["norm"] for _, e in remote)
    repos_per_hook = collections.Counter()
    for k, e in {(k, e["norm"]): e for k, e in remote}.items():
        repos_per_hook[k[1]] += 1
    cat_repo = collections.defaultdict(set)
    for k, e in remote:
        cat_repo[cats.get(e["norm"], "other")].add(k)
    unmapped = collections.Counter(e["norm"] for _, e in remote if e["norm"] not in cats)
    per_repo = [sum(1 for e in r["entries"] if e["kind"] == "remote") for r in ok]
    N["rq1"] = {"remote_entries": len(remote), "local_entries": local, "meta_entries": meta, "builtin_entries": builtin,
                "distinct_hook_repositories": len(use), "median_remote_per_config": median(per_repo),
                "configs_with_zero_remote": sum(1 for x in per_repo if x == 0),
                "category_repo_share": {c: pct(len(v), len(ok)) for c, v in sorted(cat_repo.items())},
                "entries_in_unmapped_hook_repos": sum(unmapped.values()),
                "unmapped_hook_repositories": len(unmapped)}
    with open(os.path.join(RES, "rq1_hook_repositories.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["hook_repo", "category", "configs_using", "entries"])
        for u, n in repos_per_hook.most_common():
            w.writerow([u, cats.get(u, "other"), n, use[u]])
    # ---- RQ2 / RQ3 per entry -----------------------------------------------------------------------------
    rows = []
    for k, e in remote:
        t = tags.get(e["norm"], {})
        resolvable = t.get("rc") == 0
        tagmap = t.get("tags", {})
        versions = {name: ver(name) for name in tagmap}
        released = sorted({v for v in versions.values() if v and not v.is_prerelease})
        pinned, how = None, None
        if e["pin"] == "ref":
            if e["rev"] in tagmap:
                pinned, how = versions.get(e["rev"]), "tag"
            else:
                how = "ref not a tag"
        elif e["pin"] == "sha":
            hits = [versions[n] for n, s in tagmap.items() if s == e["rev"] and versions.get(n)]
            if hits:
                pinned, how = max(hits), "sha=tag"
            elif e.get("comment") and re.search(r"frozen:\s*(\S+)", e["comment"] or ""):
                pinned, how = ver(re.search(r"frozen:\s*(\S+)", e["comment"]).group(1)), "frozen comment"
            else:
                how = "sha unmatched"
        behind = None
        if pinned and released:
            behind = sum(1 for v in released if v > pinned)
        rows.append({"repo": k, "hook": e["norm"], "category": cats.get(e["norm"], "other"), "pin": e["pin"],
                     "rev": e["rev"], "resolvable": resolvable, "resolved_by": how,
                     "pinned": str(pinned) if pinned else "", "latest": str(released[-1]) if released else "",
                     "behind": behind,
                     "frozen_comment": bool(e.get("comment") and "frozen" in (e.get("comment") or ""))})
    with open(os.path.join(RES, "entries.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    measured = [r for r in rows if r["behind"] is not None]
    pins = collections.Counter(r["pin"] for r in rows)
    sha_rows = [r for r in rows if r["pin"] == "sha"]
    N["rq3"] = {"pin_kind": {k: pct(v, len(rows)) for k, v in pins.items()},
                "sha_with_frozen_comment": pct(sum(1 for r in sha_rows if r["frozen_comment"]), len(sha_rows)),
                "ref_not_a_tag": sum(1 for r in rows if r["resolved_by"] == "ref not a tag"),
                "sha_unmatched": sum(1 for r in rows if r["resolved_by"] == "sha unmatched"),
                "unresolvable_hook_repositories": sum(1 for u in use if tags.get(u, {}).get("rc") != 0),
                "entries_in_unresolvable": sum(1 for r in rows if not r["resolvable"]),
                "configs_with_unresolvable": len({r["repo"] for r in rows if not r["resolvable"]})}
    red, owners = load("hook_redirects.json"), load("former_owners.json")
    moved = {u for u, v in red.items() if v["status"] == 301}
    N["rq3"]["moved"] = {"hook_repositories": len(moved),
                         "entries": pct(sum(1 for r in rows if r["hook"] in moved), len(rows)),
                         "configs": pct(len({r["repo"] for r in rows if r["hook"] in moved}), len(ok)),
                         "former_owner_accounts": len({u.split("/")[1] for u in moved}),
                         "former_owner_missing": sum(1 for o in {u.split("/")[1] for u in moved}
                                                     if owners.get(o, {}).get("status") == 404),
                         "not_github": sum(1 for u in red if not u.startswith("github.com/")),
                         "http_404": sum(1 for v in red.values() if v["status"] == 404)}
    N["rq2"] = {"entries_measured": len(measured), "entries_not_measured": len(rows) - len(measured),
                "current": pct(sum(1 for r in measured if r["behind"] == 0), len(measured)),
                "median_behind": median([r["behind"] for r in measured]),
                "behind_5_or_more": pct(sum(1 for r in measured if r["behind"] >= 5), len(measured)),
                "resolved_by": dict(collections.Counter(r["resolved_by"] for r in measured))}
    # days behind for PyPI-mirroring hooks, at the snapshot
    cutoff = N["frame"]["snapshot_last"]
    days = []
    for r in measured:
        proj = mirrors.get(r["hook"])
        rr = rel.get(proj or "", {}).get("releases") if proj else None
        if not rr:
            continue
        dated = {ver(v): t for v, t in rr.items() if ver(v) and not ver(v).is_prerelease and t <= cutoff}
        if not dated:
            continue
        pv = ver(r["pinned"])
        if pv not in dated:
            continue
        latest = max(dated)
        d0 = datetime.datetime.fromisoformat(dated[pv].replace("Z", "+00:00"))
        d1 = datetime.datetime.fromisoformat(dated[latest].replace("Z", "+00:00"))
        days.append((d1 - d0).days)
    N["rq2"]["days_behind"] = {"entries": len(days), "median": median(days),
                               "over_365": pct(sum(1 for d in days if d > 365), len(days))}
    # automation association, per configuration
    def auto(key):
        folder = os.path.join(FILES, key.replace("/", "__"))
        flags = {"ci_section": False, "dependabot": False, "renovate": False}
        rec = next(r for r in ok if r["key"] == key)
        flags["ci_section"] = rec["ci_section"]
        for f in (".github/dependabot.yml", ".github/dependabot.yaml"):
            p = os.path.join(folder, f)
            if os.path.exists(p) and re.search(r"package-ecosystem:\s*['\"]?pre-commit", open(p, encoding="utf-8",
                                                                                          errors="replace").read()):
                flags["dependabot"] = True
        for f in ("renovate.json", "renovate.json5", ".github/renovate.json", ".github/renovate.json5", ".renovaterc",
                  ".renovaterc.json"):
            p = os.path.join(folder, f)
            if os.path.exists(p) and "pre-commit" in open(p, encoding="utf-8", errors="replace").read():
                flags["renovate"] = True
        return flags
    per_cfg = collections.defaultdict(list)
    for r in measured:
        per_cfg[r["repo"]].append(r["behind"])
    flags = {k: auto(k) for k in per_cfg}
    a = [sum(v) / len(v) for k, v in per_cfg.items() if any(flags[k].values())]
    b = [sum(v) / len(v) for k, v in per_cfg.items() if not any(flags[k].values())]
    N["rq2"]["automation"] = {
        "configs": len(per_cfg),
        "any_indicator": pct(len(a), len(per_cfg)),
        "ci_section": sum(1 for f in flags.values() if f["ci_section"]),
        "dependabot": sum(1 for f in flags.values() if f["dependabot"]),
        "renovate": sum(1 for f in flags.values() if f["renovate"]),
        "median_mean_behind_with": median(a), "median_mean_behind_without": median(b),
        "all_current_with": pct(sum(1 for k, v in per_cfg.items() if any(flags[k].values()) and max(v) == 0), len(a)),
        "all_current_without": pct(sum(1 for k, v in per_cfg.items() if not any(flags[k].values()) and max(v) == 0),
                                   len(b)),
        "mann_whitney": mannwhitney(a, b) if a and b else None}
    # ---- RQ4 drift ---------------------------------------------------------------------------------------
    drift = []
    for r in measured:
        proj = mirrors.get(r["hook"])
        if not proj or proj in ("pre-commit-hooks",):
            continue
        specs = project_specs(r["repo"]).get(proj.lower())
        if not specs:
            continue
        pv = Version(r["pinned"])
        for src, s in specs:
            try:
                ss = SpecifierSet(s)
            except InvalidSpecifier:
                continue
            state = "unpinned" if not s else ("agrees" if ss.contains(pv, prereleases=True) else "disagrees")
            drift.append({"repo": r["repo"], "tool": proj, "hook_version": r["pinned"], "source": src,
                          "specifier": s, "state": state})
    if drift:
        with open(os.path.join(RES, "rq4_drift.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(drift[0]))
            w.writeheader()
            w.writerows(drift)
    pairs = {}
    for d in drift:   # one verdict per (repo, tool): disagrees if any declared pin excludes the hook version
        k = (d["repo"], d["tool"])
        order = {"disagrees": 2, "agrees": 1, "unpinned": 0}
        if k not in pairs or order[d["state"]] > order[pairs[k]]:
            pairs[k] = d["state"]
    constrained = [v for v in pairs.values() if v != "unpinned"]
    N["rq4"] = {"repo_tool_pairs": len(pairs), "unpinned_in_project": sum(1 for v in pairs.values() if v == "unpinned"),
                "constrained": len(constrained),
                "disagree": pct(sum(1 for v in constrained if v == "disagrees"), len(constrained)),
                "by_tool": {t: pct(sum(1 for (r, tt), v in pairs.items() if tt == t and v == "disagrees"),
                                   sum(1 for (r, tt), v in pairs.items() if tt == t and v != "unpinned"))
                            for t in sorted({t for _, t in pairs})}}
    json.dump(N, open(os.path.join(RES, "numbers.json"), "w", encoding="utf-8"), indent=1, default=str)
    print(json.dumps(N, indent=1, default=str)[:6000])
    print("\nunmapped hook repositories (top 25):", unmapped.most_common(25))


main()
