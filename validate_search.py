#!/usr/bin/env python3
"""
Validate search accuracy with known test queries.
"""
import requests
import json

# Test queries with expected characteristics
TEST_QUERIES = [
    {
        "query": "homer eating donut",
        "expected_character": "Homer",
        "description": "Should show Homer with donuts"
    },
    {
        "query": "bart on skateboard",
        "expected_character": "Bart",
        "description": "Should show Bart skateboarding"
    },
    {
        "query": "marge in kitchen",
        "expected_character": "Marge",
        "description": "Should show Marge cooking/in kitchen"
    },
    {
        "query": "lisa playing saxophone",
        "expected_character": "Lisa",
        "description": "Should show Lisa with her saxophone"
    },
    {
        "query": "family on couch",
        "expected_character": "Homer",  # At least one family member
        "description": "Should show couch gag or family together"
    },
    {
        "query": "mr burns excellent",
        "expected_character": "Burns",
        "description": "Should show Mr. Burns"
    },
    {
        "query": "springfield elementary school",
        "expected_character": "Bart",  # Or other school characters
        "description": "Should show school building or classrooms"
    },
]

def validate_search(base_url="http://127.0.0.1:8000"):
    """Run validation tests on search."""
    print("🔍 SEARCH VALIDATION REPORT")
    print("=" * 70)
    print()

    results = []

    for test in TEST_QUERIES:
        query = test["query"]
        expected_char = test["expected_character"]

        print(f"Query: '{query}'")
        print(f"Expected: {test['description']}")

        try:
            response = requests.get(f"{base_url}/search", params={"q": query, "limit": 5})
            response.raise_for_status()
            frames = response.json()

            if not frames:
                print("❌ NO RESULTS FOUND")
                results.append({"query": query, "status": "FAIL", "reason": "No results"})
                print()
                continue

            # Check top result
            top_result = frames[0]
            score = top_result["score"]
            caption = top_result["caption"]
            characters = top_result["characters"]

            print(f"✅ Top result: {top_result['episode']} @ {top_result['timestamp']}s")
            print(f"   Score: {score*100:.1f}%")
            print(f"   Caption: {caption}")
            print(f"   Characters: {characters if characters else 'None detected'}")

            # Validate expected character appears in results
            char_found = any(expected_char.lower() in r["characters"].lower() for r in frames)

            if char_found:
                print(f"   ✓ Found expected character: {expected_char}")
                results.append({"query": query, "status": "PASS"})
            else:
                print(f"   ⚠️  Expected character '{expected_char}' not in top 5 results")
                results.append({"query": query, "status": "PARTIAL", "reason": f"Character {expected_char} not found"})

        except Exception as e:
            print(f"❌ ERROR: {e}")
            results.append({"query": query, "status": "ERROR", "reason": str(e)})

        print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    passed = sum(1 for r in results if r["status"] == "PASS")
    partial = sum(1 for r in results if r["status"] == "PARTIAL")
    failed = sum(1 for r in results if r["status"] in ["FAIL", "ERROR"])

    print(f"✅ Passed: {passed}/{len(results)}")
    print(f"⚠️  Partial: {partial}/{len(results)}")
    print(f"❌ Failed: {failed}/{len(results)}")
    print()

    accuracy = (passed + partial * 0.5) / len(results) * 100
    print(f"Overall Accuracy: {accuracy:.1f}%")
    print()

    if failed > 0:
        print("Failed queries:")
        for r in results:
            if r["status"] in ["FAIL", "ERROR"]:
                print(f"  - {r['query']}: {r.get('reason', 'Unknown')}")

if __name__ == "__main__":
    validate_search()
