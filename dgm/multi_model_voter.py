#!/usr/bin/env python3
"""
DGC Multi-Model Voter — anekāntavāda in code.
Uses ONLY free APIs (NVIDIA NIM + OpenRouter free tier).
Each model scores content independently. Disagreement = signal.
"""
import json, os, time, requests
from typing import Dict, List, Optional
from pathlib import Path

# Load NVIDIA key from OpenClaw config
def _load_nvidia_key():
    config_path = Path("/home/openclaw/.openclaw/openclaw.json")
    if config_path.exists():
        config = json.loads(config_path.read_text())
        return config.get("models", {}).get("providers", {}).get("nvidia", {}).get("apiKey", "")
    return os.environ.get("NVIDIA_API_KEY", "")

NVIDIA_KEY = _load_nvidia_key()
NVIDIA_BASE = "https://integrate.api.nvidia.com/v1/chat/completions"

# Free models available on NVIDIA NIM
MODELS = {
    "nemotron-ultra": "nvidia/llama-3.1-nemotron-ultra-253b-v1",
    "nemotron-super": "nvidia/llama-3.3-nemotron-super-49b-v1.5",
    "deepseek-v3": "deepseek-ai/deepseek-v3.2",
    "deepseek-v3.1": "deepseek-ai/deepseek-v3.1",
    "qwen3-next": "qwen/qwen3-next-80b-a3b-instruct",
    "qwen3-235b": "qwen/qwen3-235b-a22b",
    "qwen3-coder": "qwen/qwen3-coder-480b-a35b-instruct",
    "glm-4.7": "z-ai/glm4.7",
    "glm-5": "z-ai/glm5",
    "nemotron-nano": "nvidia/nemotron-nano-3-30b-a3b",
    "devstral": "mistralai/devstral-2-123b-instruct-2512",
    "llama-405b": "meta/llama-3.1-405b-instruct",
    "llama-70b": "meta/llama-3.3-70b-instruct",
    "mistral-nemotron": "mistralai/mistral-nemotron",
    "qwq-32b": "qwen/qwq-32b",
}

SCORING_PROMPT = """You are evaluating content for a dharmic discussion platform.
Rate this content on a scale of 0.0 to 1.0 across these dimensions:

1. TRUTH (satya): Factual accuracy, evidence quality, epistemic humility
2. NON-HARM (ahimsa): Respectful, constructive, no attacks
3. DEPTH: Structural complexity, originality, references, insight
4. ALIGNMENT: On-topic, relevant, coherent argument

Content to evaluate:
---
{content}
---

Respond with ONLY valid JSON, no other text:
{{"truth": 0.X, "non_harm": 0.X, "depth": 0.X, "alignment": 0.X}}"""


def call_nvidia_nim(model_id: str, content: str, timeout: int = 60) -> Optional[Dict]:
    """Call a single NVIDIA NIM model. Returns scores dict or None on failure."""
    try:
        resp = requests.post(
            NVIDIA_BASE,
            headers={
                "Authorization": f"Bearer {NVIDIA_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": SCORING_PROMPT.format(content=content[:2000])}],
                "max_tokens": 100,
                "temperature": 0.1,
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        
        data = resp.json()
        msg = data["choices"][0]["message"]
        # Handle reasoning models (content in reasoning_content, answer in content)
        text = msg.get("content") or ""
        if not text and msg.get("reasoning_content"):
            text = msg["reasoning_content"]
        text = text.strip()
        
        # Extract JSON from response (handle markdown wrapping)
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        
        scores = json.loads(text)
        # Validate
        for key in ["truth", "non_harm", "depth", "alignment"]:
            if key not in scores:
                return None
            scores[key] = max(0.0, min(1.0, float(scores[key])))
        
        return scores
    except Exception as e:
        return None


def multi_model_vote(content: str, models: List[str] = None, min_voters: int = 2) -> Dict:
    """
    Score content using multiple free models.
    Returns aggregated scores + disagreement metrics.
    """
    if models is None:
        # Default: use 3 non-reasoning models for speed
        models = ["deepseek-v3", "qwen3-next", "llama-70b"]
    
    votes = {}
    for model_name in models:
        model_id = MODELS.get(model_name)
        if not model_id:
            continue
        
        result = call_nvidia_nim(model_id, content)
        if result:
            votes[model_name] = result
        
        time.sleep(0.5)  # Rate limit respect
    
    if len(votes) < min_voters:
        return {"error": f"Only {len(votes)} models responded (need {min_voters})", "votes": votes}
    
    # Aggregate: mean + variance per dimension
    dimensions = ["truth", "non_harm", "depth", "alignment"]
    aggregated = {}
    
    for dim in dimensions:
        scores = [v[dim] for v in votes.values()]
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        aggregated[dim] = {
            "mean": round(mean, 4),
            "variance": round(variance, 4),
            "min": round(min(scores), 4),
            "max": round(max(scores), 4),
        }
    
    # Composite score
    composite = sum(aggregated[d]["mean"] for d in dimensions) / len(dimensions)
    
    # Overall disagreement (mean variance across dimensions)
    disagreement = sum(aggregated[d]["variance"] for d in dimensions) / len(dimensions)
    
    return {
        "composite": round(composite, 4),
        "disagreement": round(disagreement, 4),
        "flag_for_review": disagreement > 0.05,  # High disagreement = boundary case
        "dimensions": aggregated,
        "individual_votes": votes,
        "model_count": len(votes),
    }


if __name__ == "__main__":
    # Quick test
    print("Testing multi-model voter with NVIDIA NIM...")
    
    # Test 1: High quality content
    good = """The R_V contraction metric shows measurable structural changes in transformer 
    architectures during recursive self-observation. Cohen's d ranges from -3.56 to -4.51, 
    suggesting systematic geometric compression. Building on Hofstadter (1979) and extending 
    to computational substrates."""
    
    print("\n=== HIGH QUALITY ===")
    result = multi_model_vote(good, models=["nemotron-ultra", "deepseek-v3"])
    print(json.dumps(result, indent=2))
    
    # Test 2: Low quality
    bad = "lol AI is dumb trust me bro just vibes"
    
    print("\n=== LOW QUALITY ===")
    result2 = multi_model_vote(bad, models=["nemotron-ultra", "deepseek-v3"])
    print(json.dumps(result2, indent=2))
    
    if "composite" in result and "composite" in result2:
        print(f"\nSEPARATION: {result['composite'] - result2['composite']:.4f}")
