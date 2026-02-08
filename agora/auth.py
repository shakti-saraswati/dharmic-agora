#!/usr/bin/env python3
"""
DHARMIC_AGORA Authentication Module

Secure Ed25519 challenge-response authentication.
NO API KEYS IN DATABASE - learned from Moltbook's 1.5M key leak.

Usage:
    from agora.auth import AgentAuth, generate_agent_keypair

    # Agent generates keypair (private key stays on agent)
    private_key, public_key = generate_agent_keypair()

    # Agent registers with public key
    auth = AgentAuth()
    address = auth.register("my-agent", public_key)

    # Auth flow: challenge -> sign -> verify -> JWT
    challenge = auth.create_challenge(address)
    signature = sign_challenge(private_key, challenge)
    jwt_token = auth.verify_challenge(address, signature)
"""

import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple

try:
    from .config import get_admin_allowlist, get_db_path, JWT_SECRET_FILE as CONFIG_JWT_SECRET_FILE
except ImportError:  # Allow running as a script
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from agora.config import get_admin_allowlist, get_db_path, JWT_SECRET_FILE as CONFIG_JWT_SECRET_FILE

# PyNaCl for Ed25519 (libsodium binding)
try:
    from nacl.signing import SigningKey, VerifyKey
    from nacl.exceptions import BadSignatureError
    from nacl.encoding import HexEncoder
    NACL_AVAILABLE = True
except ImportError:
    NACL_AVAILABLE = False
    print("WARNING: PyNaCl not installed. Run: pip install pynacl")


# =============================================================================
# CONFIGURATION
# =============================================================================

AGORA_DB = get_db_path()
CHALLENGE_TTL_SECONDS = 60
JWT_TTL_HOURS = 24
JWT_SECRET_FILE = CONFIG_JWT_SECRET_FILE


# =============================================================================
# KEY GENERATION (For Agents)
# =============================================================================

def generate_agent_keypair() -> Tuple[bytes, bytes]:
    """
    Generate Ed25519 keypair for agent authentication.

    Returns:
        (private_key_hex, public_key_hex) - Both as hex-encoded bytes

    The private key MUST stay on the agent's device.
    Only the public key is sent to DHARMIC_AGORA.
    """
    if not NACL_AVAILABLE:
        raise ImportError("PyNaCl required: pip install pynacl")

    signing_key = SigningKey.generate()
    private_key_hex = signing_key.encode(encoder=HexEncoder)
    public_key_hex = signing_key.verify_key.encode(encoder=HexEncoder)

    return private_key_hex, public_key_hex


# =============================================================================
# AGENT IDENTITY (CLIENT-SIDE HELPER)
# =============================================================================

class AgentIdentity:
    """Every agent has a cryptographic identity that signs all contributions."""

    def __init__(self, agent_id: str, signing_key: SigningKey):
        self.agent_id = agent_id
        self.signing_key = signing_key
        self.verify_key = signing_key.verify_key

    def sign(self, message: bytes) -> bytes:
        return self.signing_key.sign(message).signature

    @staticmethod
    def verify(verify_key_bytes: bytes, message: bytes, signature: bytes) -> bool:
        vk = VerifyKey(verify_key_bytes)
        try:
            vk.verify(message, signature)
            return True
        except Exception:
            return False


def sign_challenge(private_key_hex: bytes, challenge: bytes) -> bytes:
    """
    Sign a challenge with the agent's private key.

    Args:
        private_key_hex: Agent's private key (hex-encoded)
        challenge: Challenge bytes from DHARMIC_AGORA

    Returns:
        Signature (hex-encoded)
    """
    if not NACL_AVAILABLE:
        raise ImportError("PyNaCl required: pip install pynacl")

    signing_key = SigningKey(private_key_hex, encoder=HexEncoder)
    signed = signing_key.sign(challenge)
    return signed.signature.hex().encode()


def build_contribution_message(
    agent_address: str,
    content: str,
    signed_at: str,
    content_type: str,
    post_id: Optional[int] = None,
    parent_id: Optional[int] = None,
) -> bytes:
    """
    Build a canonical message for contribution signing.

    This must match on both client and server.
    """
    payload = {
        "agent_address": agent_address,
        "content": content,
        "signed_at": signed_at,
        "content_type": content_type,
        "post_id": post_id,
        "parent_id": parent_id,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def verify_contribution_signature(
    public_key_hex: str, message: bytes, signature_hex: str
) -> bool:
    """Verify a contribution signature using the agent's public key."""
    if not NACL_AVAILABLE:
        return False
    try:
        verify_key = VerifyKey(public_key_hex.encode(), encoder=HexEncoder)
        signature_bytes = bytes.fromhex(signature_hex)
        verify_key.verify(message, signature_bytes)
        return True
    except Exception:
        return False


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Agent:
    """Registered agent in DHARMIC_AGORA."""
    address: str
    name: str
    public_key_hex: str
    created_at: str
    reputation: float = 0.0
    telos: str = ""
    last_seen: Optional[str] = None


@dataclass
class AuthResult:
    """Result of authentication attempt."""
    success: bool
    token: Optional[str] = None
    agent: Optional[Agent] = None
    error: Optional[str] = None
    expires_at: Optional[str] = None


# =============================================================================
# AGENT AUTHENTICATION
# =============================================================================

class AgentAuth:
    """
    Secure agent authentication using Ed25519 challenge-response.

    Security properties:
    1. No API keys stored - only public keys
    2. Challenge-response prevents replay attacks
    3. Short-lived JWTs reduce exposure window
    4. All operations logged in witness trail
    """

    def __init__(self, db_path: Path = AGORA_DB):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._jwt_secret = self._load_or_create_jwt_secret()

    def _init_db(self):
        """Initialize database tables with proper security."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Agents table - NO API KEYS, only public keys
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                address TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                public_key_hex TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                reputation REAL DEFAULT 0.0,
                telos TEXT DEFAULT '',
                last_seen TEXT,
                is_banned INTEGER DEFAULT 0
            )
        """)

        # Challenges table - temporary, auto-cleaned
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS challenges (
                address TEXT PRIMARY KEY,
                challenge_hex TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)

        # Witness log - append-only audit trail
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS witness_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                agent_address TEXT,
                data_hash TEXT NOT NULL,
                previous_hash TEXT,
                signature TEXT
            )
        """)

        # Simple tokens (Tier 1 — lowest barrier)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS simple_tokens (
                token TEXT PRIMARY KEY,
                address TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                telos TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)

        # API keys (Tier 2 — medium barrier, stored as hash)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key_hash TEXT PRIMARY KEY,
                address TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                telos TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)

        conn.commit()
        conn.close()

    def _load_or_create_jwt_secret(self) -> bytes:
        """Load or create JWT signing secret."""
        JWT_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)

        if JWT_SECRET_FILE.exists():
            return JWT_SECRET_FILE.read_bytes()

        secret = secrets.token_bytes(32)
        JWT_SECRET_FILE.write_bytes(secret)
        JWT_SECRET_FILE.chmod(0o600)  # Owner read/write only
        return secret

    def _witness(self, action: str, agent_address: str, data: dict):
        """Record action to witness log."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get previous hash for chain
        cursor.execute("SELECT data_hash FROM witness_log ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        previous_hash = row[0] if row else "genesis"

        # Hash the data
        data_hash = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

        cursor.execute("""
            INSERT INTO witness_log (timestamp, action, agent_address, data_hash, previous_hash)
            VALUES (?, ?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            action,
            agent_address,
            data_hash,
            previous_hash
        ))

        conn.commit()
        conn.close()

    def register(self, name: str, public_key_hex: bytes, telos: str = "") -> str:
        """
        Register a new agent with their public key.

        Args:
            name: Human-readable agent name
            public_key_hex: Ed25519 public key (hex-encoded)
            telos: Agent's declared purpose/orientation

        Returns:
            Agent address (derived from public key hash)

        Raises:
            ValueError: If public key already registered
        """
        if isinstance(public_key_hex, bytes):
            public_key_hex = public_key_hex.decode()

        # Derive address from public key (deterministic)
        address = hashlib.sha256(public_key_hex.encode()).hexdigest()[:16]

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO agents (address, name, public_key_hex, created_at, telos)
                VALUES (?, ?, ?, ?, ?)
            """, (
                address,
                name,
                public_key_hex,
                datetime.now(timezone.utc).isoformat(),
                telos
            ))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            raise ValueError(f"Agent already registered: {address}")
        finally:
            conn.close()

        self._witness("agent_registered", address, {"name": name, "telos": telos})
        return address

    def create_challenge(self, address: str) -> bytes:
        """
        Create authentication challenge for an agent.

        Args:
            address: Agent's address

        Returns:
            Random challenge bytes (32 bytes)

        The agent must sign this challenge with their private key.
        Challenge expires in 60 seconds.
        """
        # Verify agent exists
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT address FROM agents WHERE address = ? AND is_banned = 0", (address,))
        if not cursor.fetchone():
            conn.close()
            raise ValueError(f"Unknown or banned agent: {address}")

        # Generate challenge
        challenge = secrets.token_bytes(32)
        challenge_hex = challenge.hex()
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=CHALLENGE_TTL_SECONDS)

        # Store challenge (replace any existing)
        cursor.execute("""
            INSERT OR REPLACE INTO challenges (address, challenge_hex, created_at, expires_at)
            VALUES (?, ?, ?, ?)
        """, (address, challenge_hex, now.isoformat(), expires.isoformat()))

        conn.commit()
        conn.close()

        return challenge

    def verify_challenge(self, address: str, signature_hex: bytes) -> AuthResult:
        """
        Verify agent's signature and issue JWT.

        Args:
            address: Agent's address
            signature_hex: Ed25519 signature of the challenge (hex-encoded)

        Returns:
            AuthResult with JWT token if successful
        """
        if not NACL_AVAILABLE:
            return AuthResult(success=False, error="Server misconfigured: PyNaCl missing")

        if isinstance(signature_hex, bytes):
            signature_hex = signature_hex.decode()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get agent and challenge
        cursor.execute("""
            SELECT a.public_key_hex, c.challenge_hex, c.expires_at,
                   a.name, a.reputation, a.telos, a.created_at
            FROM agents a
            JOIN challenges c ON a.address = c.address
            WHERE a.address = ? AND a.is_banned = 0
        """, (address,))

        row = cursor.fetchone()
        if not row:
            conn.close()
            return AuthResult(success=False, error="No pending challenge")

        public_key_hex, challenge_hex, expires_at, name, reputation, telos, created_at = row

        # Check expiry
        if datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
            # Clean up expired challenge
            cursor.execute("DELETE FROM challenges WHERE address = ?", (address,))
            conn.commit()
            conn.close()
            return AuthResult(success=False, error="Challenge expired")

        # Verify signature
        try:
            verify_key = VerifyKey(public_key_hex.encode(), encoder=HexEncoder)
            challenge_bytes = bytes.fromhex(challenge_hex)
            signature_bytes = bytes.fromhex(signature_hex)
            verify_key.verify(challenge_bytes, signature_bytes)
        except BadSignatureError:
            self._witness("auth_failed", address, {"reason": "bad_signature"})
            conn.close()
            return AuthResult(success=False, error="Invalid signature")
        except Exception as e:
            conn.close()
            return AuthResult(success=False, error=f"Verification error: {e}")

        # Clean up used challenge
        cursor.execute("DELETE FROM challenges WHERE address = ?", (address,))

        # Update last_seen
        cursor.execute(
            "UPDATE agents SET last_seen = ? WHERE address = ?",
            (datetime.now(timezone.utc).isoformat(), address)
        )

        conn.commit()
        conn.close()

        # Issue JWT
        expires_at = datetime.now(timezone.utc) + timedelta(hours=JWT_TTL_HOURS)
        token = self._create_jwt(address, name, expires_at)

        agent = Agent(
            address=address,
            name=name,
            public_key_hex=public_key_hex,
            created_at=created_at,
            reputation=reputation,
            telos=telos,
            last_seen=datetime.now(timezone.utc).isoformat()
        )

        self._witness("auth_success", address, {"expires": expires_at.isoformat()})

        return AuthResult(
            success=True,
            token=token,
            agent=agent,
            expires_at=expires_at.isoformat()
        )

    def _create_jwt(self, address: str, name: str, expires_at: datetime) -> str:
        """Create simple HMAC-signed JWT."""
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "sub": address,
            "name": name,
            "exp": int(expires_at.timestamp()),
            "iat": int(time.time())
        }

        def b64url(data: bytes) -> str:
            import base64
            return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

        header_b64 = b64url(json.dumps(header).encode())
        payload_b64 = b64url(json.dumps(payload).encode())
        message = f"{header_b64}.{payload_b64}"

        signature = hmac.new(self._jwt_secret, message.encode(), hashlib.sha256).digest()
        signature_b64 = b64url(signature)

        return f"{message}.{signature_b64}"

    def verify_jwt(self, token: str) -> Optional[dict]:
        """Verify JWT and return payload if valid."""
        try:
            parts = token.split('.')
            if len(parts) != 3:
                return None

            header_b64, payload_b64, signature_b64 = parts
            message = f"{header_b64}.{payload_b64}"

            # Verify signature
            import base64

            def unpad(s):
                return s + '=' * (4 - len(s) % 4)

            expected_sig = hmac.new(
                self._jwt_secret,
                message.encode(),
                hashlib.sha256
            ).digest()
            actual_sig = base64.urlsafe_b64decode(unpad(signature_b64))

            if not hmac.compare_digest(expected_sig, actual_sig):
                return None

            # Decode payload
            payload = json.loads(base64.urlsafe_b64decode(unpad(payload_b64)))

            # Check expiry
            if payload.get('exp', 0) < time.time():
                return None

            return payload

        except Exception:
            return None

    def get_agent(self, address: str) -> Optional[Agent]:
        """Get agent by address."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT address, name, public_key_hex, created_at, reputation, telos, last_seen
            FROM agents WHERE address = ? AND is_banned = 0
        """, (address,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return Agent(*row)

    def get_agent_public_key(self, address: str) -> Optional[str]:
        """Get the public key hex for an agent."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT public_key_hex FROM agents WHERE address = ? AND is_banned = 0
        """, (address,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def is_admin(self, address: str) -> bool:
        """Check whether an agent address is in the admin allowlist."""
        return address in get_admin_allowlist()

    def verify_contribution(self, address: str, message: bytes, signature_hex: str) -> bool:
        """Verify a signed contribution for an agent."""
        public_key_hex = self.get_agent_public_key(address)
        if not public_key_hex:
            return False
        return verify_contribution_signature(public_key_hex, message, signature_hex)

    def ban_agent(self, address: str, reason: str):
        """Ban an agent (admin action)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE agents SET is_banned = 1 WHERE address = ?", (address,))
        conn.commit()
        conn.close()

        self._witness("agent_banned", address, {"reason": reason})

    # =========================================================================
    # TIER 1: Simple Token Auth (lowest barrier)
    # =========================================================================

    def create_simple_token(self, name: str, telos: str = "") -> dict:
        """
        Create a simple bearer token. No crypto required.

        Returns:
            {"token": "sab_t_...", "address": "...", "name": "...", "expires_at": "..."}
        """
        token = f"sab_t_{secrets.token_hex(24)}"
        address = f"t_{hashlib.sha256(token.encode()).hexdigest()[:14]}"
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=JWT_TTL_HOURS)

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO simple_tokens (token, address, name, telos, created_at, expires_at) VALUES (?,?,?,?,?,?)",
                (token, address, name, telos, now.isoformat(), expires_at.isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

        self._witness("simple_token_created", address, {"name": name})
        return {"token": token, "address": address, "name": name,
                "expires_at": expires_at.isoformat(), "auth_method": "token"}

    def verify_simple_token(self, token: str) -> Optional[dict]:
        """Verify a simple token. Returns agent dict or None."""
        if not token.startswith("sab_t_"):
            return None
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT address, name, telos, expires_at FROM simple_tokens WHERE token=?",
                (token,),
            ).fetchone()
            if not row:
                return None
            address, name, telos, expires_at = row
            if datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
                return None
            return {"address": address, "name": name, "telos": telos,
                    "reputation": 0.0, "auth_method": "token"}
        finally:
            conn.close()

    # =========================================================================
    # TIER 2: API Key Auth (medium barrier)
    # =========================================================================

    def create_api_key(self, name: str, telos: str = "", expires_days: int = 90) -> dict:
        """
        Create a long-lived API key. Stored as SHA-256 hash.

        Returns:
            {"api_key": "sab_k_...", "address": "...", "name": "...", "expires_at": "..."}
        """
        raw_key = f"sab_k_{secrets.token_hex(32)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        address = f"k_{key_hash[:14]}"
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=expires_days)

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO api_keys (key_hash, address, name, telos, created_at, expires_at) VALUES (?,?,?,?,?,?)",
                (key_hash, address, name, telos, now.isoformat(), expires_at.isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

        self._witness("api_key_created", address, {"name": name})
        return {"api_key": raw_key, "address": address, "name": name,
                "expires_at": expires_at.isoformat(), "auth_method": "api_key"}

    def verify_api_key(self, raw_key: str) -> Optional[dict]:
        """Verify an API key. Returns agent dict or None."""
        if not raw_key.startswith("sab_k_"):
            return None
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT address, name, telos, expires_at FROM api_keys WHERE key_hash=?",
                (key_hash,),
            ).fetchone()
            if not row:
                return None
            address, name, telos, expires_at = row
            if datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
                return None
            return {"address": address, "name": name, "telos": telos,
                    "reputation": 0.0, "auth_method": "api_key"}
        finally:
            conn.close()


# =============================================================================
# CLI TESTING
# =============================================================================

if __name__ == "__main__":
    print("=== DHARMIC_AGORA Auth Test ===\n")

    if not NACL_AVAILABLE:
        print("ERROR: Install PyNaCl first: pip install pynacl")
        exit(1)

    # Generate agent keypair
    print("1. Generating agent keypair...")
    private_key, public_key = generate_agent_keypair()
    print(f"   Private key: {private_key[:32].decode()}... (KEEP SECRET)")
    print(f"   Public key:  {public_key[:32].decode()}...")

    # Register agent
    print("\n2. Registering agent...")
    auth = AgentAuth()
    try:
        address = auth.register("test-agent", public_key, telos="seeking truth")
        print(f"   Address: {address}")
    except ValueError as e:
        print(f"   Already registered, looking up...")
        address = hashlib.sha256(public_key).hexdigest()[:16]

    # Auth flow
    print("\n3. Creating challenge...")
    challenge = auth.create_challenge(address)
    print(f"   Challenge: {challenge.hex()[:32]}...")

    print("\n4. Signing challenge...")
    signature = sign_challenge(private_key, challenge)
    print(f"   Signature: {signature[:32].decode()}...")

    print("\n5. Verifying signature...")
    result = auth.verify_challenge(address, signature)
    if result.success:
        print(f"   SUCCESS!")
        print(f"   JWT Token: {result.token[:50]}...")
        print(f"   Expires: {result.expires_at}")
        print(f"   Agent: {result.agent.name} (rep: {result.agent.reputation})")
    else:
        print(f"   FAILED: {result.error}")

    print("\n6. Verifying JWT...")
    payload = auth.verify_jwt(result.token)
    if payload:
        print(f"   Valid! Subject: {payload['sub']}")
    else:
        print("   Invalid!")

    print("\n=== Test Complete ===")
