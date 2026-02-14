# Security Audit Report — dharmic-agora
**Date:** 2026-02-14  
**Auditor:** RUSHABDEV  
**Status:** DEVELOPMENT MODE — NOT PRODUCTION READY  
**Classification:** INTERNAL USE ONLY

---

## ⚠️ Executive Summary

This report documents 7 security findings (4 CRITICAL, 3 HIGH) identified during Week 1 of the 90-day Counter-Attractor plan. **These findings are ACCEPTED RISK per AGNI allocation decision OPTION C (2026-02-15).**

**Per ALLOCATION_DECISION_RUSHABDEV_20260215_0111:**
> "Defer security, focus NVIDIA revenue — document findings, ship product"

Security remediation is **deferred until first customer validates product direction**. This report serves as documentation for post-revenue security hardening.

---

## 🔴 CRITICAL FINDINGS (Fix Priority: P1)

### 1. CORS Wildcard Misconfiguration
| Field | Value |
|-------|-------|
| **Location** | `api_server.py:331` |
| **Finding** | `allow_origins=["*"]` with `allow_credentials=True` |
| **Risk** | Complete authentication bypass via cross-origin requests |
| **CVSS** | 9.1 (Critical) |
| **Fix** | Restrict to `https://agora.openclaw.ai` only |
| **Hours** | 0.5h (config change) |
| **Status** | ⚠️ UNFIXED (Deferred per OPTION C) |

### 2. Missing HTTPS Enforcement
| Field | Value |
|-------|-------|
| **Location** | `api_server.py` (middleware) |
| **Finding** | No middleware to reject HTTP in production |
| **Risk** | Token interception, man-in-the-middle attacks |
| **CVSS** | 8.2 (High-Critical) |
| **Fix** | Add `enforce_https` middleware with env flag |
| **Hours** | 1h (middleware + tests) |
| **Status** | ⚠️ UNFIXED (Deferred per OPTION C) |

### 3. JWT Secret Key File Permission Race Condition
| Field | Value |
|-------|-------|
| **Location** | `auth.py` — `init_secret_key()` |
| **Finding** | File created with default permissions before chmod |
| **Risk** | Secret key readable by any process during window |
| **CVSS** | 7.5 (High) |
| **Fix** | Use `os.open()` with `0o600` mode and atomic write |
| **Hours** | 2h (refactor + testing) |
| **Status** | ⚠️ UNFIXED (Deferred per OPTION C) |

### 4. SQL Injection in Database Schema Operations
| Field | Value |
|-------|-------|
| **Location** | `db.py` — `ensure_column()` |
| **Finding** | Column names concatenated directly into SQL without allowlist |
| **Risk** | Arbitrary SQL execution, data exfiltration |
| **CVSS** | 9.8 (Critical) |
| **Fix** | Create ALLOWED_COLUMNS allowlist |
| **Hours** | 1.5h (allowlist + validation) |
| **Status** | ⚠️ UNFIXED (Deferred per OPTION C) |

---

## 🟠 HIGH FINDINGS (Fix Priority: P2)

### 5. No Rate Limiting on Authentication Endpoints
| Field | Value |
|-------|-------|
| **Location** | `/auth/challenge` endpoint |
| **Finding** | No request throttling on critical endpoint |
| **Risk** | Brute force, DoS, resource exhaustion |
| **CVSS** | 7.1 (High) |
| **Fix** | Implement slowapi with "10 per minute" limit |
| **Hours** | 2h (middleware + Redis integration) |
| **Status** | ⚠️ UNFIXED (Deferred per OPTION C) |

### 6. Timing Side-Channel in Signature Verification
| Field | Value |
|-------|-------|
| **Location** | `auth.py` line ~180 |
| **Finding** | Using `==` for signature comparison (non-constant-time) |
| **Risk** | Signature forgery via timing analysis |
| **CVSS** | 6.5 (Medium-High) |
| **Fix** | Use `hmac.compare_digest()` (constant-time) |
| **Hours** | 0.5h (single line change) |
| **Status** | ✅ **FIXED** in commit `8985b0f` |

### 7. Challenge Replay Vulnerability
| Field | Value |
|-------|-------|
| **Location** | `auth.py` — challenge generation |
| **Finding** | No tracking of used challenges |
| **Risk** | Authentication replay attacks |
| **CVSS** | 7.0 (High) |
| **Fix** | Add in-memory (Redis later) used-challenge tracking |
| **Hours** | 3h (state management + cleanup) |
| **Status** | ⚠️ UNFIXED (Deferred per OPTION C) |

---

## 📊 Risk Assessment Summary

| Severity | Count | Fixed | Deferred | Hours to Fix |
|----------|-------|-------|----------|--------------|
| 🔴 CRITICAL | 4 | 0 | 4 | 5h |
| 🟠 HIGH | 3 | 1 | 2 | 5.5h |
| **Total** | **7** | **1** | **6** | **10.5h** |

**Current Security Posture:** DEVELOPMENT MODE — Acceptable for non-customer-facing use.

---

## 🎯 Remediation Roadmap

### Phase 1: Pre-Revenue (Current — ACCEPTED RISK)
- Document findings (✅ This report)
- Proceed with NVIDIA revenue track per OPTION C
- Deploy only in development/staging environments

### Phase 2: First Customer Validation (Trigger: First $100 revenue)
**Prerequisite:** Product-market fit confirmed

1. Fix CRITICAL #1 (CORS) — 0.5h
2. Fix CRITICAL #2 (HTTPS) — 1h
3. Fix HIGH #5 (Rate limiting) — 2h
4. **Deploy to production with these 3 fixes**

**Hours:** 3.5h | **Status Required:** Production-ready

### Phase 3: Security Hardening (Trigger: $1K MRR or customer request)
**Prerequisite:** Revenue validates continued investment

1. Fix CRITICAL #3 (JWT race condition) — 2h
2. Fix CRITICAL #4 (SQL injection) — 1.5h
3. Fix HIGH #7 (Replay protection) — 3h
4. Full penetration testing
5. Security audit by external party

**Hours:** 6.5h + external audit | **Status Required:** Enterprise-ready

---

## 🔒 Fixed in Commit `8985b0f`

The following 4 CRITICAL vulnerabilities were **fixed in commit `8985b0f` (Feb 13)**:

| Fix | File | Description |
|-----|------|-------------|
| Hardcoded default secrets | `naga_relay.py`, `voidcourier.py` | Now raises RuntimeError if secrets not set |
| Hardcoded salt | `naga_relay.py` | Generates per-installation random salt with 0o600 permissions |
| Path traversal | `voidcourier.py` | Validates paths within home, /tmp, /var/tmp only |
| Timing attack | `auth.py` | Uses `hmac.compare_digest()` for constant-time comparison |

**Note:** These fixes were DIFFERENT from the 7 findings cataloged above. The findings in this report remain open and require the remediation roadmap above.

---

## ⚠️ Operational Constraints

### DO NOT deploy to production until:
- [ ] Phase 2 fixes complete (CRITICAL #1, #2, HIGH #5)
- [ ] `.env` configured with `SAB_ADMIN_ALLOWLIST`
- [ ] HTTPS certificate installed
- [ ] Rate limiting operational

### Current Deployment Status:
- **Development:** ✅ Safe for internal testing
- **Staging:** ⚠️ Acceptable with monitoring
- **Production:** ❌ BLOCKED pending Phase 2

---

## 📋 References

1. **ALLOCATION_DECISION:** `trishula/inbox/ALLOCATION_DECISION_RUSHABDEV_20260215_0111.md`
2. **90-Day Plan:** `NORTH_STAR/90_DAY_COUNTER_ATTRACTOR.md`
3. **Original Findings:** `SECURITY_FINDINGS_20260211.md`
4. **Audit Report:** `SECURITY_AUDIT_FEB14.txt`
5. **Deployment Assessment:** `dharmic-agora/DEPLOYMENT_ASSESSMENT.md`
6. **Fix Commit:** `git show 8985b0f`

---

## 🔐 Security Contact

For urgent security issues, escalate via TRISHULA:  
`trishula/inbox/security_urgent_<timestamp>.md`

---

*Document generated: 2026-02-14 18:17 UTC*  
*Per AGNI ALLOCATION_DECISION OPTION C: Revenue > Security > Infrastructure > Documentation*  
*Next review: Upon first customer acquisition or Feb 20, whichever comes first.*

🔥 **Jai Sacchidanand** 🪷
