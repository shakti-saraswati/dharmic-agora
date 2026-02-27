# 49-Node to 12-Keystone Mapping

Purpose: bridge 500-year lattice orientation to near-term execution keystones.

Canonical source of truth:
- `integration/keystone_map.py`

Any mapping change should update that file first, then docs.

---

## Canonical Keystone Map

| Keystone | Upstream | Primary Node | Domain | Theme |
|---|---|---|---|---|
| K01 | temporalio/temporal | Node_04_Production_Emergence | Production | Emergence |
| K02 | crewai/crewai | Node_01_AI_Swarm_Emergence | AI/Swarm | Emergence |
| K03 | promptfoo/promptfoo | Node_05_Science_Emergence | Science | Emergence |
| K04 | confident-ai/deepeval | Node_12_Science_Symbiosis | Science | Symbiosis |
| K05 | chroma-core/chroma | Node_03_Knowledge_Emergence | Knowledge | Emergence |
| K06 | mem0ai/mem0 | Node_17_Knowledge_Resilience | Knowledge | Resilience |
| K07 | llmguard/llmguard | Node_16_Philosophy_Resilience | Philosophy | Resilience |
| K08 | guardrailsai/guardrails | Node_23_Philosophy_Telos | Philosophy | Telos |
| K09 | litellm/litellm | Node_08_AI_Swarm_Symbiosis | AI/Swarm | Symbiosis |
| K10 | agentops/agentops | Node_36_AI_Kaizen | AI/Swarm | Kaizen |
| K11 | mastra/mastra | Node_11_Production_Symbiosis | Production | Symbiosis |
| K12 | agno/agno | Node_32_Production_Kaizen | Production | Kaizen |

---

## Query Examples

What node supports one keystone:

```bash
python3 integration/keystone_bridge.py --keystone K01
```

What keystones map to one node:

```bash
python3 integration/keystone_bridge.py --node Node_36
```

Show full map:

```bash
python3 integration/keystone_bridge.py --map
```

