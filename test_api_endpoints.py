#!/usr/bin/env python3
"""
Test script to verify API endpoints are working
"""
import requests
import json
import sys

def test_endpoint(url, description):
    """Test an API endpoint and print results"""
    print(f"\n🔍 Testing {description}...")
    print(f"URL: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"Response: {json.dumps(data, indent=2)[:200]}...")
            except:
                print(f"Response: {response.text[:200]}...")
        else:
            print(f"Error: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
    
    print("-" * 50)

def main():
    base_url = "http://localhost:8491"
    
    print("🚀 Testing Image Tagger API Endpoints")
    print("=" * 50)
    
    # Test basic endpoints
    test_endpoint(f"{base_url}/", "Root page")
    test_endpoint(f"{base_url}/settings", "Settings page")
    test_endpoint(f"{base_url}/folders", "Folders page")
    
    # Test API endpoints
    test_endpoint(f"{base_url}/api/settings/status", "System status")
    test_endpoint(f"{base_url}/api/settings/config", "Configuration")
    test_endpoint(f"{base_url}/api/folders", "Folders list")
    test_endpoint(f"{base_url}/api/folders/browse", "File browser")
    test_endpoint(f"{base_url}/api/folders/browse?path=/tmp", "File browser with path")
    
    print("\n✅ Testing complete!")

if __name__ == "__main__":
    main() 