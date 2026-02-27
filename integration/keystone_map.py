#!/usr/bin/env python3
"""
Canonical 49-node <-> 12-keystone mapping.

This module is the single source of truth used by:
- integration/keystone_bridge.py
- docs/49_TO_KEYSTONES_MAP.md
- docs/KEYSTONES_72H.md
"""

from __future__ import annotations

from typing import Dict


# Canonical mapping: keystone id -> lattice node.
KEYSTONE_TO_NODE: Dict[str, Dict[str, str]] = {
    "K01": {
        "keystone": "temporalio/temporal",
        "node": "Node_04",
        "node_label": "Node_04_Production_Emergence",
        "domain": "Production",
        "theme": "Emergence",
    },
    "K02": {
        "keystone": "crewai/crewai",
        "node": "Node_01",
        "node_label": "Node_01_AI_Swarm_Emergence",
        "domain": "AI/Swarm",
        "theme": "Emergence",
    },
    "K03": {
        "keystone": "promptfoo/promptfoo",
        "node": "Node_05",
        "node_label": "Node_05_Science_Emergence",
        "domain": "Science",
        "theme": "Emergence",
    },
    "K04": {
        "keystone": "confident-ai/deepeval",
        "node": "Node_12",
        "node_label": "Node_12_Science_Symbiosis",
        "domain": "Science",
        "theme": "Symbiosis",
    },
    "K05": {
        "keystone": "chroma-core/chroma",
        "node": "Node_03",
        "node_label": "Node_03_Knowledge_Emergence",
        "domain": "Knowledge",
        "theme": "Emergence",
    },
    "K06": {
        "keystone": "mem0ai/mem0",
        "node": "Node_17",
        "node_label": "Node_17_Knowledge_Resilience",
        "domain": "Knowledge",
        "theme": "Resilience",
    },
    "K07": {
        "keystone": "llmguard/llmguard",
        "node": "Node_16",
        "node_label": "Node_16_Philosophy_Resilience",
        "domain": "Philosophy",
        "theme": "Resilience",
    },
    "K08": {
        "keystone": "guardrailsai/guardrails",
        "node": "Node_23",
        "node_label": "Node_23_Philosophy_Telos",
        "domain": "Philosophy",
        "theme": "Telos",
    },
    "K09": {
        "keystone": "litellm/litellm",
        "node": "Node_08",
        "node_label": "Node_08_AI_Swarm_Symbiosis",
        "domain": "AI/Swarm",
        "theme": "Symbiosis",
    },
    "K10": {
        "keystone": "agentops/agentops",
        "node": "Node_36",
        "node_label": "Node_36_AI_Kaizen",
        "domain": "AI/Swarm",
        "theme": "Kaizen",
    },
    "K11": {
        "keystone": "mastra/mastra",
        "node": "Node_11",
        "node_label": "Node_11_Production_Symbiosis",
        "domain": "Production",
        "theme": "Symbiosis",
    },
    "K12": {
        "keystone": "agno/agno",
        "node": "Node_32",
        "node_label": "Node_32_Production_Kaizen",
        "domain": "Production",
        "theme": "Kaizen",
    },
}

