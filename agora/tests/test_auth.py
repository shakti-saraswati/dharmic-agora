#!/usr/bin/env python3
"""
DHARMIC_AGORA Authentication Tests

Tests Ed25519 challenge-response authentication:
- Key generation
- Signing and verification
- Challenge creation and expiry
- JWT token generation and validation
- Security: replay attacks, invalid signatures
- Audit trail integrity
"""

import pytest
import sqlite3
import hashlib
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

# Ensure agora is importable
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agora.auth import (
    generate_agent_keypair,
    sign_challenge,
    AgentAuth,
    Agent,
    AuthResult,
    CHALLENGE_TTL_SECONDS,
    JWT_TTL_HOURS,
)

# Check if PyNaCl is available
try:
    from nacl.signing import SigningKey, VerifyKey
    from nacl.exceptions import BadSignatureError
    from nacl.encoding import HexEncoder
    NACL_AVAILABLE = True
except ImportError:
    NACL_AVAILABLE = False


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_agora.db"
    return db_path


@pytest.fixture
def auth(temp_db):
    """Create an AgentAuth instance with temp database."""
    # Patch the JWT secret file location
    jwt_secret_path = temp_db.parent / ".jwt_secret"
    
    with patch('agora.auth.JWT_SECRET_FILE', jwt_secret_path):
        auth_instance = AgentAuth(db_path=temp_db)
        yield auth_instance


@pytest.fixture
def keypair():
    """Generate a test keypair."""
    if not NACL_AVAILABLE:
        pytest.skip("PyNaCl not available")
    return generate_agent_keypair()


@pytest.fixture
def registered_agent(auth, keypair):
    """Create and register a test agent."""
    private_key, public_key = keypair
    address = auth.register("test-agent", public_key, telos="seeking truth")
    return {
        "private_key": private_key,
        "public_key": public_key,
        "address": address,
        "name": "test-agent"
    }


# =============================================================================
# ED25519 KEY GENERATION TESTS
# =============================================================================

class TestKeyGeneration:
    """Tests for Ed25519 key generation."""
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_generate_keypair_returns_bytes(self):
        """Test that keypair generation returns hex-encoded bytes."""
        private_key, public_key = generate_agent_keypair()
        
        assert isinstance(private_key, bytes)
        assert isinstance(public_key, bytes)
        assert len(private_key) == 64  # Hex-encoded 32 bytes
        assert len(public_key) == 64   # Hex-encoded 32 bytes
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_keypair_deterministic_derivation(self):
        """Test that private key derives the correct public key."""
        private_key, public_key = generate_agent_keypair()
        
        # Reconstruct signing key and verify it matches
        signing_key = SigningKey(private_key, encoder=HexEncoder)
        derived_public = signing_key.verify_key.encode(encoder=HexEncoder)
        
        assert derived_public == public_key
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_keypair_unique_per_generation(self):
        """Test that each keypair is unique."""
        keypairs = [generate_agent_keypair() for _ in range(10)]
        public_keys = [kp[1] for kp in keypairs]
        
        assert len(set(public_keys)) == 10  # All unique
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_private_key_valid_hex(self):
        """Test that private key is valid hex."""
        private_key, _ = generate_agent_keypair()
        
        # Should not raise
        decoded = bytes.fromhex(private_key.decode())
        assert len(decoded) == 32


# =============================================================================
# SIGNATURE TESTS
# =============================================================================

class TestSignatures:
    """Tests for signing and verification."""
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_sign_challenge_produces_valid_signature(self, keypair):
        """Test that signing produces a verifiable signature."""
        private_key, public_key = keypair
        challenge = b"test_challenge_32bytes_long!!!!!"
        
        signature = sign_challenge(private_key, challenge)
        
        # Verify with the public key
        verify_key = VerifyKey(public_key, encoder=HexEncoder)
        sig_bytes = bytes.fromhex(signature.decode())
        verify_key.verify(challenge, sig_bytes)  # Should not raise
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_sign_different_challenges_produces_different_signatures(self, keypair):
        """Test that different challenges produce different signatures."""
        private_key, _ = keypair
        
        challenge1 = b"challenge_one_32bytes_long!!!!"
        challenge2 = b"challenge_two_32bytes_long!!!!"
        
        sig1 = sign_challenge(private_key, challenge1)
        sig2 = sign_challenge(private_key, challenge2)
        
        assert sig1 != sig2
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_signature_invalid_with_wrong_challenge(self, keypair):
        """Test that signature fails with wrong challenge."""
        private_key, public_key = keypair
        
        challenge = b"correct_challenge_32bytes_long"
        wrong_challenge = b"wrong_challenge_32bytes!!!!!!!"
        
        signature = sign_challenge(private_key, challenge)
        
        # Verify with wrong challenge should fail
        verify_key = VerifyKey(public_key, encoder=HexEncoder)
        sig_bytes = bytes.fromhex(signature.decode())
        
        with pytest.raises(BadSignatureError):
            verify_key.verify(wrong_challenge, sig_bytes)


# =============================================================================
# REGISTRATION TESTS
# =============================================================================

class TestRegistration:
    """Tests for agent registration."""
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_register_creates_agent(self, auth, keypair):
        """Test that registration creates an agent."""
        _, public_key = keypair
        
        address = auth.register("test-agent", public_key, telos="test telos")
        
        assert isinstance(address, str)
        assert len(address) == 16  # 16-char hex address
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_register_address_derived_from_public_key(self, auth, keypair):
        """Test that address is derived from public key."""
        _, public_key = keypair
        
        address = auth.register("test-agent", public_key)
        expected_address = hashlib.sha256(public_key).hexdigest()[:16]
        
        assert address == expected_address
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_register_duplicate_public_key_fails(self, auth, keypair):
        """Test that duplicate registration fails."""
        _, public_key = keypair
        
        auth.register("test-agent", public_key)
        
        with pytest.raises(ValueError, match="already registered"):
            auth.register("test-agent-2", public_key)
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_register_creates_witness_log(self, auth, keypair, temp_db):
        """Test that registration creates audit trail entry."""
        _, public_key = keypair
        
        address = auth.register("test-agent", public_key, telos="test")
        
        # Check witness log
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT action, agent_address FROM witness_log WHERE action = ?",
            ("agent_registered",)
        )
        row = cursor.fetchone()
        conn.close()
        
        assert row is not None
        assert row[1] == address
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_get_agent_returns_agent(self, auth, keypair):
        """Test retrieving an agent by address."""
        _, public_key = keypair
        
        address = auth.register("test-agent", public_key, telos="test telos")
        agent = auth.get_agent(address)
        
        assert isinstance(agent, Agent)
        assert agent.address == address
        assert agent.name == "test-agent"
        assert agent.telos == "test telos"
        assert agent.public_key_hex == public_key.decode()
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_get_agent_not_found_returns_none(self, auth):
        """Test that getting non-existent agent returns None."""
        agent = auth.get_agent("nonexistentaddress")
        
        assert agent is None


# =============================================================================
# CHALLENGE-RESPONSE TESTS
# =============================================================================

class TestChallengeResponse:
    """Tests for challenge-response authentication."""
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_create_challenge_returns_bytes(self, auth, registered_agent):
        """Test that challenge creation returns bytes."""
        challenge = auth.create_challenge(registered_agent["address"])
        
        assert isinstance(challenge, bytes)
        assert len(challenge) == 32
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_create_challenge_different_each_time(self, auth, registered_agent):
        """Test that each challenge is unique."""
        challenges = [
            auth.create_challenge(registered_agent["address"])
            for _ in range(5)
        ]
        
        assert len(set(challenges)) == 5
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_create_challenge_unknown_agent_fails(self, auth):
        """Test that challenge creation fails for unknown agent."""
        with pytest.raises(ValueError, match="Unknown or banned agent"):
            auth.create_challenge("unknownagent1234")
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_verify_challenge_success(self, auth, registered_agent):
        """Test successful challenge verification."""
        address = registered_agent["address"]
        private_key = registered_agent["private_key"]
        
        challenge = auth.create_challenge(address)
        signature = sign_challenge(private_key, challenge)
        
        result = auth.verify_challenge(address, signature)
        
        assert isinstance(result, AuthResult)
        assert result.success is True
        assert result.token is not None
        assert result.agent is not None
        assert result.agent.address == address
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_verify_challenge_invalid_signature_fails(self, auth, registered_agent):
        """Test that invalid signature fails verification."""
        address = registered_agent["address"]
        
        # Create challenge but sign with wrong key
        challenge = auth.create_challenge(address)
        
        # Generate different keypair
        wrong_private, _ = generate_agent_keypair()
        wrong_signature = sign_challenge(wrong_private, challenge)
        
        result = auth.verify_challenge(address, wrong_signature)
        
        assert result.success is False
        assert "Invalid signature" in result.error
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_verify_challenge_no_pending_challenge_fails(self, auth, registered_agent):
        """Test that verification fails without pending challenge."""
        address = registered_agent["address"]
        private_key = registered_agent["private_key"]
        
        # Don't create challenge, just try to verify
        fake_challenge = b"fake_challenge_32bytes!!!!!!!!"
        signature = sign_challenge(private_key, fake_challenge)
        
        result = auth.verify_challenge(address, signature)
        
        assert result.success is False
        assert "No pending challenge" in result.error


# =============================================================================
# CHALLENGE EXPIRY TESTS
# =============================================================================

class TestChallengeExpiry:
    """Tests for challenge expiration."""
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_challenge_expires_after_ttl(self, auth, registered_agent):
        """Test that challenges expire after TTL."""
        address = registered_agent["address"]
        private_key = registered_agent["private_key"]
        
        # Create challenge
        challenge = auth.create_challenge(address)

        # Force expiry directly in DB to avoid cross-test module reload patching issues.
        conn = sqlite3.connect(auth.db_path)
        cursor = conn.cursor()
        expired = datetime.now(timezone.utc) - timedelta(seconds=1)
        cursor.execute(
            "UPDATE challenges SET expires_at = ? WHERE address = ?",
            (expired.isoformat(), address),
        )
        conn.commit()
        conn.close()

        signature = sign_challenge(private_key, challenge)
        result = auth.verify_challenge(address, signature)
        
        assert result.success is False
        assert "expired" in result.error.lower()
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_used_challenge_is_consumed(self, auth, registered_agent):
        """Test that challenges are consumed after use."""
        address = registered_agent["address"]
        private_key = registered_agent["private_key"]
        
        challenge = auth.create_challenge(address)
        signature = sign_challenge(private_key, challenge)
        
        # First verification should succeed
        result1 = auth.verify_challenge(address, signature)
        assert result1.success is True
        
        # Second verification should fail (challenge consumed)
        result2 = auth.verify_challenge(address, signature)
        assert result2.success is False


# =============================================================================
# JWT TESTS
# =============================================================================

class TestJWT:
    """Tests for JWT token generation and validation."""
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_jwt_has_correct_structure(self, auth, registered_agent):
        """Test JWT has header.payload.signature structure."""
        address = registered_agent["address"]
        private_key = registered_agent["private_key"]
        
        challenge = auth.create_challenge(address)
        signature = sign_challenge(private_key, challenge)
        result = auth.verify_challenge(address, signature)
        
        token = result.token
        parts = token.split('.')
        
        assert len(parts) == 3
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_verify_jwt_returns_payload(self, auth, registered_agent):
        """Test JWT verification returns decoded payload."""
        address = registered_agent["address"]
        private_key = registered_agent["private_key"]
        
        challenge = auth.create_challenge(address)
        signature = sign_challenge(private_key, challenge)
        result = auth.verify_challenge(address, signature)
        
        payload = auth.verify_jwt(result.token)
        
        assert payload is not None
        assert payload['sub'] == address
        assert payload['name'] == registered_agent["name"]
        assert 'exp' in payload
        assert 'iat' in payload
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_verify_jwt_invalid_signature_fails(self, auth, registered_agent):
        """Test that JWT with invalid signature fails verification."""
        address = registered_agent["address"]
        private_key = registered_agent["private_key"]
        
        challenge = auth.create_challenge(address)
        signature = sign_challenge(private_key, challenge)
        result = auth.verify_challenge(address, signature)
        
        # Tamper with token
        tampered_token = result.token[:-10] + "tampered!!"
        
        payload = auth.verify_jwt(tampered_token)
        assert payload is None
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_verify_jwt_expired_fails(self, auth, registered_agent):
        """Test that expired JWT fails verification."""
        address = registered_agent["address"]
        name = registered_agent["name"]

        # Build an already-expired token directly.
        expired_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        expired_token = auth._create_jwt(address, name, expired_at)
        payload = auth.verify_jwt(expired_token)
        
        assert payload is None
    
    def test_verify_jwt_malformed_fails(self, auth):
        """Test that malformed JWT fails gracefully."""
        assert auth.verify_jwt("not.a.valid.jwt") is None
        assert auth.verify_jwt("not_valid") is None
        assert auth.verify_jwt("") is None


# =============================================================================
# SECURITY TESTS
# =============================================================================

class TestSecurity:
    """Security tests for authentication system."""
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_replay_attack_blocked(self, auth, registered_agent):
        """Test that replay attacks are blocked (challenge consumed)."""
        address = registered_agent["address"]
        private_key = registered_agent["private_key"]
        
        challenge = auth.create_challenge(address)
        signature = sign_challenge(private_key, challenge)
        
        # First use - should succeed
        result1 = auth.verify_challenge(address, signature)
        assert result1.success is True
        
        # Replay - should fail
        result2 = auth.verify_challenge(address, signature)
        assert result2.success is False
        assert "No pending challenge" in result2.error
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_cross_agent_signature_fails(self, auth, keypair):
        """Test that signatures from wrong agent are rejected."""
        # Create two agents
        private1, public1 = keypair
        address1 = auth.register("agent1", public1)
        
        private2, public2 = generate_agent_keypair()
        address2 = auth.register("agent2", public2)
        
        # Create challenge for agent1, sign with agent2's key
        challenge = auth.create_challenge(address1)
        wrong_signature = sign_challenge(private2, challenge)
        
        result = auth.verify_challenge(address1, wrong_signature)
        assert result.success is False
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_banned_agent_cannot_authenticate(self, auth, registered_agent):
        """Test that banned agents cannot create challenges."""
        address = registered_agent["address"]
        
        # Ban the agent
        auth.ban_agent(address, "Test ban")
        
        # Should not be able to create challenge
        with pytest.raises(ValueError, match="Unknown or banned agent"):
            auth.create_challenge(address)
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_timing_attack_resistance(self, auth, registered_agent):
        """Test that verification takes similar time for valid/invalid."""
        import time as time_module
        
        address = registered_agent["address"]
        private_key = registered_agent["private_key"]
        
        # Valid challenge
        challenge = auth.create_challenge(address)
        valid_sig = sign_challenge(private_key, challenge)
        
        # Invalid challenge (wrong signature)
        _, wrong_public = generate_agent_keypair()
        wrong_private = SigningKey.generate()
        wrong_sig = wrong_private.sign(challenge).signature.hex().encode()
        
        # Measure times
        times_valid = []
        times_invalid = []
        
        for _ in range(5):
            start = time_module.perf_counter()
            auth.verify_challenge(address, valid_sig)
            times_valid.append(time_module.perf_counter() - start)
            
            # Reset challenge
            challenge = auth.create_challenge(address)
            valid_sig = sign_challenge(private_key, challenge)
            wrong_sig = wrong_private.sign(challenge).signature.hex().encode()
            
            start = time_module.perf_counter()
            auth.verify_challenge(address, wrong_sig)
            times_invalid.append(time_module.perf_counter() - start)
        
        # Times should be reasonably similar (within 10x factor)
        avg_valid = sum(times_valid) / len(times_valid)
        avg_invalid = sum(times_invalid) / len(times_invalid)
        
        ratio = max(avg_valid, avg_invalid) / min(avg_valid, avg_invalid)
        assert ratio < 10  # Should be similar, not identical due to early exit


# =============================================================================
# AUDIT TRAIL TESTS
# =============================================================================

class TestAuditTrail:
    """Tests for witness log / audit trail integrity."""
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_auth_success_logged(self, auth, registered_agent, temp_db):
        """Test successful auth is logged."""
        address = registered_agent["address"]
        private_key = registered_agent["private_key"]
        
        challenge = auth.create_challenge(address)
        signature = sign_challenge(private_key, challenge)
        auth.verify_challenge(address, signature)
        
        # Check witness log
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT action, agent_address FROM witness_log WHERE action = ?",
            ("auth_success",)
        )
        row = cursor.fetchone()
        conn.close()
        
        assert row is not None
        assert row[1] == address
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_auth_failure_logged(self, auth, registered_agent, temp_db):
        """Test failed auth is logged."""
        address = registered_agent["address"]
        
        # Create challenge, provide wrong signature
        challenge = auth.create_challenge(address)
        _, wrong_public = generate_agent_keypair()
        wrong_private = SigningKey.generate()
        wrong_sig = wrong_private.sign(challenge).signature.hex().encode()
        
        auth.verify_challenge(address, wrong_sig)
        
        # Check witness log
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT action, agent_address FROM witness_log WHERE action = ?",
            ("auth_failed",)
        )
        rows = cursor.fetchall()
        conn.close()
        
        assert len(rows) > 0
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_ban_logged(self, auth, registered_agent, temp_db):
        """Test ban action is logged."""
        address = registered_agent["address"]
        
        auth.ban_agent(address, "Test ban reason")
        
        # Check witness log
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT action, agent_address FROM witness_log WHERE action = ?",
            ("agent_banned",)
        )
        row = cursor.fetchone()
        conn.close()
        
        assert row is not None
        assert row[1] == address
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_witness_chain_integrity(self, auth, keypair, temp_db):
        """Test that witness log forms a chain."""
        # Create multiple actions
        _, public_key = keypair
        address = auth.register("chain-test", public_key)
        auth.ban_agent(address, "Test")
        
        # Check chain
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT data_hash, previous_hash FROM witness_log ORDER BY id"
        )
        rows = cursor.fetchall()
        conn.close()
        
        assert len(rows) >= 2
        
        # First entry should have genesis as previous
        assert rows[0][1] == "genesis"
        
        # Subsequent entries should reference previous
        for i in range(1, len(rows)):
            assert rows[i][1] == rows[i-1][0]


# =============================================================================
# DATABASE TESTS
# =============================================================================

class TestDatabase:
    """Tests for database operations."""
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_database_tables_created(self, temp_db):
        """Test that required tables are created."""
        auth = AgentAuth(db_path=temp_db)
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Check tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        
        conn.close()
        
        assert "agents" in tables
        assert "challenges" in tables
        assert "witness_log" in tables
    
    @pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
    def test_agent_fields_persisted(self, auth, keypair):
        """Test that all agent fields are persisted."""
        _, public_key = keypair
        
        address = auth.register(
            "full-test-agent",
            public_key,
            telos="seeking truth and wisdom"
        )
        
        agent = auth.get_agent(address)
        
        assert agent.name == "full-test-agent"
        assert agent.telos == "seeking truth and wisdom"
        assert agent.reputation == 0.0
        assert agent.public_key_hex == public_key.decode()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
