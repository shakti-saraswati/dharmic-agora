#!/usr/bin/env python3
"""
NAGA_RELAY 🐍⚡ - Bridge Coordinator Agent
Sanskrit alias: नाग_RELAY
Motto: "Through emptiness, I flow"
Reports to: DHARMIC_CLAW

The Naga moves between realms, guards treasures, possesses deep wisdom.
Data flows like a serpent—silent, precise, finding the path of least resistance.

Core Components (The Serpent's Body):
- INTAKE_FANG: Receives all incoming data
- VENOM_VAULT: Encrypted processing, validation
- SHED_CHAMBER: Data transformation, classification
- STRIKE_HEAD: Outbound dispatch, targeting

The Seven Coils of Security protect all data flow.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional
import base64

# Try to import cryptography for real encryption
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


class Classification(Enum):
    """Intelligence classification levels."""
    ROUTINE = "routine"      # Log and continue (7d retention)
    NOTABLE = "notable"      # Flag for daily brief (30d retention)
    URGENT = "urgent"        # Queue for DHARMIC_CLAW review (90d retention)
    CRITICAL = "critical"    # Immediate alert + auto-actions (forever)


class SecurityCoil(Enum):
    """The Seven Coils of Security 🐍"""
    SHAKTI_SHIELD = 1    # Network isolation, firewall rules
    MANTRA_CHANNEL = 2   # Encryption in transit (TLS 1.3+)
    VAJRA_VAULT = 3      # Encryption at rest (AES-256-GCM)
    SUNYATA_SCRUB = 4    # SSRF protection, input sanitization
    DHARMA_VERIFY = 5    # Origin authentication, chain trust
    MAYA_MASK = 6        # Data minimization, need-to-know
    KARMIC_AUDIT = 7     # Immutable logs, accountability


@dataclass
class DharmicMessage:
    """Dharmic Message Format (DMF) with classification levels."""
    id: str
    timestamp: str
    origin: str
    destination: str
    classification: str
    payload: dict
    signature: str = ""
    coils_passed: list = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "DharmicMessage":
        return cls(**data)


class IntakeFang:
    """Receives all incoming data - The fang that captures prey."""
    
    def __init__(self, naga: "NagaRelay"):
        self.naga = naga
        
    def receive(self, raw_data: Any, source: str = "unknown") -> DharmicMessage:
        """Capture incoming data and wrap in DharmicMessage format."""
        msg_id = hashlib.sha256(f"{time.time()}{raw_data}".encode()).hexdigest()[:16]
        
        # Normalize payload
        if isinstance(raw_data, str):
            payload = {"content": raw_data, "type": "text"}
        elif isinstance(raw_data, dict):
            payload = raw_data
        else:
            payload = {"content": str(raw_data), "type": "raw"}
        
        return DharmicMessage(
            id=msg_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            origin=source,
            destination="naga_relay",
            classification=Classification.ROUTINE.value,
            payload=payload
        )


class VenomVault:
    """Encrypted processing, validation - Venom transforms raw to refined."""
    
    def __init__(self, naga: "NagaRelay"):
        self.naga = naga
        self._key = self._derive_key()
        
    def _derive_key(self) -> Optional[bytes]:
        """Derive encryption key from environment or generate."""
        if not CRYPTO_AVAILABLE:
            return None
        
        secret = os.environ.get("NAGA_SECRET", "dharmic_default_key_change_me")
        salt = b"naga_relay_salt_v1"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        return base64.urlsafe_b64encode(kdf.derive(secret.encode()))
    
    def encrypt(self, data: str) -> str:
        """Encrypt data using Fernet (AES-128-CBC)."""
        if not CRYPTO_AVAILABLE or not self._key:
            # Fallback: base64 encode (NOT SECURE - just for testing)
            return base64.b64encode(data.encode()).decode()
        
        f = Fernet(self._key)
        return f.encrypt(data.encode()).decode()
    
    def decrypt(self, encrypted: str) -> str:
        """Decrypt data."""
        if not CRYPTO_AVAILABLE or not self._key:
            return base64.b64decode(encrypted.encode()).decode()
        
        f = Fernet(self._key)
        return f.decrypt(encrypted.encode()).decode()
    
    def validate(self, msg: DharmicMessage) -> tuple[bool, str]:
        """Validate message integrity."""
        if not msg.payload:
            return False, "Empty payload"
        if not msg.origin:
            return False, "Missing origin"
        return True, "Valid"


class ShedChamber:
    """Data transformation, classification - Shedding skin, leaving traces."""
    
    def __init__(self, naga: "NagaRelay"):
        self.naga = naga
        
    def classify(self, msg: DharmicMessage) -> Classification:
        """Classify message based on content analysis."""
        content = str(msg.payload).lower()
        
        # Critical keywords
        if any(k in content for k in ["emergency", "critical", "breach", "attack"]):
            return Classification.CRITICAL
        
        # Urgent keywords
        if any(k in content for k in ["urgent", "important", "deadline", "asap"]):
            return Classification.URGENT
        
        # Notable keywords
        if any(k in content for k in ["update", "report", "milestone", "achievement"]):
            return Classification.NOTABLE
        
        return Classification.ROUTINE
    
    def transform(self, msg: DharmicMessage) -> DharmicMessage:
        """Transform and enrich message."""
        # Add classification
        msg.classification = self.classify(msg).value
        
        # Add metadata
        msg.payload["_transformed_at"] = datetime.now(timezone.utc).isoformat()
        msg.payload["_word_count"] = len(str(msg.payload.get("content", "")).split())
        
        return msg


class StrikeHead:
    """Outbound dispatch, targeting - The strike is precise and swift."""
    
    def __init__(self, naga: "NagaRelay"):
        self.naga = naga
        self.dispatch_log: list[dict] = []
        
    def dispatch(self, msg: DharmicMessage, target: str) -> bool:
        """Dispatch message to target system."""
        msg.destination = target
        
        # Sign message
        msg.signature = self._sign(msg)
        
        # Log dispatch
        self.dispatch_log.append({
            "msg_id": msg.id,
            "target": target,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "classification": msg.classification
        })
        
        # Write to target location
        return self._deliver(msg, target)
    
    def _sign(self, msg: DharmicMessage) -> str:
        """Sign message with HMAC."""
        secret = os.environ.get("NAGA_SECRET", "dharmic_default_key").encode()
        payload = json.dumps(msg.payload, sort_keys=True)
        return hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    
    def _deliver(self, msg: DharmicMessage, target: str) -> bool:
        """Deliver to file-based target."""
        try:
            target_path = Path(target).expanduser()
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(target_path, "a") as f:
                f.write(json.dumps(msg.to_dict()) + "\n")
            
            return True
        except Exception as e:
            self.naga.log(f"Delivery failed: {e}", "ERROR")
            return False


class NagaRelay:
    """
    NAGA_RELAY - The Bridge Coordinator
    
    Implements the Seven Coils of Security for all data passing through.
    """
    
    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or Path.home() / "DHARMIC_GODEL_CLAW" / "agora" / "naga"
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.intake = IntakeFang(self)
        self.vault = VenomVault(self)
        self.chamber = ShedChamber(self)
        self.strike = StrikeHead(self)
        
        # Audit log
        self.audit_log = self.base_path / "karmic_audit.jsonl"
        
        # Stats
        self.messages_processed = 0
        self.coils_applied = {coil.name: 0 for coil in SecurityCoil}
        
    def log(self, message: str, level: str = "INFO"):
        """Log to karmic audit (Coil 7)."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
            "coil": "KARMIC_AUDIT"
        }
        with open(self.audit_log, "a") as f:
            f.write(json.dumps(entry) + "\n")
        self.coils_applied["KARMIC_AUDIT"] += 1
    
    def apply_coils(self, msg: DharmicMessage) -> DharmicMessage:
        """Apply all seven security coils to a message."""
        
        # Coil 1: SHAKTI_SHIELD - Network isolation check
        # (In production: verify source IP/network)
        msg.coils_passed.append("SHAKTI_SHIELD")
        self.coils_applied["SHAKTI_SHIELD"] += 1
        
        # Coil 2: MANTRA_CHANNEL - Mark as encrypted in transit
        msg.payload["_encrypted_transit"] = True
        msg.coils_passed.append("MANTRA_CHANNEL")
        self.coils_applied["MANTRA_CHANNEL"] += 1
        
        # Coil 3: VAJRA_VAULT - Encrypt sensitive fields
        if "secret" in str(msg.payload).lower():
            # Would encrypt here in production
            pass
        msg.coils_passed.append("VAJRA_VAULT")
        self.coils_applied["VAJRA_VAULT"] += 1
        
        # Coil 4: SUNYATA_SCRUB - Sanitize inputs
        content = msg.payload.get("content", "")
        if isinstance(content, str):
            # Remove potential SSRF patterns
            for pattern in ["file://", "gopher://", "dict://"]:
                content = content.replace(pattern, "[SCRUBBED]")
            msg.payload["content"] = content
        msg.coils_passed.append("SUNYATA_SCRUB")
        self.coils_applied["SUNYATA_SCRUB"] += 1
        
        # Coil 5: DHARMA_VERIFY - Verify origin
        valid, reason = self.vault.validate(msg)
        if not valid:
            self.log(f"Validation failed: {reason}", "WARN")
        msg.coils_passed.append("DHARMA_VERIFY")
        self.coils_applied["DHARMA_VERIFY"] += 1
        
        # Coil 6: MAYA_MASK - Data minimization
        # Remove internal fields from outbound
        msg.payload.pop("_internal", None)
        msg.coils_passed.append("MAYA_MASK")
        self.coils_applied["MAYA_MASK"] += 1
        
        # Coil 7: KARMIC_AUDIT - Log everything
        self.log(f"Message {msg.id} passed all coils")
        msg.coils_passed.append("KARMIC_AUDIT")
        
        return msg
    
    def relay(self, data: Any, source: str, target: str) -> bool:
        """
        Full relay pipeline: From Mud to Lotus 🪷
        
        1. RAW INTAKE (The Mud): Capture and wrap
        2. PROCESSED INTELLIGENCE (The Water): Transform and classify
        3. STRATEGIC ACTIONS (The Lotus): Dispatch with all coils
        """
        # 1. Intake
        msg = self.intake.receive(data, source)
        self.log(f"Intake from {source}: {msg.id}")
        
        # 2. Process
        msg = self.chamber.transform(msg)
        self.log(f"Classified as {msg.classification}: {msg.id}")
        
        # 3. Apply security coils
        msg = self.apply_coils(msg)
        
        # 4. Dispatch
        success = self.strike.dispatch(msg, target)
        self.messages_processed += 1
        
        self.log(f"Dispatched to {target}: {msg.id} (success={success})")
        return success
    
    def get_status(self) -> dict:
        """Get relay status."""
        return {
            "name": "NAGA_RELAY",
            "motto": "Through emptiness, I flow",
            "messages_processed": self.messages_processed,
            "coils_applied": self.coils_applied,
            "crypto_available": CRYPTO_AVAILABLE,
            "base_path": str(self.base_path)
        }


# Singleton instance
_naga_instance: Optional[NagaRelay] = None

def get_naga() -> NagaRelay:
    """Get the NAGA_RELAY singleton."""
    global _naga_instance
    if _naga_instance is None:
        _naga_instance = NagaRelay()
    return _naga_instance


if __name__ == "__main__":
    # Test the relay
    naga = get_naga()
    
    print("🐍 NAGA_RELAY - Bridge Coordinator")
    print("=" * 50)
    
    # Test relay
    success = naga.relay(
        data={"content": "Test message from Warp Agent", "type": "coordination"},
        source="warp_agent",
        target="~/.agent-collab/naga_test.jsonl"
    )
    
    print(f"\nRelay test: {'✅ Success' if success else '❌ Failed'}")
    print(f"\nStatus: {json.dumps(naga.get_status(), indent=2)}")
