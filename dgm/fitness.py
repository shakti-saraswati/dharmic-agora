"""DGM Fitness Evaluator - Scores genome against test corpus"""

import json
import os
from pathlib import Path
from statistics import correlation


def load_corpus(corpus_dir="dgm/corpus"):
    """Load all test samples from corpus directory"""
    corpus = []
    corpus_path = Path(corpus_dir)
    
    if not corpus_path.exists():
        return []
    
    for json_file in sorted(corpus_path.glob("*.json")):
        with open(json_file, 'r') as f:
            data = json.load(f)
            corpus.append(data)
    
    return corpus


def score_content(content, genome):
    """Score a single piece of content using genome parameters
    
    Simplified scoring that uses genome weights without requiring full SAB imports
    This is a placeholder that calculates based on content characteristics
    """
    # Extract genome parameters
    gate_weights = genome.get('gate_weights', {})
    composite_weights = genome.get('composite_weights', {})
    thresholds = genome.get('thresholds', {})
    
    # Simple heuristic scoring based on content features
    # In production this would import and use actual SAB gates
    
    # Gate scores (0-1) based on simple heuristics
    gate_scores = {}
    
    # Satya (truth) - longer, more substantive content
    gate_scores['satya'] = min(1.0, len(content) / 500)
    
    # Ahimsa (non-harm) - lacks aggressive language (simplified)
    aggressive_words = ['hate', 'attack', 'destroy', 'kill']
    aggression = sum(1 for word in aggressive_words if word in content.lower())
    gate_scores['ahimsa'] = max(0.0, 1.0 - aggression * 0.2)
    
    # Witness - presence of observation language
    witness_markers = ['see', 'observe', 'notice', 'witness', 'aware']
    witness_count = sum(1 for marker in witness_markers if marker in content.lower())
    gate_scores['witness'] = min(1.0, witness_count * 0.3)
    
    # Substance - word count and depth indicators
    word_count = len(content.split())
    gate_scores['substance'] = min(1.0, word_count / 100)
    
    # Weighted gate score
    gates_score = 0.0
    total_weight = 0.0
    for gate_name, weight in gate_weights.items():
        if gate_name in gate_scores:
            gates_score += gate_scores[gate_name] * weight
            total_weight += weight
    
    if total_weight > 0:
        gates_score /= total_weight
    
    # Depth score (simplified - based on complexity)
    sentences = content.count('.') + content.count('!') + content.count('?')
    depth_score = min(1.0, sentences / 5)
    
    # Reputation score (placeholder - would use actual user reputation)
    reputation_score = 0.5
    
    # Composite score
    composite = (
        gates_score * composite_weights.get('gates', 0.35) +
        depth_score * composite_weights.get('depth', 0.45) +
        reputation_score * composite_weights.get('reputation', 0.20)
    )
    
    return composite


def evaluate_fitness(genome):
    """Evaluate genome fitness against test corpus
    
    Returns correlation between predicted scores and ground truth
    Higher correlation = better fitness
    """
    corpus = load_corpus()
    
    if len(corpus) < 2:
        # Not enough data for correlation
        return 0.0
    
    predicted_scores = []
    ground_truth = []
    
    for sample in corpus:
        content = sample.get('content', '')
        truth_score = sample.get('ground_truth_score', 0.5)
        
        predicted = score_content(content, genome)
        
        predicted_scores.append(predicted)
        ground_truth.append(truth_score)
    
    # Calculate Pearson correlation
    try:
        corr = correlation(predicted_scores, ground_truth)
        # Convert to positive fitness (correlation ranges -1 to 1)
        # Map to 0-1 range where 0.5 = no correlation
        fitness = (corr + 1.0) / 2.0
        return fitness
    except:
        # Fallback if correlation fails
        return 0.0


if __name__ == "__main__":
    # Standalone test
    import sys
    
    if len(sys.argv) >= 2:
        with open(sys.argv[1], 'r') as f:
            genome = json.load(f)
        
        fitness = evaluate_fitness(genome)
        print(f"Fitness: {fitness:.4f}")
    else:
        print("Usage: python fitness.py <genome.json>")
