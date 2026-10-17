# Publishing the clients and the skill (owner steps, 2026-10-17)

Both clients are at 0.2.0 and tested against the live API (brief, regime, cascades, packages,
a 402 without a payer, a rejected fake x402 signature). Publishing needs your accounts.

## PyPI — `liquidvision` — PUBLISHED 2026-10-17 (0.2.0)

Trusted publishing, no token: a pending publisher was registered on PyPI (owner lv-analytics,
repo liquidvision-mcp, workflow publish-pypi.yml, environment pypi) and the tag `py-v0.2.0`
triggered `.github/workflows/publish-pypi.yml`. Next release: bump `version` in
`clients/python/pyproject.toml` and `__version__`, commit, then

```bash
git tag -a py-v0.2.1 -m "liquidvision 0.2.1 (Python)" && git push origin py-v0.2.1
```
Check: `pip install liquidvision && python -c "from liquidvision import LiquidVision; print(LiquidVision().brief('BTCUSDT')['asset']['price'])"`.
If the name is taken, the fallback is `liquidvision-app` (change `name` in pyproject.toml and
the import stays `liquidvision`).

## npm — `liquidvision` — pending (owner step)

The workflow `.github/workflows/publish-npm.yml` publishes on `js-v*` tags with provenance, but npm
only lets a trusted publisher be attached to a package that already exists. One-time, on your
machine:

```bash
cd clients/js
npm login
npm publish --access public
```
Then on npmjs.com: package settings -> Trusted publisher -> GitHub Actions (lv-analytics /
liquidvision-mcp / publish-npm.yml / environment npm). Later releases: tag `js-v0.2.1`.
Check: `npx -y liquidvision` is not a CLI; test with `node -e "import('liquidvision').then(async m => console.log((await new m.LiquidVision().brief('BTCUSDT')).asset.price))"`.
If the name is taken, publish as `@lv-analytics/liquidvision`.

## Claude Code skill

The skill lives in `skills/liquidvision/SKILL.md`. Anyone can install it by copying the folder
into `~/.claude/skills/` (personal) or `.claude/skills/` in a project. To list it in a
marketplace, add this repo as a plugin source: `claude plugin marketplace add lv-analytics/liquidvision-mcp`
once a `.claude-plugin/marketplace.json` is added (next step if the skill gets traction).

## After publishing

- Update the install lines in `README.md` (they already say `pip install liquidvision` / `npm install liquidvision`).
- Mention both packages in `https://liquidvision.app/llms.txt` and the Data page.
- Post once from @LVisionLab: "pip install liquidvision — the derivatives market in one JSON, and your agent can pay per file in USDC".
