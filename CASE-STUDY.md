# LangGraph integration case study

[Back to the README](README.md) · [Pipeline](PIPELINE.md) · [Matrix](MATRIX.md) · [Results](evidence/results.json)

The local application used synthetic users, a workflow that paused for human approval, and SQLite for checkpoints, notes, and the application ledger. A recorded execution was a dummy database row.

## Checking the assertion

The suite included two negative controls. One used a synthetic mapping in which two users appeared to receive each other's fixture data. The other supplied a dummy execution record where the rule required an empty ledger. In each test, the assertion accepted the correct fixture and rejected the deliberately wrong fixture.

Here is a shortened illustration of the second check using only in-memory data.

```python
import pytest


def require_no_execution(records):
    assert records == []


def test_assertion_rejects_an_unexpected_record():
    require_no_execution([])

    with pytest.raises(AssertionError):
        require_no_execution(["dummy-record"])
```

The test passes when the second call raises the expected error. This is a negative control for the assertion. A mutation-testing score would require deliberate changes to the implementation and a separate test run.

## Three application checks that failed

| Matrix row | Expected | Observed | What to check in a fix |
| --- | --- | --- | --- |
| B18 | A terminal ledger status agrees with the workflow checkpoint | The ledger had one execution record and an approved status. The workflow still showed a pending decision. | Verify reconciliation after a restart. |
| B20 | A single action enters execution at most once | Two execution attempts were counted and one row was saved. | Check attempt count as well as row count. |
| B21 | A denied action has zero execution records | The final status was denied and an execution record remained. | Verify that the decision and execution record agree. |

The October 24, 2026 full run recorded **70 passes and 3 failures**. A repeat of nine cases recorded **6 passes and the same 3 failures**. The failures describe application guarantees in this synthetic integration. The experiment measured local state and did not exercise live users or external tools. [Recorded results](evidence/results.json)
