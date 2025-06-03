#!/usr/bin/env python3
"""
Test script to diagnose Ollama timeout issues
"""

import requests
import time
import base64
from pathlib import Path
import json

def test_ollama_connection():
    """Test basic Ollama connection"""
    print("Testing Ollama connection...")
    
    try:
        response = requests.get("http://127.0.0.1:11434/api/tags", timeout=30)
        if response.status_code == 200:
            print("✓ Ollama server is responding")
            models = response.json()
            print(f"Available models: {[m['name'] for m in models['models']]}")
            return True
        else:
            print(f"✗ Ollama server returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Failed to connect to Ollama: {e}")
        return False

def test_text_generation(model="llama3.2:latest"):
    """Test basic text generation"""
    print(f"\nTesting text generation with {model}...")
    
    try:
        payload = {
            "model": model,
            "prompt": "Hello, please respond with just 'Hello back!'",
            "stream": False
        }
        
        start_time = time.time()
        response = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json=payload,
            timeout=120
        )
        end_time = time.time()
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ Text generation successful in {end_time - start_time:.2f}s")
            print(f"Response: {result.get('response', '')[:100]}...")
            return True
        else:
            print(f"✗ Text generation failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"✗ Text generation error: {e}")
        return False

def test_vision_model(model="llama3.2-vision:latest"):
    """Test vision model with a simple test image"""
    print(f"\nTesting vision model {model}...")
    
    # Create a simple test image (1x1 pixel PNG)
    test_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChAGA0qCOkQAAAABJRU5ErkJggg=="
    
    try:
        payload = {
            "model": model,
            "prompt": "What do you see in this image?",
            "stream": False,
            "images": [test_image_b64]
        }
        
        start_time = time.time()
        response = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json=payload,
            timeout=300  # 5 minutes for vision
        )
        end_time = time.time()
        
        if response.status_code == 200:
            result = response.json()
            print(f"✓ Vision model successful in {end_time - start_time:.2f}s")
            print(f"Response: {result.get('response', '')[:200]}...")
            return True
        else:
            print(f"✗ Vision model failed: {response.status_code}")
            print(f"Response: {response.text[:300]}...")
            return False
            
    except requests.exceptions.Timeout:
        print(f"✗ Vision model timed out after {time.time() - start_time:.2f}s")
        return False
    except Exception as e:
        print(f"✗ Vision model error: {e}")
        return False

def test_system_resources():
    """Check system resources"""
    print("\nChecking system resources...")
    
    try:
        import psutil
        
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        print(f"CPU usage: {cpu_percent}%")
        
        # Memory usage
        memory = psutil.virtual_memory()
        print(f"Memory usage: {memory.percent}% ({memory.used / 1024**3:.1f}GB / {memory.total / 1024**3:.1f}GB)")
        
        # GPU info (if nvidia-smi is available)
        try:
            import subprocess
            result = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total', '--format=csv,noheader,nounits'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                gpu_info = result.stdout.strip().split('\n')[0].split(', ')
                print(f"GPU usage: {gpu_info[0]}%, Memory: {gpu_info[1]}MB / {gpu_info[2]}MB")
            else:
                print("No NVIDIA GPU detected")
        except:
            print("Unable to check GPU status")
            
    except ImportError:
        print("psutil not available - install with: pip install psutil")
    except Exception as e:
        print(f"Error checking resources: {e}")

if __name__ == "__main__":
    print("Ollama Diagnostics Tool")
    print("=" * 50)
    
    # Test connection
    if not test_ollama_connection():
        exit(1)
    
    # Test system resources
    test_system_resources()
    
    # Test text generation first
    if not test_text_generation():
        print("Text generation failed - skipping vision test")
        exit(1)
    
    # Test vision model
    test_vision_model()
    
    print("\nTest completed!")
