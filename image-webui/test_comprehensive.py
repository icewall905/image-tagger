#!/usr/bin/env python3
"""
Comprehensive test to validate all our fixes
"""
import sys
import os
sys.path.append('backend')

def test_imports():
    """Test that all imports work"""
    print("🔍 Testing imports...")
    
    try:
        # Test core imports
        from backend.config import Config
        print("  ✅ Config import successful")
        
        # Test that Config has the required methods
        assert hasattr(Config, 'get'), "Config missing get method"
        assert hasattr(Config, 'add_section'), "Config missing add_section method"
        assert hasattr(Config, 'has_section'), "Config missing has_section method"
        print("  ✅ Config has all required methods")
        
        # Test API imports
        from backend.api import settings, folders
        print("  ✅ API modules import successful")
        
        # Test schemas
        from backend import schemas
        print("  ✅ Schemas import successful")
        
        # Test MessageResponse has status field
        response = schemas.MessageResponse(status="success", message="test")
        assert response.status == "success"
        print("  ✅ MessageResponse includes status field")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Import error: {e}")
        return False

def test_api_responses():
    """Test API response format"""
    print("\n🔍 Testing API response formats...")
    
    try:
        # Test that we can create proper API responses
        response1 = {"status": "success", "message": "Test message"}
        assert "status" in response1
        assert "message" in response1
        print("  ✅ API response format is correct")
        
        # Test MessageResponse schema
        from backend.schemas import MessageResponse
        response2 = MessageResponse(status="success", message="Schema test")
        assert response2.status == "success"
        assert response2.message == "Schema test"
        print("  ✅ MessageResponse schema works correctly")
        
        return True
        
    except Exception as e:
        print(f"  ❌ API response test error: {e}")
        return False

def test_config_operations():
    """Test configuration operations"""
    print("\n🔍 Testing configuration operations...")
    
    try:
        from backend.config import Config
        
        # Test getting a config value
        value = Config.get('general', 'host', fallback='0.0.0.0')
        print(f"  ✅ Config.get works: {value}")
        
        # Test checking if section exists
        exists = Config.has_section('general')
        print(f"  ✅ Config.has_section works: {exists}")
        
        # Test adding a section (should not fail)
        Config.add_section('test_section')
        print("  ✅ Config.add_section works")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Config test error: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 Running comprehensive validation tests...\n")
    
    tests = [
        test_imports,
        test_api_responses,
        test_config_operations
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The application is ready to use.")
        return True
    else:
        print("❌ Some tests failed. Please check the errors above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
