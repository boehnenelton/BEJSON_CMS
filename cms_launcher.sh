#!/usr/bin/env bash
# ==============================================================================
# BEJSON CMS: MODULAR LAUNCHER
# PURPOSE: Ensure only ONE service runs at a time for maximum RAM efficiency.
# ==============================================================================

get_script_path() {
    local source="${BASH_SOURCE[0]}"
    while [ -h "$source" ]; do
        local dir="$( cd -P "$( dirname "$source" )" >/dev/null 2>&1 && pwd )"
        source="$(readlink "$source")"
        [[ $source != /* ]] && source="$dir/$source"
    done
    echo "$( cd -P "$( dirname "$source" )" >/dev/null 2>&1 && pwd )"
}
SCRIPT_PATH=$(get_script_path)
WEB_DIR="$SCRIPT_PATH/src/web"
LOG_DIR="$SCRIPT_PATH/storage/tmp/logs"
mkdir -p "$LOG_DIR"

# Colors
C_RED='\033[1;31m'
C_GREEN='\033[1;32m'
C_CYAN='\033[1;36m'
C_YELLOW='\033[1;33m'
C_RESET='\033[0m'

function kill_services() {
    echo -e "${C_CYAN}[System] Stopping all active CMS services to free RAM...${C_RESET}"
    pkill -f "Flask_CMS.py" 2>/dev/null
    pkill -f "Flask_Page_Editor.py" 2>/dev/null
    pkill -f "Flask_CMS_Publisher.py" 2>/dev/null
    pkill -f "Flask_Profile_Manager.py" 2>/dev/null
    pkill -f "Page_Editor_v2.py" 2>/dev/null
    sleep 1
}

function launch_service() {
    local script_name=$1
    local port=$2
    local log_file="$LOG_DIR/${script_name}.log"

    # 1. Kill everything else first
    kill_services

    # 2. Launch the requested service
    echo -e "${C_GREEN}[System] Bootstrapping $script_name on port $port...${C_RESET}"
    echo -e "${C_YELLOW}[System] Logging output to: $log_file${C_RESET}"
    echo "--------------------------------------------------------"

    # Run the script, capturing output to the terminal AND saving it to the log file
    python3 "$WEB_DIR/$script_name" 2>&1 | tee "$log_file"

    # Capture the exit code of the python script (not the tee command)
    local exit_code=${PIPESTATUS[0]}

    echo "--------------------------------------------------------"
    if [ $exit_code -ne 0 ]; then
        echo -e "${C_RED}[CRITICAL] $script_name crashed with exit code $exit_code!${C_RESET}"
        echo -e "${C_YELLOW}Review the traceback above. A full log has been saved to: $log_file${C_RESET}"
    else
        echo -e "${C_CYAN}[System] Service stopped normally.${C_RESET}"
    fi

    # 3. Force the menu to wait so you can actually read the error
    echo ""
    read -p "Press [Enter] to return to the menu..."
}

while true; do
    clear
    echo "========================================================"
    echo -e " ${C_RED}BEJSON ECOSYSTEM: MODULAR CMS LAUNCHER${C_RESET}"
    echo "========================================================"
    echo " RAM-Optimized Mode: Only ONE service runs at a time."
    echo ""
    echo "  1) Launch CMS Manager (Dashboard)       [Port 5001]"
    echo "  2) Launch Page Editor                   [Port 5003]"
    echo "  3) Launch Page Editor v2 (Ultimate)     [Port 5010]"
    echo "  4) Launch Static Site Publisher         [Port 5001]"
    echo "  5) Launch Persona Hub (Profile Manager) [Port 5004]"
    echo ""
    echo "  6) Stop All Services & Exit"
    echo "========================================================"
    read -p " Select an option (1-6): " choice

    case $choice in
        1) launch_service "Flask_CMS.py" "5001" ;;
        2) launch_service "Flask_Page_Editor.py" "5003" ;;
        3) launch_service "Page_Editor_v2.py" "5010" ;;
        4) launch_service "Flask_CMS_Publisher.py" "5001" ;;
        5) launch_service "Flask_Profile_Manager.py" "5004" ;;
        6)
            kill_services
            echo -e "${C_GREEN}[System] All CMS services stopped. Exiting.${C_RESET}"
            exit 0
            ;;
        *)
            echo -e "${C_RED}[Error] Invalid selection. Please choose 1-6.${C_RESET}"
            sleep 2
            ;;
    esac
done
