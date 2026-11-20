# Bokdeongi Lotto 6/45 Results Data

Read-only machine-validated Korean Lotto 6/45 draw results for the Bokdeongi mobile app.

- Generated files (after first successful workflow): `docs/latest.json`, `docs/rounds/<round>.json`
- Public HTTPS JSON: GitHub Pages from the `main` branch's `/docs` directory
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

Repository Settings → Pages → Build and deployment → Deploy from a branch → `main` / `/docs`.
Repository Settings → Actions → General → Workflow permissions → Read and write permissions.
Check the Actions run before treating any JSON as published. A failed run never commits new data.

## Limitations

Official site-internal endpoints can change, block bots or return HTML. In these situations the job fails and the previous verified data stays unchanged. If more than one draw was missed, this first version refuses to skip rounds; operator-verified backfill is required. Public git commits are an audit trail, not a guarantee of lottery outcomes. GitHub scheduled workflow execution may be delayed or disabled after prolonged inactivity.
