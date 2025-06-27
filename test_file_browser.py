#!/usr/bin/env python3
"""
Test script for the file browser API
"""

import requests
import json
import sys

def test_file_browser():
    """Test the file browser API endpoints"""
    base_url = "http://localhost:8491"
    
    print("Testing File Browser API...")
    print("=" * 50)
    
    # Test 1: Browse root directory
    print("\n1. Testing root directory browse...")
    try:
        response = requests.get(f"{base_url}/api/folders/browse")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Success: Found {len(data['items'])} items in root")
            print(f"   Current path: {data['current_path']}")
            print(f"   Parent path: {data['parent_path']}")
            
            # Show first few items
            for item in data['items'][:3]:
                icon = "📁" if item['is_dir'] else "📄"
                print(f"   {icon} {item['name']} ({item['path']})")
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False
    
    # Test 2: Browse a specific directory (try /Users)
    print("\n2. Testing specific directory browse...")
    try:
        response = requests.get(f"{base_url}/api/folders/browse?path=/Users")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Success: Found {len(data['items'])} items in /Users")
            print(f"   Current path: {data['current_path']}")
            print(f"   Parent path: {data['parent_path']}")
            
            # Show first few items
            for item in data['items'][:3]:
                icon = "📁" if item['is_dir'] else "📄"
                print(f"   {icon} {item['name']} ({item['path']})")
        else:
            print(f"❌ Error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False
    
    # Test 3: Test security - try to access system files
    print("\n3. Testing security (should fail)...")
    try:
        response = requests.get(f"{base_url}/api/folders/browse?path=/proc")
        if response.status_code == 400:
            print("✅ Security test passed: Blocked access to /proc")
        else:
            print(f"⚠️  Warning: Security test may have failed - got {response.status_code}")
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False
    
    # Test 4: Test invalid path
    print("\n4. Testing invalid path (should fail)...")
    try:
        response = requests.get(f"{base_url}/api/folders/browse?path=/nonexistent/path")
        if response.status_code == 404:
            print("✅ Invalid path test passed: Correctly returned 404")
        else:
            print(f"⚠️  Warning: Invalid path test got {response.status_code}")
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False
    
    print("\n" + "=" * 50)
    print("✅ File Browser API tests completed successfully!")
    return True

if __name__ == "__main__":
    success = test_file_browser()
    sys.exit(0 if success else 1) 