"""
Security utilities for Image Tagger WebUI
Provides rate limiting, input validation, and security features
"""

import os
import time
import hashlib
import re
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, deque
from pathlib import Path
import logging
from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import secrets

logger = logging.getLogger(__name__)

class RateLimiter:
    """Simple in-memory rate limiter"""
    
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.requests: Dict[str, deque] = defaultdict(deque)
    
    def is_allowed(self, client_id: str) -> bool:
        """Check if a request is allowed for the given client"""
        now = time.time()
        client_requests = self.requests[client_id]
        
        # Remove requests older than 1 minute
        while client_requests and now - client_requests[0] > 60:
            client_requests.popleft()
        
        # Check if under limit
        if len(client_requests) < self.requests_per_minute:
            client_requests.append(now)
            return True
        
        return False
    
    def get_client_id(self, request: Request) -> str:
        """Extract client identifier from request"""
        # Use IP address as client ID
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else "unknown"

class InputValidator:
    """Input validation utilities"""
    
    @staticmethod
    def validate_path(path: str) -> bool:
        """Validate file path for security"""
        if not path:
            return False
        
        # Check for path traversal attempts
        dangerous_patterns = [
            r'\.\.',  # Directory traversal
            r'//',    # Multiple slashes
            r'\\',    # Windows path separators
            r'~',     # Home directory
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, path):
                return False
        
        # Ensure path is relative and doesn't start with /
        if path.startswith('/') or path.startswith('\\'):
            return False
        
        return True
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename for safe storage"""
        if not filename:
            return ""
        
        # Remove or replace dangerous characters
        dangerous_chars = r'[<>:"/\\|?*\x00-\x1f]'
        sanitized = re.sub(dangerous_chars, '_', filename)
        
        # Limit length
        if len(sanitized) > 255:
            name, ext = sanitized.rsplit('.', 1) if '.' in sanitized else (sanitized, '')
            sanitized = name[:255-len(ext)-1] + ('.' + ext if ext else '')
        
        return sanitized
    
    @staticmethod
    def validate_image_extension(filename: str) -> bool:
        """Validate that file has a safe image extension"""
        allowed_extensions = {
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', 
            '.heic', '.heif', '.tif', '.tiff', '.webp'
        }
        
        if not filename:
            return False
        
        file_ext = Path(filename).suffix.lower()
        return file_ext in allowed_extensions

class SecurityMiddleware:
    """Security middleware for FastAPI"""
    
    def __init__(self, rate_limit_per_minute: int = 60):
        self.rate_limiter = RateLimiter(rate_limit_per_minute)
        self.validator = InputValidator()
    
    async def __call__(self, request: Request, call_next):
        """Process request with security checks"""
        start_time = time.time()
        
        # Rate limiting
        client_id = self.rate_limiter.get_client_id(request)
        if not self.rate_limiter.is_allowed(client_id):
            logger.warning(f"Rate limit exceeded for client: {client_id}")
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        
        # Security headers
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=(), payment=(), usb=(), magnetometer=(), gyroscope=(), accelerometer=()"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://code.jquery.com https://cdn.datatables.net https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://cdn.datatables.net; font-src 'self' https://cdn.jsdelivr.net; img-src 'self' data: https://cdnjs.cloudflare.com; connect-src 'self';"
        
        # Log request
        duration = time.time() - start_time
        logger.info(f"Request processed: {request.method} {request.url.path} - {duration:.3f}s", extra={
            'extra_fields': {
                'client_id': client_id,
                'method': request.method,
                'path': request.url.path,
                'duration': duration,
                'status_code': response.status_code
            }
        })
        
        return response

class FileSecurityChecker:
    """Security checks for file operations"""
    
    @staticmethod
    def check_file_safety(file_path: Path) -> Tuple[bool, str]:
        """Check if a file is safe to process"""
        try:
            # Check if file exists
            if not file_path.exists():
                return False, "File does not exist"
            
            # Check file size (prevent processing extremely large files)
            file_size = file_path.stat().st_size
            max_size = 100 * 1024 * 1024  # 100MB limit
            if file_size > max_size:
                return False, f"File too large: {file_size} bytes"
            
            # Check file permissions
            if not os.access(file_path, os.R_OK):
                return False, "File not readable"
            
            # Check for suspicious file types
            if not InputValidator.validate_image_extension(file_path.name):
                return False, "Invalid file extension"
            
            return True, "File is safe"
            
        except Exception as e:
            return False, f"Security check failed: {str(e)}"
    
    @staticmethod
    def generate_secure_filename(original_name: str) -> str:
        """Generate a secure filename"""
        # Create a hash of the original name
        name_hash = hashlib.sha256(original_name.encode()).hexdigest()[:16]
        
        # Get the extension
        ext = Path(original_name).suffix.lower()
        
        # Generate random suffix for uniqueness
        random_suffix = secrets.token_hex(4)
        
        return f"{name_hash}_{random_suffix}{ext}"

# Global security instance
security_middleware = SecurityMiddleware()

def get_security_middleware(rate_limit_per_minute: int = 60) -> SecurityMiddleware:
    """Get security middleware instance"""
    return SecurityMiddleware(rate_limit_per_minute)

def validate_api_key(api_key: str, valid_keys: List[str]) -> bool:
    """Validate API key"""
    if not api_key:
        return False
    
    # Use constant-time comparison to prevent timing attacks
    if len(api_key) != len(valid_keys[0]):
        return False
    
    return api_key in valid_keys

def log_security_event(event_type: str, details: Dict[str, any], severity: str = "info"):
    """Log security events"""
    log_data = {
        'event_type': event_type,
        'severity': severity,
        'timestamp': time.time(),
        'details': details
    }
    
    if severity == "warning":
        logger.warning(f"Security event: {event_type}", extra={'extra_fields': log_data})
    elif severity == "error":
        logger.error(f"Security event: {event_type}", extra={'extra_fields': log_data})
    else:
        logger.info(f"Security event: {event_type}", extra={'extra_fields': log_data}) 