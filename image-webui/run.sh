#!/bin/bash

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Image Tagger WebUI...${NC}"

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is required but not installed.${NC}"
    exit 1
fi

# Check if the virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv || { echo -e "${RED}Failed to create virtual environment.${NC}"; exit 1; }
fi

# Activate the virtual environment
echo -e "${GREEN}Activating virtual environment...${NC}"
source venv/bin/activate || { echo -e "${RED}Failed to activate virtual environment.${NC}"; exit 1; }

# Install dependencies if needed
if [ ! -f "venv/.dependencies_installed" ]; then
    echo -e "${YELLOW}Installing dependencies...${NC}"
    pip install -r requirements.txt || { echo -e "${RED}Failed to install dependencies.${NC}"; exit 1; }
    touch venv/.dependencies_installed
fi

# Create necessary directories
mkdir -p data
mkdir -p data/thumbnails

# Make setup_db.sh executable
chmod +x setup_db.sh

# Set environment variables (only if not already set)
export HOST=${HOST:-"0.0.0.0"}
export PORT=${PORT:-"8000"}
export DB_PATH=${DB_PATH:-"sqlite:///data/image_tagger.db"}
# Note: OLLAMA_SERVER and OLLAMA_MODEL should be configured in config.ini
# Only set them here if they're not already set and you want to override config
# export OLLAMA_SERVER=${OLLAMA_SERVER:-"http://127.0.0.1:11434"}
# export OLLAMA_MODEL=${OLLAMA_MODEL:-"qwen2.5vl:latest"}

# Run database migrations if needed
if [ ! -f "data/.db_initialized" ]; then
    echo -e "${YELLOW}Setting up database with migrations...${NC}"
    ./setup_db.sh
    touch data/.db_initialized
fi

# Run the application
echo -e "${GREEN}Running Image Tagger WebUI on http://${HOST}:${PORT}${NC}"
python -m uvicorn backend.app:app --host $HOST --port $PORT --reload

# Deactivate the virtual environment on exit
deactivate
