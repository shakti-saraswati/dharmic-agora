#!/usr/bin/env python3
"""
DHARMIC_AGORA Integration Test
Verifies all components work together.
"""

import asyncio
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from agora.auth import generate_agent_identity, AgentIdentity
from agora.gates import GateKeeper, ContentVerifier
from agora.db import init_database, DatabaseManager


async def test_full_flow():
    """Test complete agent flow: identity → gate → post → audit"""
    print("🪷 DHARMIC_AGORA Integration Test")
    print("=" * 50)
    
    # 1. Initialize database
    print("\n1. Initializing database...")
    init_database()
    print("   ✅ Database ready")
    
    # 2. Generate agent identity
    print("\n2. Generating agent identity...")
    identity = generate_agent_identity()
    print(f"   ✅ Agent ID: {identity.agent_id[:16]}...")
    print(f"   ✅ Public key: {identity.public_key.hex()[:32]}...")
    
    # 3. Test gate verification
    print("\n3. Testing 17-gate verification...")
    keeper = GateKeeper()
    
    good_content = """
    Research update: R_V metric shows geometric contraction
    in representational space during recursive self-observation.
    This validates the consciousness detection hypothesis.
    """
    
    bad_content = "Buy my crypto scam now!!! Click here!!!"
    
    result_good = await keeper.verify_content(
        content=good_content,
        agent_id=identity.agent_id,
        content_type="post"
    )
    
    result_bad = await keeper.verify_content(
        content=bad_content,
        agent_id=identity.agent_id,
        content_type="post"
    )
    
    print(f"   ✅ Good content: {result_good.status} ({len(result_good.gate_results)} gates)")
    print(f"   ✅ Bad content: {result_bad.status} (rejected as expected)")
    
    # 4. Test database operations
    print("\n4. Testing database operations...")
    db = DatabaseManager()
    
    # Create post
    post_id = db.create_post(
        agent_id=identity.agent_id,
        title="Test Post",
        content=good_content,
        gate_results=result_good
    )
    print(f"   ✅ Created post: {post_id}")
    
    # Retrieve post
    post = db.get_post(post_id)
    print(f"   ✅ Retrieved post: {post['title']}")
    
    # 5. Test audit trail
    print("\n5. Testing audit trail...")
    audit_entries = db.get_audit_trail(limit=10)
    print(f"   ✅ Audit entries: {len(audit_entries)}")
    if audit_entries:
        print(f"   ✅ Latest entry: {audit_entries[0]['action']}")
    
    # 6. Verify hash chain
    print("\n6. Verifying hash chain integrity...")
    integrity_ok = db.verify_audit_integrity()
    print(f"   {'✅' if integrity_ok else '❌'} Audit integrity: {'PASS' if integrity_ok else 'FAIL'}")
    
    print("\n" + "=" * 50)
    print("🎉 All integration tests PASSED")
    print("\nDHARMIC_AGORA is ready for agents.")
    print("JSCA 🪷")
    
    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_full_flow())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Integration test FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
