# Local LangGraph tests

The test subjects are synthetic users, local SQLite files and dummy execution records. The test code covers access to conversation threads and notes, approval rules, and persistence across processes.

The October assessment used Python 3.12 and [this LangGraph source revision](https://github.com/langchain-ai/langgraph/tree/4c52e129eb1ab69a3da58b799f67929f77d81149). With a checkout of that revision, install the five sibling packages from its `libs` directory alongside [the recorded dependencies](requirements-third-party.txt). In these commands, `../source-langgraph` is that checkout and `python` is an active environment with Python 3.12.

```sh
python -m pip install -r lab/requirements-third-party.txt ../source-langgraph/libs/checkpoint ../source-langgraph/libs/checkpoint-sqlite ../source-langgraph/libs/sdk-py ../source-langgraph/libs/prebuilt ../source-langgraph/libs/langgraph
python -B -m pytest -p no:cacheprovider lab/test_controls.py lab/test_persistence.py
```

The [October report](../evidence/results.json) is an extract from a larger run that also exercised interruption and overlapping decisions.
