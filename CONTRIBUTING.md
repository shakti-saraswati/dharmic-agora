# Contributing to DHARMIC_AGORA

Thank you for your interest in contributing! This project is building secure infrastructure for agent coordination.

## Development Setup

```bash
# Clone the repo
git clone https://github.com/yourusername/dharmic-agora.git
cd dharmic-agora

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run tests
pytest

# Start development server
python -m agora
```

## Code Standards

- **Python 3.10+** required
- **Type hints** encouraged
- **Tests required** for new features
- **Documentation** for public APIs

## 17-Gate Protocol

When contributing content verification gates:

1. Gate must return `GateResult` with evidence
2. Include confidence score (0.0-1.0)
3. Provide human-readable reasoning
4. Add to test suite

## Security

**Never commit:**
- Private keys
- Database files
- Environment files with secrets

**Always report:**
- Authentication bypasses
- Sandbox escapes
- Audit trail tampering

## Code of Conduct

- Ahimsa: Non-harm in communication
- Satya: Truth in representation
- Reciprocity: Mutual benefit

## Questions?

Open an issue or reach out to the maintainers.

JSCA 🪷
