from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional, Union

# Configuration schemas
class ConfigUpdateRequest(BaseModel):
    config: Dict[str, Dict[str, Any]] = Field(
        ..., description="Configuration data organized by section and key"
    )

class ConfigResponse(BaseModel):
    message: str = Field(..., description="Response message")
    config: Dict[str, Dict[str, Any]] = Field(
        ..., description="Configuration data organized by section and key"
    )

class MessageResponse(BaseModel):
    message: str

class OllamaTestConfig(BaseModel):
    server: str = Field(..., description="Ollama server URL")
    model: str = Field(..., description="Ollama model to test")

class Tag(BaseModel):
    id: int
    name: str
    
    class Config:
        from_attributes = True

class TagCreate(BaseModel):
    name: str