#!/usr/bin/env python3
"""
Test script to verify the scan API works correctly
"""
import requests
def test_processing_status_fields():
    resp = requests.get('http://localhost:8491/api/settings/processing-status', timeout=5)
    assert resp.status_code == 200
    data = resp.json()
    # Accept either old or new schema keys
    assert ('active' in data and 'current_task' in data and 'progress' in data) or 
           ('is_processing' in data and 'current_operation' in data)
import json

def test_scan_api():
    """Test the scan API endpoints"""
    base_url = "http://localhost:8001"
    
    print("🔍 Testing Image Tagger API...")
    
    # Test 1: Scan all folders
    print("\n1️⃣ Testing scan-all-folders endpoint...")
    try:
        response = requests.post(f"{base_url}/api/settings/scan-all-folders", timeout=10)
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   Response: {json.dumps(data, indent=2)}")
            
            # Check if response has the expected format
            if "status" in data and "message" in data:
                print("   ✅ Response format is correct!")
                if data["status"] == "success":
                    print("   ✅ Status is 'success'!")
                else:
                    print(f"   ⚠️ Status is '{data['status']}' instead of 'success'")
            else:
                print("   ❌ Response missing 'status' or 'message' field")
        else:
            print(f"   ❌ HTTP Error: {response.status_code}")
            print(f"   Response: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("   ❌ Connection failed - is the server running on port 8001?")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 2: Process all images  
    print("\n2️⃣ Testing process-all-images endpoint...")
    try:
        response = requests.post(f"{base_url}/api/settings/process-all-images", timeout=10)
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   Response: {json.dumps(data, indent=2)}")
            
            # Check if response has the expected format
            if "status" in data and "message" in data:
                print("   ✅ Response format is correct!")
                if data["status"] == "success":
                    print("   ✅ Status is 'success'!")
                else:
                    print(f"   ⚠️ Status is '{data['status']}' instead of 'success'")
            else:
                print("   ❌ Response missing 'status' or 'message' field")
        else:
            print(f"   ❌ HTTP Error: {response.status_code}")
            print(f"   Response: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("   ❌ Connection failed - is the server running on port 8001?")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print("\n🎉 API Testing Complete!")

if __name__ == "__main__":
    test_scan_api()
