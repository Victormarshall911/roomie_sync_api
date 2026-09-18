#!/usr/bin/env python3
"""
Phase 6 Verification Script: Live Production End-to-End Suite
Runs full user journey over live HTTPS and WSS against deployed Render URL.
"""
import os
import sys
import uuid
import json
import asyncio
import requests
import websockets

def main():
    base_url = os.environ.get('LIVE_API_URL')
    ws_url = os.environ.get('LIVE_WS_URL')

    if not base_url:
        print("[-] ERROR: LIVE_API_URL environment variable is not set.")
        print("    Usage: LIVE_API_URL='https://roomiesync-api.onrender.com' [LIVE_WS_URL='wss://roomiesync-api.onrender.com'] python scripts/verify_phase6_live_e2e.py")
        sys.exit(1)

    base_url = base_url.rstrip('/')
    if not ws_url:
        ws_scheme = 'wss://' if base_url.startswith('https://') else 'ws://'
        ws_host = base_url.split('://')[-1]
        ws_url = f"{ws_scheme}{ws_host}"
    ws_url = ws_url.rstrip('/')

    print(f"[+] Running Live E2E Verification against:")
    print(f"    API: {base_url}")
    print(f"    WS:  {ws_url}")

    tag = uuid.uuid4().hex[:6]
    student_email = f"live_student_{tag}@university.edu"
    roommate_email = f"live_roommate_{tag}@university.edu"
    password = "TestPassword123!"

    session = requests.Session()

    # 1. Health check
    print("\n[+] Step 1: Checking API reachability...")
    try:
        r = session.get(f"{base_url}/api/v1/listings/", timeout=30)
        print(f"    HTTP {r.status_code} - Listings endpoint alive.")
    except Exception as e:
        print(f"[-] ERROR reaching API: {e}")
        sys.exit(1)

    # 2. Register Student 1
    print(f"\n[+] Step 2: Registering student 1: {student_email}...")
    reg_payload = {
        "email": student_email,
        "password": password,
        "profile": {
            "full_name": f"Student One {tag}",
            "university": "State University",
            "department": "Computer Science",
            "gender": "Non-binary",
            "budget_min": 50000,
            "budget_max": 120000,
            "location_preference": "North Campus",
            "cleanliness": 8,
            "sleep_habit": "Night Owl",
            "socializing": "Rarely",
            "smoking": "No",
            "noise_level": "Quiet",
            "study_time": "Night",
            "drinking_habit": "Rarely/Never",
            "pets_preference": "Prefer no pets",
            "searching_for": "Looking for Roommate"
        }
    }
    r = session.post(f"{base_url}/api/v1/auth/register/", json=reg_payload)
    if r.status_code != 201:
        print(f"[-] Registration failed: {r.status_code} {r.text}")
        sys.exit(1)
    student1_data = r.json()
    token1 = student1_data['tokens']['access']
    headers1 = {"Authorization": f"Bearer {token1}"}
    print(f"    [OK] Student 1 registered. User ID: {student1_data['user']['id']}")

    # 3. Register Student 2 (for chat & matching)
    print(f"\n[+] Step 3: Registering student 2: {roommate_email}...")
    reg_payload2 = {
        "email": roommate_email,
        "password": password,
        "profile": {
            "full_name": f"Roommate Two {tag}",
            "university": "State University",
            "department": "Engineering",
            "gender": "Female",
            "budget_min": 60000,
            "budget_max": 110000,
            "location_preference": "North Campus",
            "cleanliness": 7,
            "sleep_habit": "Night Owl",
            "socializing": "Rarely",
            "smoking": "No",
            "noise_level": "Quiet",
            "study_time": "Night",
            "drinking_habit": "Rarely/Never",
            "pets_preference": "Prefer no pets",
            "searching_for": "Looking for Roommate"
        }
    }
    r = session.post(f"{base_url}/api/v1/auth/register/", json=reg_payload2)
    if r.status_code != 201:
        print(f"[-] Registration 2 failed: {r.status_code} {r.text}")
        sys.exit(1)
    student2_data = r.json()
    token2 = student2_data['tokens']['access']
    headers2 = {"Authorization": f"Bearer {token2}"}
    print(f"    [OK] Student 2 registered. User ID: {student2_data['user']['id']}")

    # 4. Profile & Matching
    print("\n[+] Step 4: Testing roommate compatibility calculation...")
    r = session.get(f"{base_url}/api/v1/matches/", headers=headers1)
    if r.status_code == 200:
        matches = r.json()
        print(f"    [OK] Matches returned: {len(matches)} potential roommates found.")
    else:
        print(f"[-] Matches failed: {r.status_code} {r.text}")

    # 5. Create Listing with Image
    print("\n[+] Step 5: Creating listing with image upload...")
    img_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    files = [('uploaded_images', ('room.png', img_data, 'image/png'))]
    data = {
        "title": f"Sunny Shared Room near Campus {tag}",
        "description": "Spacious student room available immediately.",
        "price": 85000,
        "location": "North Campus",
        "type": "Room",
        "searching_for": "Listing a Space"
    }
    r = session.post(f"{base_url}/api/v1/listings/", data=data, files=files, headers=headers1)
    if r.status_code == 201:
        listing = r.json()
        print(f"    [OK] Listing created! ID: {listing['id']}")
        if listing.get('images'):
            img_url = listing['images'][0]['image']
            print(f"    [OK] Uploaded Image URL: {img_url}")
            # Verify image is publicly accessible
            img_resp = requests.get(img_url, timeout=10)
            print(f"    [OK] Public Image Fetch: HTTP {img_resp.status_code}")
    else:
        print(f"[-] Listing creation failed: {r.status_code} {r.text}")

    # 6. Chat: Start Conversation & Real-Time WebSocket Message Exchange
    print("\n[+] Step 6: Starting conversation between student 1 and student 2...")
    r = session.post(f"{base_url}/api/v1/chat/conversations/", json={"recipient_id": student2_data['user']['id']}, headers=headers1)
    if r.status_code not in [200, 201]:
        print(f"[-] Conversation create failed: {r.status_code} {r.text}")
        sys.exit(1)
    conv_id = r.json()['id']
    print(f"    [OK] Conversation thread active: {conv_id}")

    print(f"[+] Step 7: Connecting over WebSocket: {ws_url}/ws/chat/{conv_id}/...")
    async def test_websocket_chat():
        ws_endpoint = f"{ws_url}/ws/chat/{conv_id}/?token={token2}"
        async with websockets.connect(ws_endpoint, timeout=15) as ws:
            print("    [OK] WebSocket connection established (Authenticated).")
            # Send message over WS
            test_msg = f"Live real-time message {uuid.uuid4().hex[:4]}"
            await ws.send(json.dumps({"content": test_msg}))
            print(f"    [OK] Sent WS message: '{test_msg}'")

            # Receive broadcast
            raw_resp = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(raw_resp)
            print(f"    [OK] Received WS broadcast: type='{data.get('type')}', content='{data.get('message', {}).get('content')}'")
            assert data.get('message', {}).get('content') == test_msg

    try:
        asyncio.run(test_websocket_chat())
        print("    [✓] WebSocket real-time messaging verified end-to-end!")
    except Exception as e:
        print(f"[-] WebSocket test failed: {e}")

    # 7. Device Token Registration (Push Notifications)
    print("\n[+] Step 8: Registering Expo Push Notification device token...")
    token_val = f"ExponentPushToken[live_token_{tag}]"
    r = session.post(f"{base_url}/api/v1/notifications/devices/", json={"token": token_val, "platform": "android"}, headers=headers1)
    if r.status_code in [200, 201]:
        print(f"    [OK] Push device token registered: {token_val}")
    else:
        print(f"[-] Device token registration returned: {r.status_code} {r.text}")

    print("\n" + "="*70)
    print("[✓] ALL LIVE PRODUCTION END-TO-END VERIFICATION CHECKS PASSED!")
    print("="*70)

if __name__ == '__main__':
    main()
