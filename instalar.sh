#!/bin/bash
# ============================================================
#  Instalador del Compilador / Ofuscador de Lua para MTA
#  Crea el comando global 'compilador'.
#  Uso:   bash instalar.sh    (usa sudo automaticamente si hace falta)
# ============================================================

DIR="$(cd "$(dirname "$0")" && pwd)"
echo "== Instalador del Compilador Lua MTA =="

# 1) Comprobar que estamos en la carpeta correcta
if [ ! -f "$DIR/compilador.py" ] || [ ! -f "$DIR/mta_obfuscator.py" ]; then
    echo "ERROR: ejecuta este script desde la carpeta del proyecto"
    echo "       (donde estan compilador.py y mta_obfuscator.py)."
    exit 1
fi

# 2) Comprobar / instalar Python 3
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 no encontrado. Intentando instalarlo..."
    SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
    if command -v apt-get >/dev/null 2>&1; then
        $SUDO apt-get update -y && $SUDO apt-get install -y python3
    else
        echo "Instala Python 3 manualmente y vuelve a ejecutar."
        exit 1
    fi
fi

# 3) Crear carpetas de trabajo
mkdir -p "$DIR/input" "$DIR/output"

# 4) Crear el lanzador global
TMP="$(mktemp)"
cat > "$TMP" << EOF
#!/bin/bash
cd "$DIR" || exit 1
python3 compilador.py
EOF
chmod +x "$TMP"

DEST="/usr/local/bin/compilador"
if [ -w "$(dirname "$DEST")" ]; then
    mv "$TMP" "$DEST"
else
    SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
    $SUDO mv "$TMP" "$DEST"
fi
[ -f "$DEST" ] && { chmod +x "$DEST" 2>/dev/null || sudo chmod +x "$DEST"; }

echo ""
echo "============================================="
echo " Listo! Abre el menu desde cualquier carpeta:"
echo ""
echo "     compilador"
echo ""
echo "============================================="
