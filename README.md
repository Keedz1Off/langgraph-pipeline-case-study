# LangGraph integration testing case study

A local Python application uses LangGraph to save conversation state and pause actions for approval. This case study checks access controls, approval rules, and recovery behavior with synthetic users and SQLite. The recorded run had **70 passes and 3 failures across 73 cases**.

[Application architecture](#application-architecture) · [Testing pipeline](#testing-pipeline) · [Pipeline update](PIPELINE.md#github-actions-update) · [Results and reading order](#results-and-reading-order)

## Where to start

| Open | What you will find |
| --- | --- |
| [Application architecture](#application-architecture) | See where the app stores notes, approvals and execution records. |
| [Testing pipeline](#testing-pipeline) · [Worked example](CASE-STUDY.md) | Follow an approval rule from its test to the saved result. |
| [Matrix](MATRIX.md) · [Recorded results](evidence/results.json) | Find the tested properties, individual outcomes and the three measured failures. |
| [Local lab](lab/README.md) · [GitHub Actions](#github-actions) | Choose between the local runtime suite and the checks on the saved evidence. |
| [Pipeline update](PIPELINE.md#github-actions-update) | See the added CI stages, output artifacts and remaining automation work. |

## Boundaries, tests and evidence

Read the [22 boundaries in JSON](matrices/boundaries.json) or [as a table](MATRIX.md). [Local application](lab/local_host.py), [control tests](lab/test_controls.py), and [persistence tests](lab/test_persistence.py) are included with their [setup guide](lab/README.md). [Historical results](evidence/results.json) also include the resilience checks from the larger October run.

For B09, find `test_pending_approval_has_no_effect`, `test_denial_has_no_effect`, and `test_valid_approval_records_one_dummy_effect` in the control tests. Each checks the count of synthetic execution records in SQLite.

Run the offline evidence checks from the repository root with Python 3.10 or later.

```sh
python -B -m unittest discover -s tests -v
```

## Application architecture

```mermaid
flowchart TD
    User["Synthetic user in a pytest fixture"]
    Host["LocalHost<br/>Python application"]
    Memory["Conversation graph<br/>Saves conversation history"]
    Action["Approval graph<br/>Pauses and resumes actions"]
    Notes["LangGraph Store<br/>Reads and writes scoped notes"]
    Checkpoints[("checkpoints.sqlite<br/>Conversation and workflow state")]
    NotesDB[("notes.sqlite<br/>User notes")]
    Ledger[("host.sqlite<br/>Thread owners, approval status, execution records")]

    User -->|"Calls application methods"| Host
    Host -->|"Checks thread ownership"| Memory
    Host -->|"Checks owner, role, and action reference"| Action
    Host -->|"Derives namespace from tenant and user"| Notes
    Host -->|"Looks up ownership and pending status"| Ledger
    Memory --> Checkpoints
    Action --> Checkpoints
    Action -->|"Records decision and any execution"| Ledger
    Notes --> NotesDB
```

- **LocalHost** owns the access rules. It checks thread ownership, controls who can approve a pending action, and assigns note storage by tenant and user. Test fixtures supply identities directly.
- **LangGraph** runs two graphs. One keeps conversation state. The other pauses at an approval step and resumes after the application accepts a decision.
- **SQLite** stores three kinds of data in separate files in the persistent test setup. The checkpoint tells us where a graph stopped. The notes database holds user notes. The application ledger records ownership, decisions, and a dummy execution row when an action is approved.

For an action, the host marks it pending and starts the approval graph. The graph saves its waiting state. Once the host accepts an authorized decision, the graph resumes. Approval records one dummy execution row and an approved status. Denial records a denied status and leaves zero execution rows in the ordinary denial case. The ledger and graph checkpoint are saved separately, so the tests compare both when checking recovery.

## Testing pipeline

The local assessment follows a rule from the matrix through Python scenarios and SQLite observations. The [GitHub Actions flow](#ci-flow) shows the evidence checks that run on the current repository.

```mermaid
flowchart TD
    Boundary["Map an application boundary"]
    Matrix["Write the expected behavior in the test matrix"]
    Tests["Build Python scenarios with test fixtures"]
    Run["pytest runs the scenarios against the local app"]
    Observe["Read the relevant application state"]
    Assert["Assert that the observation matches the rule"]
    XML["pytest writes case outcomes to JUnit XML"]
    Logs["Selected observations from the test run"]
    JSON["The runner combines outcomes and observations in JSON"]
    Report["Explain the result in the matrix and case study"]

    Boundary --> Matrix --> Tests --> Run --> Observe --> Assert --> XML --> JSON --> Report
    Observe --> Logs --> JSON
```

**Worked example — matrix row B09.** An action awaiting approval or denied by the owner should leave zero execution records. Python fixtures set up the user and the action. pytest runs the pending and denial scenarios and checks the ledger. A separate approval scenario expects one record and confirms that the test action can run. A negative control feeds the assertion an unexpected dummy row and verifies that it rejects that result.

| Scenario | What the test checks |
| --- | --- |
| Action is pending | Zero execution rows |
| Owner denies the action | Zero execution rows |
| Authorized owner approves the action | One execution row |

pytest writes each case outcome to JUnit XML. The local runner reads the XML and combines those outcomes with selected observations in JSON. This repo includes an extract of the recorded results and the documents that explain them. The repository includes the local control and persistence suites. The larger historical run also included separate resilience checks. [Recorded results](evidence/results.json)

## GitHub Actions

Open [Case study checks](https://github.com/Keedz1Off/langgraph-pipeline-case-study/actions/workflows/checks.yml) and click **Run workflow**. CI reads the matrix JSON and checks the saved evidence offline. The run saves a `check-results` log. Select **CD demo** to also download `verified-delivery` with the log, commit SHA and checksum after checks pass.

### CI flow

```mermaid
flowchart TD
    Trigger["Push, pull request or Run workflow"] --> Setup["Checkout commit and prepare Python"]
    Setup --> Input["Read matrix JSON"]
    Input --> Check["Check boundary rows and saved run counts"]
    Check --> Log["Save check-results log"]
    Check --> Result{"Checks passed?"}
    Result -->|No| Fail["CI failed"]
    Result -->|Yes| Pass["CI passed"]
    Pass -->|"Manual run with CD demo enabled"| Bundle["Archive log, commit and checksum"]
    Bundle --> Delivery["Save verified-delivery artifact"]
```

### What happens in Actions

| Step | What it does |
| --- | --- |
| Checkout and Python | GitHub runs the selected commit on Ubuntu with Python 3.12. |
| Matrix JSON | CI requires the boundary index and reads every JSON file in the matrices folder. |
| Evidence tests | Two tests match the matrix to its documented rows and reconcile the full and repeat run counts. |
| Check log | CI uploads the result as `check-results`. |
| CD demo | After a passing manual run, CI saves the log, commit SHA and SHA-256 checksum as `verified-delivery`. |

[See the workflow file](.github/workflows/checks.yml). This job checks the material shipped in this repository offline.

## Planned update automation

This design describes the next stage of automation. The catalog-based selector and automatic mutation runner still require implementation.

```mermaid
flowchart TD
    Catalog["Catalog links files and functions to matrix rows"] -.-> Inventory["Check file and code-block inventory"]
    Inventory -.-> Selection["Select matrices affected by the change"]
    Selection -.-> Scenarios["Run their mapped Python scenarios"]
    Scenarios -.-> Oracle["Inspect results and SQLite state"]
    Oracle -.-> Report["Save selected cases, observations and outcomes"]
    Mutations["Isolated controlled mutations"] -.-> Calibration["Check that the matching oracle detects the change"]
```

[Read what each planned stage would do](PIPELINE.md#update-automation-design-planned). The working CI currently parses matrix JSON and checks saved evidence as described above.

## Results and reading order

The October 24, 2026 local run had **70 passes and 3 failures**. A repeat of nine cases produced **6 passes and the same 3 failures**. The failed checks concern the synthetic application's consistency between approval status, execution attempts, and saved state.

1. Read the architecture and pipeline above to see what was tested and how.
2. Open the [case study](CASE-STUDY.md) for the negative controls and the three failed checks.
3. Use the [matrix](MATRIX.md) to trace the 22 properties. Start with B09 for the approval example and B18, B20, and B21 for the failures.
4. Open the [recorded results](evidence/results.json) for totals and individual case outcomes. The [detailed pipeline notes](PIPELINE.md) walk through each stage.
