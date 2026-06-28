#!/bin/bash
# Elimina el comando global 'compilador'
DEST="/usr/local/bin/compilador"
if [ -f "$DEST" ]; then
    SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
    $SUDO rm -f "$DEST" && echo "Comando 'compilador' eliminado."
else
    echo "El comando no estaba instalado."
fi
