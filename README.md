# Bokdeongi Lotto 6/45 Results Data

Read-only machine-validated Korean Lotto 6/45 draw results for the Bokdeongi mobile app.

- Generated files (after first successful workflow): `docs/latest.json`, `docs/rounds/<round>.json`
- Public HTTPS JSON: GitHub Pages deployed directly by the scheduled GitHub Actions workflow from verified `docs/` files
- Uses only Korean lottery operator (동행복권) website-internal result feeds; not a documented or supported public API.
- This project does NOT issue lottery tickets, verify ticket ownership, pay prizes, or guarantee winnings.
- Final results and prizes must be verified at [the operator's official site](https://www.dhlottery.co.kr/lt645/result).
- Two official operator paths must agree; schema/range/date checks block publication when anything is wrong.
- Does not collect or transmit app users' saved numbers, identifiers, or ticket QR codes.

## Automated schedule

Saturday 21:37 and 22:37, Sunday 09:37 KST, plus manual `workflow_dispatch`.

## Tests

```sh
python -m unittest discover -s lotto_data/tests -v
```

## Set up GitHub Pages

1. Repository **Settings → Pages → Build and deployment → Source: GitHub Actions** (NOT "Deploy from a branch").
2. Repository **Settings → Actions → General → Workflow permissions → Read and write permissions** if the workflow cannot push verified JSON. The workflow itself declares the required minimal job permissions.
3. **Actions → Verify and publish Lotto 6/45 results → Run workflow** on `main`.
4. Verify all steps: tests, official source verification, Git commit, **Upload verified JSON files as Pages artifact**, **Deploy verified JSON to GitHub Pages**.
5. Check `https://gurdung-sys.github.io/Bokdeongi-lotto-data/latest.json` only *after* the workflow finishes successfully.

**Important:** GitHub's `GITHUB_TOKEN` commits do not trigger a branch-source Pages build. For this reason the same workflow explicitly uploads and deploys the verified `docs/` directory to Pages. If the official site is unavailable or data inconsistent, the workflow fails and does **not** publish unverified results.

## Limitations

Official site-internal endpoints can change, block bots or return HTML. In these situations the job fails and the previous verified data stays unchanged. If more than one draw was missed, this first version refuses to skip rounds; operator-verified backfill is required. Public git commits are an audit trail, not a guarantee of lottery outcomes. GitHub scheduled workflow execution may be delayed or disabled after prolonged inactivity.
