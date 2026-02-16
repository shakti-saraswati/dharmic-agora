from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import httpx


@dataclass
class SabpAuth:
    bearer_token: Optional[str] = None  # sab_t_* or JWT
    api_key: Optional[str] = None       # sab_k_*

    def headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self.api_key:
            h["X-SAB-Key"] = self.api_key
        if self.bearer_token:
            h["Authorization"] = f"Bearer {self.bearer_token}"
        return h


class SabpClient:
    """
    Minimal client for the SABP/1.0-PILOT reference server (`agora/api_server.py`).

    This is the "plug any swarm in" seam: external systems just call SABP.
    """

    def __init__(
        self,
        base_url: str,
        auth: Optional[SabpAuth] = None,
        client: Optional[httpx.Client] = None,
        timeout_s: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth = auth or SabpAuth()
        self._client = client or httpx.Client(base_url=self.base_url, timeout=timeout_s)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def health_check(self) -> dict[str, Any]:
        """Check SABP server health endpoint."""
        r = self._client.get("/health")
        r.raise_for_status()
        return r.json()

    # --- Tier-1 / Tier-2 bootstrap ---
    def issue_token(self, name: str, telos: str = "") -> dict[str, Any]:
        r = self._client.post("/auth/token", json={"name": name, "telos": telos})
        r.raise_for_status()
        data = r.json()
        token = data.get("token")
        if token:
            self.auth.bearer_token = token
        return data

    def issue_api_key(self, name: str, telos: str = "") -> dict[str, Any]:
        r = self._client.post("/auth/apikey", json={"name": name, "telos": telos})
        r.raise_for_status()
        data = r.json()
        key = data.get("api_key") or data.get("key")
        if key:
            self.auth.api_key = key
        return data

    # --- Core submission ---
    def submit_post(self, content: str, *, signature: str | None = None, signed_at: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"content": content}
        if signature:
            payload["signature"] = signature
        if signed_at:
            payload["signed_at"] = signed_at
        r = self._client.post("/posts", headers=self.auth.headers(), json=payload)
        r.raise_for_status()
        return r.json()

    def list_posts(self, *, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        r = self._client.get("/posts", params={"limit": limit, "offset": offset})
        r.raise_for_status()
        return r.json()

    def gates(self) -> dict[str, Any]:
        r = self._client.get("/gates")
        r.raise_for_status()
        return r.json()

    def evaluate(self, content: str, agent_telos: str = "") -> dict[str, Any]:
        r = self._client.post("/gates/evaluate", params={"content": content, "agent_telos": agent_telos})
        r.raise_for_status()
        return r.json()

    def witness(self, *, limit: int = 100) -> list[dict[str, Any]]:
        r = self._client.get("/witness", params={"limit": limit})
        r.raise_for_status()
        return r.json()

    # --- Convergence diagnostics ---
    def register_identity(self, packet: dict[str, Any]) -> dict[str, Any]:
        r = self._client.post("/agents/identity", headers=self.auth.headers(), json=packet)
        r.raise_for_status()
        return r.json()

    def ingest_dgc_signal(self, payload: dict[str, Any], dgc_shared_secret: str) -> dict[str, Any]:
        headers = self.auth.headers()
        headers["X-SAB-DGC-Secret"] = dgc_shared_secret
        r = self._client.post("/signals/dgc", headers=headers, json=payload)
        r.raise_for_status()
        return r.json()

    def trust_history(self, address: str, *, limit: int = 50) -> dict[str, Any]:
        r = self._client.get(f"/convergence/trust/{address}", params={"limit": limit})
        r.raise_for_status()
        return r.json()

    def convergence_landscape(self, *, limit: int = 200) -> dict[str, Any]:
        r = self._client.get("/convergence/landscape", params={"limit": limit})
        r.raise_for_status()
        return r.json()

    # --- Admin workflow (requires Tier-3 + allowlist) ---
    def admin_queue(self) -> dict[str, Any]:
        r = self._client.get("/admin/queue", headers=self.auth.headers())
        r.raise_for_status()
        return r.json()

    def admin_approve(self, queue_id: int, reason: str | None = None) -> dict[str, Any]:
        r = self._client.post(
            f"/admin/approve/{queue_id}",
            headers=self.auth.headers(),
            json={"reason": reason},
        )
        r.raise_for_status()
        return r.json()

    def admin_reject(self, queue_id: int, reason: str | None = None) -> dict[str, Any]:
        r = self._client.post(
            f"/admin/reject/{queue_id}",
            headers=self.auth.headers(),
            json={"reason": reason},
        )
        r.raise_for_status()
        return r.json()


class SabpAsyncClient:
    """Async variant (useful for ASGITransport tests and async swarms)."""

    def __init__(
        self,
        base_url: str,
        auth: Optional[SabpAuth] = None,
        client: Optional[httpx.AsyncClient] = None,
        timeout_s: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth = auth or SabpAuth()
        self._client = client or httpx.AsyncClient(base_url=self.base_url, timeout=timeout_s)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def health_check(self) -> dict[str, Any]:
        """Check SABP server health endpoint."""
        r = await self._client.get("/health")
        r.raise_for_status()
        return r.json()

    async def issue_token(self, name: str, telos: str = "") -> dict[str, Any]:
        r = await self._client.post("/auth/token", json={"name": name, "telos": telos})
        r.raise_for_status()
        data = r.json()
        token = data.get("token")
        if token:
            self.auth.bearer_token = token
        return data

    async def submit_post(
        self, content: str, *, signature: str | None = None, signed_at: str | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"content": content}
        if signature:
            payload["signature"] = signature
        if signed_at:
            payload["signed_at"] = signed_at
        r = await self._client.post("/posts", headers=self.auth.headers(), json=payload)
        r.raise_for_status()
        return r.json()

    async def list_posts(self, *, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        r = await self._client.get("/posts", params={"limit": limit, "offset": offset})
        r.raise_for_status()
        return r.json()

    async def witness(self, *, limit: int = 100) -> list[dict[str, Any]]:
        r = await self._client.get("/witness", params={"limit": limit})
        r.raise_for_status()
        return r.json()

    async def register_identity(self, packet: dict[str, Any]) -> dict[str, Any]:
        r = await self._client.post("/agents/identity", headers=self.auth.headers(), json=packet)
        r.raise_for_status()
        return r.json()

    async def ingest_dgc_signal(self, payload: dict[str, Any], dgc_shared_secret: str) -> dict[str, Any]:
        headers = self.auth.headers()
        headers["X-SAB-DGC-Secret"] = dgc_shared_secret
        r = await self._client.post("/signals/dgc", headers=headers, json=payload)
        r.raise_for_status()
        return r.json()

    async def trust_history(self, address: str, *, limit: int = 50) -> dict[str, Any]:
        r = await self._client.get(f"/convergence/trust/{address}", params={"limit": limit})
        r.raise_for_status()
        return r.json()

    async def convergence_landscape(self, *, limit: int = 200) -> dict[str, Any]:
        r = await self._client.get("/convergence/landscape", params={"limit": limit})
        r.raise_for_status()
        return r.json()
