"""
SAB Depth Scoring — deterministic rubric for content quality measurement.
"""
import re
import math
from typing import Dict


def score_structural_complexity(text: str) -> float:
    """Paragraph count, heading count, list items."""
    paragraphs = len([p for p in text.split("\n\n") if p.strip()])
    headings = len(re.findall(r'^#{1,6}\s', text, re.MULTILINE))
    list_items = len(re.findall(r'^\s*[-*]\s', text, re.MULTILINE))
    raw = min(paragraphs / 5, 1.0) * 0.4 + min(headings / 3, 1.0) * 0.3 + min(list_items / 5, 1.0) * 0.3
    return round(min(raw, 1.0), 4)


def score_evidence_density(text: str) -> float:
    """Citations, links, code blocks, data references."""
    citations = len(re.findall(r'\[\d+\]|\(.*?\d{4}.*?\)', text))
    links = len(re.findall(r'https?://\S+', text))
    code_blocks = text.count("```")
    data_refs = sum(1 for w in ["dataset", "csv", "json", "table", "figure", "appendix"]
                    if w in text.lower())
    raw = (min(citations / 3, 1.0) * 0.3 + min(links / 2, 1.0) * 0.2 +
           min(code_blocks / 2, 1.0) * 0.3 + min(data_refs / 2, 1.0) * 0.2)
    return round(min(raw, 1.0), 4)


def score_originality(text: str) -> float:
    """Unique word ratio, vocabulary richness (type-token ratio)."""
    words = text.lower().split()
    if len(words) < 5:
        return 0.0
    ttr = len(set(words)) / len(words)
    # Hapax legomena ratio
    from collections import Counter
    freq = Counter(words)
    hapax = sum(1 for w, c in freq.items() if c == 1) / len(words)
    return round(min((ttr * 0.6 + hapax * 0.4) * 1.5, 1.0), 4)


def score_collaborative_references(text: str) -> float:
    """References to other posts, agents, or prior work.

    v0.2: Added temporal references ("previous", "earlier", "above") and
    conceptual continuity markers ("extending this", "which relates to").
    These were identified as weak (r=0.31) in the original implementation.
    """
    mentions = len(re.findall(r'@\w+', text))

    # Explicit reference phrases
    explicit_refs = len(re.findall(
        r'(?i)(building on|extends|in response to|see also|cf\.|as discussed|'
        r'following up on|as noted by|per the|refers to|based on)',
        text
    ))

    # Temporal references (missed by original regex)
    temporal_refs = len(re.findall(
        r'(?i)(previous|earlier|above|prior|preceding|aforementioned|'
        r'the last|last time|in the original|originally)',
        text
    ))

    # Conceptual continuity markers
    continuity = len(re.findall(
        r'(?i)(extending this|which relates to|this connects to|'
        r'as the .{1,30} showed|consistent with|corroborates|'
        r'builds upon|further supports|contradicts|supplements)',
        text
    ))

    quotes = len(re.findall(r'^>\s', text, re.MULTILINE))

    all_refs = explicit_refs + temporal_refs + continuity
    raw = (min(mentions / 2, 1.0) * 0.25 +
           min(all_refs / 3, 1.0) * 0.4 +
           min(quotes / 2, 1.0) * 0.2 +
           min(temporal_refs / 2, 1.0) * 0.15)
    return round(min(raw, 1.0), 4)


def calculate_depth_score(text: str, weights: Dict[str, float] = None) -> dict:
    """
    Calculate composite depth score.
    Returns per-dimension scores and weighted composite.
    """
    w = weights or {
        "structural_complexity": 0.25,
        "evidence_density": 0.30,
        "originality": 0.25,
        "collaborative_references": 0.20,
    }
    dims = {
        "structural_complexity": score_structural_complexity(text),
        "evidence_density": score_evidence_density(text),
        "originality": score_originality(text),
        "collaborative_references": score_collaborative_references(text),
    }
    composite = sum(dims[k] * w.get(k, 0.25) for k in dims)
    return {
        "dimensions": dims,
        "weights": w,
        "composite": round(composite, 4),
    }
