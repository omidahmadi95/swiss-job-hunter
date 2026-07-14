# Jack integration policy

This fork candidate is a **job-source engine only**. It is not the source of truth for applications or RAV records.

## Trust boundary

Allowed output:

1. Swiss Job Hunter searches and enriches public job listings.
2. A normalized JSON export is produced.
3. Jack's importer validates and deduplicates the records.
4. Accepted records are added only to `03_Stellen_Leads/leads.csv` with status `neu`.

Forbidden:

- writing `06_Status/bewerbungen.csv`
- marking a job as sent/applied
- creating RAV entries
- sending email or submitting forms
- importing personal CVs, application documents, tokens, or RAV files into this repository
- automatic upstream merges into the locally used branch

## Local branches and remotes

- `upstream/main`: Donvink's original repository
- `jack-safe`: reviewed local source-only changes
- future `origin`: Omid's public AGPL fork, containing no personal data

The working copy is located at:

`/Users/omidahmadi/Workspace/swiss-job-hunter`

## Updating from upstream

Never merge upstream directly into a running installation.

```bash
git fetch upstream
git log --oneline --left-right jack-safe...upstream/main
git switch jack-safe
git merge --no-commit --no-ff upstream/main
```

Before completing the merge:

1. Review changes to `scrapers/`, `server.py`, `config/settings.py`, dependencies and Docker files.
2. Confirm source-only guards still work.
3. Run the backend tests and frontend build.
4. Run one constrained test search against one source and one page.
5. Verify normalized export and Jack dry-run import.
6. Commit only after all checks pass.

A Hermes no-agent watchdog checks `upstream/main` every Monday at 09:00. It
stays silent when nothing changed and reports available commits to Jack. It
never merges or changes the working tree.

Abort an unsafe update with:

```bash
git merge --abort
```

## Runtime safety

The service must bind to loopback only. Do not expose it through LAN, public Docker port mappings, Tailscale or a reverse proxy without adding authentication and authorization.

The Jack-side importer defaults to dry-run. `--write` is required to change `leads.csv`.

## GitHub fork setup

GitHub CLI authentication is required before creating the remote fork:

```bash
gh auth login
gh repo fork Donvink/swiss-job-hunter --remote --remote-name origin
```

After the fork exists, verify:

```bash
git remote -v
```

Expected:

- `upstream` → `Donvink/swiss-job-hunter`
- `origin` → Omid's fork

Do not commit `.env`, `data/`, CVs, database files or any application material.
