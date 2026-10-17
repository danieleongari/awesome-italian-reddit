# Updating the directory

`subreddits.csv` is the source of truth. Add a row manually for each new
community, using the subreddit name without `r/`, preserving the header and
number of columns. Names must be unique, ignoring capitalization. You can
leave the metadata cells empty. Keep any commas in descriptions inside quoted
CSV cells. `tag`, `language`, `reason` and other custom columns remain yours.

`python update.py` reads the **entire current list** through the official
Reddit Developer Platform app, then updates `subreddits.csv`, `README.md` and
`docs/index.html`. It never creates posts or comments. No anonymous scraping,
legacy Reddit OAuth client or third-party data service is used.

## Local setup: Conda base

Use Python 3.13 and Node 24. The local `.venv` is no longer needed.

```sh
conda activate base
python -m pip install -r requirements.txt
# Use Node 24; if you use nvm:
nvm install 24.18.0
nvm use 24.18.0
npm ci --prefix devvit
python update.py
```

The existing app is `awesome-italian-subr`, installed in the account's test
community `awesome_italian_s_dev`. These names are in `devvit/devvit.json`.
The account used for authentication must own the app and be a moderator of
that community. The app uses install/upgrade triggers and finite scheduled
batches to read metadata. It does not need a Reddit post or an open playtest.
Running two refreshes against the same app at once can interrupt the older run.

## Credentials: `.env` and GitHub Actions

The updater needs **one Reddit credential**, `DEVVIT_AUTH_TOKEN`. The root
`.env` already contains the credential copied from the current Devvit login.
It is ignored by Git and restricted to the local user (permissions `600`).
The CLI's original credential remains in `~/.devvit/token`.

`DEVVIT_AUTH_TOKEN` contains the **complete JSON credential**, including the
encoded access/refresh credentials and the CLI's login mode. It is not just
an access token. Never publish it, commit `.env`, or paste the value into logs.
`.env.example` documents the variable without containing its value.
Existing unrelated `.env` variables are preserved; an `OPENAI_API_KEY`, if
present, is not used by the updater and is not loaded from `.env` for Devvit.
No `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` or paid service key is required.

To replace the credential after logging in again:

```sh
cd devvit
npx devvit login
cd ..
python update.py --sync-auth
```

Logging in again can invalidate the old credential. Copy the new value to
GitHub again if needed. Devvit refreshes access tokens through its CLI, but
Reddit can revoke authorization: no credential is guaranteed to last forever.
Environment variables take precedence over `.env`, so Actions uses its secret.

In the [repository's Actions secrets settings](https://github.com/danieleongari/awesome-italian-reddit/settings/secrets/actions),
create a repository secret named **`DEVVIT_AUTH_TOKEN`**. Copy the full value
from `.env`, without its outer single quotes. Do not upload `.env` itself.
GitHub supplies `GITHUB_TOKEN` automatically for committing the output; you
do not need a personal GitHub token.

After committing/pushing this refactor to `master`, the workflow
**Update subreddit directory** runs:

- manually from Actions → Run workflow;
- after a push that changes `subreddits.csv` on `master`;
- on January 1 and July 1 at 07:00 UTC.

It validates/builds the reader, uploads it to Devvit, installs the new version
in the configured test community, retrieves the completed metadata log, and
commits only the CSV, README and HTML. A JSON report is saved as an Actions
artifact. Refreshes are serialized. Repository rules must permit the Actions
bot to push to `master`; branch protection may require adapting the final
step to your repository policy. The separate check workflow uses no Reddit
secret and performs no live metadata requests.

For a public repository, [GitHub disables scheduled workflows after 60 days
without repository activity](https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-workflow-runs/disabling-and-enabling-a-workflow).
Check the workflow is enabled when relying on the semiannual schedule.
Manual and CSV-push updates remain available.

## Data handling and recovery

Subscriber counts and descriptions are read from
`reddit.getSubredditInfoByName`. Descriptions are normalized to one line and
limited to 50 characters, as in the original directory. Creation dates are
filled when absent. Existing dates, manual fields and historical extra columns
are retained. A successful response updates `updated_utc` in that row.

If Reddit omits a description, its old text is preserved. A returned empty
string is a valid description. If a community fails, its existing metadata is
preserved and the error is included in `.cache/update-report.json`. Failure
does not mean the subreddit was deleted. Rows with a manually set `reason`
are excluded from the public directory; clear that field manually if desired.
Rows without a known subscriber count are also excluded until one is retrieved.
README and HTML are sorted by subscriber count; the CSV retains its row order.

An interrupted/incomplete run, mismatched list, invalid metadata, or a run
with no usable results leaves the three directory files unchanged. The raw
JSON log is in ignored `.cache/devvit.jsonl`. It can be replayed only against
the same community list. A preview still retrieves live metadata and uploads
an app version, but does not change the CSV or public pages.

```sh
python update.py --dry-run
python update.py --from-log .cache/devvit.jsonl --dry-run
python update.py --from-log .cache/devvit.jsonl
python update.py --render-only  # offline; leaves the CSV untouched
```

## Repository layout and checks

- `update.py`: single entry point.
- `directory_updater/`: credentials, validation, Devvit orchestration, import and rendering.
- `devvit/`: server-only metadata reader and pinned JavaScript dependencies.
- `tests/`: Python integration tests, using synthetic logs without network access.
- `docs/index.html`: generated, searchable/sortable page, without external JavaScript dependencies.

The Devvit community list is generated from the CSV and is not tracked.
Prepare it before testing or building directly:

```sh
python update.py --prepare
python -m unittest discover -s tests -v
npm test --prefix devvit
```

The CLI and SDK are pinned to `0.14.8`, the npm `latest` release checked on
2026-10-17. A clean `npm ci` currently reports 19 audit findings in the CLI's
dependency tree (11 high, 6 moderate, 2 low), plus deprecated transitive
packages. These upstream findings remain; the reader's tests/build and live
refresh pass. Do not apply `npm audit fix --force` blindly: the proposed
`devvit@1.0.0` is not the registry's supported `latest` release. Recheck these
findings when updating the official CLI/SDK together.
