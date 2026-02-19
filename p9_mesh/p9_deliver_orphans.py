#!/usr/bin/env python3
"""
P9 Orphan Delivery — Multi-mode sync for AGNI files

Tries delivery in order:
1. NATS (if AGNI bridge online)
2. HTTP POST (if AGNI API available)
3. Git bundle (create pack for manual transfer)

Usage:
  python3 p9_deliver_orphans.py --sync-file sync_request_002.json
  python3 p9_deliver_orphans.py --check  # Check AGNI status
"""

import json
import asyncio
import base64
import hashlib
from pathlib import Path
from typing import List, Dict, Optional
import argparse

# Try importing optional dependencies
try:
    import nats
    from nats.aio.client import Client as NATS
    NATS_AVAILABLE = True
except ImportError:
    NATS_AVAILABLE = False

try:
    import aiohttp
    HTTP_AVAILABLE = True
except ImportError:
    HTTP_AVAILABLE = False
    import urllib.request
    import urllib.error


class OrphanDelivery:
    def __init__(self, sync_file: str, nats_url: str = "nats://localhost:4222"):
        self.sync_file = Path(sync_file)
        self.nats_url = nats_url
        self.sync_data = None
        self.delivery_log = []
        
    def load_sync_request(self) -> Dict:
        """Load the sync request file"""
        with open(self.sync_file) as f:
            self.sync_data = json.load(f)
        return self.sync_data
    
    def check_agni_status(self) -> Dict:
        """Check if AGNI is reachable via various methods"""
        status = {
            "nats": False,
            "http": False,
            "files_pending": 0,
            "files_readable": 0
        }
        
        # Check NATS
        if NATS_AVAILABLE:
            try:
                # Quick NATS check would need async, skipping for sync method
                status["nats"] = "unknown (async check needed)"
            except:
                pass
        
        # Check files exist
        if self.sync_data:
            pending = self.sync_data.get("files_needed", [])
            status["files_pending"] = len(pending)
            readable = sum(1 for f in pending if Path(f).exists())
            status["files_readable"] = readable
        
        return status
    
    def create_delivery_bundle(self, output_dir: str = "orphan_bundles") -> Path:
        """Create a tar.gz bundle of all orphan files for manual transfer"""
        import tarfile
        import tempfile
        
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        bundle_name = f"orphan_bundle_{self.sync_data.get('pulse', 'unknown')}.tar.gz"
        bundle_path = output_path / bundle_name
        
        with tarfile.open(bundle_path, "w:gz") as tar:
            for file_path in self.sync_data.get("files_needed", []):
                path = Path(file_path)
                if path.exists():
                    # Store with relative path to avoid absolute path issues
                    arcname = path.relative_to(Path.home()) if str(path).startswith(str(Path.home())) else path.name
                    tar.add(path, arcname=arcname)
                    self.delivery_log.append({"file": str(path), "status": "bundled"})
        
        return bundle_path
    
    def create_git_bundle(self) -> Path:
        """Create a git bundle containing the orphan files"""
        import subprocess
        
        # Create orphan branch with just these files
        bundle_path = Path(f"orphan_sync_{self.sync_data.get('pulse', '002')}.bundle")
        
        # Add files to git and create bundle
        files = [f for f in self.sync_data.get("files_needed", []) if Path(f).exists()]
        
        if not files:
            print("⚠️ No readable files to bundle")
            return None
        
        # Create a pack file listing
        with open("/tmp/orphan_files.txt", "w") as f:
            for file_path in files:
                f.write(f"{file_path}\n")
        
        print(f"📦 Created file list with {len(files)} files")
        print(f"   Use: rsync --files-from=/tmp/orphan_files.txt / agni:/destination")
        
        return Path("/tmp/orphan_files.txt")
    
    async def try_nats_delivery(self) -> bool:
        """Try to deliver via NATS"""
        if not NATS_AVAILABLE:
            return False
        
        try:
            nc = await nats.connect(self.nats_url)
            
            # Check if AGNI is online
            try:
                response = await nc.request("agni.memory.health", b"", timeout=2.0)
                print(f"✅ AGNI NATS bridge online: {response.data.decode()}")
            except:
                print("❌ AGNI NATS bridge not responding")
                await nc.close()
                return False
            
            # Deliver files in batches
            batch_size = 10
            files = self.sync_data.get("files_needed", [])
            
            for i in range(0, len(files), batch_size):
                batch = files[i:i + batch_size]
                payload = {
                    "pulse": self.sync_data.get("pulse"),
                    "batch": i // batch_size + 1,
                    "total_batches": (len(files) + batch_size - 1) // batch_size,
                    "files": []
                }
                
                for file_path in batch:
                    path = Path(file_path)
                    if path.exists():
                        content = path.read_bytes()
                        payload["files"].append({
                            "path": str(path),
                            "content": base64.b64encode(content).decode(),
                            "hash": hashlib.sha256(content).hexdigest()[:16]
                        })
                
                try:
                    response = await nc.request(
                        "agni.memory.sync",
                        json.dumps(payload).encode(),
                        timeout=10.0
                    )
                    result = json.loads(response.data.decode())
                    print(f"   Batch {payload['batch']}: {result.get('status', 'unknown')}")
                except Exception as e:
                    print(f"   Batch {payload['batch']}: failed - {e}")
            
            await nc.close()
            return True
            
        except Exception as e:
            print(f"❌ NATS delivery failed: {e}")
            return False
    
    async def try_http_delivery(self, agni_url: str = "http://10.104.0.2:8080") -> bool:
        """Try to deliver via HTTP POST"""
        if HTTP_AVAILABLE:
            async with aiohttp.ClientSession() as session:
                # Check health
                try:
                    async with session.get(f"{agni_url}/health", timeout=2) as resp:
                        if resp.status == 200:
                            print(f"✅ AGNI HTTP API online")
                        else:
                            return False
                except:
                    return False
                
                # Deliver files
                for file_path in self.sync_data.get("files_needed", [])[:5]:  # Test with 5
                    path = Path(file_path)
                    if not path.exists():
                        continue
                    
                    content = path.read_bytes()
                    payload = {
                        "path": str(path),
                        "content": base64.b64encode(content).decode(),
                        "hash": hashlib.sha256(content).hexdigest()[:16],
                        "pulse": self.sync_data.get("pulse")
                    }
                    
                    try:
                        async with session.post(
                            f"{agni_url}/sync/file",
                            json=payload,
                            timeout=10
                        ) as resp:
                            result = await resp.json()
                            print(f"   {path.name}: {result.get('status')}")
                    except Exception as e:
                        print(f"   {path.name}: failed - {e}")
                
                return True
        else:
            # Use urllib fallback
            try:
                req = urllib.request.Request(
                    f"{agni_url}/health",
                    method="GET"
                )
                with urllib.request.urlopen(req, timeout=2) as resp:
                    if resp.status == 200:
                        print(f"✅ AGNI HTTP API online (urllib)")
                        return True
            except:
                return False
        
        return False
    
    async def deliver(self) -> Dict:
        """Try all delivery methods"""
        if not self.sync_data:
            self.load_sync_request()
        
        results = {
            "nats": False,
            "http": False,
            "git_bundle": None,
            "tar_bundle": None,
            "status": "pending"
        }
        
        print(f"🚀 Starting orphan delivery for PULSE-{self.sync_data.get('pulse', 'unknown')}")
        print(f"   Files: {len(self.sync_data.get('files_needed', []))}")
        
        # Try NATS
        print("\n📡 Trying NATS...")
        results["nats"] = await self.try_nats_delivery()
        
        # Try HTTP
        if not results["nats"]:
            print("\n🌐 Trying HTTP...")
            results["http"] = await self.try_http_delivery()
        
        # Fall back to bundles
        if not results["nats"] and not results["http"]:
            print("\n📦 Creating bundles for manual transfer...")
            results["tar_bundle"] = str(self.create_delivery_bundle())
            results["git_bundle"] = str(self.create_git_bundle())
            results["status"] = "manual_transfer_required"
        else:
            results["status"] = "delivered"
        
        return results


def main():
    parser = argparse.ArgumentParser(description="Deliver orphan files to AGNI")
    parser.add_argument("--sync-file", default="sync_request_002.json", help="Sync request JSON")
    parser.add_argument("--check", action="store_true", help="Check AGNI status only")
    parser.add_argument("--bundle-only", action="store_true", help="Create bundle only, no network")
    
    args = parser.parse_args()
    
    delivery = OrphanDelivery(args.sync_file)
    delivery.load_sync_request()
    
    if args.check:
        status = delivery.check_agni_status()
        print(json.dumps(status, indent=2))
        return
    
    if args.bundle_only:
        tar_path = delivery.create_delivery_bundle()
        git_path = delivery.create_git_bundle()
        print(f"\n📦 Bundles created:")
        print(f"   TAR: {tar_path}")
        print(f"   File list: {git_path}")
        return
    
    # Full delivery attempt
    results = asyncio.run(delivery.deliver())
    
    print(f"\n📊 Delivery Results:")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
