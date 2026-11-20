# LangGraph approval and state testing

A synthetic LangGraph application tests whether scoped notes stay private, pending actions wait for approval, and saved state stays consistent after a restart. The recorded local run completed **73 checks: 70 passed, 3 failed**. A repeat of nine checks showed the same three failures.

## Testing pipeline

Define the rule → create test scenarios → run pytest → compare responses and SQLite state → save the results.

For the approval rule, the execution ledger must show **zero rows while an action is pending or denied** and **one row after approval**. The three recorded failures concern consistency across approval status, execution attempts and saved state.

## Evidence and local lab

- [Case study and the three failures](CASE-STUDY.md)
- [22 tested properties](MATRIX.md) · [Boundary matrix index](matrices/boundaries.json)
- [Recorded results](evidence/results.json) · [Pipeline details](PIPELINE.md)
- [Local application and pytest setup](lab/README.md)

## Run the checks

[Open Case study checks in GitHub Actions](https://github.com/Keedz1Off/langgraph-pipeline-case-study/actions/workflows/checks.yml) and select **Run workflow**. CI runs two offline tests that verify the matrix and the recorded counts. The local lab has separate control and persistence suites.

The run saves `check-results`. Select **CD demo** to also package the passing log, commit SHA and checksum as `verified-delivery`.

Run locally with Python 3.10 or later:

```sh
python -B -m unittest discover -s tests -v
```
