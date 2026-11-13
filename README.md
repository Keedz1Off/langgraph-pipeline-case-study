# LangGraph integration testing case study

A local Python application uses LangGraph to save conversation state and pause actions for approval. This case study checks access controls, approval rules, and recovery behavior with synthetic users and SQLite. The recorded run had **70 passes and 3 failures across 73 cases**.

[Application architecture](#application-architecture) · [Testing pipeline](#testing-pipeline) · [Results and reading order](#results-and-reading-order)

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

pytest writes each case outcome to JUnit XML. The local runner reads the XML and combines those outcomes with selected observations in JSON. This repo includes an extract of the recorded results and the documents that explain them. The original application and test runner are needed to rerun the suite. [Recorded results](evidence/results.json)

## Results and reading order

The October 24, 2026 local run had **70 passes and 3 failures**. A repeat of nine cases produced **6 passes and the same 3 failures**. The failed checks concern the synthetic application's consistency between approval status, execution attempts, and saved state.

1. Read the architecture and pipeline above to see what was tested and how.
2. Open the [case study](CASE-STUDY.md) for the negative controls and the three failed checks.
3. Use the [matrix](MATRIX.md) to trace the 22 properties. Start with B09 for the approval example and B18, B20, and B21 for the failures.
4. Open the [recorded results](evidence/results.json) for totals and individual case outcomes. The [detailed pipeline notes](PIPELINE.md) walk through each stage.
