# AgentX contract schemas — vendored copy

Copied from `pankajkamble75/agentx` (`docs/contracts/schemas/*.schema.json`, generated from `agentx/contracts.py` and `agentx/uischema.py`),
**PROPOSED v1, 2026-10-10**, as sent inline by the AgentX session (that repository is not pushed yet). `title`/`description` annotations were
removed by the sender for size; cross-file `$ref`s are file names. `HumanInteraction` was sent inside OperationState and is stored here as its
own file. AgentX also enforces in code: capability id `^[a-z][a-z0-9_-]*(\.[a-z][a-z0-9_-]*)+$`; version `^\d+\.\d+\.\d+$`; relative
endpoints; input/output schemas valid Draft 2020-12; UI text refuses markup, templates and script URLs; labels ≤ 200, help ≤ 500; ids
`^[a-z][a-z0-9_-]{0,63}$`; select/multiselect need options; an `invoke` action needs `capability`. KA's tests check all of these
(`ka/tests/test_plan29_agentx_core.py`, `ka/tests/test_plan30_*`). When AgentX pushes its repository, replace these files with its copies.
