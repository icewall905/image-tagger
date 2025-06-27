#!/usr/bin/env python3
"""
Generate type stubs for the project.
This script helps resolve import errors by creating stub files for 
imported packages that might not be available during development.
"""

import os
import sys
import subprocess
import shutil
import json
from pathlib import Path

# Get the current directory
current_dir = Path(__file__).parent.absolute()
stubs_dir = current_dir / "stubs"

def ensure_dir(path):
    """Ensure directory exists"""
    os.makedirs(path, exist_ok=True)

def create_stub_file(module_path, content):
    """Create a stub file"""
    ensure_dir(os.path.dirname(module_path))
    with open(module_path, 'w') as f:
        f.write(content)
    print(f"Created stub file: {module_path}")

def main():
    """Main function to generate stubs"""
    print("Generating type stubs for the project...")
    
    # Ensure stubs directory exists
    ensure_dir(stubs_dir)
    
    # Create __init__.py in stubs directory
    create_stub_file(stubs_dir / "__init__.py", "# Type stubs package")
    
    # Create stub directories and files for common packages
    packages = [
        "fastapi",
        "fastapi/middleware",
        "fastapi/middleware/cors",
        "fastapi/responses",
        "fastapi/staticfiles",
        "fastapi/templating",
        "uvicorn",
        "sqlalchemy",
        "sqlalchemy/orm",
        "watchdog",
        "watchdog/observers",
        "watchdog/events",
    ]
    
    for package in packages:
        package_path = stubs_dir / package
        ensure_dir(package_path)
        init_file = package_path / "__init__.py"
        if not init_file.exists():
            create_stub_file(init_file, f"# Type stubs for {package}")
    
    # Create specific stub files
    stubs = {
        "fastapi/__init__.py": """# Type stubs for FastAPI
from typing import Any, Callable, Dict, List, Optional, Type, Union

class FastAPI:
    def __init__(self, **kwargs): ...
    def get(self, path: str, **kwargs) -> Callable[[Callable], Callable]: ...
    def post(self, path: str, **kwargs) -> Callable[[Callable], Callable]: ...
    def put(self, path: str, **kwargs) -> Callable[[Callable], Callable]: ...
    def delete(self, path: str, **kwargs) -> Callable[[Callable], Callable]: ...
    def mount(self, path: str, app: Any, name: Optional[str] = None) -> None: ...
    def add_middleware(self, middleware_class: Type[Any], **kwargs: Any) -> None: ...
    def include_router(self, router: Any, **kwargs: Any) -> None: ...
    def on_event(self, event_type: str) -> Callable[[Callable], Callable]: ...

class HTTPException(Exception):
    def __init__(self, status_code: int, detail: Any = None, headers: Optional[Dict[str, Any]] = None): ...

class Request:
    pass

class Depends:
    def __init__(self, dependency: Optional[Callable[..., Any]] = None): ...

class APIRouter:
    def __init__(self, **kwargs: Any): ...
    def get(self, path: str, **kwargs) -> Callable[[Callable], Callable]: ...
    def post(self, path: str, **kwargs) -> Callable[[Callable], Callable]: ...
    def put(self, path: str, **kwargs) -> Callable[[Callable], Callable]: ...
    def delete(self, path: str, **kwargs) -> Callable[[Callable], Callable]: ...""",
        
        "fastapi/middleware/__init__.py": """# Type stubs for FastAPI middleware
# This file re-exports modules to match FastAPI's structure

# Import cors module to make it available as fastapi.middleware.cors
from . import cors""",
        
        "fastapi/middleware/cors.py": """# Type stubs for FastAPI middleware.cors
from typing import Any, Callable, Dict, List, Optional, Union

class CORSMiddleware:
    def __init__(self, app: Any, allow_origins: List[str] = None, 
                allow_methods: List[str] = None, 
                allow_headers: List[str] = None, 
                allow_credentials: bool = False, 
                expose_headers: List[str] = None, 
                max_age: int = 600): ...""",
        
        "fastapi/staticfiles.py": """# Type stubs for FastAPI staticfiles
from typing import Any, Optional

class StaticFiles:
    def __init__(self, directory: Optional[str] = None, html: bool = False): ...""",
        
        "fastapi/templating.py": """# Type stubs for FastAPI templating
from typing import Any, Dict, Optional

class Jinja2Templates:
    def __init__(self, directory: str): ...
    def TemplateResponse(self, name: str, context: Dict[str, Any], 
                       status_code: int = 200, 
                       headers: Optional[Dict[str, str]] = None, 
                       media_type: Optional[str] = None, 
                       background: Optional[Any] = None): ...""",
        
        "fastapi/responses.py": """# Type stubs for FastAPI responses
from typing import Any, Dict, Optional, Union

class FileResponse:
    def __init__(self, path: str, **kwargs): ...

class HTMLResponse:
    def __init__(self, content: Any, status_code: int = 200, 
                headers: Optional[Dict[str, str]] = None, 
                media_type: Optional[str] = None): ...""",
        
        "uvicorn.pyi": """from typing import Any, Callable, List, Optional, Union

def run(app: Any, host: str = "127.0.0.1", port: int = 8491, 
       debug: bool = False, reload: bool = False, 
       workers: int = 1, **kwargs: Any) -> None: ...

class Config:
    app: Any
    host: str
    port: int
    reload: bool
    workers: int
    log_level: str
    access_log: bool
    proxy_headers: bool
    forwarded_allow_ips: Optional[str]
    root_path: str
    limit_concurrency: Optional[int]
    limit_max_requests: Optional[int]
    timeout_keep_alive: int
    
    def __init__(self, app: Any, **kwargs: Any): ...""",
        
        "sqlalchemy/__init__.py": """# Type stubs for SQLAlchemy
from typing import Any, Optional, Type, TypeVar, Generic, Union

T = TypeVar('T')

def create_engine(url: str, **kwargs: Any): ...

class Column:
    def __init__(self, type_: Any, *args: Any, **kwargs: Any): ...

class Integer:
    def __init__(self, *args: Any, **kwargs: Any): ...

class String:
    def __init__(self, length: int = 255, *args: Any, **kwargs: Any): ...

class Boolean:
    def __init__(self, *args: Any, **kwargs: Any): ...

class DateTime:
    def __init__(self, *args: Any, **kwargs: Any): ...

class Float:
    def __init__(self, *args: Any, **kwargs: Any): ...

class ForeignKey:
    def __init__(self, column: str, *args: Any, **kwargs: Any): ...

class Table:
    def __init__(self, name: str, metadata: Any, *args: Any, **kwargs: Any): ...

class MetaData:
    def __init__(self, *args: Any, **kwargs: Any): ...
    def create_all(self, bind: Any, **kwargs: Any) -> None: ...""",
        
        "sqlalchemy/orm.py": """from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, Union, Generic, Iterator

T = TypeVar('T')

def relationship(argument: Any, **kwargs: Any): ...

def sessionmaker(bind: Any = None, **kwargs: Any): ...

def declarative_base(**kwargs: Any): ...

class Session:
    def __init__(self, **kwargs: Any): ...
    def add(self, instance: Any) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...
    def query(self, *entities: Any, **kwargs: Any) -> "Query": ...
    def __enter__(self) -> "Session": ...
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None: ...

class Query(Generic[T]):
    def filter(self, *criterion: Any) -> "Query[T]": ...
    def filter_by(self, **kwargs: Any) -> "Query[T]": ...
    def all(self) -> List[T]: ...
    def first(self) -> Optional[T]: ...
    def one(self) -> T: ...
    def one_or_none(self) -> Optional[T]: ...
    def count(self) -> int: ...
    def delete(self) -> int: ...
    def order_by(self, *criterion: Any) -> "Query[T]": ...
    def limit(self, limit: int) -> "Query[T]": ...
    def offset(self, offset: int) -> "Query[T]": ...
    def __iter__(self) -> Iterator[T]: ...""",
        
        "watchdog/__init__.py": """# Type stubs for watchdog""",
        
        "watchdog/observers.py": """from typing import Any, Callable, List, Optional, Union
from pathlib import Path

class Observer:
    def __init__(self): ...
    def schedule(self, event_handler, path: Union[str, Path], recursive: bool = False) -> Any: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def join(self, timeout: Optional[float] = None) -> None: ...
    def is_alive(self) -> bool: ...""",
        
        "watchdog/events.py": """from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type, TypeVar, Union, Generic

class FileSystemEvent:
    is_directory: bool
    src_path: str
    
    def __init__(self, src_path: str, is_directory: bool = False): ...

class FileSystemMovedEvent(FileSystemEvent):
    dest_path: str
    
    def __init__(self, src_path: str, dest_path: str, is_directory: bool = False): ...

class FileCreatedEvent(FileSystemEvent): ...
class FileDeletedEvent(FileSystemEvent): ...
class FileModifiedEvent(FileSystemEvent): ...

class FileSystemEventHandler:
    def __init__(self): ...
    def on_moved(self, event: FileSystemMovedEvent) -> None: ...
    def on_created(self, event: FileCreatedEvent) -> None: ...
    def on_deleted(self, event: FileDeletedEvent) -> None: ...
    def on_modified(self, event: FileModifiedEvent) -> None: ...
    def dispatch(self, event: FileSystemEvent) -> None: ...""",
    }
    
    for path, content in stubs.items():
        file_path = stubs_dir / path
        create_stub_file(file_path, content)
    
    # Create or update pyrightconfig.json
    pyright_config = current_dir / "pyrightconfig.json"
    config_content = {
        "include": ["backend", "migrations"],
        "exclude": ["**/__pycache__", "**/node_modules", ".git", "venv"],
        "reportMissingImports": "warning",
        "reportMissingTypeStubs": "none",
        "pythonVersion": "3.10",
        "pythonPlatform": "All",
        "venvPath": ".",
        "venv": "venv",
        "typeCheckingMode": "basic",
        "useLibraryCodeForTypes": True,
        "reportOptionalMemberAccess": "warning",
        "reportPrivateUsage": "warning",
        "reportUnknownParameterType": "none",
        "reportUnknownArgumentType": "none",
        "reportUnknownMemberType": "none",
        "reportUnknownVariableType": "none",
        "reportUntypedBaseClass": "none",
        "reportUnusedFunction": "none",
        "reportUntypedFunctionDecorator": "none",
        "reportMissingParameterType": "none",
        "reportAttributeAccessIssue": "none",
        "stubPath": "stubs",
        "extraPaths": [".", "./stubs"]
    }
    
    with open(pyright_config, 'w') as f:
        json.dump(config_content, f, indent=2)
    
    print(f"Updated {pyright_config}")
    
    # Update VS Code settings
    vscode_dir = current_dir / ".vscode"
    ensure_dir(vscode_dir)
    
    settings_file = vscode_dir / "settings.json"
    settings = {}
    if settings_file.exists():
        try:
            with open(settings_file, 'r') as f:
                settings = json.load(f)
        except json.JSONDecodeError:
            print("Error reading settings.json, creating a new one")
    
    # Add Python-specific settings
    settings.update({
        "python.analysis.extraPaths": ["./stubs"],
        "python.analysis.typeCheckingMode": "basic",
        "python.linting.enabled": True,
        "python.linting.pylintEnabled": False,
        "python.linting.flake8Enabled": True,
        "python.linting.mypyEnabled": False,
        "python.analysis.diagnosticMode": "workspace",
        "python.analysis.stubPath": "./stubs",
        "python.analysis.useLibraryCodeForTypes": True,
    })
    
    with open(settings_file, 'w') as f:
        json.dump(settings, f, indent=2)
    
    print(f"Updated {settings_file}")
    
    print("\nStub generation complete!")
    print("Restart VS Code for the changes to take effect.")
    print("If import errors persist, you may need to reload the VS Code window.")

if __name__ == "__main__":
    main()
