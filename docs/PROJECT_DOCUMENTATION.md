# Project 3E: Code Review Agent

Prepared for the Week 3 Agentic AI Systems project, November 8, 2026.

## Project overview

Review Studio helps an engineer review a submitted source change in Streamlit. Three specialist agents inspect bugs and anti-patterns, security vulnerabilities, and testing gaps; a fourth LLM role synthesizes a prioritized report, and a LangGraph interrupt reserves the final assessment decision for a human.

The implementation uses Python, LangChain read-only tools, LangGraph state and checkpoints, Streamlit, Pydantic contracts, and the OpenAI Python client pointed at Nebius Token Factory. Every model-backed role uses `nvidia/Nemotron-3_5-Lightning`; no other provider or model is used as a fallback.

## One-line primer

My agent helps software engineers review source changes in a Streamlit workspace, replacing repeated manual passes for defects, security risks, and missing tests; it independently reads source with three tools, combines specialist findings, hands off the assessment to a human, and succeeds when all three real sample reviews finish with valid source references and downloadable reports.

## Agent framework

| Field | Implementation |
| --- | --- |
| Goal | Produce one prioritized, actionable code review from three specialist assessments. |
| Surface | A local Streamlit app plus a Python CLI. |
| Control flow | Validate snapshot → parallel correctness/security/testing agents → validate locations and extract source → deduplicate and synthesize → human interrupt/resume. |
| Tools | `inspect_sources` reads numbered source plus AST observations and test inventory; `read_lines` verifies a selected range; `search_sources` searches literal text in the submitted snapshot. All three are read-only. |
| Memory | A session-owned LangGraph `InMemorySaver` stores source, results, reports and trace across graph steps and Streamlit reruns. Process restart or session reset clears it; exported JSON and Markdown persist only when explicitly saved/downloaded. |
| Hard limits | Never execute submitted code, install its dependencies, read outside the selected snapshot, apply fixes, merge code, or publish a review. Never claim measured coverage from static inspection. |
| Human intervention | A native LangGraph interrupt presents the draft; the user accepts the assessment or requests changes with notes. An incomplete review cannot be accepted. |
| Failure behavior | Retry transient transport failures at most once, attempt one targeted schema/location repair, isolate failed specialists, and mark partial results incomplete. Orchestrator failure falls back to deterministic ranking and also marks the review incomplete. |
| Success measure | Three real source snapshots finish with 3/3 specialist results, a successful synthesis, source-valid line ranges, severity ordering, an explicit pending human decision, and Markdown/JSON reports. This measures workflow completion, not ground-truth defect accuracy. |

## Agent roles and communication

1. **Correctness agent:** checks logic, boundaries, shared mutable state, lifecycle errors and consequential anti-patterns. It should explain a trigger and consequence rather than offer style commentary.
2. **Security agent:** checks input provenance, sensitive sinks, injection, access boundaries and unsafe serialization. It must state exploitation preconditions and distinguish hardening from demonstrated risk.
3. **Testing agent:** inventories only the supplied tests, maps visible assertions to behaviors, and suggests specific missing cases. Missing submitted tests are not proof that the upstream repository has no tests.
4. **Orchestrator:** consumes only validated findings and specialist status. It summarizes and orders existing IDs; deterministic code enforces severity ordering and prevents synthesis from adding findings.

The three specialists run on independent LangGraph branches. Their results and trace events use append reducers, and a fan-in edge runs the orchestrator only after all three finish. Source and tools are scoped to one immutable review request; credentials live only in provider configuration.

The specialists use native OpenAI-format tool calls to select verification tools, with at most three tool rounds and six tool invocations. JSON Schema constrains final output; the final schema also restricts filenames to the submitted paths. Pydantic checks the result, the application validates line ranges, and source excerpts are extracted from the original text instead of trusting generated quotations. Semantic truth still requires reviewer judgment.

## Datasets and provenance

The real evaluation uses unmodified source files fetched from pinned upstream release refs. `examples/real_samples.json` contains exact URLs, SHA-256 checksums, file sizes and local paths; the sample loader verifies these checksums.

| Sample | Release | Submitted scope | License |
| --- | --- | --- | --- |
| [Flask](https://github.com/pallets/flask/tree/3.1.2/examples/tutorial) | 3.1.2 | Tutorial authentication, database helper, and authentication tests | BSD-3-Clause |
| [FastAPI](https://github.com/fastapi/fastapi/tree/0.115.0/docs_src/security) | 0.115.0 | Introductory OAuth2 dependency and its upstream tests | MIT |
| [Starlette](https://github.com/encode/starlette/tree/0.41.3/starlette) | 0.41.3 | Authentication primitives; upstream middleware and tests are outside the snapshot | BSD-3-Clause |

Upstream license files accompany each snapshot. The separate `examples/demo` checkout service is an intentionally flawed synthetic fixture containing SQL interpolation, shell execution, a mutable default and an empty-list division edge case. It is clearly labeled synthetic and never counted toward the three real samples.

No sample source or sample tests are executed by this application. Reports are AI-generated assessments of limited source snapshots and are not verified claims about the upstream projects.

## Prompts used during the build

The implementation began with the user request to build Project 3E from the Week 3 handout, use LangGraph multi-agent orchestration, add a Streamlit UI, and access `nvidia/Nemotron-3_5-Lightning` through the supplied Nebius credential. This request served as the AI-assisted development brief; there were no separately supplied hidden coding prompts or prior solutions.

The actual runtime prompts are inspectable in `src/code_review/agents.py` (`ROLE_PROMPTS` and `COMMON_PROMPT`) and `src/code_review/graph.py` (orchestrator). They define scope, treat source comments as untrusted data, constrain severity, require existing source paths and lines, forbid runtime-coverage claims, and request schema-valid output. Tool descriptions and output schemas are sent with those prompts.

## Iterations and observations

1. **Initial provider probe:** verified the exact requested regional endpoint and model with the provided key, without displaying the credential.
2. **First full workflow:** default model thinking consumed the output budget in two specialist reviews. The system correctly retained completed results, marked the report incomplete, and required further work.
3. **Direct-output control:** applied NVIDIA's `chat_template_kwargs.enable_thinking=false` parameter for Lightning, preserving the response budget for tool calls and JSON. This materially reduced latency in subsequent local runs.
4. **Source evidence:** generated code quotations were occasionally paraphrased or included adjacent lines outside the citation. The final implementation validates the location and extracts exact source text on the server, eliminating fabricated quotation text.
5. **Structured repair:** final JSON uses provider-side schema constraints, explicit allowed filenames, and targeted validation feedback. Invented or invalid source locations fail the specialist after the bounded repair attempt.
6. **UI and orchestration checks:** tests exercise real LangGraph parallel branches and interrupt/resume with mocked model responses, source-only tools, failure isolation, input limits, credential handling, and Streamlit review/decision flows. Browser inspection checks the rendered interface separately.

The main observation is that reliable orchestration needs contracts, budgets, error states and explicit ownership of source evidence in addition to specialist prompts. Static LLM review can still produce false positives; the human decision is part of the product's completion criteria.

## Validation and saved results

Run `python -m pytest -q` for deterministic automated checks. Run `python -m code_review evaluate --output reports` for live provider evaluation; it writes per-sample Markdown/JSON reports, graph traces and aggregate completion metrics. `reports/evaluation.md` and `reports/evaluation.json` contain the observed timings and statuses from the saved run; model assessments are left pending human review.

The final automated run passed **30 tests**. The saved live evaluation completed **3/3 real samples**, with all three specialists and the orchestrator succeeding: Flask in 12.93 seconds, FastAPI in 20.16 seconds, and Starlette in 20.68 seconds. These are single-run local observations; no recall, precision or coverage accuracy is claimed. `pip check` also found no broken dependency requirements.

The final browser check ran the synthetic sample through Streamlit, completed all review stages in 14.8 seconds, downloaded a valid JSON draft, and resumed the human gate with a “changes requested” decision and reviewer notes. The request count stayed at eight after the decision, confirming that feedback did not rerun the model. The downloaded draft is saved as `reports/demo.json` and `reports/demo.md`.

`requirements.lock` records installed dependency versions. `scripts/package_project.py` creates a source ZIP from an explicit allowlist and excludes the original credential, `.env`, Streamlit secrets, virtual environments and session data.

## Five-minute demo script

- **0:00–0:40:** Introduce the engineering problem and three review lenses. Open How it works to show fan-out, fan-in and the human decision.
- **0:40–1:20:** Select the synthetic checkout sample, inspect its source and supplied test, then run a review. Explain that all AI roles use the requested Nemotron model on Nebius.
- **1:20–2:30:** Open a prioritized finding, inspect its exact source lines, recommended fix and suggested regression test. Filter by security or severity without making another model call.
- **2:30–3:15:** Open Agent assessments and Workflow & scope to inspect tool usage, agent status, limits and trace. Explain why static inspection is not measured test coverage.
- **3:15–4:00:** Record a human decision with notes. Show that the graph resumes without rerunning specialists and that no source file is changed.
- **4:00–4:40:** Visit Sample reports to inspect the three real-source evaluations and show the export buttons. Explain pinned source refs and source hashes.
- **4:40–5:00:** Describe the AI-assisted build, output-budget and citation iterations, and the automated test result. End with the local source repository and documentation ready for submission.

## Submission handoff

The code, documentation, real-source sample reports and source ZIP are prepared locally. The course additionally requests a Google Doc, a demo recording of five minutes or less, and a GitHub link. Copy this document into a Google Doc, record the demonstration, and publish the sanitized source ZIP/repository from your own accounts when ready.

## Primary implementation references

- [LangGraph graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [Streamlit AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest)
- [Nebius quickstart](https://docs.tokenfactory.nebius.com/quickstart)
- [Nebius tool calling](https://docs.tokenfactory.nebius.com/ai-models-inference/function-calling)
- [Nebius structured output](https://docs.tokenfactory.nebius.com/ai-models-inference/json)
- [Nebius direct-output verification for Lightning](https://github.com/nebius/nebius-physical-ai/blob/main/docs/workbench/token-factory-deprecation-verification.md)
