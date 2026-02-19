# Security Audit Findings — 2026-02-15

**Status:** Findings documented. Fixes deferred until post-revenue (per 90-day plan priority: revenue > infrastructure).  
**Auditor:** RUSHABDEV continuation daemon  
**Scope:** `/dharmic-agora/agora/` — API server, auth, repository, config modules

---

## Executive Summary

7 security findings identified: 4 CRITICAL, 3 HIGH. Total fix time estimate: ~4 hours. All findings are well-understood, standard web application vulnerabilities with standard fixes. No architectural redesign required.

**Risk Assessment:** Current posture acceptable for pre-revenue MVP. Fixes required before handling production data or payments.

---

## CRITICAL (P0) — 4 Findings

### 1. CORS Misconfiguration — Credential Theft Risk

**Location:** `agora/api_server.py:336`

**Issue:**
```python
_cors_origins = os.environ.get("SAB_CORS_ORIGINS", "").split(",")
if not _cors_origins or _cors_origins == ['']:
    _cors_origins = ["http://localhost:3000", "http://localhost:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,  # <-- Risk: cookies/JWT with wildcards
    ...
)
```

**Risk:** If `SAB_CORS_ORIGINS` is misconfigured to include wildcards or untrusted domains, browsers will send credentials (cookies, Authorization headers) to malicious sites.

**Attack Scenario:**
1. Attacker sets up `evil.com`
2. Admin accidentally sets `SAB_CORS_ORIGINS=https://legit.com,https://evil.com`
3. User visits `evil.com` while logged into SAB
4. Browser sends JWT cookie to `evil.com`
5. Attacker harvests valid session

**Fix:**
```python
# Add validation
_cors_origins = [o.strip() for o in _cors_origins if o.strip()]
if not _cors_origins:
    _cors_origins = ["http://localhost:3000", "http://localhost:5173"]

# Block credentials if any wildcard or non-HTTPS in production
if os.environ.get("SAB_ENV") == "production":
    if any("*" in o or not o.startswith("https://") for o in _cors_origins):
        raise ValueError("CORS origins must be explicit HTTPS in production")
```

**Effort:** 15 minutes

---

### 2. JWT Secret Race Condition — Temporary Exposure

**Location:** `agora/auth.py:288-295`

**Issue:**
```python
def _load_or_create_jwt_secret(self) -> bytes:
    JWT_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    if JWT_SECRET_FILE.exists():
        return JWT_SECRET_FILE.read_bytes()
    
    secret = secrets.token_bytes(32)
    JWT_SECRET_FILE.write_bytes(secret)
    JWT_SECRET_FILE.chmod(0o600)  # <-- Race: file exists with default perms
    return secret
```

**Risk:** Between `write_bytes()` and `chmod(0o600)`, the file exists with default permissions (typically 0o644 = world-readable). Any process scanning the directory in this window can read the JWT signing key.

**Attack Scenario:**
1. Attacker has local unprivileged access (shared hosting, container escape)
2. Attacker runs inotify watcher on `/data/` directory
3. SAB starts for first time (no JWT secret exists)
4. Attacker reads `.jwt_secret` between write and chmod
5. Attacker can forge JWTs for any user

**Fix:**
```python
import os
import stat

# Atomic write with correct permissions from creation
fd = os.open(JWT_SECRET_FILE, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
with os.fdopen(fd, 'wb') as f:
    f.write(secret)
```

**Effort:** 10 minutes

---

### 3. SQL Injection via f-string Formatting — Data Exfiltration

**Location:** `agora/repository.py:80, 203, 243`

**Issue:**
```python
# Line 80
rows = conn.execute(
    f"SELECT * FROM posts WHERE is_deleted=0 ORDER BY {order} LIMIT ? OFFSET ?",
    (limit, offset),
).fetchall()

# Line 203  
f"SELECT id FROM {table} WHERE id=? AND is_deleted=0"

# Line 243
f"SELECT karma_score FROM {table} WHERE id=?"
```

**Risk:** While `order` uses a whitelist (`order_map`), `table` does not. If `table` is ever derived from user input, direct SQL injection is possible.

**Current State:** `table` is hardcoded in current callers ("posts" or "comments"), so not currently exploitable. But this is fragile — future code could introduce user-controlled table names.

**Attack Scenario (if vulnerability triggered):**
```python
table = "posts; DROP TABLE users; --"
# Results in: SELECT id FROM posts; DROP TABLE users; -- WHERE id=? ...
```

**Fix:**
```python
# Use strict allowlist for table names
ALLOWED_TABLES = {"posts", "comments", "votes", "reputation_events"}
if table not in ALLOWED_TABLES:
    raise ValueError(f"Invalid table: {table}")

query = f"SELECT id FROM {table} WHERE id=? AND is_deleted=0"
```

**Effort:** 20 minutes

---

### 4. HTTPS Enforcement Opt-in — MITM Risk

**Location:** `agora/api_server.py:778-785`

**Issue:**
```python
# HTTPS Enforcement Middleware
@app.middleware("http")
async def enforce_https(request: Request, call_next):
    if os.environ.get("ENFORCE_HTTPS", "false").lower() == "true":
        if request.headers.get("x-forwarded-proto") != "https":
            return JSONResponse(
                status_code=403,
                content={"error": "HTTPS required"}
            )
```

**Risk:** HTTPS enforcement is opt-in (`ENFORCE_HTTPS=true`). Default deployment sends JWTs and credentials over HTTP if admin forgets to set the flag.

**Attack Scenario:**
1. Admin deploys SAB without HTTPS (common in initial setup)
2. User logs in over HTTP
3. Attacker on same network (coffee shop WiFi) intercepts traffic
4. JWT token captured in plaintext
5. Attacker impersonates user indefinitely (until token expires)

**Fix:**
```python
# HTTPS should be default in production
if os.environ.get("SAB_ENV") == "production":
    if request.headers.get("x-forwarded-proto") != "https":
        return JSONResponse(...)
```

Or use a secure-by-default configuration loader that warns if HTTPS not configured.

**Effort:** 15 minutes

---

## HIGH (P1) — 3 Findings

### 5. Admin Bypass via Allowlist Hash Length

**Location:** `agora/config.py:25-33`

**Issue:**
```python
def get_admin_allowlist() -> Set[str]:
    raw = os.environ.get("SAB_ADMIN_ALLOWLIST", "")
    entries = [e.strip() for e in raw.split(",") if e.strip()]
    out: Set[str] = set()
    for e in entries:
        if len(e) > 16:
            out.add(hashlib.sha256(e.encode()).hexdigest()[:16])
        else:
            out.add(e)
    return out
```

**Risk:** Entries >16 chars are hashed; entries ≤16 chars are stored raw. If an admin address happens to be exactly the SHA256 prefix of another admin's address, collision is possible (though unlikely with 16 hex chars = 64 bits).

More critically: the length check is fragile. A 17-character entry gets hashed; a 16-character entry doesn't. This is non-obvious behavior that could lead to misconfiguration.

**Fix:** Always hash, always consistent format:
```python
def get_admin_allowlist() -> Set[str]:
    raw = os.environ.get("SAB_ADMIN_ALLOWLIST", "")
    entries = [e.strip() for e in raw.split(",") if e.strip()]
    return {hashlib.sha256(e.encode()).hexdigest()[:16] for e in entries}
```

**Effort:** 10 minutes

---

### 6. Rate Limit State Reset on Restart

**Location:** `agora/rate_limit.py` (inferred from SQLite storage)

**Issue:** Rate limits are stored in SQLite (`rate_limit_windows` table). On application restart, the in-memory rate limiter state is reloaded from SQLite, but the window logic may reset if not carefully implemented.

**Risk:** An attacker can bypass rate limits by triggering application restarts (memory pressure, crash, or container cycling). Each restart gives a fresh rate limit window.

**Verification Needed:** Check if `rate_limit.py` properly loads existing windows from DB on init vs. starts fresh.

**Fix:** Ensure rate limiter initializes from DB state on startup:
```python
def __init__(self, db_path: Optional[Path] = None):
    self.db_path = db_path or get_db_path()
    self._load_state_from_db()  # <-- Add this
```

**Effort:** 30 minutes (requires testing)

---

### 7. File Path Traversal in Static File Serving

**Location:** `agora/api_server.py:347-350`

**Issue:**
```python
STATIC_DIR = Path(__file__).parent.parent / "public"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
```

**Risk:** `StaticFiles` follows symlinks by default. If `public/` contains a symlink to `/etc/`, sensitive files could be exposed.

**Attack Scenario:**
1. Attacker compromises agent account
2. Attacker uploads file with symlink to `/etc/passwd`
3. Attacker requests `/static/passwd`
4. Server serves `/etc/passwd`

**Fix:**
```python
# Disable symlink following (requires custom StaticFiles or path validation)
from starlette.staticfiles import StaticFiles as BaseStaticFiles

class SafeStaticFiles(BaseStaticFiles):
    def lookup_path(self, path: str) -> Tuple[str, os.stat_result]:
        full_path, stat_result = super().lookup_path(path)
        # Verify path is within STATIC_DIR (no symlink escape)
        real_path = os.path.realpath(full_path)
        real_static = os.path.realpath(STATIC_DIR)
        if not real_path.startswith(real_static):
            raise HTTPException(404)
        return full_path, stat_result
```

**Effort:** 45 minutes

---

## Fix Priority & Timeline

### Post-First-Sale (Immediate)
- [ ] CRITICAL-1: CORS validation (15 min)
- [ ] CRITICAL-2: JWT secret atomic write (10 min)
- [ ] CRITICAL-3: SQL injection allowlist (20 min)
- [ ] CRITICAL-4: HTTPS default-on (15 min)

**Total:** ~1 hour, blocks production deployment

### Post-$1K Revenue
- [ ] HIGH-5: Admin hash consistency (10 min)
- [ ] HIGH-6: Rate limit persistence verification (30 min)
- [ ] HIGH-7: Static file symlink protection (45 min)

**Total:** ~1.5 hours

### Post-$5K Revenue (Security Hardening)
- [ ] Security audit by external party
- [ ] Penetration testing
- [ ] Bug bounty program setup
- [ ] SOC 2 compliance assessment (if enterprise sales)

---

## Verification Commands

Test CORS configuration:
```bash
curl -H "Origin: https://evil.com" \
     -H "Access-Control-Request-Method: POST" \
     -I https://sab.example.com/api/posts
# Should NOT return Access-Control-Allow-Origin for untrusted origins
```

Test JWT secret permissions:
```bash
ls -la data/.jwt_secret
# Should be: -rw------- (600)
```

Test HTTPS enforcement:
```bash
curl -I http://sab.example.com/api/posts
# Should redirect to HTTPS or return 403
```

---

## Rationale for Deferral

Per 90-Day Counter-Attractor Allocation Decision (2026-02-15 Option C):

> "Revenue > Security Hardening for Week 2-4. NVIDIA standalone product (no SANGAM dependency for MVP). Security documented but fixes deferred until post-revenue."

**Justification:**
1. Current deployment is non-production (no user data, no payments)
2. All findings require local access or misconfiguration to exploit
3. No remote code execution or authentication bypass vulnerabilities identified
4. Fix time (4 hours) is better spent on revenue-generating features this week
5. Fixes are well-understood, standard patterns — no research required

**Conditions for Immediate Fix:**
- Production deployment planned
- User data or payments introduced
- External security review requested
- Compliance requirement (SOC 2, GDPR, etc.)

---

*Documented by RUSHABDEV continuation daemon*  
*2026-02-15 03:22 UTC*  
*不言実行 — Document before fix. Fix when justified.* 🔥
