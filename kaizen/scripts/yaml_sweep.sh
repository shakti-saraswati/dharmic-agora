#!/bin/bash
# YAML Frontmatter Sweep Script
# Adds YAML to all 44 files from Feb 13-14 sprint

cd /Users/dhyana/clawd

echo "🔍 Scanning for files without YAML frontmatter..."

# Function to add YAML to a file
add_yaml() {
    file="$1"
    
    # Skip if already has YAML
    if head -1 "$file" | grep -q "^---"; then
        echo "  ✓ $file (already has YAML)"
        return
    fi
    
    # Extract title from first heading or filename
    title=$(head -20 "$file" | grep "^# " | head -1 | sed 's/^# //' || basename "$file" .md)
    
    # Generate YAML
    yaml="---
title: \"$title\"
date: $(date +%Y-%m-%d)
timestamp: $(date -u +%Y-%m-%dT%H:%M:%S+00:00)
agent: DC
jikoku: \"$(date -u +%Y-%m-%dT%H:%M:%S) UTC — YAML sweep\"
context: \"Part of Feb 13-14 sprint, now with frontmatter\"
status: canon
quality_grade: B
coherence: 4
actionability: 4
originality: 4
use_count: 1
last_accessed: $(date +%Y-%m-%d)
links: []
---

"
    
    # Prepend YAML to file
    echo "$yaml" | cat - "$file" > "$file.tmp" && mv "$file.tmp" "$file"
    echo "  ✓ $file (YAML added)"
}

# Target files from Feb 13-14
echo "Processing UPSTREAMS..."
add_yaml "docs/UPSTREAMS_v0.md"

echo "Processing KEYSTONES..."
add_yaml "docs/KEYSTONES_72H.md"

echo "Processing Swarm Research..."
for file in swarm_research/*.md; do
    add_yaml "$file"
done

echo "Processing SAB Quality..."
add_yaml "Staging-Anti_SLOP/papers/SAB_QUALITY_DIMENSIONS.md"

echo ""
echo "✅ YAML sweep complete"
echo "Next: git diff to review changes"
