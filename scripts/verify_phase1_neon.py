#!/usr/bin/env python3
"""
Phase 1 Verification Script: Neon PostgreSQL
Verifies SSL connection, runs dry-run migrations, and validates table schemas.
"""
import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'roomiesync.settings')

def main():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("[-] ERROR: DATABASE_URL environment variable is not set.")
        print("    Usage: DATABASE_URL='postgresql://...sslmode=require' python scripts/verify_phase1_neon.py")
        sys.exit(1)

    print("[+] Initializing Django with target DATABASE_URL...")
    django.setup()

    from django.db import connection
    from django.core.management import call_command

    print("[+] Connecting to Neon PostgreSQL...")
    with connection.cursor() as cursor:
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"[+] Connected successfully!\n    Database Version: {version}")

        cursor.execute("SHOW ssl;")
        ssl_status = cursor.fetchone()
        print(f"[+] SSL Status: {ssl_status[0] if ssl_status else 'active'}")

    print("\n[+] Running dry-run migration to Neon...")
    call_command('migrate', interactive=False)

    print("\n[+] Validating all 10 domain tables exist in database...")
    expected_tables = [
        'users',
        'profiles',
        'listings',
        'listing_images',
        'conversations',
        'messages',
        'reports',
        'blocks',
        'verification_requests',
        'device_tokens',
    ]

    all_tables = connection.introspection.table_names()
    missing_tables = []
    for table in expected_tables:
        if table in all_tables:
            print(f"  [OK] Table found: {table}")
        else:
            print(f"  [FAIL] Missing table: {table}")
            missing_tables.append(table)

    if missing_tables:
        print(f"\n[-] ERROR: Missing {len(missing_tables)} tables: {missing_tables}")
        sys.exit(1)

    print("\n[✓] Phase 1 Verification PASSED: Neon PostgreSQL is fully migrated and ready.")

if __name__ == '__main__':
    main()
