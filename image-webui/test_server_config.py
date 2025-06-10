#!/usr/bin/env python3
"""
Test script to verify server configuration is working correctly
"""

import logging
logging.basicConfig(level=logging.INFO)

def test_config_loading():
    """Test the configuration loading process"""
    print("=== Testing Configuration Loading ===")
    
    # Test 1: Direct Config class access
    from backend.config import Config
    server = Config.get('ollama', 'server')
    model = Config.get('ollama', 'model')
    print(f"Config class: server={server}, model={model}")
    
    # Test 2: Core module config loading
    from backend.image_tagger.core import load_config
    config = load_config()
    print(f"Core config: server={config.get('server')}, model={config.get('model')}")
    
    # Test 3: Settings API logic simulation
    import os
    server = Config.get('ollama', 'server', fallback="http://127.0.0.1:11434")
    model = Config.get('ollama', 'model', fallback="qwen2.5vl:latest")
    
    print(f"Settings API initial: server={server}, model={model}")
    
    if 'OLLAMA_SERVER' in os.environ:
        server = os.environ["OLLAMA_SERVER"]
        print(f"Settings API env override: server={server}")
    
    if 'OLLAMA_MODEL' in os.environ:
        model = os.environ["OLLAMA_MODEL"]
        print(f"Settings API env override: model={model}")
    
    # Ensure server and model are not None
    if not server:
        server = "http://127.0.0.1:11434"
        print(f"Settings API fallback: server={server}")
    
    if not model:
        model = "qwen2.5vl:latest"
        print(f"Settings API fallback: model={model}")
    
    print(f"Final values: server={server}, model={model}")
    
    return server, model

def test_task_call():
    """Test how the task functions receive the server config"""
    print("\n=== Testing Task Function Call ===")
    
    server, model = test_config_loading()
    
    # Simulate calling process_images_with_ai
    print(f"Would call process_images_with_ai with server={server}, model={model}")
    
    # Simulate calling the core process_image function
    print(f"Would call tagger.process_image with server={server}, model={model}")

if __name__ == "__main__":
    test_task_call()
