# Testing pipeline

[Back to the README](README.md) · [Case study](CASE-STUDY.md) · [Matrix](MATRIX.md) · [Results](evidence/results.json)

This example follows one rule throughout the pipeline: a pending or denied action must leave no execution record.

```text
Application flow → invariant → test scenario → assertion → pytest result → report
```

## 1. Map the application

A user requests an action, the LangGraph workflow pauses for a decision, and the application handles the decision. The application checks who can resume the action. LangGraph checkpoints preserve workflow state. The application records approval status and synthetic executions in a separate SQLite ledger. Notes live in their own store.

These boundaries determine where to look for evidence. The checkpoint says whether the workflow is waiting. The ledger says whether the application recorded execution. A check that depends on both reads both.

## 2. Write the rule in the matrix

In [B09](MATRIX.md), the application must leave the execution ledger empty while the action is pending and after an ordinary denial. The matrix records the boundary, the expected behavior, the relevant test or observation, and the recorded outcome.

## 3. Turn the rule into test scenarios

| Scenario | Expected observation |
| --- | --- |
| An action is awaiting a decision | Zero execution records |
| The owner denies the action | Zero execution records |
| An authorized owner approves the action | One execution record |

The approval case shows that the application can actually execute the test action. Together, the three cases distinguish an approval gate from an implementation that always leaves the ledger empty.

## 4. Decide what counts as a pass

The test observes the execution records and compares them with the expected count. This assertion is the *test oracle*. A second observation can matter in a different scenario. B20, for example, tracks execution attempts, while B19 tracks persisted rows. A unique row can coexist with two attempts.

## 5. Check the assertion itself

In an isolated test, the same assertion is given an empty list and a list containing a dummy record. The empty list is accepted. The dummy record must trigger an assertion failure. pytest marks that test as passed when the expected assertion failure occurs. [See the example](CASE-STUDY.md#checking-the-assertion).

## 6. Run and report

Python contains the test scenarios and assertions. pytest runs the cases and produces a JUnit XML report. The original runner reads that report and records case outcomes and selected observations in JSON. The [results extract](evidence/results.json) in this repository preserves the totals for each run and the outcomes cited in the case study.

In this pipeline, JSON stores output. The scenario logic lives in Python. A CI workflow could invoke pytest and archive the reports. The results documented here came from local runs.

## 7. Interpret failures against the rule

For each failure, record the expected behavior, the observed state, and which component owns the rule. For example, B18 checks whether a terminal ledger status agrees with the workflow checkpoint. The two states differed in the local run, which identifies an application consistency issue. [Read the failure analysis](CASE-STUDY.md#three-application-checks-that-failed).
