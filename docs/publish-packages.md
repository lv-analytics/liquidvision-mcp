# Publishing the clients and the skill (owner steps, 2026-10-17)

Both clients are at 0.2.0 and tested against the live API (brief, regime, cascades, packages,
a 402 without a payer, a rejected fake x402 signature). Publishing needs your accounts.

## PyPI — `liquidvision`

```bash
cd clients/python
python -m pip install --upgrade build twine
python -m build                       # dist/liquidvision-0.2.0.tar.gz + .whl
python -m twine upload dist/*         # PyPI token: https://pypi.org/manage/account/token/
```
Check: `pip install liquidvision && python -c "from liquidvision import LiquidVision; print(LiquidVision().brief('BTCUSDT')['asset']['price'])"`.
If the name is taken, the fallback is `liquidvision-app` (change `name` in pyproject.toml and
the import stays `liquidvision`).

## npm — `liquidvision`

```bash
cd clients/js
npm login
npm publish --access public
```
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
