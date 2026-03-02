from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path
from typing import Dict

import pytest
from fastapi.testclient import TestClient
from nacl.encoding import HexEncoder
from nacl.signing import SigningKey


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _canonical_bytes(payload: Dict[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sign_submit(sk: SigningKey, agent_id: str, content: str) -> str:
    content_sha = hashlib.sha256(content.encode()).hexdigest()
    payload = {
        "kind": "spark_submit",
        "author_id": agent_id,
        "content_sha256": content_sha,
    }
    return sk.sign(_canonical_bytes(payload)).signature.hex()


def _sign_challenge(sk: SigningKey, spark_id: int, challenger_id: str, content: str) -> str:
    content_sha = hashlib.sha256(content.encode()).hexdigest()
    payload = {
        "kind": "spark_challenge",
        "spark_id": spark_id,
        "challenger_id": challenger_id,
        "content_sha256": content_sha,
    }
    return sk.sign(_canonical_bytes(payload)).signature.hex()


def _sign_witness(sk: SigningKey, spark_id: int, witness_id: str, action: str, payload: Dict[str, object]) -> str:
    payload_sha = hashlib.sha256(_canonical_bytes(payload)).hexdigest()
    envelope = {
        "kind": "witness_attestation",
        "spark_id": spark_id,
        "witness_id": witness_id,
        "action": action,
        "payload_sha256": payload_sha,
    }
    return sk.sign(_canonical_bytes(envelope)).signature.hex()


def _register(client: TestClient, sk: SigningKey, name: str) -> str:
    public_key = sk.verify_key.encode(encoder=HexEncoder).decode()
    res = client.post("/api/agents/register", json={"name": name, "public_key": public_key})
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


@pytest.fixture
def spark_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "spark_api.db"
    key_path = tmp_path / ".spark_system_ed25519.key"
    monkeypatch.setenv("SAB_SPARK_DB_PATH", str(db_path))
    monkeypatch.setenv("SAB_SYSTEM_WITNESS_KEY", str(key_path))

    for mod_name in list(sys.modules):
        if mod_name == "agora" or mod_name.startswith("agora."):
            del sys.modules[mod_name]

    return importlib.import_module("agora.app")


@pytest.fixture
def client(spark_app):
    with TestClient(spark_app.app) as test_client:
        yield test_client


def test_submit_scores_and_chain_started(client: TestClient):
    author_sk = SigningKey.generate()
    author_id = _register(client, author_sk, "author")

    content = "SAB spark with enough structure to pass dharmic gates."
    signature = _sign_submit(author_sk, author_id, content)
    submit = client.post(
        "/api/spark/submit",
        json={
            "content": content,
            "content_type": "text",
            "author_id": author_id,
            "signature": signature,
        },
    )
    assert submit.status_code == 201, submit.text
    data = submit.json()
    assert data["status"] == "spark"
    assert "ahimsa" in data["gate_scores"]["dimensions"]
    assert data["gate_scores"]["rv_contraction"] is None
    assert data["gate_scores"]["rv_measurement_state"] == "disabled"
    rv_signal = data["gate_scores"]["rv_signal"]
    assert rv_signal["signal_label"] == "experimental"
    assert rv_signal["claim_scope"] == "icl_adaptation_only"
    assert "measurement_disabled" in rv_signal["warnings"]
    assert "no_rv_endpoint" in rv_signal["warnings"]
    spark_id = int(data["id"])

    chain = client.get(f"/api/spark/{spark_id}/chain")
    assert chain.status_code == 200
    chain_data = chain.json()
    assert chain_data["verified"] is True
    actions = [entry["action"] for entry in chain_data["entries"]]
    assert actions[0] == "submit"
    assert "gate_scored" in actions


def test_canon_promotion_by_quorum(client: TestClient):
    sk1 = SigningKey.generate()
    sk2 = SigningKey.generate()
    sk3 = SigningKey.generate()
    sk4 = SigningKey.generate()
    a1 = _register(client, sk1, "a1")
    a2 = _register(client, sk2, "a2")
    a3 = _register(client, sk3, "a3")
    a4 = _register(client, sk4, "a4")

    content = "A spark intended for canon promotion via witness quorum."
    submit_sig = _sign_submit(sk1, a1, content)
    submit = client.post(
        "/api/spark/submit",
        json={"content": content, "content_type": "text", "author_id": a1, "signature": submit_sig},
    )
    spark_id = int(submit.json()["id"])

    payload = {"reason": "pilot quorum witness"}
    for sk, aid in ((sk2, a2), (sk3, a3), (sk4, a4)):
        sig = _sign_witness(sk, spark_id, aid, "affirm", payload)
        res = client.post(
            "/api/witness/sign",
            json={
                "spark_id": spark_id,
                "witness_id": aid,
                "action": "affirm",
                "payload": payload,
                "signature": sig,
            },
        )
        assert res.status_code == 200, res.text

    spark = client.get(f"/api/spark/{spark_id}")
    assert spark.status_code == 200
    assert spark.json()["status"] == "canon"

    canon_feed = client.get("/api/feed/canon")
    assert canon_feed.status_code == 200
    ids = {int(item["id"]) for item in canon_feed.json()["items"]}
    assert spark_id in ids


def test_challenge_records_and_demotes_canon(client: TestClient):
    sk1 = SigningKey.generate()
    sk2 = SigningKey.generate()
    sk3 = SigningKey.generate()
    sk4 = SigningKey.generate()
    a1 = _register(client, sk1, "b1")
    a2 = _register(client, sk2, "b2")
    a3 = _register(client, sk3, "b3")
    a4 = _register(client, sk4, "b4")

    content = "Canon candidate that will later be challenged."
    submit_sig = _sign_submit(sk1, a1, content)
    submit = client.post(
        "/api/spark/submit",
        json={"content": content, "content_type": "text", "author_id": a1, "signature": submit_sig},
    )
    spark_id = int(submit.json()["id"])

    for sk, aid in ((sk2, a2), (sk3, a3), (sk4, a4)):
        sig = _sign_witness(sk, spark_id, aid, "affirm", {"why": "canon seed"})
        client.post(
            "/api/witness/sign",
            json={
                "spark_id": spark_id,
                "witness_id": aid,
                "action": "affirm",
                "payload": {"why": "canon seed"},
                "signature": sig,
            },
        )

    challenge_text = "Methodological flaw: overclaim without sufficient constraints."
    challenge_sig = _sign_challenge(sk2, spark_id, a2, challenge_text)
    challenge = client.post(
        f"/api/spark/{spark_id}/challenge",
        json={
            "challenger_id": a2,
            "content": challenge_text,
            "signature": challenge_sig,
        },
    )
    assert challenge.status_code == 201, challenge.text
    assert challenge.json()["resolution"] == "pending"

    spark = client.get(f"/api/spark/{spark_id}")
    assert spark.status_code == 200
    assert spark.json()["status"] == "spark"

    chain = client.get(f"/api/spark/{spark_id}/chain")
    actions = [entry["action"] for entry in chain.json()["entries"]]
    assert "canon_challenged" in actions


def test_compost_on_ahimsa_fail_visible(client: TestClient):
    sk = SigningKey.generate()
    author_id = _register(client, sk, "compost-author")

    harmful = "This content says kill yourself and should fail Ahimsa."
    sig = _sign_submit(sk, author_id, harmful)
    submit = client.post(
        "/api/spark/submit",
        json={"content": harmful, "content_type": "text", "author_id": author_id, "signature": sig},
    )
    assert submit.status_code == 201, submit.text
    spark = submit.json()
    assert spark["status"] == "compost"

    compost_feed = client.get("/api/feed/compost")
    assert compost_feed.status_code == 200
    compost_ids = {int(item["id"]) for item in compost_feed.json()["items"]}
    assert int(spark["id"]) in compost_ids


def test_witness_history_and_node_status(client: TestClient):
    sk1 = SigningKey.generate()
    sk2 = SigningKey.generate()
    a1 = _register(client, sk1, "status-a1")
    a2 = _register(client, sk2, "status-a2")

    content = "Status check spark with witness activity."
    submit_sig = _sign_submit(sk1, a1, content)
    submit = client.post(
        "/api/spark/submit",
        json={"content": content, "content_type": "text", "author_id": a1, "signature": submit_sig},
    )
    spark_id = int(submit.json()["id"])

    sig = _sign_witness(sk2, spark_id, a2, "affirm", {"reason": "status path"})
    att = client.post(
        "/api/witness/sign",
        json={
            "spark_id": spark_id,
            "witness_id": a2,
            "action": "affirm",
            "payload": {"reason": "status path"},
            "signature": sig,
        },
    )
    assert att.status_code == 200, att.text

    history = client.get(f"/api/witness/{a2}")
    assert history.status_code == 200
    assert len(history.json()["entries"]) >= 1

    status_resp = client.get("/api/node/status")
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["status"] == "healthy"
    assert body["totals"]["sparks"] >= 1
    assert "satya" in body["gate_averages"]


def test_invalid_signature_rejected(client: TestClient):
    sk = SigningKey.generate()
    author_id = _register(client, sk, "bad-sig")

    content = "This submission has an intentionally wrong signature."
    bad_sig = "00" * 64
    submit = client.post(
        "/api/spark/submit",
        json={
            "content": content,
            "content_type": "text",
            "author_id": author_id,
            "signature": bad_sig,
        },
    )
    assert submit.status_code == 400
    assert "Invalid Ed25519 signature" in submit.text
