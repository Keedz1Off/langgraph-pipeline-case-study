# LangGraph integration testing case study

A local case study in testing a LangGraph application's access controls, approval gates, and recovery behavior. The application used synthetic users and SQLite records as stand-ins for real tool actions.

**Start with [the testing pipeline](PIPELINE.md).** It follows one rule from the test matrix through the pytest assertion and the final report.

## Reading order

1. [Pipeline](PIPELINE.md) explains the application boundaries, test design, observations, and reporting.
2. [Case study](CASE-STUDY.md) shows how an intentionally wrong fixture checks the assertion and what three failed application checks revealed.
3. [Test matrix](MATRIX.md) lists 22 properties and their outcomes. Start with B09 for the worked example and B18, B20, and B21 for the failed checks.
4. [Recorded results](evidence/results.json) contains the run counts and the individual outcomes cited in the case study.

## Results

The local run on October 24, 2026 produced **70 passes and 3 failures across 73 cases**. A separate repeat of nine cases produced **6 passes and the same 3 failures**. All three failures concern consistency in the synthetic application built around LangGraph. This repository documents the experiment and includes an extract of the recorded results.
