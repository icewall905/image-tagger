#!/bin/bash

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}       Image Tagger Launcher          ${NC}"
echo -e "${BLUE}=======================================${NC}"

# Check current directory
if [[ ! -f "image-tagger-install.sh" && ! -d "image-webui" ]]; then
    echo -e "${RED}Error: Please run this script from the image-tagger directory.${NC}"
    exit 1
fi

# Function to display menu
show_menu() {
    echo -e "\n${GREEN}Please select an option:${NC}"
    echo -e "1. ${YELLOW}Launch CLI Image Tagger${NC}"
    echo -e "2. ${YELLOW}Launch Web UI${NC}"
    echo -e "3. ${YELLOW}Exit${NC}"
    echo -e "\nEnter your choice [1-3]: "
}

# Launch CLI version
launch_cli() {
    echo -e "\n${GREEN}Launching CLI Image Tagger...${NC}"
    # Run the original installer script
    bash image-tagger-install.sh
}

# Launch Web UI
launch_webui() {
    echo -e "\n${GREEN}Launching Image Tagger Web UI...${NC}"
    
    # Check if the Web UI directory exists
    if [[ ! -d "image-webui" ]]; then
        echo -e "${RED}Error: Web UI directory not found. Please ensure the image-webui directory exists.${NC}"
        return
    fi
    
    # Change to the Web UI directory and run it
    cd image-webui
    
    if [[ -f "run.sh" ]]; then
        bash run.sh
    else
        echo -e "${RED}Error: run.sh script not found in the image-webui directory.${NC}"
    fi
    
    # Change back to the original directory
    cd ..
}

# Main loop
while true; do
    show_menu
    read -r choice
    
    case $choice in
        1)
            launch_cli
            ;;
        2)
            launch_webui
            ;;
        3)
            echo -e "\n${GREEN}Exiting. Goodbye!${NC}"
            exit 0
            ;;
        *)
            echo -e "\n${RED}Invalid option. Please try again.${NC}"
            ;;
    esac
    
    # Ask to continue
    echo -e "\n${YELLOW}Press Enter to return to the menu or Ctrl+C to exit...${NC}"
    read -r
done
