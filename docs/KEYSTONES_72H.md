---
version: 72H
keystones: 12
selection_criteria: kernel_integrity_first
deadline: 2026-02-17T06:00:00Z
---

# KEYSTONES 72H — Critical Path Dependencies

Exactly 12 keystones selected from UPSTREAMS_v0 (2 per category).
Each keystone includes: why keystone, integration type, first file to create, first deterministic check.

---

## ORCHESTRATION (2 keystones)

### 1. temporalio/temporal
**Why keystone:** Durable execution is the foundation of reliable multi-agent workflows—agents must survive crashes and resume deterministically.

**Integration type:** KERNEL

**First file:** `kernel/orchestration/temporal_adapter.py`

**First deterministic check:** 
```python
# Test: workflow resumes from crash at exact step
assert workflow_state.after_crash == workflow_state.before_crash
assert replay_events.hash == original_events.hash
```

---

### 2. crewai/crewai
**Why keystone:** Multi-agent role delegation patterns without hard-coding agent relationships—enables emergent coordination.

**Integration type:** SWARM

**First file:** `swarm/roles/role_delegation.py`

**First deterministic check:**
```python
# Test: same task + same roles = same delegation graph
assert delegation_graph(task_hash, role_set) == expected_graph_hash
assert role_assignment.confidence > 0.85
```

---

## EVALUATION (2 keystones)

### 3. promptfoo/promptfoo
**Why keystone:** Only falsifiable LLM testing in the list—pass/fail oracles replace subjective "quality scores."

**Integration type:** VERIFICATION

**First file:** `verification/test_harness/promptfoo_adapter.py`

**First deterministic check:**
```python
# Test: assertion passes iff condition is met
assert run_assertion("contains(x)", output_with_x).pass == True
assert run_assertion("contains(x)", output_without_x).pass == False
assert test_result.hash == deterministic_hash(test_config, output)
```

---

### 4. confident-ai/deepeval
**Why keystone:** Pytest-style evaluation integrates with existing CI—evaluation becomes part of build, not afterthought.

**Integration type:** VERIFICATION

**First file:** `verification/metrics/deepeval_adapter.py`

**First deterministic check:**
```python
# Test: metric score reproducible across runs
score_1 = evaluate_metric(test_case, model_output)
score_2 = evaluate_metric(test_case, model_output)
assert abs(score_1 - score_2) < 0.001  # deterministic
assert score_1 >= 0.0 and score_1 <= 1.0  # bounded
```

---

## RETRIEVAL (2 keystones)

### 5. chroma-core/chroma
**Why keystone:** Most lightweight vector store—embeds without heavy infra, critical for kernel minimality.

**Integration type:** ADAPTER

**First file:** `adapters/retrieval/chroma_client.py`

**First deterministic check:**
```python
# Test: same query + same embeddings = same results (top-k deterministic)
results_1 = query_chroma(embedding, k=5)
results_2 = query_chroma(embedding, k=5)
assert results_1.ids == results_2.ids
assert results_1.distances[0] <= results_1.distances[1]  # sorted
```

---

### 6. mem0ai/mem0
**Why keystone:** Long-term memory layer designed for agents—episodic + semantic separation matches our architecture.

**Integration type:** KERNEL

**First file:** `kernel/memory/mem0_adapter.py`

**First deterministic check:**
```python
# Test: memory retrieval includes provenance
memory = recall(query="project deadline")
assert memory.source_event_id is not None
assert memory.verification_hash == sha256(memory.content + memory.source_event_id)
assert memory.retrieved_at is not None
```

---

## SAFETY (2 keystones)

### 7. guardrails-ai/guardrails
**Why keystone:** Structured output validation at kernel boundary—prevents malformed data from entering system.

**Integration type:** KERNEL

**First file:** `kernel/safety/output_validator.py`

**First deterministic check:**
```python
# Test: invalid output blocked, valid output passes
assert validate_output(invalid_structure).blocked == True
assert validate_output(valid_structure).blocked == False
assert validate_output(valid_structure).structure == valid_structure
```

---

### 8. azure/pyrit
**Why keystone:** Automated red teaming generates adversarial test cases continuously—security becomes validation, not audit.

**Integration type:** VERIFICATION

**First file:** `verification/redteam/pyrit_adapter.py`

**First deterministic check:**
```python
# Test: red team finds known vulnerabilities
attack_results = run_redteam(target="prompt_injection", iterations=100)
assert attack_results.found_jailbreaks >= 1  # should find something
assert attack_results.false_positives < 0.1  # precision check
```

---

## SOCIAL (2 keystones)

### 9. farcasterxyz/protocol
**Why keystone:** Decentralized identity + social graph without central authority—reputation emerges from verified work, not platform control.

**Integration type:** SOCIAL

**First file:** `social/identity/farcaster_adapter.py`

**First deterministic check:**
```python
# Test: identity verification requires proof, not registration
identity = verify_identity(farcaster_fid)
assert identity.proof_type in ["ens", "onchain_tx", "kernel_attestation"]
assert identity.verification_hash is not None
assert identity.registered_at < datetime.now()
```

---

### 10. lens-protocol
**Why keystone:** Modular reputation primitives—reputation is composable, context-specific, and non-transferable.

**Integration type:** SOCIAL

**First file:** `social/reputation/lens_adapter.py`

**First deterministic check:**
```python
# Test: reputation derived only from verified work
reputation = calculate_reputation(profile_id)
assert all(attestation.verified_by_kernel for attestation in reputation.attestations)
assert reputation.speculation_contributions == 0  # no karma farming
assert reputation.transferable == False
```

---

## CRITICAL INFRASTRUCTURE (2 additional keystones)

### 11. apache/airflow (reclassified as OBSERVABILITY)
**Why keystone:** DAG lineage tracking—every agent action has traceable upstream/downstream dependencies.

**Integration type:** OBSERVABILITY

**First file:** `observability/lineage/airflow_adapter.py`

**First deterministic check:**
```python
# Test: complete lineage reconstructable from logs
dag_run = execute_dag(agent_workflow)
lineage = reconstruct_lineage(dag_run.run_id)
assert lineage.start_event.hash in WitnessEvent.log
assert lineage.end_event.hash in WitnessEvent.log
assert lineage.dependency_graph.is_acyclic() == True
```

---

### 12. giskard/giskard (reclassified as OBSERVABILITY)
**Why keystone:** ML model vulnerability scanning—detects bias, robustness failures, and data leakage in agent components.

**Integration type:** OBSERVABILITY

**First file:** `observability/scanning/giskard_adapter.py`

**First deterministic check:**
```python
# Test: scan detects known vulnerability patterns
scan_results = scan_model(agent_model)
assert scan_results.vulnerabilities is not None
assert all(v.risk_level in ["low", "medium", "high", "critical"] for v in scan_results.vulnerabilities)
assert scan_results.scan_hash == deterministic_hash(scan_config, model_weights)
```

---

## Implementation Priority

**Week 1 (72H deadline):**
1. temporalio/temporal — durable execution foundation
2. promptfoo/promptfoo — falsifiable testing
3. guardrails-ai/guardrails — output validation
4. chroma-core/chroma — vector retrieval

**Week 2:**
5. crewai/crewai — role delegation
6. mem0ai/mem0 — long-term memory
7. azure/pyrit — red teaming
8. confident-ai/deepeval — pytest metrics

**Week 3:**
9. farcasterxyz/protocol — decentralized identity
10. lens-protocol — reputation
11. apache/airflow — lineage
12. giskard/giskard — vulnerability scanning

---

## Abort Conditions

- Any keystone fails deterministic check → halt integration, escalate to human
- Two keystones in same category fail → re-evaluate category architecture
- License verification fails for any keystone → immediate exclusion

---

*12 keystones. 72 hours. Kernel integrity non-negotiable.*
