# Compilador / Ofuscador de Lua para MTA:SA

Herramienta con **menú** para proteger tus scripts `.lua` de Multi Theft Auto (MTA:SA).
Pensada para correr en un **VPS Ubuntu**: dejas tus scripts en una carpeta, abres el menú
y los obtienes protegidos, con opción de **bloqueo por IP** (licencia) para que no arranquen
en servidores que no sean el tuyo.

> Compatible con **Lua 5.1** (la versión que usa MTA). No necesita librerías externas:
> solo Python 3, que Ubuntu ya trae.

---

## ¿Qué hace?

Aplica varias **capas** de protección, que puedes activar o desactivar desde el menú:

- **Cifrado de textos** — los `strings` (mensajes, nombres de eventos, etc.) dejan de ser legibles.
- **Minificado** — quita comentarios y espacios; el código queda apelmazado.
- **Cargador cifrado** — envuelve todo el script en un bloque cifrado que se descifra al ejecutarse.
- **Bloqueo por IP (licencia)** — el script averigua la IP pública del servidor y **solo arranca**
  si está en tu lista permitida; si no, **se apaga solo** (`stopResource`). La lista de IPs
  va escondida dentro de las capas cifradas.

---

## Instalación (una sola línea)

En tu VPS, como root (cambia `TU_USUARIO` por tu usuario de GitHub):

```bash
curl -sL https://raw.githubusercontent.com/2025-0181-spec/compilador-lua-mta/main/setup.sh | bash
```

> Antes de usar esta línea debes tener el repositorio **subido y público** en GitHub,
> y haber editado `GH_USER` dentro de `setup.sh` con tu usuario real.

El instalador comprueba Python 3, descarga los componentes, crea las carpetas de trabajo
y registra el comando global. Luego abres el menú desde cualquier sitio con:

```bash
compilador
```

### Alternativa: clonando el repo

```bash
git clone https://github.com/2025-0181-spec/compilador-lua-mta.git
cd compilador-lua-mta
bash instalar.sh
```

Para quitar el comando: `bash desinstalar.sh`

---

## Cómo se usa

1. Copia tus scripts `.lua` dentro de la carpeta **`input/`**.
2. Abre el menú: `compilador`
3. *(Opcional)* Entra en **Bloqueo por IP**, añade la IP **pública** de tu servidor y actívalo.
4. Elige **Compilar TODO**.
5. Recoge los archivos protegidos de **`output/`** y súbelos a tu servidor MTA en lugar de los originales.

Tus ajustes y tu lista de IPs se guardan en `config.json` (este archivo **no** se sube a GitHub).

---

## Importante sobre el bloqueo por IP

- Funciona en scripts del **lado del servidor** (server-side): comprueba la IP pública de *tu* servidor.
- Tu servidor MTA necesita **salida a internet** (usa `fetchRemote` contra servicios de "cuál es mi IP").
- Si no logra verificar la IP, el script **no arranca** a propósito: para una licencia es más seguro
  que no corra a que corra sin permiso.
- **Pon siempre tu propia IP antes de compilar**, o ni tu servidor podrá iniciar el script.

---

## Recomendación: doble protección

La ofuscación **disuade**, pero no es 100 % inviolable. Para mayor seguridad, pasa el resultado
de esta herramienta por el **compilador oficial de MTA**, que lo convierte a bytecode:

<https://luac.multitheftauto.com/>

Las dos capas combinadas dan una protección bastante sólida.

---

## Uso por línea de comandos (avanzado)

Sin menú, directamente sobre un archivo:

```bash
python3 mta_obfuscator.py mi.lua -o mi.obf.lua --ip 203.0.113.7
```

Opciones: `--no-strings`, `--no-minify`, `--no-wrap`, `--ip IP` (repetible para varias IPs).

---

## Aviso

Úsala para proteger **tus propios** scripts. La ofuscación dificulta la copia, pero ningún
método es totalmente irreversible.

## Licencia

MIT. Edita el archivo `LICENSE` y pon tu nombre.
