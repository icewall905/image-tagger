#!/usr/bin/env python3
"""
Simple test script to check Config.get() behavior
"""

import os
import sys
sys.path.append('.')

def test_config_behavior():
    """Test the exact behavior we see in folders.py"""
    print("=== Testing Config.get() Behavior ===")
    
    try:
        from backend.config import Config
    except Exception as e:
        print(f"Error importing Config: {e}")
        return
    
    # Test 1: Direct Config.get() calls
    server = Config.get('ollama', 'server')
    model = Config.get('ollama', 'model')
    print(f"Direct Config.get(): server={repr(server)}, model={repr(model)}")
    
    # Test 2: Config.get() with fallback (current folders.py pattern)
    server_with_fallback = Config.get('ollama', 'server', fallback="http://127.0.0.1:11434")
    model_with_fallback = Config.get('ollama', 'model', fallback="qwen2.5vl:latest")
    print(f"With fallback: server={repr(server_with_fallback)}, model={repr(model_with_fallback)}")
    
    # Test 3: Check if values are truthy
    print(f"Server truthy check: bool({repr(server)}) = {bool(server)}")
    print(f"Model truthy check: bool({repr(model)}) = {bool(model)}")
    
    # Test 4: Simulate the exact folders.py logic
    print("\n=== Simulating folders.py Logic ===")
    
    # Step 1: Get from config with fallback
    ollama_server_val = Config.get('ollama', 'server', fallback="http://127.0.0.1:11434")
    ollama_model_val = Config.get('ollama', 'model', fallback="qwen2.5vl:latest")
    print(f"Step 1 - Config with fallback: server={ollama_server_val}, model={ollama_model_val}")
    
    # Step 2: Environment override
    if 'OLLAMA_SERVER' in os.environ:
        ollama_server_val = os.environ["OLLAMA_SERVER"]
        print(f"Step 2 - Env override: server={ollama_server_val}")
    
    if 'OLLAMA_MODEL' in os.environ:
        ollama_model_val = os.environ["OLLAMA_MODEL"]
        print(f"Step 2 - Env override: model={ollama_model_val}")
    
    print(f"Final result: server={ollama_server_val}, model={ollama_model_val}")
    
    # Test 5: Test improved logic
    print("\n=== Testing Improved Logic ===")
    
    # Get from config first (no fallback)
    server_from_config = Config.get('ollama', 'server')
    model_from_config = Config.get('ollama', 'model')
    
    # Apply defaults only if config values are None or empty
    improved_server = server_from_config if server_from_config else "http://127.0.0.1:11434"
    improved_model = model_from_config if model_from_config else "qwen2.5vl:latest"
    
    # Environment override
    if 'OLLAMA_SERVER' in os.environ:
        improved_server = os.environ["OLLAMA_SERVER"]
    if 'OLLAMA_MODEL' in os.environ:
        improved_model = os.environ["OLLAMA_MODEL"]
    
    print(f"Improved result: server={improved_server}, model={improved_model}")

if __name__ == "__main__":
    test_config_behavior()
