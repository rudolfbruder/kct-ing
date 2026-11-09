# Demo

`DEMO.ipynb` (in the project root) tells the whole story in 10 steps, with
presenter notes. It runs in one of three modes, set in its first cell:

| Mode | Answers from |
|---|---|
| `replay` | `demo/recordings/demo/`: real Gemini answers recorded once (default when present) |
| `live` | Gemini now (needs the Google project in `.env`) |
| `fake` | Fixed sample answers (`tests/fixtures/fake_ai/`) |

## Recording the replay

1. Set up Gemini in `.env` (`KCT_AI_PROVIDER=gemini`, `KCT_PROJECT_ID`, `KCT_LOCATION`).
2. In the first cell of `DEMO.ipynb`: `MODE = "live"`, `RECORD = True`; restart the kernel; Run All.
3. The answers are saved to `demo/recordings/demo/<agent>/*.json`. Commit them:
   they hold only the AI's answers about the made-up sample control, no documents.
4. Set `MODE = "auto"` again: the demo now replays them.

From the terminal, any run can be recorded with `KCT_AI_RECORD=<name>` and
replayed with `KCT_AI_PROVIDER=replay KCT_AI_REPLAY=<name>`.
