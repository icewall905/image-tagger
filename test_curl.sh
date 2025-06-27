#!/bin/bash

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

BASE_URL="http://localhost:8491"

echo -e "${GREEN}🚀 Testing Image Tagger API Endpoints${NC}"
echo "=================================================="

test_endpoint() {
    local url="$1"
    local description="$2"
    
    echo -e "\n${YELLOW}🔍 Testing $description...${NC}"
    echo "URL: $url"
    
    response=$(curl -s -w "%{http_code}" "$url")
    http_code="${response: -3}"
    body="${response%???}"
    
    echo "Status: $http_code"
    
    if [ "$http_code" = "200" ]; then
        echo -e "${GREEN}✅ Success${NC}"
        echo "Response: ${body:0:200}..."
    else
        echo -e "${RED}❌ Error${NC}"
        echo "Response: $body"
    fi
    
    echo "--------------------------------------------------"
}

# Test basic endpoints
test_endpoint "$BASE_URL/" "Root page"
test_endpoint "$BASE_URL/settings" "Settings page"
test_endpoint "$BASE_URL/folders" "Folders page"

# Test API endpoints
test_endpoint "$BASE_URL/api/settings/status" "System status"
test_endpoint "$BASE_URL/api/settings/config" "Configuration"
test_endpoint "$BASE_URL/api/folders" "Folders list"
test_endpoint "$BASE_URL/api/folders/browse" "File browser"
test_endpoint "$BASE_URL/api/folders/browse?path=/tmp" "File browser with path"

echo -e "\n${GREEN}✅ Testing complete!${NC}" 