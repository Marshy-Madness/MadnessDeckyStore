"""Rebuild plugins.json from the plugin submodules and store.toml.

Decky's custom store channel fetches one URL and parses the body as
StorePlugin[] (decky-loader frontend/src/store.tsx). There is no API behind
it, so the whole store is this generated file plus worker.js to serve it.

Every submodule under plugins/ that has an id in store.toml is listed. For
each one this reads plugin.json from the repo on GitHub and every published
stable release that carries a .zip.

Rules Decky imposes on the output:
  * name must equal the plugin's own plugin.json name, or update checks and
    the "installed" badge never match.
  * versions[0] must be the newest: checkForPluginUpdates() only looks there.
  * artifact must be set, or Decky falls back to the official CDN.
  * hash is the SHA-256 of the exact zip; Decky verifies it after download.

Hashes are cached from the previous plugins.json and reused while GitHub's
asset digest still agrees, so a rebuild normally downloads nothing.

Stdlib only. Set GITHUB_TOKEN to lift the 60 requests/hour API limit.
"""
import configparser
import hashlib
import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "plugins.json")
RAW = "https://raw.githubusercontent.com/%s/HEAD/%s"
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def fetch(url, api=False):
    headers = {"User-Agent": "madness-decky-store"}
    if api:
        headers["Accept"] = "application/vnd.github+json"
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as fh:
        return fh.read()


def semver(tag):
    """Sort key. Unparseable parts sort last rather than crashing the run."""
    parts = re.split(r"[.\-+]", tag.lstrip("vV"))
    return tuple((0, int(p), "") if p.isdigit() else (-1, 0, p) for p in parts)


def submodules():
    """plugins/<folder> -> owner/repo, from .gitmodules."""
    cp = configparser.ConfigParser()
    cp.read(os.path.join(ROOT, ".gitmodules"))
    found = {}
    for section in cp.sections():
        path, url = cp[section].get("path", ""), cp[section].get("url", "")
        m = re.search(r"github\.com[/:]([^/]+/[^/]+?)(?:\.git)?/?$", url)
        if path.startswith("plugins/") and m:
            found[path.split("/", 1)[1]] = m.group(1)
    return found


def previous():
    try:
        with open(OUT, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


def image_for(key, repo, pj, entry):
    if entry.get("image_url"):
        return entry["image_url"]
    for ext in IMAGE_EXTS:
        if os.path.exists(os.path.join(ROOT, "assets", key + ext)):
            return RAW % (os.environ.get("STORE_REPO", "Marshy-Madness/MadnessDeckyStore"), "assets/" + key + ext)
    return pj.get("publish", {}).get("image") or ""


def versions_for(repo, name, entry, cache):
    releases = [r for r in json.loads(fetch("https://api.github.com/repos/%s/releases?per_page=100" % repo, api=True))
                if not r["draft"] and (entry.get("prereleases") or not r["prerelease"])]
    releases.sort(key=lambda r: semver(r["tag_name"]), reverse=True)

    versions = []
    for rel in releases:
        tag = rel["tag_name"].lstrip("vV")
        zips = [a for a in rel["assets"] if a["name"].lower().endswith(".zip")]
        # Prefer the conventional <repo>-<version>.zip if a release carries extras.
        preferred = [a for a in zips if a["name"] == "%s-%s.zip" % (repo.split("/")[1], tag)]
        zips = preferred or zips
        if len(zips) != 1:
            print("  skip %s %s: expected one .zip asset, found %d" % (repo, tag, len(zips)))
            continue
        asset = zips[0]
        url = asset["browser_download_url"]
        digest = cache.get((name, tag, url))
        expected = asset.get("digest")
        if digest and expected and expected != "sha256:" + digest:
            digest = None
        if not digest:
            digest = hashlib.sha256(fetch(url)).hexdigest()
            if expected and expected != "sha256:" + digest:
                raise ValueError("SHA-256 mismatch for " + url)
        versions.append({"name": tag, "hash": digest, "artifact": url})
    return versions


def build():
    with open(os.path.join(ROOT, "store.toml"), "rb") as fh:
        config = tomllib.load(fh)
    defaults = config.get("defaults", {})
    entries = config.get("plugins", {})
    subs = submodules()
    old = previous()
    cache = {(p["name"], v["name"], v["artifact"]): v["hash"] for p in old for v in p["versions"]}

    for key in sorted(set(subs) - set(entries)):
        print("  %s: submodule has no [plugins.%s] id in store.toml, not listed" % (key, key))
    ids = [e["id"] for e in entries.values()]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError("duplicate ids in store.toml: %s" % sorted(dupes))

    store = []
    for key, entry in entries.items():
        if entry.get("hidden"):
            continue
        repo = entry.get("repo") or subs.get(key)
        if not repo:
            print("  %s: not a submodule and no repo = set, skipped" % key)
            continue
        try:
            pj = json.loads(fetch(RAW % (repo, "plugin.json")))
            name = entry.get("name", pj["name"])
            versions = versions_for(repo, name, entry, cache)
        except (urllib.error.URLError, ValueError, KeyError) as exc:
            # Keep the last good entry rather than dropping a plugin from
            # everyone's store because GitHub hiccuped.
            kept = next((p for p in old if p["id"] == entry["id"]), None)
            print("  %s: %s%s" % (key, exc, " (kept previous entry)" if kept else ""))
            if kept:
                store.append(kept)
            continue
        if not versions:
            print("  %-24s no releases yet, not listed" % name)
            continue

        pub = pj.get("publish", {})
        store.append({
            "id": entry["id"],
            "name": name,
            "author": entry.get("author") or pj.get("author") or defaults.get("author", ""),
            "description": entry.get("description") or pub.get("description") or pj.get("description", ""),
            "tags": entry.get("tags") or pub.get("tags") or defaults.get("tags", []),
            "image_url": image_for(key, repo, pj, entry),
            "versions": versions,
        })
        print("  %-24s %-10s %d version(s)" % (name, versions[0]["name"], len(versions)))

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(store, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("wrote %d plugin(s) to plugins.json" % len(store))


if __name__ == "__main__":
    try:
        build()
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        sys.exit("build failed: %s" % exc)
