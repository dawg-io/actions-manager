#!/bin/bash


################################################################################
# ActionsManager Self-Hosted Installation Script
# 
# IMPORTANT: This script requires Docker or Podman to be installed.
# Docker/Podman is the ONLY supported installation method for end users.
#
# This script automates the setup of a self-hosted ActionsManager.io instance.
# It will:
# - Check for Docker/Podman availability (required)
# - Prompt for GitHub OAuth credentials and license key
# - Generate secure SECRET_KEY
# - Create .env.self-hosted configuration file
# - Build and start the Docker containers
# - Display installation status and troubleshooting tips
#
# Usage: ./install.sh
#
# For more information, visit: https://github.com/dawg-io/actions-manager
################################################################################

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Default values
DEFAULT_PORT=8080
DOCKER_COMPOSE_FILE="docker-compose.self-hosted.yml"
DOCKER_COMPOSE_DEV_OVERLAY="docker-compose.self-hosted.dev.yml"

# Image flow:
#   * Default: pull the official pre-built image from GHCR
#   * --build: build locally from Dockerfile.self-hosted (contributors only)
BUILD_FROM_SOURCE=false

# Allow contributors / advanced operators to opt into local builds.
for arg in "$@"; do
    case "$arg" in
        --build|--from-source)
            BUILD_FROM_SOURCE=true
            ;;
        --help|-h)
            cat <<'USAGE'
Usage: ./install.sh [--build]

Options:
  --build, --from-source   Build the self-hosted image locally from
                           Dockerfile.self-hosted instead of pulling the
                           pre-built image from GitHub Container Registry.
                           Intended for contributors and development use.
  -h, --help               Show this help and exit.

By default the installer pulls the official self-hosted image:
  ghcr.io/dawg-io/actions-manager:latest

Override the tag via the ACTIONS_MANAGER_TAG environment variable, or
override the full image reference via ACTIONS_MANAGER_IMAGE.
USAGE
            exit 0
            ;;
    esac
done

################################################################################
# Helper Functions
################################################################################

print_header() {
    echo ""
    echo -e "${BOLD}${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${CYAN}║                                                                ║${NC}"
    echo -e "${BOLD}${CYAN}║        ActionsManager.io Self-Hosted Installer                ║${NC}"
    echo -e "${BOLD}${CYAN}║                                                                ║${NC}"
    echo -e "${BOLD}${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_step() {
    echo -e "${BOLD}${BLUE}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ $1${NC}"
}

prompt_input() {
    local prompt="$1"
    local var_name="$2"
    local default="$3"
    local secure="$4"
    
    if [ -n "$default" ]; then
        prompt="$prompt [default: $default]"
    fi
    
    if [ "$secure" = "true" ]; then
        read -sp "$prompt: " value
        echo ""
    else
        read -p "$prompt: " value
    fi
    
    if [ -z "$value" ] && [ -n "$default" ]; then
        value="$default"
    fi
    
    eval "$var_name='$value'"
}

generate_secret_key() {
    # Generate a 32-character random secret key
    if command -v openssl &> /dev/null; then
        openssl rand -hex 32
    elif command -v python3 &> /dev/null; then
        python3 -c "import secrets; print(secrets.token_hex(32))"
    else
        # Fallback to /dev/urandom
        cat /dev/urandom | LC_ALL=C tr -dc 'a-zA-Z0-9' | fold -w 64 | head -n 1
    fi
}

detect_server_ip() {
    # Try to find the primary non-loopback IP address of this machine.
    # Returns an empty string if detection fails.
    local ip=""
    # Linux: hostname -I returns all addresses; take the first
    if command -v hostname &> /dev/null; then
        ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    fi
    # Fallback: use 'ip route' to find the address used for outbound traffic
    if [ -z "$ip" ] && command -v ip &> /dev/null; then
        ip=$(ip route get 1 2>/dev/null | awk '/src/ {for(i=1;i<=NF;i++) if($i=="src") print $(i+1); exit}')
    fi
    # macOS: use ifconfig to find the first en* interface with an inet address
    if [ -z "$ip" ] && command -v ifconfig &> /dev/null; then
        ip=$(ifconfig 2>/dev/null | awk '/inet / && !/127\.0\.0\.1/ {print $2; exit}')
    fi
    echo "$ip"
}

check_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
        print_success "Detected Linux operating system"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
        print_success "Detected macOS operating system"
    else
        print_error "Unsupported operating system: $OSTYPE"
        print_info "This script supports Linux and macOS only"
        exit 1
    fi
}

check_docker() {
    print_step "Checking for Docker/Podman..."
    
    if command -v docker &> /dev/null && docker ps &> /dev/null 2>&1; then
        CONTAINER_CMD="docker"
        COMPOSE_CMD="docker compose"
        print_success "Docker found and running"
        return 0
    elif command -v podman &> /dev/null; then
        CONTAINER_CMD="podman"
        COMPOSE_CMD="podman-compose"
        print_success "Podman found"
        
        # Check if podman-compose is installed
        if ! command -v podman-compose &> /dev/null; then
            print_error "podman-compose not found"
            print_info "Install with: pip install podman-compose"
            exit 1
        fi
        return 0
    else
        print_error "Neither Docker nor Podman found"
        echo ""
        print_info "Please install Docker or Podman:"
        echo "  Docker: https://docs.docker.com/get-docker/"
        echo "  Podman: https://podman.io/getting-started/installation"
        exit 1
    fi
}

check_dependencies() {
    print_step "Checking system dependencies..."
    
    local missing_deps=()
    
    # Check for curl (used for health checks)
    if ! command -v curl &> /dev/null; then
        missing_deps+=("curl")
    fi
    
    # Check for git (useful but not required)
    if ! command -v git &> /dev/null; then
        print_warning "git not found (recommended but not required)"
    fi
    
    if [ ${#missing_deps[@]} -gt 0 ]; then
        print_error "Missing required dependencies: ${missing_deps[*]}"
        print_info "Please install the missing dependencies and try again"
        exit 1
    fi
    
    print_success "All required dependencies found"
}

################################################################################
# Configuration Functions
################################################################################

prompt_github_oauth() {
    echo ""
    print_step "GitHub OAuth Configuration"
    echo ""
    print_info "You need to create a GitHub OAuth App to enable authentication."
    print_info "Visit: https://github.com/settings/developers"
    echo ""

    # Detect the server IP now so we can show the correct callback URL
    local detected_ip
    detected_ip=$(detect_server_ip)
    local oauth_base_url
    if [ -n "$detected_ip" ]; then
        oauth_base_url="http://${detected_ip}:${PORT}"
    else
        oauth_base_url="http://YOUR_SERVER_IP_OR_DOMAIN:${PORT}"
    fi

    echo -e "  ${BOLD}Create a new OAuth App with:${NC}"
    echo "    Homepage URL: ${oauth_base_url}"
    echo "    Authorization callback URL: ${oauth_base_url}/auth/callback"
    echo ""
    if [ -n "$detected_ip" ]; then
        print_info "Detected server IP: ${detected_ip}"
        print_info "Use this IP (or your domain) — NOT 'localhost' — so that users on"
        print_info "other machines can complete the OAuth login flow."
    else
        print_warning "Could not detect server IP. Replace YOUR_SERVER_IP_OR_DOMAIN above"
        print_warning "with the IP or hostname that users will type in their browser."
    fi
    echo ""
    
    prompt_input "GitHub Client ID" GITHUB_CLIENT_ID ""
    prompt_input "GitHub Client Secret" GITHUB_CLIENT_SECRET "" "true"
    
    if [ -z "$GITHUB_CLIENT_ID" ] || [ -z "$GITHUB_CLIENT_SECRET" ]; then
        print_error "GitHub OAuth credentials are required"
        exit 1
    fi
    
    print_success "GitHub OAuth configured"
}

prompt_license_key() {
    echo ""
    print_step "License Configuration (Optional)"
    echo ""
    print_info "ActionsManager.io offers three tiers:"
    echo ""
    echo "  ${BOLD}Free Tier${NC} (default):"
    echo "    • 3 projects"
    echo "    • 5 public repositories per project"
    echo "    • 2 secrets per project"
    echo "    • No private repository support"
    echo ""
    echo "  ${BOLD}Professional Tier${NC}:"
    echo "    • 10 projects"
    echo "    • Private repository support"
    echo "    • 10 secrets per project"
    echo "    • Reusable workflows"
    echo ""
    echo "  ${BOLD}Enterprise Tier${NC}:"
    echo "    • Unlimited projects"
    echo "    • Unlimited repositories"
    echo "    • Unlimited secrets"
    echo "    • Priority support"
    echo ""
    print_info "Leave blank to use the free tier."
    print_info "For license information, visit: https://github.com/dawg-io/actions-manager"
    echo ""
    
    prompt_input "License Key (optional)" LICENSE_KEY ""
    
    if [ -n "$LICENSE_KEY" ]; then
        print_success "License key configured"
    else
        print_info "Using the free beta tier. No paid plans are currently available."
    fi
}

prompt_admin_credentials() {
    echo ""
    print_step "Admin Panel Configuration"
    echo ""
    print_info "The self-hosted beta image does not require admin panel credentials."
    print_info "Use GitHub OAuth or Personal Access Token login, and keep credentials private."
}

prompt_port() {
    echo ""
    print_step "Port Configuration"
    echo ""
    print_info "The application will be accessible on this port"
    echo ""
    
    prompt_input "Port" PORT "$DEFAULT_PORT"
    
    # Validate port number
    if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
        print_error "Invalid port number: $PORT"
        exit 1
    fi
    
    print_success "Port configured: $PORT"
}

create_env_file() {
    print_step "Generating configuration file..."
    
    # Generate SECRET_KEY
    SECRET_KEY=$(generate_secret_key)

    # Detect the server's primary IP for remote-access URLs.
    # If detection fails, we leave the URL variables commented out so the
    # frontend falls back to window.location (works for any client machine).
    SERVER_IP=$(detect_server_ip)
    if [ -n "$SERVER_IP" ]; then
        DETECTED_BACKEND_URL="http://${SERVER_IP}:${PORT}"
        DETECTED_WS_URL="ws://${SERVER_IP}:${PORT}/ws"
        print_success "Detected server IP: ${SERVER_IP}"
    else
        DETECTED_BACKEND_URL=""
        DETECTED_WS_URL=""
        print_info "Could not detect server IP — URLs will auto-detect from browser location"
    fi
    
    # Create .env.self-hosted file
    cat > .env.self-hosted << EOF
# =============================================================================
# Self-Hosted Deployment Environment Configuration
# Generated by install.sh on $(date)
# =============================================================================

# =============================================================================
# Installation Mode (DO NOT CHANGE)
# =============================================================================
INSTALLATION_MODE=self-hosted

# =============================================================================
# License Configuration (Self-Hosted Only)
# =============================================================================
EOF

    if [ -n "$LICENSE_KEY" ]; then
        cat >> .env.self-hosted << EOF
LICENSE_KEY=$LICENSE_KEY
EOF
    else
        cat >> .env.self-hosted << EOF
# No license key configured - using the free beta tier
# No paid plans are currently available during beta
# LICENSE_KEY=your_jwt_license_key_here
EOF
    fi

    cat >> .env.self-hosted << EOF

# =============================================================================
# Application URLs (runtime env vars — no image rebuild needed)
# =============================================================================
# For PAT login: leave this section commented out. The frontend auto-detects
# the browser location (window.location), so the app works whether you access
# it via localhost, a LAN IP address, or a custom domain.
#
# For GitHub OAuth login: set APP_URL to the actual URL that browsers
# will use to reach the server. Backend, frontend, and WebSocket URLs are
# derived automatically.
EOF

    if [ -n "$DETECTED_BACKEND_URL" ]; then
        cat >> .env.self-hosted << EOF
# Detected server IP: ${SERVER_IP}
# Leave commented out for auto-detection (recommended for PAT login).
# Uncomment and edit only if you use GitHub OAuth login:
# APP_URL=${DETECTED_BACKEND_URL}
EOF
    else
        cat >> .env.self-hosted << EOF
# Server IP could not be detected automatically.
# Leave commented out for auto-detection (recommended for PAT login).
# Uncomment and set only if you use GitHub OAuth login:
# APP_URL=http://YOUR_SERVER_IP_OR_DOMAIN:${PORT}
EOF
    fi

# =============================================================================
# GitHub OAuth Configuration
# =============================================================================
GITHUB_CLIENT_ID=$GITHUB_CLIENT_ID
GITHUB_CLIENT_SECRET=$GITHUB_CLIENT_SECRET

# =============================================================================
# Security
# =============================================================================
SECRET_KEY=$SECRET_KEY

# =============================================================================
# Database Configuration (Optional)
# =============================================================================
# Using SQLite by default - no additional configuration needed
# For PostgreSQL, uncomment and configure:
# POSTGRES_USER=your_postgres_user
# POSTGRES_PASSWORD=your_postgres_password
# POSTGRES_DB=actions_manager
# POSTGRES_HOST=localhost
# POSTGRES_PORT=5432
# DATABASE_URL=postgresql://user:password@localhost:5432/actions_manager

# =============================================================================
# Development Settings
# =============================================================================
DEBUG_MODE=false
USE_MOCK_RESPONSES=false

# (No CRA/webpack file-watching variables needed; Vite handles polling internally)
EOF

    print_success "Configuration file created: .env.self-hosted"
}

################################################################################
# Docker Functions
################################################################################

update_docker_compose_port() {
    # If using non-default port, expose it via the PORT env var that the
    # compose file consumes (no file rewrite needed).
    if [ "$PORT" != "$DEFAULT_PORT" ]; then
        print_step "Configuring application to listen on host port $PORT..."
        export PORT
        print_success "Port override applied (PORT=$PORT)"
    fi
}

# Build the compose argument list. When --build is requested we layer the dev
# overlay on top so the image is built locally from Dockerfile.self-hosted.
compose_args() {
    if [ "$BUILD_FROM_SOURCE" = "true" ]; then
        echo "-f $DOCKER_COMPOSE_FILE -f $DOCKER_COMPOSE_DEV_OVERLAY"
    else
        echo "-f $DOCKER_COMPOSE_FILE"
    fi
}

pull_or_build_image() {
    echo ""
    if [ "$BUILD_FROM_SOURCE" = "true" ]; then
        print_step "Building Docker image from local source (--build)..."
        echo ""
        print_info "This is the contributor / development flow."
        print_info "First build can take 10-15 minutes (frontend + backend)."
        echo ""

        BUILD_DATE=$(date +%s)
        if $COMPOSE_CMD $(compose_args) build --build-arg BUILD_DATE=$BUILD_DATE; then
            print_success "Image built successfully"
        else
            print_error "Failed to build image"
            echo ""
            print_troubleshooting
            exit 1
        fi
    else
        local default_image="ghcr.io/dawg-io/actions-manager:${ACTIONS_MANAGER_TAG:-latest}"
        local image_ref="${ACTIONS_MANAGER_IMAGE:-$default_image}"
        # Export the fully-resolved reference so docker compose uses exactly
        # what was just printed, regardless of whether ACTIONS_MANAGER_IMAGE
        # and/or ACTIONS_MANAGER_TAG were set by the caller.
        export ACTIONS_MANAGER_IMAGE="$image_ref"
        print_step "Pulling pre-built self-hosted image from GHCR..."
        echo ""
        print_info "Image: $image_ref"
        print_info "(Use --build to build from local source instead.)"
        echo ""

        if $COMPOSE_CMD $(compose_args) pull; then
            print_success "Image pulled successfully"
        else
            print_error "Failed to pull image"
            print_info "If the image is private or unavailable, you can build from source with:"
            print_info "  ./install.sh --build"
            echo ""
            print_troubleshooting
            exit 1
        fi
    fi
}

start_containers() {
    echo ""
    print_step "Starting containers..."
    echo ""
    
    if $COMPOSE_CMD $(compose_args) up -d; then
        print_success "Containers started successfully"
    else
        print_error "Failed to start containers"
        echo ""
        print_troubleshooting
        exit 1
    fi
}

wait_for_app() {
    echo ""
    print_step "Waiting for application to be ready..."
    echo ""
    
    local max_attempts=30
    local attempt=1
    local url="http://localhost:${PORT}"
    
    while [ $attempt -le $max_attempts ]; do
        if curl -f -s -o /dev/null "$url"; then
            print_success "Application is ready!"
            return 0
        fi
        
        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo ""
    print_warning "Application did not respond within expected time"
    print_info "This may be normal for first startup. Check logs with: $COMPOSE_CMD $(compose_args) logs -f"
    return 1
}

################################################################################
# Output Functions
################################################################################

print_success_message() {
    local server_ip
    server_ip=$(detect_server_ip)
    local local_url="http://localhost:${PORT}"
    local remote_url=""
    if [ -n "$server_ip" ]; then
        remote_url="http://${server_ip}:${PORT}"
    fi

    echo ""
    echo -e "${BOLD}${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${GREEN}║                                                                ║${NC}"
    echo -e "${BOLD}${GREEN}║             Installation Completed Successfully!               ║${NC}"
    echo -e "${BOLD}${GREEN}║                                                                ║${NC}"
    echo -e "${BOLD}${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${BOLD}Access your ActionsManager.io instance:${NC}"
    echo -e "  ${CYAN}🌐 On this machine:     ${local_url}${NC}"
    if [ -n "$remote_url" ]; then
    echo -e "  ${CYAN}🌐 From other machines: ${remote_url}${NC}"
    fi
    echo -e "  ${CYAN}📚 API Documentation:   ${local_url}/docs${NC}"
    echo ""
    echo -e "${BOLD}Deployment Type:${NC} Docker/Podman containerized (self-hosted)"
    echo ""
    
    # Display tier information
    if [ -n "$LICENSE_KEY" ]; then
        echo -e "${BOLD}License:${NC} Professional/Enterprise tier"
    else
        echo -e "${BOLD}License:${NC} Free tier"
        echo ""
        echo -e "${YELLOW}📊 Free Tier Limits:${NC}"
        echo "  • 3 projects"
        echo "  • 5 public repositories per project"
        echo "  • 2 secrets per project"
        echo ""
        echo -e "${BOLD}Beta note:${NC} No paid plans are currently available. Future paid licensing may change before GA."
    fi
    
    echo ""
    echo -e "${BOLD}Useful Commands:${NC}"
    echo -e "  View logs:      ${CYAN}$COMPOSE_CMD $(compose_args) logs -f${NC}"
    echo -e "  Stop:           ${CYAN}$COMPOSE_CMD $(compose_args) down${NC}"
    echo -e "  Restart:        ${CYAN}$COMPOSE_CMD $(compose_args) restart${NC}"
    echo -e "  View status:    ${CYAN}$COMPOSE_CMD $(compose_args) ps${NC}"
    echo ""
}

print_troubleshooting() {
    echo ""
    echo -e "${BOLD}${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${YELLOW}                    TROUBLESHOOTING GUIDE${NC}"
    echo -e "${BOLD}${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    
    echo -e "${BOLD}1. Application won't start:${NC}"
    echo "   • Check logs: $COMPOSE_CMD $(compose_args) logs"
    echo "   • Verify port $PORT is not in use: netstat -an | grep $PORT"
    echo "   • Ensure Docker/Podman has enough memory (4GB+ recommended)"
    echo ""
    
    echo -e "${BOLD}2. GitHub OAuth errors:${NC}"
    echo "   • Verify the OAuth App callback URL uses your server's actual IP or domain,"
    echo "     NOT 'localhost' (unless all users run the container locally)."
    echo "   • Expected callback URL: http://YOUR_SERVER_IP:${PORT}/auth/callback"
    echo "   • Check GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in .env.self-hosted"
    echo "   • Ensure OAuth App is active on GitHub"
    echo ""
    
    echo -e "${BOLD}3. Image pull or build fails:${NC}"
    echo "   • Default flow pulls ghcr.io/dawg-io/actions-manager:\${ACTIONS_MANAGER_TAG:-latest}"
    echo "   • If GHCR is unreachable, build from source: ./install.sh --build"
    echo "   • Check disk space: df -h"
    echo "   • Clear Docker cache: $CONTAINER_CMD system prune -a"
    echo "   • For Podman OOM (when building): podman machine set --memory 4096"
    echo ""
    
    echo -e "${BOLD}4. Database errors:${NC}"
    echo "   • SQLite is used by default (no setup needed)"
    echo "   • Check write permissions in current directory"
    echo "   • View logs for specific error messages"
    echo ""
    
    echo -e "${BOLD}5. License key issues:${NC}"
    echo "   • Verify LICENSE_KEY was copied exactly as issued"
    echo "   • Check license hasn't expired"
    echo "   • Application falls back to free tier on license errors"
    echo ""
    
    echo -e "${BOLD}6. Network connectivity issues (accessing from another machine):${NC}"
    echo "   • The app auto-detects the correct host from the browser URL."
    echo "   • For PAT login: just open http://YOUR_SERVER_IP:${PORT} — no config needed."
    echo "   • For OAuth login: set APP_URL=http://YOUR_SERVER_IP:${PORT} in .env.self-hosted"
    echo "     and register that URL in your GitHub OAuth App settings."
    echo "   • Ensure your firewall allows port $PORT from remote hosts."
    echo "   • Check if containers are running: $COMPOSE_CMD $(compose_args) ps"
    echo "   • Test locally: curl http://localhost:${PORT}"
    echo ""
    
    echo -e "${BOLD}7. Memory/Performance issues:${NC}"
    echo "   • Increase Docker/Podman memory allocation (4GB+ recommended)"
    echo "   • Monitor resources: $CONTAINER_CMD stats"
    echo "   • Check system resources: top or htop"
    echo ""
    
    echo -e "${BOLD}Need more help?${NC}"
    echo "   • GitHub Issues: https://github.com/dawg-io/actions-manager/issues"
    echo "   • Documentation: https://github.com/dawg-io/actions-manager"
    echo "   • Check logs: $COMPOSE_CMD $(compose_args) logs -f"
    echo ""
}

################################################################################
# Main Installation Flow
################################################################################

main() {
    # Print header
    print_header
    
    # Pre-flight checks
    check_os
    check_docker
    check_dependencies
    
    # Gather configuration
    prompt_port
    prompt_github_oauth
    prompt_license_key
    prompt_admin_credentials
    
    # Create configuration file
    create_env_file
    
    # Update docker-compose if needed
    update_docker_compose_port
    
    # Build and start containers
    pull_or_build_image
    start_containers
    
    # Wait for application to be ready
    wait_for_app
    
    # Print success message
    print_success_message
    
    # Print troubleshooting guide
    echo -e "${BOLD}If you experience any issues, refer to the troubleshooting guide below:${NC}"
    print_troubleshooting
}

# Run main installation
main
