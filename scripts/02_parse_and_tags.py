r"""Parse every fetched pre-commit config and resolve the tags of every hook repository. Auth-free, resumable.

    py scripts/02_parse_and_tags.py
Outputs in data/: parsed.json (one record per repos: entry), hook_tags.json (git ls-remote --tags per hook repo),
tool_releases.json (PyPI upload dates for hook repositories that mirror a PyPI project).
"""
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

import yaml

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
FILES = os.path.join(DATA, "files")
UA = {"User-Agent": "precommit-pins-study/1.0 (research; auth-free)"}
CONFIGS = [".pre-commit-config.yaml", ".pre-commit-config.yml"]
SHA = re.compile(r"^[0-9a-f]{40}$")
REV_LINE = re.compile(r"^\s*rev:\s*['\"]?([^'\"\s#]+)['\"]?\s*(?:#\s*(.*))?$")

# hook repository (normalised) -> PyPI project it mirrors; checked against PyPI before use
MIRRORS = {
    "github.com/astral-sh/ruff-pre-commit": "ruff", "github.com/charliermarsh/ruff-pre-commit": "ruff",
    "github.com/psf/black-pre-commit-mirror": "black", "github.com/psf/black": "black",
    "github.com/pre-commit/mirrors-mypy": "mypy", "github.com/pycqa/flake8": "flake8",
    "github.com/pycqa/isort": "isort", "github.com/asottile/pyupgrade": "pyupgrade",
    "github.com/codespell-project/codespell": "codespell", "github.com/pycqa/bandit": "bandit",
    "github.com/pycqa/pydocstyle": "pydocstyle", "github.com/pycqa/autoflake": "autoflake",
    "github.com/pycqa/docformatter": "docformatter", "github.com/asottile/add-trailing-comma": "add-trailing-comma",
    "github.com/asottile/reorder-python-imports": "reorder-python-imports",
    "github.com/adamchainz/blacken-docs": "blacken-docs", "github.com/asottile/blacken-docs": "blacken-docs",
    "github.com/python-jsonschema/check-jsonschema": "check-jsonschema",
    "github.com/zizmorcore/zizmor-pre-commit": "zizmor", "github.com/woodruffw/zizmor-pre-commit": "zizmor",
    "github.com/astral-sh/uv-pre-commit": "uv", "github.com/pre-commit/pre-commit-hooks": "pre-commit-hooks",
    "github.com/pycqa/pylint": "pylint", "github.com/pylint-dev/pylint": "pylint",
    "github.com/hadialqattan/pycln": "pycln", "github.com/tox-dev/pyproject-fmt": "pyproject-fmt",
    "github.com/abravalheri/validate-pyproject": "validate-pyproject", "github.com/rhysd/actionlint": None,
    "github.com/adamchainz/django-upgrade": "django-upgrade", "github.com/pycqa/flake8-docstrings": None,
    "github.com/executablebooks/mdformat": "mdformat", "github.com/sphinx-contrib/sphinx-lint": "sphinx-lint",
    "github.com/pre-commit/mirrors-clang-format": "clang-format", "github.com/igorshubovych/markdownlint-cli": None,
    "github.com/crate-ci/typos": "typos", "github.com/pappasam/toml-sort": "toml-sort",
    "github.com/nbqa-dev/nbqa": "nbqa", "github.com/kynan/nbstripout": "nbstripout",
    "github.com/pre-commit/mirrors-prettier": None, "github.com/rbubley/mirrors-prettier": None,
    "github.com/tox-dev/tox-ini-fmt": "tox-ini-fmt", "github.com/macisamuele/language-formatters-pre-commit-hooks": None,
    "github.com/google/yamlfmt": None, "github.com/adrienverge/yamllint": "yamllint",
    "github.com/shellcheck-py/shellcheck-py": "shellcheck-py", "github.com/scop/pre-commit-shfmt": None,
    "github.com/jsh9/pydoclint": "pydoclint", "github.com/pycqa/doc8": "doc8", "github.com/regebro/pyroma": "pyroma",
    "github.com/mgedmin/check-manifest": "check-manifest", "github.com/pre-commit/mirrors-autopep8": "autopep8",
    "github.com/hhatto/autopep8": "autopep8", "github.com/pycqa/autopep8": "autopep8",
    "github.com/asottile/setup-cfg-fmt": "setup-cfg-fmt", "github.com/pre-commit/pygrep-hooks": None,
    "github.com/microsoft/pyright": None, "github.com/rbubley/mirrors-pyright": None,
    "github.com/rtts/djhtml": "djhtml", "github.com/biomejs/pre-commit": None,
    # former locations and further PyPI-backed hooks (added 19.11.2026 after the first unmapped list)
    "github.com/ambv/black": "black", "github.com/python/black": "black", "github.com/timothycrosley/isort": "isort",
    "github.com/pre-commit/mirrors-isort": "isort", "github.com/sirosen/check-jsonschema": "check-jsonschema",
    "github.com/asottile/reorder_python_imports": "reorder-python-imports", "github.com/hukkin/mdformat": "mdformat",
    "github.com/robertcraigie/pyright-python": "pyright", "github.com/astral-sh/ty-pre-commit": "ty",
    "github.com/commitizen-tools/commitizen": "commitizen", "github.com/marcogorelli/cython-lint": "cython-lint",
    "github.com/jorisroovers/gitlint": "gitlint", "github.com/yelp/detect-secrets": "detect-secrets",
    "github.com/econchick/interrogate": "interrogate", "github.com/rstcheck/rstcheck": "rstcheck",
    "github.com/asottile/yesqa": "yesqa", "github.com/myint/autoflake": "autoflake",
    "github.com/pre-commit/mirrors-pylint": "pylint", "gitlab.com/pycqa/flake8": "flake8",
    "github.com/jendrikseipp/vulture": "vulture", "github.com/google/yapf": "yapf", "github.com/omnilib/ufmt": "ufmt",
    "github.com/numpy/numpydoc": "numpydoc", "github.com/mwouts/jupytext": "jupytext",
    "github.com/netromdk/vermin": "vermin", "github.com/lyz-code/yamlfix": "yamlfix",
    "github.com/hukkin/docformatter": "docformatter", "github.com/fsfe/reuse-tool": "reuse",
    "github.com/python-poetry/poetry": "poetry", "github.com/henryiii/check-sdist": "check-sdist",
    "github.com/ariebovenberg/slotscheck": "slotscheck", "github.com/keewis/blackdoc": "blackdoc",
    "github.com/lilspazjoekp/docstrfmt": "docstrfmt", "github.com/marcogorelli/absolufy-imports": "absolufy-imports",
    "github.com/marcogorelli/auto-walrus": "auto-walrus", "github.com/isidentical/teyit": "teyit",
    "github.com/sqlalchemyorg/zimports": "zimports", "github.com/compilerla/conventional-pre-commit": "conventional-pre-commit",
    "github.com/facebook/pyrefly-pre-commit": "pyrefly", "github.com/tox-dev/tox-toml-fmt": "tox-toml-fmt",
    "github.com/asottile/seed-isort-config": "seed-isort-config",
}


def norm(url):
    u = url.strip().lower()
    u = re.sub(r"^(https?://|git@|ssh://git@)", "", u).replace("github.com:", "github.com/")
    return re.sub(r"(\.git)?/?$", "", u)


def parse_repo(key):
    folder = os.path.join(FILES, key.replace("/", "__"))
    for name in CONFIGS:
        p = os.path.join(folder, name)
        if os.path.exists(p):
            text = open(p, encoding="utf-8", errors="replace").read()
            break
    else:
        return None
    rec = {"key": key, "file": name, "ok": True, "entries": [], "ci_section": False}
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        rec.update(ok=False, error=str(e)[:200])
        return rec
    if not isinstance(doc, dict):
        rec.update(ok=False, error="top level is not a mapping")
        return rec
    rec["ci_section"] = isinstance(doc.get("ci"), dict)
    comments = {}
    for line in text.splitlines():
        m = REV_LINE.match(line)
        if m:
            comments.setdefault(m.group(1), m.group(2))
    for r in doc.get("repos") or []:
        if not isinstance(r, dict):
            continue
        url = str(r.get("repo", ""))
        rev = None if r.get("rev") is None else str(r.get("rev"))
        hooks = [h.get("id") for h in (r.get("hooks") or []) if isinstance(h, dict)]
        kind = url if url in ("local", "meta", "builtin") else "remote"
        e = {"url": url, "norm": norm(url) if kind == "remote" else url, "kind": kind, "rev": rev, "hooks": hooks}
        if kind == "remote":
            e["pin"] = "missing" if not rev else "sha" if SHA.match(rev) else "ref"
            e["comment"] = comments.get(rev) if rev else None
        rec["entries"].append(e)
    return rec


def ls_tags(nurl):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="echo", GCM_INTERACTIVE="never")
    url = "https://" + nurl if not nurl.startswith("http") else nurl
    try:
        r = subprocess.run(["git", "-c", "credential.helper=", "-c", "core.askPass=", "ls-remote", "--tags", url + ".git"], capture_output=True, text=True,
                           timeout=90, env=env)
    except subprocess.TimeoutExpired:
        return nurl, {"rc": None, "err": "timeout", "tags": {}}
    tags = {}
    for line in r.stdout.splitlines():
        sha, ref = line.split("\t")
        name = ref[len("refs/tags/"):]
        if name.endswith("^{}"):
            tags[name[:-3]] = sha          # peeled commit wins over the tag object
        else:
            tags.setdefault(name, sha)
    return nurl, {"rc": r.returncode, "err": None if r.returncode == 0 else r.stderr.strip()[:200], "tags": tags}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def location(nurl):
    """GitHub answers a renamed or transferred repository with 301 to its new name; record it, do not follow."""
    if not nurl.startswith("github.com/"):
        return nurl, {"status": None, "location": None}
    op = urllib.request.build_opener(NoRedirect)
    for k in range(3):
        try:
            r = op.open(urllib.request.Request("https://" + nurl, headers=UA, method="HEAD"), timeout=40)
            return nurl, {"status": r.status, "location": None}
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 404):
                return nurl, {"status": e.code, "location": e.headers.get("Location")}
        except Exception:  # noqa: BLE001
            pass
        time.sleep(3 * (k + 1))
    return nurl, {"status": None, "location": None}


def get(url):
    for k in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, b""
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2 * (k + 1))
    return None, b""


def releases(project):
    s, b = get(f"https://pypi.org/pypi/{project}/json")
    if s != 200:
        return project, {"status": s}
    d = json.loads(b)
    out = {}
    for ver, files in d.get("releases", {}).items():
        times = [f.get("upload_time_iso_8601") for f in files if f.get("upload_time_iso_8601")]
        if times:
            out[ver] = min(times)
    return project, {"status": 200, "releases": out}


def main():
    heads = json.load(open(os.path.join(DATA, "heads.json"), encoding="utf-8"))
    parsed = [r for r in (parse_repo(k) for k in sorted(heads)) if r]
    json.dump(parsed, open(os.path.join(DATA, "parsed.json"), "w", encoding="utf-8"), indent=0)
    bad = sum(1 for r in parsed if not r["ok"])
    print("configs parsed: %d (%d unparseable)" % (len(parsed), bad))
    hook_urls = sorted({e["norm"] for r in parsed for e in r["entries"] if e["kind"] == "remote"})
    p = os.path.join(DATA, "hook_tags.json")
    tags = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    todo = [u for u in hook_urls if u not in tags or tags[u].get("err") == "timeout"]
    print("hook repositories: %d distinct, %d to resolve" % (len(hook_urls), len(todo)))
    with cf.ThreadPoolExecutor(12) as ex:
        for u, v in ex.map(ls_tags, todo):
            tags[u] = v
    json.dump(tags, open(p, "w", encoding="utf-8"), indent=0)
    print("hook repos unresolvable:", sum(1 for u in hook_urls if tags[u]["rc"] != 0))
    projects = sorted({v for k, v in MIRRORS.items() if v and k in set(hook_urls)})
    with cf.ThreadPoolExecutor(8) as ex:
        rel = dict(ex.map(releases, projects))
    json.dump(rel, open(os.path.join(DATA, "tool_releases.json"), "w", encoding="utf-8"), indent=0)
    print("mirrored PyPI tools with release dates: %d of %d" % (sum(1 for v in rel.values() if v["status"] == 200),
                                                               len(projects)))
    json.dump(MIRRORS, open(os.path.join(DATA, "mirrors.json"), "w", encoding="utf-8"), indent=0)
    pr = os.path.join(DATA, "hook_redirects.json")
    red = json.load(open(pr, encoding="utf-8")) if os.path.exists(pr) else {}
    with cf.ThreadPoolExecutor(6) as ex:
        for u, v in ex.map(location, [u for u in hook_urls if u not in red or red[u]["status"] is None]):
            red[u] = v
    json.dump(red, open(pr, "w", encoding="utf-8"), indent=0)
    print("hook repositories answering 301 (moved):", sum(1 for v in red.values() if v["status"] == 301),
          "| 404:", sum(1 for v in red.values() if v["status"] == 404),
          "| unknown:", sum(1 for v in red.values() if v["status"] is None and v.get("location") is None))
    # for a moved repository: does the FORMER owner account still exist? (a missing account can be re-registered)
    po = os.path.join(DATA, "former_owners.json")
    own = json.load(open(po, encoding="utf-8")) if os.path.exists(po) else {}
    olds = sorted({u.split("/")[1] for u, v in red.items() if v["status"] == 301} - set(own))
    with cf.ThreadPoolExecutor(4) as ex:
        for o, (_, v) in zip(olds, ex.map(location, ["github.com/" + o for o in olds])):
            own[o] = v
    json.dump(own, open(po, "w", encoding="utf-8"), indent=0)
    print("former owners of moved hook repos:", len(own), "| account missing (404):",
          sum(1 for v in own.values() if v["status"] == 404), "| redirecting account (renamed user/org):",
          sum(1 for v in own.values() if v["status"] == 301))


main()
