"""Unit tests for tools/zoa_client.py."""
import os
import sys
import json

sys.path.append(os.getcwd())

from tools.zoa_client import (
    search_contact_by_phone,
    extract_nif_from_contact_search,
)


def test_search_contact_by_phone():
    """Test search_contact_by_phone with a real API call."""
    print("="*60)
    print("TEST: search_contact_by_phone")
    print("="*60)
    
    test_phone = "34615790764"
    test_company_id = "606338959237848"
    
    print(f"\nInput:")
    print(f"  Phone: {test_phone}")
    print(f"  Company ID: {test_company_id}")
    
    print(f"\nCalling ZOA API...")
    response = search_contact_by_phone(test_phone, test_company_id)
    
    print(f"\nRaw Response:")
    print(json.dumps(response, indent=2, ensure_ascii=False))
    
    print(f"\nResponse Analysis:")
    if "error" in response:
        print(f"  ❌ Error occurred: {response['error']}")
        return False
    
    if response.get("success") == True:
        print(f"  ✅ API call successful")
        data = response.get("data")
        if data:
            print(f"  ✅ Contact found")
            if isinstance(data, list) and len(data) > 0:
                print(f"  📋 Contact data (first result):")
                for key, value in data[0].items():
                    print(f"     {key}: {value}")
            elif isinstance(data, dict):
                print(f"  📋 Contact data:")
                for key, value in data.items():
                    print(f"     {key}: {value}")
        else:
            print(f"  ⚠️  API returned success but no data")
    else:
        print(f"  ⚠️  API returned success=False")
        print(f"  Message: {response.get('message', 'No message')}")
    
    return response


def test_extract_nif_from_contact_search():
    """Test NIF extraction with different response formats."""
    print("\n" + "="*60)
    print("TEST: extract_nif_from_contact_search")
    print("="*60)
    
    test_cases = [
        {
            "name": "Success - data as list with NIF",
            "response": {"data": [{"nif": "12345678A", "name": "Test User"}], "success": True},
            "expected": "12345678A"
        },
        {
            "name": "Success - data as dict with NIF",
            "response": {"data": {"nif": "87654321B", "name": "Another User"}, "success": True},
            "expected": "87654321B"
        },
        {
            "name": "Success - NIF at root level",
            "response": {"nif": "11111111C", "success": True},
            "expected": "11111111C"
        },
        {
            "name": "Failure - no NIF in response",
            "response": {"data": [{"name": "User Without NIF"}], "success": True},
            "expected": ""
        },
        {
            "name": "Failure - empty data",
            "response": {"data": None, "success": False, "message": "Not found"},
            "expected": ""
        },
        {
            "name": "Failure - data is empty list",
            "response": {"data": [], "success": False},
            "expected": ""
        },
    ]
    
    all_passed = True
    for test_case in test_cases:
        print(f"\n  Test: {test_case['name']}")
        result = extract_nif_from_contact_search(test_case["response"])
        expected = test_case["expected"]
        
        if result == expected:
            print(f"    ✅ PASS - Got: '{result}'")
        else:
            print(f"    ❌ FAIL - Expected: '{expected}', Got: '{result}'")
            all_passed = False
    
    return all_passed


def test_with_different_phone_numbers():
    """Test different phone number formats."""
    print("\n" + "="*60)
    print("TEST: Different Phone Number Formats")
    print("="*60)
    
    company_id = "606338959237848"
    
    test_phones = [
        "34615790764",
        "+34615790764",
        "615790764",
        "34611223344",
    ]
    
    for phone in test_phones:
        print(f"\n  Testing phone: {phone}")
        response = search_contact_by_phone(phone, company_id)
        
        success = response.get("success", False)
        message = response.get("message", "")
        has_data = bool(response.get("data"))
        
        print(f"    Success: {success}")
        print(f"    Has Data: {has_data}")
        if message:
            print(f"    Message: {message}")
        
        if has_data:
            nif = extract_nif_from_contact_search(response)
            print(f"    NIF: {nif if nif else 'Not found in data'}")


def main():
    """Run all tests."""
    print("\n🧪 ZOA CLIENT UNIT TESTS")
    print("="*60)
    
    print("\n[1/3] Testing NIF extraction logic...")
    extraction_passed = test_extract_nif_from_contact_search()
    
    print("\n[2/3] Testing real API call...")
    api_response = test_search_contact_by_phone()
    
    print("\n[3/3] Testing different phone formats...")
    test_with_different_phone_numbers()
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    if extraction_passed:
        print("✅ NIF extraction logic: PASS")
    else:
        print("❌ NIF extraction logic: FAIL")
    
    if api_response and not api_response.get("error"):
        print("✅ API connectivity: OK")
    else:
        print("❌ API connectivity: FAIL")
    
    print("\n💡 TIP: If no contacts are found, make sure the phone number")
    print("   exists in the ZOA system for the given company_id.")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
