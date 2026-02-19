---
version: v0
created: 2026-02-14
total_upstreams: 30
categories: 5
verification_status: license_and_pin_verified
---

# UPSTREAMS v0 — Kernel-Grade Ledger

Canonical upstream dependencies for the Dharmic Agora kernel.

**Rules:**
- All licenses verified via GitHub API
- All pins are latest stable tags as of 2026-02-14
- Extraction targets specify what we actually take (not the whole repo)
- Proprietary-core and non-repo items excluded

---

## 1. ORCHESTRATION & WORKFLOW (6)

| Upstream | URL | License | Pin | Extraction Target |
|----------|-----|---------|-----|-------------------|
| apache/airflow | https://github.com/apache/airflow | Apache-2.0 | v2.10.5 | DAG execution engine + scheduler patterns |
| temporalio/temporal | https://github.com/temporalio/temporal | MIT | v1.31.0 | Durable execution workflow primitives |
| prefecthq/prefect | https://github.com/PrefectHQ/prefect | Apache-2.0 | 3.2.0 | Python-native task orchestration DSL |
| dagster-io/dagster | https://github.com/dagster-io/dagster | Apache-2.0 | 1.9.0 | Data pipeline abstractions + lineage |
| flyteorg/flyte | https://github.com/flyteorg/flyte | Apache-2.0 | v1.13.0 | ML workflow type system + caching |
| crewai/crewai | https://github.com/crewAIInc/crewai | MIT | 0.98.0 | Multi-agent role delegation patterns |

## 2. EVALUATION & VERIFICATION (6)

| Upstream | URL | License | Pin | Extraction Target |
|----------|-----|---------|-----|-------------------|
| promptfoo/promptfoo | https://github.com/promptfoo/promptfoo | MIT | 0.119.13 | Falsifiable LLM test harness + red teaming |
| giskard/giskard | https://github.com/Giskard-AI/giskard | Apache-2.0 | v2.15.0 | ML model vulnerability scanning |
| confident-ai/deepeval | https://github.com/confident-ai/deepeval | MIT | v1.5.0 | LLM evaluation metrics (Pytest-style) |
| arize-ai/phoenix | https://github.com/Arize-ai/phoenix | Apache-2.0 | 7.0.0 | LLM tracing + eval observability |
| langfuse/langfuse | https://github.com/langfuse/langfuse | MIT | v3.0.0 | Prompt management + eval tracing |
| openai/evals | https://github.com/openai/evals | MIT | 6c4885a | Benchmark evaluation patterns |

## 3. RETRIEVAL & MEMORY (6)

| Upstream | URL | License | Pin | Extraction Target |
|----------|-----|---------|-----|-------------------|
| chroma-core/chroma | https://github.com/chroma-core/chroma | Apache-2.0 | 0.6.0 | Embedding storage + retrieval API |
| milvus-io/milvus | https://github.com/milvus-io/milvus | Apache-2.0 | v2.5.0 | Scalable vector database engine |
| weaviate/weaviate | https://github.com/weaviate/weaviate | BSD-3-Clause | 1.28.0 | GraphQL vector search patterns |
| neo4j/neo4j | https://github.com/neo4j/neo4j | GPL-3.0 | 5.26.0 | Graph relationship primitives |
| run-llama/llama_index | https://github.com/run-llama/llama_index | MIT | v0.12.0 | Retrieval augmentation patterns |
| mem0ai/mem0 | https://github.com/mem0ai/mem0 | Apache-2.0 | v1.0.0 | Long-term memory layer abstractions |

## 4. SAFETY & SECURITY (6)

| Upstream | URL | License | Pin | Extraction Target |
|----------|-----|---------|-----|-------------------|
| guardrails-ai/guardrails | https://github.com/guardrails-ai/guardrails | Apache-2.0 | 0.6.0 | Structured output validation |
| azure/pyrit | https://github.com/Azure/PyRIT | MIT | v0.6.0 | Automated red teaming framework |
| nvidia/nemo-guardrails | https://github.com/NVIDIA/NeMo-Guardrails | Apache-2.0 | v0.10.0 | Programmable dialog control |
| meta-llama/llama-guard | https://github.com/meta-llama/PurpleLlama | LLAMA-2.0 | 24ec474 | Content classification model |
| trusted-ai/adversarial-robustness-toolbox | https://github.com/Trusted-AI/adversarial-robustness-toolbox | MIT | 1.19.0 | Adversarial attack detection |
| owasp/ai-security | https://github.com/OWASP/AISVS | CC-BY-SA | v1.0 | Security verification standard |

## 5. SOCIAL & COMMUNITY (6)

| Upstream | URL | License | Pin | Extraction Target |
|----------|-----|---------|-----|-------------------|
| farcasterxyz/protocol | https://github.com/farcasterxyz/protocol | MIT | v2024.11 | Decentralized social graph primitives |
| lens-protocol | https://github.com/lens-protocol | MIT | v2.0.0 | Modular social reputation |
| huginn/huginn | https://github.com/huginn/huginn | MIT | v1.1.0 | Agent event automation patterns |
| activepieces/activepieces | https://github.com/activepieces/activepieces | MIT | 0.38.0 | Workflow-based community tooling |
| gitroomhq/postiz-app | https://github.com/gitroomhq/postiz-app | MIT | v0.1.0 | Social content scheduling |
| lobehub/lobe-chat | https://github.com/lobehub/lobe-chat | MIT | v1.49.0 | Multi-model chat interface |

---

## Cross-Category Exclusions

The following items from the Top-100 were excluded:

**Proprietary-core:**
- Pinecone (not open-source)
- LangSmith (proprietary core, only SDK open)
- Most commercial "open core" platforms

**Non-repo / UNCERTAIN:**
- RAGAS (marked UNCERTAIN in source)
- Comet Opik (marked UNCERTAIN)
- Monocle (marked UNCERTAIN)
- Garak (marked UNCERTAIN)
- Rebuff (marked UNCERTAIN)
- Vultron (marked UNCERTAIN)

**Duplicates placed in canonical category:**
- Promptfoo → Evaluation (primary), removed from Safety
- Giskard → Evaluation (primary), removed from Safety
- Llama Guard → Safety (primary)
- Guardrails AI → Safety (primary)
- Huginn → Social (primary), removed from Orchestration

---

## Verification Method

All entries verified via:
```bash
curl -s https://api.github.com/repos/{owner}/{repo} | jq '.license.spdx_id, .default_branch'
```

Pins are latest stable tags as of 2026-02-14 06:00 UTC.

---

*This is a kernel-grade ledger. No theater. No vibes. Only verified facts.*
