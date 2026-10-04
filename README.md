# Madness Decky Store

A custom [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin store for MarshyMadness' plugins. Point a Steam Deck (or any Decky handheld) at it, and these plugins install and update from Decky's store tab like official ones.

Author: [MarshyMadness](https://github.com/Marshy-Madness)

Each plugin lives in **its own repository** and publishes its own releases. This repo collects them as git submodules under `plugins/` and builds the store listing from their releases.

| Plugin | Repository | What it does |
|---|---|---|
| Zipline Uploader | [zipline-auto-uploader](https://github.com/Marshy-Madness/zipline-auto-uploader) | Uploads new screenshots and recordings to your Zipline server |
| Smart Game Launcher | [decky-smart-launcher](https://github.com/Marshy-Madness/decky-smart-launcher) | Picks the Steam, desktop or streamed version of a game based on availability and network |
| Session Notes | [decky-session-notes](https://github.com/Marshy-Madness/decky-session-notes) | Per-game session notes, run tracking and stats |
| Deck Launcher | [deck-launcher](https://github.com/Marshy-Madness/deck-launcher) | Launch games remotely by NFC tap, QR code or Home Assistant |
| gg.deals | [gg-deals](https://github.com/Marshy-Madness/gg-deals) | Shows the lowest current gg.deals price on Steam store pages |

## Using the store on a Deck

Go to **Decky → Settings → General → Store Channel → Custom** and set the URL to:

```
https://madness-decky-store.<your-subdomain>.workers.dev
```

The plugins above now show in the store tab and get update notifications.

### Testing channel

To try prerelease builds before they reach everyone, use the same URL with `/testing` on the end:

```
https://madness-decky-store.<your-subdomain>.workers.dev/testing
```

It lists every stable release plus prereleases, newest first, so you get update prompts for both. Plugins that only have prereleases so far appear only here. Switch back to the plain URL to go back to stable. Installed prerelease versions stay installed and get replaced when the next stable release comes out. Switching back to **Default** brings back the official store, and installed plugins stay installed. Only one channel is active at a time, so plugins from the official store won't show update prompts while you're on Custom.

## How it works

Decky's custom store is a single URL that returns a JSON list of plugins and their versions. Each version has a zip URL and a SHA-256 hash.

1. **Releasing a plugin:** bump `version` in its `package.json`, commit, then `git tag -a v<version> -m v<version> && git push --follow-tags` (`-a` matters: `--follow-tags` only pushes annotated tags). A version with a dash, such as `0.2.0-beta.1`, is published as a prerelease and only appears in the testing channel. You can also run its *Release* workflow on GitHub. The plugin's `release.yml` calls [`release-plugin.yml`](.github/workflows/release-plugin.yml) here, which builds, packages with [`scripts/package-plugin.sh`](scripts/package-plugin.sh), and publishes `<repo>-<version>.zip` as a GitHub release.
2. **Building the store:** [`build-store.yml`](.github/workflows/build-store.yml) runs [`build_store.py`](build_store.py) every 30 minutes, on changes to `store.toml`, and on demand. It reads each submodule's `plugin.json` and releases from GitHub, then commits `plugins.json` (stable) and `plugins-testing.json` (stable plus prereleases) if anything changed.
3. **Serving:** [`worker.js`](worker.js), a Cloudflare Worker, serves `plugins.json` from this repo, or `plugins-testing.json` at `/testing`. Decky's request triggers a CORS preflight that GitHub can't answer; without the Worker, the store tab spins forever.

If a plugin repo has a `STORE_TOKEN` secret, its releases trigger a store rebuild immediately instead of waiting for the next scheduled run. Use a fine-grained token with *Actions: read and write* on this repo only.

## Working with this repo

```bash
# Clone everything
git clone --recurse-submodules https://github.com/Marshy-Madness/MadnessDeckyStore.git

# Get new commits for every plugin
git submodule update --remote --merge

# Work on one plugin: it's a normal git repo
cd plugins/decky-smart-launcher
git switch main
pnpm install && pnpm run build
# ...edit, commit...
git push

# Then record the new version in this repo
cd ../..
git add plugins/decky-smart-launcher
git commit -m "Bump decky-smart-launcher"
git push
```

Test a package locally with `scripts/package-plugin.sh plugins/<repo> /tmp/out <repo>` after `pnpm run build`. It needs `zip`, and `uv` if the plugin has a `requirements.txt`.

### Adding a new plugin

1. Create the plugin repo from the [decky-plugin-template](https://github.com/SteamDeckHomebrew/decky-plugin-template). Copy `.github/workflows/release.yml` from any plugin here, and push it to GitHub as a **public** repo, since Decks download releases anonymously.
2. `git submodule add https://github.com/Marshy-Madness/<repo>.git plugins/<repo>`
3. In `store.toml`, add `[plugins.<repo>]` with the next unused `id`. Never reuse or renumber ids.
4. Optionally add artwork at `assets/<repo>.png` (16:9).
5. Add a row to the table above, then commit and push. The plugin appears once its first release is published.

## One-time setup

1. **Cloudflare Worker:** in the Cloudflare dashboard go to Workers & Pages → Create → *Hello World* Worker. Name it `madness-decky-store`, replace its code with `worker.js`, and deploy. The `*.workers.dev` URL is the store URL.
2. **Actions permissions:** in this repo's Settings → Actions → General, set *Workflow permissions* to **Read and write** so the build can commit `plugins.json`.
3. **Keep the schedule alive:** GitHub pauses scheduled workflows in repos with no activity for 60 days. Releases with `STORE_TOKEN` trigger builds anyway; otherwise, re-enable it from the Actions tab if it pauses.
