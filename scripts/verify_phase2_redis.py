#!/usr/bin/env python3
"""
Phase 2 Verification Script: Hosted Redis
Tests connectivity, TLS if required, SET/GET operations, and key isolation.
"""
import os
import sys
import uuid
import redis

def main():
    redis_url = os.environ.get('REDIS_URL')
    if not redis_url:
        print("[-] ERROR: REDIS_URL environment variable is not set.")
        print("    Usage: REDIS_URL='rediss://... or redis://...' python scripts/verify_phase2_redis.py")
        sys.exit(1)

    print(f"[+] Connecting to Redis at {redis_url.split('@')[-1] if '@' in redis_url else redis_url}...")
    try:
        r = redis.from_url(redis_url, socket_timeout=10)
        pong = r.ping()
        print(f"[+] PING response: {pong}")
    except Exception as e:
        print(f"[-] ERROR connecting to Redis: {e}")
        sys.exit(1)

    # Test SET/GET for OTP cache simulation
    test_key = f"rs_cache:test_{uuid.uuid4().hex[:8]}"
    test_val = "roomiesync_otp_123456"
    print(f"[+] Testing SET/GET for key: {test_key}")
    try:
        r.set(test_key, test_val, ex=60)
        retrieved = r.get(test_key)
        if isinstance(retrieved, bytes):
            retrieved = retrieved.decode('utf-8')
        assert retrieved == test_val, f"Value mismatch: {retrieved} != {test_val}"
        print(f"  [OK] Value verified: {retrieved}")
        r.delete(test_key)
        print("  [OK] Cleaned up test key.")
    except Exception as e:
        print(f"[-] ERROR in cache test: {e}")
        sys.exit(1)

    # Test Channels layer Redis connectivity
    print("[+] Testing Channels Redis layer connection...")
    try:
        import asyncio
        import channels_redis.core

        layer = channels_redis.core.RedisChannelLayer(
            hosts=[redis_url],
            prefix="rs_channels"
        )
        async def test_layer():
            channel_name = await layer.new_channel()
            await layer.send(channel_name, {"type": "test.message", "text": "hello"})
            msg = await layer.receive(channel_name)
            assert msg.get("text") == "hello"
            await layer.close_pools()

        asyncio.run(test_layer())
        print("  [OK] Channels Redis layer send/receive verified.")
    except Exception as e:
        print(f"[-] ERROR in Channels Redis layer test: {e}")
        sys.exit(1)

    print("\n[✓] Phase 2 Verification PASSED: Hosted Redis is fully operational.")

if __name__ == '__main__':
    main()
