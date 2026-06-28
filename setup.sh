#!/usr/bin/env bash
# ============================================================
#  Compilador / Ofuscador de Lua para MTA - Instalador
#  Uso:
#    curl -sL https://raw.githubusercontent.com/2025-0181-spec/compilador-lua-mta/main/setup.sh | bash
# ============================================================
set -euo pipefail

# Tu usuario y repositorio de GitHub
GH_USER="2025-0181-spec"
GH_REPO="compilador-lua-mta"
BRANCH="main"

REPO_RAW="https://raw.githubusercontent.com/${GH_USER}/${GH_REPO}/${BRANCH}"
INSTALL_DIR="/opt/compilador-lua-mta"
BIN_PATH="/usr/local/bin/compilador"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET} $*"; }
success() { echo -e "${GREEN}[OK]${RESET}   $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
die()     { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }

banner() {
    echo -e "${CYAN}${BOLD}"
    echo "==========================================="
    echo "   COMPILADOR LUA - MTA:SA - instalador"
    echo "==========================================="
    echo -e "${RESET}"
}

check_root() {
    [ "$(id -u)" -eq 0 ] || die "Ejecuta como root. Prueba: curl -sL URL | sudo bash"
}

check_internet() {
    info "Verificando conexion a internet..."
    curl -s --max-time 20 -o /dev/null https://github.com || die "Sin acceso a internet o GitHub no responde."
    success "Conexion OK"
}

install_python() {
    if ! command -v python3 >/dev/null 2>&1; then
        info "Instalando Python 3..."
        apt-get update -qq && apt-get install -y -qq python3 || die "No se pudo instalar Python 3."
    fi
    command -v curl >/dev/null 2>&1 || { apt-get update -qq && apt-get install -y -qq curl; }
    success "Python 3 disponible"
}

download_files() {
    info "Descargando componentes desde GitHub ${GH_USER}/${GH_REPO}..."
    mkdir -p "$INSTALL_DIR/input" "$INSTALL_DIR/output"
    for f in mta_obfuscator.py compilador.py; do
        if curl -fsSL --retry 3 --retry-delay 2 -o "$INSTALL_DIR/$f" "$REPO_RAW/$f"; then
            success "Descargado: $f"
        else
            die "No se pudo descargar $f. Revisa que el repo sea PUBLICO y contenga ese archivo."
        fi
    done
}

create_command() {
    cat > "$BIN_PATH" << EOF
#!/bin/bash
cd "$INSTALL_DIR" || exit 1
python3 compilador.py
EOF
    chmod +x "$BIN_PATH"
    success "Comando global 'compilador' creado"
}

verify_install() {
    [ -f "$INSTALL_DIR/compilador.py" ] && [ -f "$INSTALL_DIR/mta_obfuscator.py" ] || die "Instalacion incompleta."
    [ -x "$BIN_PATH" ] || die "No se pudo crear el comando global."
    success "Instalacion verificada"
}

print_success() {
    echo ""
    echo -e "${GREEN}${BOLD}===========================================${RESET}"
    echo -e "${GREEN}${BOLD}   Instalacion completada${RESET}"
    echo -e "${GREEN}${BOLD}===========================================${RESET}"
    echo -e "   Abre el menu con:   ${BOLD}compilador${RESET}"
    echo -e "   Pon tus .lua en:    ${BOLD}$INSTALL_DIR/input${RESET}"
    echo -e "   Resultados en:      ${BOLD}$INSTALL_DIR/output${RESET}"
    echo ""
}

main() {
    banner
    check_root
    check_internet
    install_python
    download_files
    create_command
    verify_install
    print_success
}

main "$@"
