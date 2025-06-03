"""Check for missing packages in the environment."""
import sys
import importlib

def check_import(module_name):
    print(f"Checking for {module_name}...", end=" ")
    try:
        importlib.import_module(module_name)
        print("✓")
        return True
    except ImportError as e:
        print(f"✗ ({e})")
        return False

modules_to_check = [
    "fastapi", "uvicorn", "sqlalchemy", "alembic", "pydantic", 
    "watchdog", "requests", "psutil", "PIL", "dotenv"
]

missing = []
for module in modules_to_check:
    if not check_import(module):
        missing.append(module)

if missing:
    print(f"\nMissing packages: {', '.join(missing)}")
    print("Please install them with: pip install " + " ".join(missing))
else:
    print("\nAll required packages are installed!")

# Print Python version and interpreter path
print(f"\nPython version: {sys.version}")
print(f"Python path: {sys.executable}")
