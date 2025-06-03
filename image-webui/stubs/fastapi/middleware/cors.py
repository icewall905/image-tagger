# Type stubs for FastAPI middleware.cors
from typing import Any, Callable, Dict, List, Optional, Union

class CORSMiddleware:
    def __init__(self, app: Any, allow_origins: Optional[List[str]] = None, 
                allow_methods: Optional[List[str]] = None, 
                allow_headers: Optional[List[str]] = None, 
                allow_credentials: bool = False, 
                expose_headers: Optional[List[str]] = None, 
                max_age: int = 600): ...