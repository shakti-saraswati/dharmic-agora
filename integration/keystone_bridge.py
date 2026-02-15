#!/usr/bin/env python3
"""
49→12 Keystone Bridge Query
Queries the relationship between 49-node lattice and 12 KEYSTONES

Usage:
  python3 keystone_bridge.py --keystone K01          # What 49-nodes support this keystone?
  python3 keystone_bridge.py --node "Node_01"        # What keystones map to this node?
  python3 keystone_bridge.py --theme "Kaizen"        # All keystones with Kaizen theme
  python3 keystone_bridge.py --map                   # Full mapping table
"""

import yaml
import sys
from pathlib import Path

# Mapping from 49_TO_KEYSTONES_MAP.md
KEYSTONE_TO_NODE = {
    "K01": {"keystone": "temporalio/temporal", "node": "Node_04", "domain": "Production", "theme": "Emergence"},
    "K02": {"keystone": "crewai/crewai", "node": "Node_01", "domain": "AI/Swarm", "theme": "Emergence"},
    "K03": {"keystone": "promptfoo/promptfoo", "node": "Node_05", "domain": "Science", "theme": "Emergence"},
    "K04": {"keystone": "confident-ai/deepeval", "node": "Node_12", "domain": "Science", "theme": "Symbiosis"},
    "K05": {"keystone": "chroma-core/chroma", "node": "Node_03", "domain": "Knowledge", "theme": "Emergence"},
    "K06": {"keystone": "mem0ai/mem0", "node": "Node_17", "domain": "Knowledge", "theme": "Resilience"},
    "K07": {"keystone": "llmguard/llmguard", "node": "Node_16", "domain": "Philosophy", "theme": "Resilience"},
    "K08": {"keystone": "guardrailsai/guardrails", "node": "Node_23", "domain": "Philosophy", "theme": "Telos"},
    "K09": {"keystone": "litellm/litellm", "node": "Node_08", "domain": "AI/Swarm", "theme": "Symbiosis"},
    "K10": {"keystone": "agentops/agentops", "node": "Node_36", "domain": "AI/Swarm", "theme": "Kaizen"},
    "K11": {"keystone": "mastra/mastra", "node": "Node_11", "domain": "Production", "theme": "Symbiosis"},
    "K12": {"keystone": "agno/agno", "node": "Node_32", "domain": "Production", "theme": "Kaizen"},
}

# Reverse mapping
NODE_TO_KEYSTONES = {}
for k_id, mapping in KEYSTONE_TO_NODE.items():
    node = mapping["node"]
    if node not in NODE_TO_KEYSTONES:
        NODE_TO_KEYSTONES[node] = []
    NODE_TO_KEYSTONES[node].append({
        "keystone_id": k_id,
        "keystone": mapping["keystone"],
        "theme": mapping["theme"]
    })

class KeystoneBridge:
    """Bridge between 49-node lattice and 12 KEYSTONES"""
    
    def __init__(self, project_root=None):
        self.project_root = Path(project_root) if project_root else Path(__file__).parent.parent
        
    def query_keystone(self, keystone_id):
        """Get 49-node support for a keystone"""
        mapping = KEYSTONE_TO_NODE.get(keystone_id.upper())
        if not mapping:
            return None
            
        # Find related nodes (same domain, adjacent themes)
        domain = mapping["domain"]
        theme = mapping["theme"]
        
        related = []
        for node_id, keystones in NODE_TO_KEYSTONES.items():
            for k in keystones:
                if k["keystone_id"] != keystone_id.upper():
                    # Check if same domain or theme
                    k_mapping = KEYSTONE_TO_NODE.get(k["keystone_id"])
                    if k_mapping and (k_mapping["domain"] == domain or k_mapping["theme"] == theme):
                        related.append({
                            "node": node_id,
                            "keystone": k["keystone_id"],
                            "name": k["keystone"]
                        })
                        
        return {
            "keystone": mapping["keystone"],
            "primary_node": mapping["node"],
            "domain": domain,
            "theme": theme,
            "related_nodes": related[:3]  # Top 3 related
        }
        
    def query_node(self, node_id):
        """Get keystones mapped to a 49-node"""
        keystones = NODE_TO_KEYSTONES.get(node_id)
        if not keystones:
            return None
            
        # Find node metadata from 49_NODES.md
        node_meta = self._get_node_metadata(node_id)
        
        return {
            "node": node_id,
            "metadata": node_meta,
            "keystones": keystones
        }
        
    def query_theme(self, theme):
        """Get all keystones with a specific theme"""
        matching = []
        for k_id, mapping in KEYSTONE_TO_NODE.items():
            if mapping["theme"].lower() == theme.lower():
                matching.append({
                    "keystone_id": k_id,
                    "keystone": mapping["keystone"],
                    "node": mapping["node"],
                    "domain": mapping["domain"]
                })
        return matching
        
    def _get_node_metadata(self, node_id):
        """Extract metadata from 49_NODES.md"""
        nodes_file = self.project_root / "nvidia_core" / "docs" / "49_NODES.md"
        if not nodes_file.exists():
            return {}
            
        content = nodes_file.read_text()
        
        # Simple extraction - look for node number in content
        # e.g., "1.1 | Recursive Self-Modification"
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if node_id.replace("Node_", "").lstrip('0') in line or node_id in line:
                # Return surrounding context
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                return {"context": '\n'.join(lines[start:end])}
                
        return {}
        
    def print_full_map(self):
        """Print complete mapping table"""
        print("\n" + "="*70)
        print("49-NODE → 12 KEYSTONE MAPPING")
        print("="*70)
        print(f"{'Keystone':<12} {'Node':<10} {'Domain':<20} {'Theme':<15}")
        print("-"*70)
        
        for k_id in sorted(KEYSTONE_TO_NODE.keys()):
            m = KEYSTONE_TO_NODE[k_id]
            print(f"{k_id:<12} {m['node']:<10} {m['domain']:<20} {m['theme']:<15}")
            
        print("="*70)

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="49→12 Keystone Bridge")
    parser.add_argument("--keystone", help="Query by keystone ID (e.g., K01)")
    parser.add_argument("--node", help="Query by node ID (e.g., Node_01)")
    parser.add_argument("--theme", help="Query by theme (e.g., Kaizen)")
    parser.add_argument("--map", action="store_true", help="Show full mapping")
    
    args = parser.parse_args()
    
    bridge = KeystoneBridge()
    
    if args.map:
        bridge.print_full_map()
        
    elif args.keystone:
        result = bridge.query_keystone(args.keystone)
        if result:
            print(f"\n🔷 {args.keystone.upper()}: {result['keystone']}")
            print(f"   Primary 49-node: {result['primary_node']} ({result['domain']})")
            print(f"   Theme: {result['theme']}")
            if result['related_nodes']:
                print(f"\n   Related nodes:")
                for r in result['related_nodes']:
                    print(f"     • {r['node']} → {r['keystone']}: {r['name']}")
        else:
            print(f"❌ Keystone {args.keystone} not found")
            
    elif args.node:
        result = bridge.query_node(args.node)
        if result:
            print(f"\n🕸️ {args.node}")
            if result['keystones']:
                print(f"   Mapped keystones:")
                for k in result['keystones']:
                    print(f"     • {k['keystone_id']}: {k['keystone']}")
        else:
            print(f"❌ Node {args.node} not found")
            
    elif args.theme:
        results = bridge.query_theme(args.theme)
        if results:
            print(f"\n🎯 Theme: {args.theme}")
            for r in results:
                print(f"   • {r['keystone_id']}: {r['keystone']} ({r['node']}, {r['domain']})")
        else:
            print(f"❌ No keystones with theme '{args.theme}'")
    else:
        bridge.print_full_map()

if __name__ == "__main__":
    main()
