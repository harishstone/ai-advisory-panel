"""
End-to-end test: run all 16 questions against the live backend and print results.
Usage: python tests/test_all_questions.py
"""
import httpx
import json
import sys

BASE = "http://localhost:8000"
QUOTE = "1775512473115"

QUESTIONS = {
    1:  "IOPS & Throughput",
    2:  "Restore Rate",
    3:  "Backup Speed",
    4:  "Network Throughput",
    5:  "RAID Recommendation",
    6:  "RAID Rebuild Time",
    7:  "Power Consumption",
    8:  "Rack Units",
    9:  "UPS Requirements",
    10: "SSD Sizing (SNSD S3)",
    11: "Storage Efficiency",
    12: "Dedup Index RAM",
    13: "Concurrent Jobs",
    14: "Cache & Storage Tiers",
    15: "Network Bonding Mode",
    16: "Backup Storage Capacity",
}

SEPARATOR = "=" * 80


def consume_sse(response) -> tuple[str, list]:
    """Parse SSE stream and return (full_text, warnings)."""
    full_text = ""
    warnings = []
    buffer = ""
    for chunk in response.iter_bytes():
        buffer += chunk.decode("utf-8", errors="replace")
        while "\n\n" in buffer:
            msg, buffer = buffer.split("\n\n", 1)
            for line in msg.splitlines():
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        if event["type"] == "start":
                            warnings = event.get("warnings", [])
                        elif event["type"] == "token":
                            full_text += event.get("text", "")
                    except Exception:
                        pass
    return full_text.strip(), warnings


def run_tests():
    print(f"\n{'StoneFly AI Advisory Panel — Full Test Run':^80}")
    print(f"{'Quote: ' + QUOTE:^80}")
    print(SEPARATOR)

    # Load quote
    with httpx.Client(timeout=30) as client:
        r = client.post(f"{BASE}/api/load-quote", json={"quote_number": QUOTE})
        if not r.json().get("success"):
            print("ERROR: Could not load quote")
            sys.exit(1)
        summary = r.json()["config_summary"]
        print(f"Config loaded: {summary['storage_media']['primary_disk_count']}x "
              f"{summary['storage_media']['primary_disk_type'].upper()} drives, "
              f"RAID from config, {summary['network']['nic_speed'].upper()} x{summary['network']['active_data_ports']} NICs, "
              f"{summary['compute']['total_ram_gb']} GB RAM")
        print(SEPARATOR)

    passed = 0
    failed = 0
    results = []

    with httpx.Client(timeout=120) as client:
        for qid, label in QUESTIONS.items():
            print(f"\nQ{qid:02d}: {label}")
            print("-" * 60)
            try:
                with client.stream(
                    "POST",
                    f"{BASE}/api/ask-stream",
                    json={"question_id": qid},
                    timeout=120,
                ) as r:
                    text, warnings = consume_sse(r)

                if not text:
                    print("  [FAIL] EMPTY RESPONSE")
                    failed += 1
                    results.append((qid, label, "FAIL - EMPTY RESPONSE", ""))
                else:
                    # Print first 700 chars, replacing unencodable chars
                    preview = text[:700] + ("..." if len(text) > 700 else "")
                    print(preview.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace"))
                    if warnings:
                        print(f"\n  [WARN] Warnings: {', '.join(warnings)}")
                    print(f"\n  [OK] ({len(text)} chars)")
                    passed += 1
                    results.append((qid, label, "OK", text))

            except Exception as e:
                err = str(e).encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace")
                print(f"  [FAIL] ERROR: {err}")
                failed += 1
                results.append((qid, label, "ERROR", str(e)))

    print(f"\n{SEPARATOR}")
    print(f"RESULTS: {passed}/16 passed, {failed} failed")
    print(SEPARATOR)

    if failed:
        print("\nFailed questions:")
        for qid, label, status, detail in results:
            if status != "OK":
                print(f"  Q{qid:02d} {label}: {status} — {detail[:120]}")

    return failed == 0


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
