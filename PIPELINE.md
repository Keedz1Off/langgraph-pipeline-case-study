# Testing pipeline

[Back to the README](README.md) · [Case study](CASE-STUDY.md) · [Matrix](MATRIX.md) · [Results](evidence/results.json)

This example follows one rule throughout the pipeline: a pending or denied action must leave no execution record.

[Open the diagrams in the README](README.md#testing-pipeline) for the local tests, current CI and planned update automation.

```text
Application flow → invariant → test scenario → assertion → pytest result → report
```

## GitHub Actions update

The added [workflow](.github/workflows/checks.yml) runs the repository's evidence checks on pushes and pull requests to `main`. It also supports a manual run through [Actions → Case study checks → Run workflow](https://github.com/Keedz1Off/langgraph-pipeline-case-study/actions/workflows/checks.yml).

```text
Push, pull request or manual run → read matrix JSON → check recorded evidence → save check log
Manual run with CD demo enabled → passing checks → package verified results
```

| Stage | What happens in this repository |
| --- | --- |
| Prepare the runner | GitHub checks out the selected revision on Ubuntu and installs Python 3.12. |
| Read the matrix | The job requires `matrices/boundaries.json` and parses every JSON file in `matrices/`. The current file contains 22 boundary rows. |
| Check the boundary index | One offline test checks that the 22 IDs and their boundary and invariant text match `MATRIX.md`. |
| Check recorded outcomes | A second offline test reconciles the saved totals and checks that the full run and repeat run contain the same three recorded failures. |
| Save the log | Actions uploads the check output as the `check-results` artifact, including output from a failed check. |
| Package the optional CD demo | After a successful manual run with **CD demo** enabled, Actions uploads `verified-delivery` with the check log archive, commit SHA and SHA-256 checksum. |

The case study's 73 runtime cases and their 70-pass, 3-failure result came from the local assessment. Actions executes the two offline tests in [tests/test_recorded_evidence.py](tests/test_recorded_evidence.py). The [local lab guide](lab/README.md) provides the separate runtime test commands.

The current automation covers the matrix index, recorded evidence and result packaging. Automatic file-to-boundary bindings, changed-block selection and mutation runs remain pending. The optional CD demo produces a downloadable archive.

## Update automation design (planned)

The [planned update flow](README.md#planned-update-automation) describes how the pipeline would react to application changes. These stages still require implementation in the runner and workflow.

| Stage | Intended behavior | LangGraph example |
| --- | --- | --- |
| Catalog and bindings | Record which application files and functions each matrix row covers, and which Python scenarios check it. | Bind the approval methods in `lab/local_host.py` to B07, B08 and B09 and their tests. |
| Check files and code blocks | Compare the current application inventory with the recorded bindings. A new unbound file or function would stop the run until its rule and tests are recorded. | A newly added approval method would need an explicit boundary binding. |
| Select affected matrices | Use changed files and functions to choose the relevant rules. Shared setup or dependency changes would select the full suite. | A change to `LocalHost.decide` would select approval checks. |
| Run selected scenarios | Execute the mapped Python tests against the local application. Each oracle would inspect the result and relevant SQLite state. | Pending and denied actions should leave zero execution rows. An authorized approval should leave one. |
| Save the report | Record the source revision, detected changes, selected boundaries and tests, observations and outcomes. | The report would show why B09 was selected and its observed execution-row count. |
| Mutation checks | Run isolated, controlled changes to observations or behavior to confirm that the corresponding oracle detects a violation. | Give the zero-execution oracle an unexpected dummy row and confirm it rejects the observation. |

The [existing assertion example](CASE-STUDY.md#checking-the-assertion) explains the last idea. An automatic mutation runner and the catalog-based selection system remain future work.

The following sections explain how the local assessment follows an application rule through scenarios, observations and the report.

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

The boundary index in `matrices/boundaries.json` records the rules, and `evidence/results.json` stores recorded outcomes. The scenario logic lives in Python. The results documented here came from local runs. GitHub Actions checks the index and those saved outcomes as described in the [pipeline update](#github-actions-update).

## 7. Interpret failures against the rule

For each failure, record the expected behavior, the observed state, and which component owns the rule. For example, B18 checks whether a terminal ledger status agrees with the workflow checkpoint. The two states differed in the local run, which identifies an application consistency issue. [Read the failure analysis](CASE-STUDY.md#three-application-checks-that-failed).
