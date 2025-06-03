# Type stubs for FastAPI responses
from typing import Any, Dict, Optional, Union

class FileResponse:
    def __init__(self, path: str, **kwargs): ...

class HTMLResponse:
    def __init__(self, content: Any, status_code: int = 200, 
                headers: Optional[Dict[str, str]] = None, 
                media_type: Optional[str] = None): ...