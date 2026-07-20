# Backend reliability

- A single-worker executor prevents competing extraction runs.
- A cross-process lock prevents API extraction and publication from overlapping with another RefEngine process.
- Queued or processing runs are marked failed after an interrupted backend restart.
- Every run stores an input hash inventory and its own local draft directory.
- SQLite uses WAL, foreign keys, busy timeout, transactions, and integrity checks.
- Field edits recompile the entire run so ordering and same-author/year suffixes remain deterministic.
- Publication is atomic and preserves the previous successful `output/latest` in history.
- Final exports are unavailable until every included work passes the quality gate.
