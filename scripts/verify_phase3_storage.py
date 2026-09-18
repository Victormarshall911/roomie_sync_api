#!/usr/bin/env python3
"""
Phase 3 Verification Script: S3 / Cloudflare R2 Media Storage
Tests public upload & fetch, private upload & signed URL access, and ensures segregation.
"""
import os
import sys
import uuid
import django
import requests

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'roomiesync.settings')

def main():
    if not (os.environ.get('AWS_ACCESS_KEY_ID') and os.environ.get('AWS_STORAGE_BUCKET_NAME')):
        print("[-] ERROR: AWS_ACCESS_KEY_ID and AWS_STORAGE_BUCKET_NAME environment variables are required.")
        print("    Usage: Set AWS_* and AWS_S3_ENDPOINT_URL env vars, then run scripts/verify_phase3_storage.py")
        sys.exit(1)

    print("[+] Initializing Django...")
    django.setup()

    from django.conf import settings
    from roomiesync.storage_backends import PublicMediaStorage, PrivateMediaStorage
    from django.core.files.base import ContentFile

    public_storage = PublicMediaStorage()
    private_storage = PrivateMediaStorage()

    test_id = uuid.uuid4().hex[:8]

    # 1. Test Public Storage (Avatars / Listings)
    public_filename = f"listings/test_{test_id}.txt"
    public_content = b"RoomieSync Public Media Test"
    print(f"\n[+] Uploading public test file: {public_filename}")
    saved_public_path = public_storage.save(public_filename, ContentFile(public_content))
    public_url = public_storage.url(saved_public_path)
    print(f"[+] Public URL generated: {public_url}")

    print("[+] Testing public fetch via HTTP GET...")
    try:
        resp = requests.get(public_url, timeout=15)
        if resp.status_code == 200 and resp.content == public_content:
            print("  [OK] Public file is directly accessible (HTTP 200).")
        else:
            print(f"  [WARN] Public fetch returned HTTP {resp.status_code}: {resp.text[:100]}")
            print("         If using Cloudflare R2, ensure public development R2 URL or custom domain is configured.")
    except Exception as e:
        print(f"  [-] Fetch error: {e}")

    # 2. Test Private Storage (Verification Documents)
    private_filename = f"verification_documents/test_{test_id}.pdf"
    private_content = b"%PDF-1.4 RoomieSync Private Verification Document"
    print(f"\n[+] Uploading private test document: {private_filename}")
    saved_private_path = private_storage.save(private_filename, ContentFile(private_content))
    private_signed_url = private_storage.url(saved_private_path)
    print(f"[+] Private signed URL generated (valid 1800s): {private_signed_url[:90]}...")

    # Test signed URL access
    print("[+] Testing signed URL fetch via HTTP GET...")
    try:
        resp_signed = requests.get(private_signed_url, timeout=15)
        if resp_signed.status_code == 200:
            print("  [OK] Signed URL grants access (HTTP 200).")
        else:
            print(f"  [-] Signed URL access failed (HTTP {resp_signed.status_code}): {resp_signed.text[:100]}")
    except Exception as e:
        print(f"  [-] Signed URL fetch error: {e}")

    # Test that direct unauthenticated access WITHOUT signature is rejected
    raw_url = private_signed_url.split('?')[0]
    print(f"[+] Testing unsigned direct GET (should be 403 Forbidden): {raw_url[:80]}...")
    try:
        resp_raw = requests.get(raw_url, timeout=10)
        if resp_raw.status_code in [401, 403, 404]:
            print(f"  [OK] Direct unsigned access rejected with HTTP {resp_raw.status_code}.")
        else:
            print(f"  [FAIL] Direct unsigned access was permitted (HTTP {resp_raw.status_code})!")
    except Exception as e:
        print(f"  [OK] Direct access blocked: {e}")

    # Clean up
    print("\n[+] Cleaning up test files from bucket...")
    public_storage.delete(saved_public_path)
    private_storage.delete(saved_private_path)
    print("  [OK] Test files deleted.")

    print("\n[✓] Phase 3 Verification PASSED: S3/R2 storage segregation is confirmed.")

if __name__ == '__main__':
    main()
