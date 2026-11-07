# Working on KCT

KCT (Key Control Testing) turns a control's documents and evidence into test steps
and verdicts, with Gemini or Claude. Start with `README.md`.

## How work is delivered: releases on one line

The work is handed to ING in releases, one at a time, so each can be reviewed,
deployed and accepted on its own. Every release contains all earlier ones.

```
master ──●  (what ING has accepted)
          \
delivery   ●── 01 ──── 02 ──── 03 ──── …     one commit per release, in order
               │        │        │
            tag delivery-01  delivery-02  …   (one tag per release)
            branch release/01-…  release/02-…  (one branch per release, at its tag)
```

- `delivery`: the line of all releases, in order. Work happens at its tip.
- `delivery-NN` tags and `release/NN-<name>` branches point at each release's commit.
- `master`: what ING has accepted. A release is delivered by merging its
  `release/NN-…` branch into `master` (or opening a pull request from it).
- `docs/RELEASES.md`: the log of releases and their status (prepared / delivered).

### Rules

1. **One release = one commit** on `delivery` (a few commits are fine when they belong
   together), with its tag and branch.
2. **Every release stands on its own**: the code, tests, notebooks, README and
   `.env.example` describe only what exists at that release. Nothing of a later release
   may leak into an earlier one, not even in the README.
3. **Tests pass and every notebook runs at every release**, checked before tagging and
   before pushing:
   ```bash
   python -m unittest discover tests        # fake AI, no cloud needed
   python scripts/run_notebooks.py          # every notebook in order, fake AI, temporary storage
   ```
4. **Never rewrite a delivered release.** Once a release is merged into `master` or
   handed over, its commit, tag and branch stay as they are.
5. **Undelivered releases may be rewritten** (they never left this machine), as long as
   rules 2 and 3 still hold for each of them afterwards.
6. No real ING data in the repository (evidence is C3 confidential, the repository is
   public); fake data only, made with `factories/` where they exist. Never commit
   secrets (`.env`, service-account keys), databases, logs, documents or ZIPs, and
   commit notebooks without outputs (Clear All Outputs, then save).
   `.gitignore` keeps most of it out; `tests/test_repository_hygiene.py` fails if any
   of it is committed.

### Adding the next release

```bash
git checkout delivery                     # the tip: the newest release
# ... make the change, with tests and README ...
python -m unittest discover tests
python scripts/run_notebooks.py
git commit -am "Release NN: <what it delivers>"
git tag delivery-NN
git branch release/NN-<short-name>
```

Then add a line to `docs/RELEASES.md` (in the same commit).

### Delivering a release (e.g. weekly)

Take the oldest prepared release, in order, never skipping one:

```bash
git checkout release/NN-<name>
python -m unittest discover tests          # still green
git checkout master && git merge --ff-only release/NN-<name>   # or a pull request into master
```

Mark it "delivered" with the date in `docs/RELEASES.md` on the next release.

### When the business asks for a change

- **To a delivered release N** (it is in ING): never change N. Make the change as a
  small release on top of the last delivered one, `NN.1`:
  ```bash
  git checkout -b release/NN.1-<change> delivery-NN      # NN = last delivered release
  # ... change, tests ...
  git commit -am "Release NN.1: <change>"
  git tag delivery-NN.1
  # move the prepared, undelivered releases on top of it:
  git rebase --onto delivery-NN.1 delivery-NN delivery
  ```
  Then re-point the tags and `release/…` branches of the moved releases to their new
  commits (`git tag -f`, `git branch -f`) and run the tests on each.
- **To a release not yet delivered**: change it where it belongs (commit on its
  `release/…` branch), then rebase the later releases onto it as above.
- **A new feature**: a new release at the tip of `delivery`.

## How the code is organised

- Laravel style: routes bind to controllers, controllers only call services.
- Every service is built once in `services/app.py` (`boot()`); the API and the notebooks
  use the same object, so they run the same code.
- AI work happens in agents (`services/**/agents/`), with their instructions in
  `prompts/<agent name>.md` and fake answers in `tests/fixtures/fake_ai/`.
- Notebooks in `notebooks/` are numbered in demo order and start with a description
  (what, why, how to use).
- Documentation and comments are plain English for non-native speakers.
