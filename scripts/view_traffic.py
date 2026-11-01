#!/usr/bin/env python3
"""
Paperplane PDF — Traffic, Login & Security Activity Viewer
Run directly on the server to inspect user registrations, logins, and traffic.
Usage:
    python scripts/view_traffic.py
    python scripts/view_traffic.py --limit 100
"""

import argparse
import datetime
import sqlite3
import sys
from pathlib import Path

# Locate database
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config

def format_ts(ts):
    if not ts:
        return "N/A"
    try:
        return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return str(ts)

def main():
    parser = argparse.ArgumentParser(description="View Paperplane PDF traffic & user activity.")
    parser.add_argument("--limit", type=int, default=30, help="Number of records to display")
    args = parser.parse_args()

    db_path = Path(config.DATABASE)
    if not db_path.exists():
        print(f"[-] Database file not found at: {db_path}")
        return

    print("=" * 70)
    print("   PAPERPLANE PDF — PRODUCTION ACTIVITY & TRAFFIC MONITOR")
    print("=" * 70)
    print(f"Database: {db_path}")
    print(f"Time:     {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("-" * 70)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # 1. Total statistics
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    job_count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    completed_jobs = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'completed'").fetchone()[0]
    waitlist_count = conn.execute("SELECT COUNT(*) FROM app_waitlist").fetchone()[0]

    print(f"[+] Total Registered Users:  {user_count}")
    print(f"[+] Total Jobs Processed:    {job_count} ({completed_jobs} completed)")
    print(f"[+] Native App Waitlist:     {waitlist_count}")
    print("-" * 70)

    # 2. Registered Users (Recent)
    print("\n[+] RECENT REGISTERED USERS:")
    users = conn.execute("SELECT id, email, tier, created_at FROM users ORDER BY created_at DESC LIMIT 10").fetchall()
    if not users:
        print("    (No registered users found)")
    else:
        for u in users:
            print(f"    • {u['email']} | Tier: {u['tier'].upper()} | Registered: {format_ts(u['created_at'])}")

    # 3. Recent Audit Logs (Logins, Signups, Security)
    print("\n[+] RECENT LOGIN & SECURITY EVENTS:")
    try:
        logs = conn.execute("SELECT event_type, email, ip_address, created_at, details FROM audit_logs ORDER BY created_at DESC LIMIT ?", (args.limit,)).fetchall()
        if not logs:
            print("    (No audit log entries recorded yet)")
        else:
            for l in logs:
                det = f" ({l['details']})" if l['details'] else ""
                print(f"    [{format_ts(l['created_at'])}] {l['event_type'].upper()} | {l['email'] or 'Anonymous'} | IP: {l['ip_address']}{det}")
    except Exception as e:
        print(f"    (Audit logs table initializing: {e})")

    # 4. Recent Jobs / Operations
    print("\n[+] RECENT PROCESSED JOBS:")
    jobs = conn.execute("SELECT id, operation, status, output_name, created_at FROM jobs ORDER BY created_at DESC LIMIT 10").fetchall()
    if not jobs:
        print("    (No recent jobs found)")
    else:
        for j in jobs:
            print(f"    • [{format_ts(j['created_at'])}] {j['operation']} -> {j['status']} | Output: {j['output_name'] or 'N/A'}")

    print("=" * 70)
    conn.close()

if __name__ == "__main__":
    main()
