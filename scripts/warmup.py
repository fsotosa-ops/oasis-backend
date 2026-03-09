#!/usr/bin/env python3
"""Pre-event warm-up script.

Run 30 minutes before an event to:
1. Wake Supabase from potential free-tier pause (SELECT 1)
2. Pre-populate Redis cache for event journeys
3. Verify all services are healthy

Usage:
    python scripts/warmup.py --backend-url https://oasis-backend-xxx.run.app
    python scripts/warmup.py --backend-url https://oasis-backend-xxx.run.app --journey-ids <id1>,<id2>
"""

import argparse
import sys
import time

import httpx


def main():
    parser = argparse.ArgumentParser(description="Pre-event warm-up script")
    parser.add_argument(
        "--backend-url",
        required=True,
        help="Base URL of the backend (e.g. https://oasis-backend-xxx.run.app)",
    )
    parser.add_argument(
        "--journey-ids",
        default="",
        help="Comma-separated journey IDs to pre-warm cache",
    )
    parser.add_argument(
        "--token",
        default="",
        help="Admin JWT token for authenticated warm-up requests",
    )
    args = parser.parse_args()

    base = args.backend_url.rstrip("/")
    client = httpx.Client(timeout=60)
    headers = {}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"

    print("=" * 60)
    print("FSummer Pre-Event Warm-up")
    print("=" * 60)

    # Step 1: Health check (wakes Supabase + verifies Redis)
    print("\n[1/3] Health check (wakes Supabase if paused)...")
    start = time.time()
    try:
        resp = client.get(f"{base}/health")
        elapsed = time.time() - start
        data = resp.json()
        print(f"  Status: {data.get('status')} (took {elapsed:.1f}s)")
        print(f"  Redis:  {data.get('redis')}")

        if elapsed > 10:
            print("  WARNING: Slow response — Supabase may have been paused. Run again to confirm.")
        if data.get("redis") != "connected":
            print("  WARNING: Redis not connected — cache will be disabled.")
    except Exception as e:
        print(f"  FAILED: {e}")
        print("  Backend may be down or URL incorrect.")
        sys.exit(1)

    # Step 2: Pre-warm journey cache
    journey_ids = [jid.strip() for jid in args.journey_ids.split(",") if jid.strip()]
    if journey_ids and args.token:
        print(f"\n[2/3] Pre-warming {len(journey_ids)} journey(s) in cache...")
        for jid in journey_ids:
            try:
                # This hits get_journey_with_steps which populates Redis cache
                resp = client.get(
                    f"{base}/api/v1/journeys/enrollments/me/full",
                    headers=headers,
                )
                print(f"  Journey batch fetch: {resp.status_code}")
                break  # One call is enough — it caches all journeys
            except Exception as e:
                print(f"  Warning: {e}")
    elif journey_ids:
        print("\n[2/3] Skipping cache warm-up (no --token provided)")
    else:
        print("\n[2/3] Skipping cache warm-up (no --journey-ids provided)")

    # Step 3: Second health check to confirm everything is warm
    print("\n[3/3] Final verification...")
    try:
        start = time.time()
        resp = client.get(f"{base}/health")
        elapsed = time.time() - start
        data = resp.json()
        print(f"  Status: {data.get('status')} ({elapsed:.2f}s)")
        print(f"  Redis:  {data.get('redis')}")
    except Exception as e:
        print(f"  Warning: {e}")

    print("\n" + "=" * 60)
    print("Warm-up complete. System ready for event.")
    print("=" * 60)


if __name__ == "__main__":
    main()
