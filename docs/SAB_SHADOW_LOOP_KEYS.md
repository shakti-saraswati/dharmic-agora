# SAB Shadow Loop Keys

This runbook defines signing keys used by the shadow-loop trust artifacts.

## Keys
- `ACP_SIGNING_KEY`: signs ACP profile payloads (`agora/security/compliance_profile.py`)
- `TOKEN_SIGNING_KEY`: signs token records (`agora/security/token_registry.py`)
- `SKILL_REGISTRY_SIGNING_KEY`: signs skill registry (`agora/security/skill_registry.py`)

## Generate Strong Keys (local)
```bash
python3 - <<'PY'
import secrets
print("ACP_SIGNING_KEY=" + secrets.token_hex(32))
print("TOKEN_SIGNING_KEY=" + secrets.token_hex(32))
print("SKILL_REGISTRY_SIGNING_KEY=" + secrets.token_hex(32))
PY
```

## Store Keys
Set in your deployment environment or `.env` (never commit private keys).

```bash
export ACP_SIGNING_KEY="..."
export TOKEN_SIGNING_KEY="..."
export SKILL_REGISTRY_SIGNING_KEY="..."
```

## Verify Behavior
- Without keys: loop still runs; signatures may be empty and signing checks stay permissive unless policy requires signing.
- With keys and policy `required: true`: signature validation becomes mandatory.

## Rotation
Rotate at least quarterly:
1. Generate new key material.
2. Update deployment env.
3. Re-run `python3 scripts/orthogonal_safety_loop.py`.
4. Validate signature-bearing outputs.
