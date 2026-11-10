# Live evaluation: three real code samples

Model: `nvidia/Nemotron-3_5-Lightning`

Live end-to-end completion and citation validation, not ground-truth defect accuracy. No source tests were executed.

| Sample | Complete | Agents | Findings | Seconds |
| --- | --- | --- | --- | --- |
| flask-auth | True | 3/3 | 10 | 12.93 |
| fastapi-oauth | True | 3/3 | 11 | 20.16 |
| starlette-auth | True | 3/3 | 7 | 20.68 |

All saved reports are drafts pending a human decision. Upstream code is attributed in `examples/real_samples.json`.
