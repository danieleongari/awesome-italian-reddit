# Reddit metadata reader

Server-only Devvit app `awesome-italian-subr`, installed in
`r/awesome_italian_s_dev`. It reads each community using the official
`reddit.getSubredditInfoByName` API. Install/upgrade triggers start finite
batches of 10 communities, with 10 seconds between batches. Results are
emitted as structured logs and imported by the Python updater.

No posting or comment endpoints are implemented. The list in
`src/server/subreddits.ts` is generated from the root CSV; do not edit it.

See [UPDATING.md](../UPDATING.md) for setup, credentials and GitHub Actions.
Run `python update.py --prepare` from the repository root before building/testing.
