r"""Collect the frame for row 44 (plan/analysis_plan.md, "Population and snapshot"). Auth-free, resumable.

    py scripts/01_collect.py            # all steps
Outputs in data/: top_dump.json, pypi_repos.json, heads.json, files/<owner>__<repo>/<path> and files_index.json.
"""
import concurrent.futures as cf
import datetime
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
FILES = os.path.join(DATA, "files")
UA = {"User-Agent": "precommit-pins-study/1.0 (research; auth-free)"}
N = 5000
GH = re.compile(r"https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)")
CONFIGS = [".pre-commit-config.yaml", ".pre-commit-config.yml"]
SIDE = ["pyproject.toml", "requirements-dev.txt", "requirements_dev.txt", "dev-requirements.txt",
        "requirements-test.txt", "requirements-lint.txt", "requirements/dev.txt", "requirements/lint.txt",
        "requirements/test.txt", "requirements/development.txt", ".github/dependabot.yml",
        ".github/dependabot.yaml", "renovate.json", "renovate.json5", ".github/renovate.json",
        ".github/renovate.json5", ".renovaterc", ".renovaterc.json"]


def get(url, timeout=40, tries=3):
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return e.code, b""
            last = e.code
        except Exception as e:  # noqa: BLE001
            last = type(e).__name__
        time.sleep(2 * (k + 1))
    return last, b""


def jload(name, default):
    p = os.path.join(DATA, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def jsave(name, obj):
    p = os.path.join(DATA, name)
    tmp = p + ".tmp"
    json.dump(obj, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    os.replace(tmp, p)


def step_top():
    if os.path.exists(os.path.join(DATA, "top_dump.json")):
        return jload("top_dump.json", None)
    s, b = get("https://hugovk.github.io/top-pypi-packages/top-pypi-packages.min.json", 120)
    assert s == 200, s
    d = json.loads(b)
    d["fetched_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    jsave("top_dump.json", d)
    return d


def repo_of(project):
    s, b = get(f"https://pypi.org/pypi/{project}/json")
    if s != 200:
        return project, {"status": s}
    info = json.loads(b)["info"]
    urls = list((info.get("project_urls") or {}).items()) + [("home_page", info.get("home_page") or "")]
    for label, u in urls:
        m = GH.match(u or "")
        if m:
            owner, repo = m.group(1), re.sub(r"\.git$", "", m.group(2))
            return project, {"status": 200, "owner": owner, "repo": repo, "from": label}
    return project, {"status": 200, "owner": None}


def step_repos(top):
    done = jload("pypi_repos.json", {})
    todo = [r["project"] for r in top["rows"][:N] if r["project"] not in done]
    print("pypi: %d cached, %d to fetch" % (len(done), len(todo)))
    with cf.ThreadPoolExecutor(16) as ex:
        for i, (p, v) in enumerate(ex.map(repo_of, todo), 1):
            done[p] = v
            if i % 500 == 0:
                jsave("pypi_repos.json", done)
                print("   pypi", i)
    jsave("pypi_repos.json", done)
    return done


def head_of(key):
    owner, repo = key.split("/", 1)
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="echo", GCM_INTERACTIVE="never")
    try:
        r = subprocess.run(["git", "-c", "credential.helper=", "-c", "core.askPass=", "ls-remote", f"https://github.com/{owner}/{repo}.git", "HEAD"],
                           capture_output=True, text=True, timeout=60, env=env)
        line = r.stdout.strip().split("\n")[0]
        sha = line.split()[0] if line else None
        return key, {"sha": sha, "rc": r.returncode,
                     "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                     "err": None if sha else r.stderr.strip()[:200]}
    except subprocess.TimeoutExpired:
        return key, {"sha": None, "rc": None, "err": "timeout"}


def step_heads(repos):
    keys = sorted({f"{v['owner']}/{v['repo']}" for v in repos.values() if v.get("owner")}, key=str.lower)
    heads = jload("heads.json", {})
    todo = [k for k in keys if k not in heads or not heads[k].get("sha") and heads[k].get("err") == "timeout"]
    print("heads: %d repos, %d to resolve" % (len(keys), len(todo)))
    with cf.ThreadPoolExecutor(12) as ex:
        for i, (k, v) in enumerate(ex.map(head_of, todo), 1):
            heads[k] = v
            if i % 300 == 0:
                jsave("heads.json", heads)
                print("   heads", i)
    jsave("heads.json", heads)
    return heads


def fetch_one(args):
    key, sha, path = args
    s, b = get(f"https://raw.githubusercontent.com/{key}/{sha}/{path}")
    if s == 200:
        out = os.path.join(FILES, key.replace("/", "__"), path)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, "wb").write(b)
    return key, path, s


def step_files(heads):
    idx = jload("files_index.json", {})
    live = {k: v["sha"] for k, v in heads.items() if v.get("sha")}
    todo = [(k, s, p) for k, s in live.items() for p in CONFIGS if f"{k}|{p}" not in idx]
    print("configs: %d requests" % len(todo))
    with cf.ThreadPoolExecutor(16) as ex:
        for k, p, s in ex.map(fetch_one, todo):
            idx[f"{k}|{p}"] = s
    jsave("files_index.json", idx)
    have = sorted({k for k in live if any(idx.get(f"{k}|{p}") == 200 for p in CONFIGS)})
    todo = [(k, live[k], p) for k in have for p in SIDE if f"{k}|{p}" not in idx]
    print("repos with a config: %d; side files: %d requests" % (len(have), len(todo)))
    with cf.ThreadPoolExecutor(16) as ex:
        for i, (k, p, s) in enumerate(ex.map(fetch_one, todo), 1):
            idx[f"{k}|{p}"] = s
            if i % 2000 == 0:
                jsave("files_index.json", idx)
    jsave("files_index.json", idx)
    errs = sum(1 for v in idx.values() if v not in (200, 404, 410))
    print("files_index: %d entries, %d non-404 failures" % (len(idx), errs))


def main():
    os.makedirs(FILES, exist_ok=True)
    top = step_top()
    print("top dump last_update:", top.get("last_update"), "rows:", len(top["rows"]))
    repos = step_repos(top)
    heads = step_heads(repos)
    step_files(heads)
    print("done", datetime.datetime.now().isoformat(timespec="seconds"))


main()
