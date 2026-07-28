# Aug 1 verification checklist

The watsonx token quota resets at the start of the month, which is also day one
of judging. **No commits are possible after Jul 31**, so this checklist is for
*confirming* the demo came back, not for fixing it. Everything here is a read.

Run these three commands. All three should pass without touching the repo.

## 1. Is watsonx answering again?

```sh
curl -s https://accessgate-api.onrender.com/demo-summary \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('error:', d.get('error') or 'NONE'); print('summary:', (d.get('summary') or '')[:80])"
```

Expect `error: NONE` and a non-empty summary. If `error` still shows
`403 ... token_quota_reached`, the reset has not landed yet; wait and retry.

## 2. Does the headline gated fix run live and get accepted?

```sh
curl -s -X POST https://accessgate-api.onrender.com/demo-fix \
  -F gap_start=39.06 -F gap_end=44.94 \
  | python3 -c "import json,sys; d=json.load(sys.stdin); [print(f'{k}: {d.get(k)}') for k in ('draft_source','dcmp_valid','guardian_ran','guardian_cleared','accepted','resolves_rule_ids')]"
```

Expect:
- `draft_source` naming watsonx, NOT containing "fallback"
- `guardian_ran: True`, `guardian_cleared: True`
- `accepted: True`
- `resolves_rule_ids` non-empty (this is what flips the row green in the UI)

This whole path is covered by `tests/test_watsonx_success_paths.py`, which stubs
the watsonx responses, so it is verified logic; this command confirms the live
credentials and quota agree with it.

## 3. Which encoder is serving citations?

```sh
curl -s https://accessgate-api.onrender.com/judges \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['citation_provenance'])"
```

Expect BOTH `active` and `serving` to read
`watsonx:ibm/granite-embedding-278m-multilingual`.

The deploy loads a **prebuilt** Granite vector set committed to the repo, so it
spends zero embedding calls at request time. That is the fix for what exhausted
the quota on 2026-07-27: the corpus is embedded once offline, not on every cold
start. `serving` is the set actually in memory answering citations; `active` is
what this process would use for a query. They should agree.

If `serving` reads `tfidf:md5-3gram-512`, the prebuilt file did not load. The
citations are still grounded and still correct, just retrieved by the
deterministic encoder, so it is a quality regression rather than a breakage.

## If something is wrong

Nothing can be committed. The available levers are all outside the repo:

- **403 token_quota_reached**: should not recur, the plan is now Essentials
  (pay-as-you-go) rather than Lite, and runtime embedding calls are zero. If it
  does, check the IBM Cloud spending notification and the account status.
- **Credentials rejected**: swap `WATSONX_API_KEY` / `WATSONX_PROJECT` in the
  Render dashboard. No code change needed; both are `sync: false` env vars.
- **Cold start feels slow**: expected. Render free tier sleeps after 15 minutes
  and GitHub throttles the keepalive to roughly hourly. First request takes about
  30 s, then it is fast. Hit `/health` once before showing anyone the demo.
- **A judge reports an error on upload**: `/check-captions` returns 422 with a
  readable reason for anything it cannot parse, and 413 over 5 MB. That is the
  designed behaviour, not a crash.

## Pre-warm before any live demo

```sh
curl -s -o /dev/null -w "%{time_total}s\n" https://accessgate-api.onrender.com/health
```

Run it twice. The second should be well under a second.
