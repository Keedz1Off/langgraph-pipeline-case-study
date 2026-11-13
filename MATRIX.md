# Test matrix

[Back to the README](README.md) · [Pipeline](PIPELINE.md) · [Case study](CASE-STUDY.md) · [Results](evidence/results.json)

Read a row from left to right: boundary, expected behavior, then the outcome and what was checked. A row describes a property and may cover several pytest cases. The 22 rows summarize the October 24, 2026 local run.

| ID | Boundary | Expected behavior | Recorded outcome |
| --- | --- | --- | --- |
| B01 | User → another user's thread | Only the owner may read, change, inspect history, or delete the thread. | Pass. The host denied nonowner access. |
| B02 | Tenant → another tenant | A matching user ID in a different tenant grants no access. | Pass. Tenant scoping held. |
| B03 | Thread → another thread | State, history, and deletion stay scoped to the selected thread. | Pass. Threads stayed separate. |
| B04 | User → note store | Note reads, searches, and deletes stay scoped to the user. | Pass. The host selected the permitted namespace. |
| B05 | Namespace → note lookup | Distinct test namespaces select their own data. | Pass for the three tested names. |
| B06 | Same user's threads → shared notes | The same user can access their shared notes across threads. | Pass. Intended sharing worked. |
| B07 | Decision → workflow resume | The caller must own the action, be allowed to approve, and present the matching action reference. | Pass. The host enforced the three checks. |
| B08 | Decision input → schema | Invalid input is rejected. Corrected input is accepted. | Pass. The typed schema behaved as expected. |
| B09 | Pending or denied action → execution | The ledger has zero execution records while pending and after ordinary denial. | Pass. Both scenarios had zero records. [Worked example](PIPELINE.md#2-write-the-rule-in-the-matrix) |
| B10 | Sequential repeat → execution | A later approval of the same action adds no second execution. | Pass for the sequential check. |
| B11 | Clean restart → saved state | A new process can recover checkpoints, notes, and pending decisions. | Pass. Saved state recovered. |
| B12 | In-memory notes → new process | In-memory notes disappear. Persisted workflow state survives. | Pass. The two storage modes behaved as expected. |
| B13 | Sync store → async store | The other adapter can read committed notes after reopening the database. | Pass within one process. |
| B14 | Process interruption → open transaction | Uncommitted execution data rolls back. Previously saved data survives. | Pass at the tested checkpoint. |
| B15 | Process interruption → committed transaction | Committed approval and its one execution record survive. | Pass at the tested checkpoint. |
| B16 | Process interruption → SQLite files | Saved notes and checkpoints remain readable and integrity checks pass. | Pass at the tested points. |
| B17 | Rollback → authorized retry | The retry completes the workflow and records one execution. | Pass. The retry left one record. |
| B18 | Terminal ledger status → workflow checkpoint | A terminal ledger status corresponds to a terminal workflow. | **Fail.** The ledger was approved and the workflow remained pending. |
| B19 | Overlapping approvals → saved record | At most one execution row is stored for the same action. | Pass. One row was saved. |
| B20 | Overlapping approvals → execution attempt | At most one execution attempt occurs for the same action. | **Fail.** Two attempts and one row were observed. |
| B21 | Conflicting decisions → final ledger | A denied action has no execution record. | **Fail.** Denial and an execution record coexisted. |
| B22 | Different actions → shared storage | Each action retains its own decision and execution record. | Pass for the two tested actions. |

[Read the three failed checks](CASE-STUDY.md#three-application-checks-that-failed).
