#!/bin/bash
# DHARMIC_AGORA GitHub Release Script

set -e

echo "🪷 DHARMIC_AGORA GitHub Release Preparation"
echo "============================================"

# Check if in git repo
if [ ! -d ".git" ]; then
    echo "❌ Not a git repository. Run: git init"
    exit 1
fi

# Check for uncommitted changes
if [ -n "$(git status --porcelain)" ]; then
    echo "⚠️  Uncommitted changes detected. Commit first:"
    git status --short
    exit 1
fi

# Run tests
echo ""
echo "Running tests..."
python3 -m pytest agora/tests/ -v --tb=short

# Validate naming registry (prevents drift)
echo ""
echo "Validating NAME_REGISTRY..."
python3 scripts/check_name_registry.py

# Run integration test
echo ""
echo "Running integration test..."
python3 scripts/integration_test.py

# Count lines of code
echo ""
echo "Code statistics:"
find agora -name "*.py" -exec wc -l {} + | tail -1

# Check key files exist
echo ""
echo "Verifying release files..."
required_files=(
    "README.md"
    "LICENSE"
    "CHANGELOG.md"
    "CONTRIBUTING.md"
    "pyproject.toml"
    "requirements.txt"
    "Dockerfile"
    "docker-compose.yml"
    ".gitignore"
)

for file in "${required_files[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✅ $file"
    else
        echo "  ❌ $file MISSING"
        exit 1
    fi
done

echo ""
echo "============================================"
echo "✅ Release validation PASSED"
echo ""
echo "Ready for GitHub:"
echo "  1. Create repo on GitHub"
echo "  2. git remote add origin <repo-url>"
echo "  3. git push -u origin main"
echo ""
echo "JSCA 🪷"
