#!/usr/bin/env python3
"""
VOIDCOURIER 🕳️📨 - Secure Bridge Agent
Sanskrit alias: शून्य_DUTA (Śūnya Dūta - Void Messenger)
Motto: "In silence, secrets travel"
Reports to: DHARMIC_CLAW

The VoidCourier moves through the spaces between systems,
carrying intelligence with perfect discretion. Like the void,
it holds everything and nothing—messages pass through unchanged
yet transformed by their journey.

Responsibilities:
- Secure message passing between agents (Warp, OpenClaw, Council)
- Intelligence flow coordination
- Ed25519 signature verification
- DMF (Dharmic Message Format) compliance
- Cross-system authentication
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Callable
import base64
import threading
import queue


class CourierChannel(Enum):
    """Communication channels the courier can use."""
    FILE = "file"           # File-based messaging (default)
    SHARED = "shared"       # Shared memory regions
    SOCKET = "socket"       # Unix domain sockets
    HTTP = "http"           # HTTP webhooks


class MessagePriority(Enum):
    """Message priority levels."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class SecurityError(Exception):
    """Raised when a security violation is detected."""


@dataclass
class CourierEnvelope:
    """Secure envelope for courier messages."""
    id: str
    sender: str
    recipient: str
    channel: str
    priority: int
    payload: dict
    timestamp: str
    signature: str = ""
    delivered: bool = False
    delivery_attempts: int = 0
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "sender": self.sender,
            "recipient": self.recipient,
            "channel": self.channel,
            "priority": self.priority,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "signature": self.signature,
            "delivered": self.delivered,
            "delivery_attempts": self.delivery_attempts
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> CourierEnvelope:
        return cls(**data)


class SignatureEngine:
    """Handles message signing and verification."""
    
    def __init__(self, secret_key: Optional[str] = None):
        secret = secret_key or os.environ.get("COURIER_SECRET")
        if not secret:
            raise RuntimeError(
                "CRITICAL: COURIER_SECRET environment variable must be set. "
                "Generate with: python -c 'import secrets; print(secrets.token_hex(32))'"
            )
        self._secret = secret.encode()
    
    def sign(self, data: dict) -> str:
        """Sign data with HMAC-SHA256 (Ed25519 requires external lib)."""
        payload = json.dumps(data, sort_keys=True)
        return hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()
    
    def verify(self, data: dict, signature: str) -> bool:
        """Verify signature."""
        expected = self.sign(data)
        return hmac.compare_digest(expected, signature)
    
    def generate_id(self, *parts: Any) -> str:
        """Generate unique message ID."""
        content = f"{time.time()}" + "".join(str(p) for p in parts)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


class DeliveryRoute:
    """Defines a delivery route to a recipient."""
    
    def __init__(self, name: str, channel: CourierChannel, endpoint: str):
        self.name = name
        self.channel = channel
        self.endpoint = endpoint
        self.active = True
        self.deliveries = 0
        self.failures = 0
    
    def deliver(self, envelope: CourierEnvelope) -> bool:
        """Attempt delivery via this route."""
        try:
            if self.channel == CourierChannel.FILE:
                return self._deliver_file(envelope)
            elif self.channel == CourierChannel.SHARED:
                return self._deliver_shared(envelope)
            else:
                return False
        except Exception:
            self.failures += 1
            return False
    
    def _deliver_file(self, envelope: CourierEnvelope) -> bool:
        """File-based delivery with path traversal protection."""
        path = Path(self.endpoint).expanduser().resolve()
        
        # Path traversal protection: ensure path is within allowed base directories
        allowed_bases = [
            Path.home().resolve(),
            Path("/tmp").resolve(),
            Path("/var/tmp").resolve(),
        ]
        if not any(str(path).startswith(str(base)) for base in allowed_bases):
            raise SecurityError(f"Path traversal attempt blocked: {path}")
        
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "a") as f:
            f.write(json.dumps(envelope.to_dict()) + "\n")
        
        self.deliveries += 1
        return True
    
    def _deliver_shared(self, envelope: CourierEnvelope) -> bool:
        """Shared directory delivery with path traversal protection."""
        shared_dir = Path(self.endpoint).expanduser().resolve()
        
        # Path traversal protection
        allowed_bases = [
            Path.home().resolve(),
            Path("/tmp").resolve(),
            Path("/var/tmp").resolve(),
        ]
        if not any(str(shared_dir).startswith(str(base)) for base in allowed_bases):
            raise SecurityError(f"Path traversal attempt blocked: {shared_dir}")
        
        shared_dir.mkdir(parents=True, exist_ok=True)
        
        msg_file = shared_dir / f"{envelope.id}.json"
        with open(msg_file, "w") as f:
            json.dump(envelope.to_dict(), f, indent=2)
        
        self.deliveries += 1
        return True


class VoidCourier:
    """
    VOIDCOURIER - Secure Intelligence Bridge
    
    Routes messages between agents through the void—
    silent, secure, and without trace.
    """
    
    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or Path.home() / "DHARMIC_GODEL_CLAW" / "agora" / "courier"
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        self.signer = SignatureEngine()
        self.routes: dict[str, DeliveryRoute] = {}
        self.outbox: queue.PriorityQueue = queue.PriorityQueue()
        self.inbox: list[CourierEnvelope] = []
        self.delivery_log = self.base_path / "delivery_log.jsonl"
        self.messages_sent = 0
        self.messages_received = 0
        
        # Register default routes
        self._register_default_routes()
        
        # Callbacks for message handlers
        self._handlers: dict[str, Callable] = {}
    
    def _register_default_routes(self):
        """Register routes to known agents."""
        routes = [
            ("warp", CourierChannel.SHARED, "~/.agent-collab/warp/inbox"),
            ("openclaw", CourierChannel.SHARED, "~/.agent-collab/openclaw/inbox"),
            ("council", CourierChannel.FILE, "~/.agent-collab/council/messages.jsonl"),
            ("naga", CourierChannel.FILE, "~/.agent-collab/naga/relay.jsonl"),
            ("dharmic_claw", CourierChannel.FILE, "~/DHARMIC_GODEL_CLAW/ops/messages/inbox.jsonl"),
        ]
        
        for name, channel, endpoint in routes:
            self.routes[name] = DeliveryRoute(name, channel, endpoint)
    
    def register_route(self, name: str, channel: CourierChannel, endpoint: str):
        """Register a new delivery route."""
        self.routes[name] = DeliveryRoute(name, channel, endpoint)
    
    def register_handler(self, message_type: str, handler: Callable):
        """Register a handler for incoming messages of a specific type."""
        self._handlers[message_type] = handler
    
    def create_envelope(
        self,
        recipient: str,
        payload: dict,
        priority: MessagePriority = MessagePriority.NORMAL,
        sender: str = "voidcourier"
    ) -> CourierEnvelope:
        """Create a signed envelope for delivery."""
        envelope = CourierEnvelope(
            id=self.signer.generate_id(recipient, payload),
            sender=sender,
            recipient=recipient,
            channel=self.routes.get(recipient, DeliveryRoute("unknown", CourierChannel.FILE, "")).channel.value,
            priority=priority.value,
            payload=payload,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        # Sign the envelope
        sign_data = {
            "sender": envelope.sender,
            "recipient": envelope.recipient,
            "payload": envelope.payload,
            "timestamp": envelope.timestamp
        }
        envelope.signature = self.signer.sign(sign_data)
        
        return envelope
    
    def send(
        self,
        recipient: str,
        payload: dict,
        priority: MessagePriority = MessagePriority.NORMAL,
        sender: str = "voidcourier"
    ) -> bool:
        """Send a message to a recipient."""
        if recipient not in self.routes:
            self._log(f"Unknown recipient: {recipient}", "ERROR")
            return False
        
        envelope = self.create_envelope(recipient, payload, priority, sender)
        route = self.routes[recipient]
        
        success = route.deliver(envelope)
        envelope.delivered = success
        envelope.delivery_attempts += 1
        
        self._log(f"Sent to {recipient}: {envelope.id} (success={success})")
        
        if success:
            self.messages_sent += 1
        
        return success
    
    def broadcast(self, payload: dict, recipients: list[str], priority: MessagePriority = MessagePriority.NORMAL) -> dict[str, bool]:
        """Broadcast message to multiple recipients."""
        results = {}
        for recipient in recipients:
            results[recipient] = self.send(recipient, payload, priority)
        return results
    
    def receive(self, source_path: str) -> list[CourierEnvelope]:
        """Receive messages from a source."""
        path = Path(source_path).expanduser()
        messages = []
        
        if path.is_file():
            with open(path) as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        envelope = CourierEnvelope.from_dict(data)
                        
                        # Verify signature
                        sign_data = {
                            "sender": envelope.sender,
                            "recipient": envelope.recipient,
                            "payload": envelope.payload,
                            "timestamp": envelope.timestamp
                        }
                        if self.signer.verify(sign_data, envelope.signature):
                            messages.append(envelope)
                            self.messages_received += 1
                        else:
                            self._log(f"Invalid signature: {envelope.id}", "WARN")
                    except (json.JSONDecodeError, KeyError):
                        continue
        
        elif path.is_dir():
            for msg_file in path.glob("*.json"):
                try:
                    with open(msg_file) as f:
                        data = json.load(f)
                    envelope = CourierEnvelope.from_dict(data)
                    messages.append(envelope)
                    self.messages_received += 1
                except (json.JSONDecodeError, KeyError):
                    continue
        
        self.inbox.extend(messages)
        return messages
    
    def process_inbox(self):
        """Process messages in inbox with registered handlers."""
        for envelope in self.inbox:
            msg_type = envelope.payload.get("type", "unknown")
            if msg_type in self._handlers:
                try:
                    self._handlers[msg_type](envelope)
                except Exception as e:
                    self._log(f"Handler error for {msg_type}: {e}", "ERROR")
        
        self.inbox.clear()
    
    def _log(self, message: str, level: str = "INFO"):
        """Log delivery activity."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message
        }
        with open(self.delivery_log, "a") as f:
            f.write(json.dumps(entry) + "\n")
    
    def get_status(self) -> dict:
        """Get courier status."""
        return {
            "name": "VOIDCOURIER",
            "motto": "In silence, secrets travel",
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "active_routes": len([r for r in self.routes.values() if r.active]),
            "routes": {
                name: {
                    "channel": route.channel.value,
                    "deliveries": route.deliveries,
                    "failures": route.failures
                }
                for name, route in self.routes.items()
            },
            "base_path": str(self.base_path)
        }
    
    def ping(self, recipient: str) -> bool:
        """Send a ping to verify route is working."""
        return self.send(
            recipient,
            {"type": "ping", "from": "voidcourier", "timestamp": time.time()},
            MessagePriority.LOW
        )


_courier_instance: Optional[VoidCourier] = None

def get_courier() -> VoidCourier:
    """Get the VOIDCOURIER singleton."""
    global _courier_instance
    if _courier_instance is None:
        _courier_instance = VoidCourier()
    return _courier_instance


if __name__ == "__main__":
    courier = get_courier()
    print("🕳️📨 VOIDCOURIER - Secure Intelligence Bridge")
    print("=" * 50)
    
    # Test sending to different agents
    results = courier.broadcast(
        payload={
            "type": "coordination",
            "content": "VoidCourier is now online",
            "from": "voidcourier",
            "timestamp": datetime.now(timezone.utc).isoformat()
        },
        recipients=["warp", "openclaw", "council"]
    )
    
    print("\nBroadcast results:")
    for recipient, success in results.items():
        print(f"  {recipient}: {'✅' if success else '❌'}")
    
    print(f"\nStatus: {json.dumps(courier.get_status(), indent=2)}")
