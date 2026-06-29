#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ofuscador de Lua para MTA:SA
============================
Protege tus scripts .lua aplicando varias capas:

  1) Cifra los textos (strings) visibles  -> nadie ve mensajes ni nombres de eventos
  2) Minifica (quita comentarios/espacios) -> codigo ilegible y mas pequeno
  3) Envuelve todo en un "cargador" cifrado -> el codigo original no aparece a simple vista

Pensado para Lua 5.1 (la version que usa MTA). No usa operadores de bits,
solo aritmetica, asi que funciona en MTA sin librerias extra.

Uso:
    python mta_obfuscator.py entrada.lua -o salida.lua
    python mta_obfuscator.py entrada.lua          (crea entrada.obf.lua)

Opciones (todas activadas por defecto):
    --no-strings   No cifrar los textos
    --no-minify    No minificar
    --no-wrap      No envolver en cargador cifrado
    --seed N       Semilla para que el cifrado sea reproducible (por defecto aleatoria)
"""

import sys
import os
import random
import argparse

# ---------------------------------------------------------------------------
# 1) LEXER (analizador lexico)
# ---------------------------------------------------------------------------
# Convierte el codigo Lua en una lista de "tokens" (piezas). Lo necesitamos
# para distinguir con seguridad que es un string, que es un comentario, etc.,
# sin romper cosas como [[ strings largos ]] o "comillas \"escapadas\"".

WS, COMMENT, STRING, NAME, NUMBER, OTHER = range(6)

KEYWORDS = {
    "and","break","do","else","elseif","end","false","for","function","goto",
    "if","in","local","nil","not","or","repeat","return","then","true",
    "until","while",
}

class Tok:
    __slots__ = ("type", "text", "value")
    def __init__(self, type, text, value=None):
        self.type = type      # uno de WS/COMMENT/STRING/...
        self.text = text      # el texto original tal cual
        self.value = value    # para STRING: el contenido real ya decodificado


def _read_long_bracket(s, i):
    """Lee [[...]] , [=[...]=] , etc. Devuelve (texto_completo, contenido, fin) o None."""
    if s[i] != '[':
        return None
    j = i + 1
    level = 0
    while j < len(s) and s[j] == '=':
        level += 1
        j += 1
    if j >= len(s) or s[j] != '[':
        return None  # no era un corchete largo (p.ej. indexado normal)
    j += 1
    # Lua ignora un salto de linea inmediatamente despues de la apertura
    if j < len(s) and s[j] == '\n':
        j += 1
    close = ']' + '=' * level + ']'
    end = s.find(close, j)
    if end == -1:
        end = len(s)
        content = s[j:end]
        full = s[i:end]
    else:
        content = s[j:end]
        full = s[i:end + len(close)]
        end = end + len(close)
    return full, content, end


def _decode_short_string(text):
    """Dado un string con comillas ('..' o "..") devuelve su contenido real (bytes)."""
    quote = text[0]
    body = text[1:-1]  # quitamos comillas
    out = []
    i = 0
    simple = {'a':7,'b':8,'f':12,'n':10,'r':13,'t':9,'v':11,
              '\\':92,'"':34,"'":39,'[':91,']':93}
    while i < len(body):
        c = body[i]
        if c == '\\' and i + 1 < len(body):
            nxt = body[i+1]
            if nxt in simple:
                out.append(simple[nxt]); i += 2
            elif nxt == '\n':
                out.append(10); i += 2
            elif nxt.isdigit():
                num = nxt; i += 2
                for _ in range(2):
                    if i < len(body) and body[i].isdigit():
                        num += body[i]; i += 1
                    else:
                        break
                out.append(int(num) % 256)
            else:
                out.append(ord(nxt)); i += 2  # tolerante
        else:
            out.append(ord(c)); i += 1
    return bytes(out)


def tokenize(s):
    toks = []
    i, n = 0, len(s)
    multi_ops = ("...", "..", "==", "~=", "<=", ">=")
    while i < n:
        c = s[i]
        # --- espacios ---
        if c in " \t\r\n":
            j = i
            while j < n and s[j] in " \t\r\n":
                j += 1
            toks.append(Tok(WS, s[i:j])); i = j; continue
        # --- comentarios ---
        if c == '-' and i + 1 < n and s[i+1] == '-':
            # comentario largo --[[ ... ]] ?
            if i + 2 < n and s[i+2] == '[':
                lb = _read_long_bracket(s, i + 2)
                if lb:
                    full, _, end = lb
                    toks.append(Tok(COMMENT, s[i:end])); i = end; continue
            # comentario de linea
            j = i
            while j < n and s[j] != '\n':
                j += 1
            toks.append(Tok(COMMENT, s[i:j])); i = j; continue
        # --- strings largos [[ ]] ---
        if c == '[':
            lb = _read_long_bracket(s, i)
            if lb:
                full, content, end = lb
                toks.append(Tok(STRING, full, content.encode("latin-1", "replace")))
                i = end; continue
        # --- strings cortos ' " ---
        if c in "\"'":
            quote = c; j = i + 1
            while j < n:
                if s[j] == '\\':
                    j += 2; continue
                if s[j] == quote:
                    j += 1; break
                if s[j] == '\n':
                    break  # string sin cerrar; cortamos
                j += 1
            text = s[i:j]
            toks.append(Tok(STRING, text, _decode_short_string(text)))
            i = j; continue
        # --- numeros ---
        if c.isdigit() or (c == '.' and i + 1 < n and s[i+1].isdigit()):
            j = i
            if c == '0' and i + 1 < n and s[i+1] in "xX":
                j = i + 2
                while j < n and (s[j] in "0123456789abcdefABCDEF"):
                    j += 1
            else:
                while j < n and (s[j].isdigit() or s[j] == '.'):
                    j += 1
                if j < n and s[j] in "eE":
                    j += 1
                    if j < n and s[j] in "+-":
                        j += 1
                    while j < n and s[j].isdigit():
                        j += 1
            toks.append(Tok(NUMBER, s[i:j])); i = j; continue
        # --- nombres / palabras clave ---
        if c.isalpha() or c == '_':
            j = i
            while j < n and (s[j].isalnum() or s[j] == '_'):
                j += 1
            toks.append(Tok(NAME, s[i:j])); i = j; continue
        # --- operadores multi-caracter ---
        matched = False
        for op in multi_ops:
            if s.startswith(op, i):
                toks.append(Tok(OTHER, op)); i += len(op); matched = True; break
        if matched:
            continue
        # --- un solo caracter ---
        toks.append(Tok(OTHER, c)); i += 1
    return toks


# ---------------------------------------------------------------------------
# 2) CIFRADO (aritmetica simple, compatible con Lua 5.1 de MTA)
# ---------------------------------------------------------------------------
# Cifra cada byte:   e = (b + clave[pos]) % 256
# Descifra:          b = (e - clave[pos]) % 256
# La clave es una lista de numeros generada al azar para cada compilado.

def make_key(rng, length=8):
    return [rng.randint(1, 255) for _ in range(length)]

def encrypt_bytes(data, key):
    return [(b + key[idx % len(key)]) % 256 for idx, b in enumerate(data)]

def lua_num_list(nums):
    return "{" + ",".join(str(x) for x in nums) + "}"

def decoder_function(name, key):
    """Genera la funcion Lua que descifra (con la clave incrustada)."""
    k = ",".join(str(x) for x in key)
    return (f"local {name}=function(t)local r={{}}local k={{{k}}}"
            f"for i=1,#t do r[i]=string.char((t[i]-k[(i-1)%#k+1])%256)end "
            f"return table.concat(r)end")


# ---------------------------------------------------------------------------
# 3) CAPAS DE OFUSCACION
# ---------------------------------------------------------------------------

def encrypt_strings(code, rng):
    """Reemplaza cada string literal por una llamada al descifrador."""
    toks = tokenize(code)
    if not any(t.type == STRING for t in toks):
        return code
    key = make_key(rng)
    dname = "_" + "".join(rng.choice("abcdef0123456789") for _ in range(6))
    out = []
    for t in toks:
        if t.type == STRING:
            enc = encrypt_bytes(t.value, key)
            out.append(f"{dname}({lua_num_list(enc)})")
        else:
            out.append(t.text)
    return decoder_function(dname, key) + "\n" + "".join(out)


def minify(code):
    """Quita comentarios y espacios sobrantes sin romper el codigo."""
    toks = [t for t in tokenize(code) if t.type != COMMENT]
    # quitamos los tokens de espacio; los reinsertaremos solo donde hagan falta
    toks = [t for t in toks if t.type != WS]
    out = []
    prev = None
    for t in toks:
        if prev is not None and _needs_space(prev, t):
            out.append(" ")
        out.append(t.text)
        prev = t
    return "".join(out)


def _is_word(t):
    return t.type in (NAME, NUMBER)

def _needs_space(p, n):
    """Decide si hay que dejar un espacio entre dos tokens al minificar."""
    if _is_word(p) and _is_word(n):
        return True
    a, b = p.text[-1], n.text[0]
    # numero seguido de '.' -> evitar que '1' '..' se pegue como 1..
    if p.type == NUMBER and b == '.':
        return True
    # evitar formar comentario --
    if a == '-' and b == '-':
        return True
    # evitar pegar puntos (.. ...)
    if a == '.' and b == '.':
        return True
    # evitar abrir string/comentario largo [[ o [=
    if a == '[' and (b == '[' or b == '='):
        return True
    # evitar formar == <= >= ~= a partir de dos tokens sueltos
    if a in "=<>~" and b == '=':
        return True
    # evitar etiqueta ::
    if a == ':' and b == ':':
        return True
    return False


def wrap_loader(code, rng):
    """Cifra TODO el script y lo mete en un cargador que lo ejecuta con loadstring."""
    key = make_key(rng, 12)
    data = code.encode("utf-8", "replace")
    enc = encrypt_bytes(data, key)
    dname = "_" + "".join(rng.choice("abcdef0123456789") for _ in range(6))
    parts = [
        decoder_function(dname, key),
        f"local _c=loadstring({dname}({lua_num_list(enc)}))",
        "if _c then return _c() end",
    ]
    return "\n".join(parts)


def inject_license_guard(code, rng, url, license_key, recheck_seconds=60):
    """Guardia de licencia REMOTO con DOBLE proteccion (IP + clave de licencia).

    - Al arrancar y cada 'recheck_seconds', consulta tu lista en la URL.
    - Solo ejecuta el codigo si la IP esta registrada Y su clave coincide con la
      clave del sistema incrustada en el recurso.
    - Si la licencia no es valida o no se puede verificar, el codigo NUNCA corre
      e intenta apagar el recurso (con reintentos).
    - Mensajes en el debug de MTA: verde (activa) / rojo (denegada).

    Formato del archivo remoto:  return {["1.2.3.4"]="CLAVE",["5.6.7.8"]=false}
    Solo para scripts del lado del SERVIDOR.
    """
    sfx = "".join(rng.choice("abcdef0123456789") for _ in range(6))
    main = "_mn" + sfx
    deny = "_dn" + sfx
    started = "_st" + sfx
    logged = "_lg" + sfx
    getip = "_gi" + sfx
    urls = "_ur" + sfx
    verify = "_vf" + sfx
    activar = "_ac" + sfx
    ms = int(recheck_seconds) * 1000

    g = []
    g.append("do")
    g.append("if outputServerLog then outputServerLog('[LICENCIA] Iniciando verificacion de licencia...') end")
    g.append("if outputDebugString then outputDebugString('[LICENCIA] Iniciando verificacion de licencia...',0,255,255,0) end")
    g.append("local %s=false" % started)
    g.append("local %s=false" % logged)
    g.append("local function %s()" % main)
    g.append(code)
    g.append("end")

    # activar: mensaje VERDE en debug (licencia valida) + ejecutar el codigo real
    g.append("local function %s()" % activar)
    g.append("local m='[LICENCIA] Licencia activa. Recurso autorizado correctamente.'")
    g.append("if outputDebugString then outputDebugString(m,0,0,255,0) end")
    g.append("if outputServerLog then outputServerLog(m) end")
    g.append("%s()" % main)
    g.append("end")

    # apagar: mensaje ROJO limpio (nivel 0 con color, SIN el prefijo de ERROR/linea)
    g.append("local function %s(motivo)" % deny)
    g.append("if not %s then" % logged)
    g.append("%s=true" % logged)
    g.append("local m='[LICENCIA] Este recurso requiere una licencia activa. '..tostring(motivo)")
    g.append("if outputDebugString then outputDebugString(m,0,255,0,0) end")
    g.append("if outputServerLog then outputServerLog(m) end")
    g.append("end")
    g.append("local r=getThisResource and getThisResource()")
    g.append("if r and stopResource then")
    g.append("stopResource(r)")  # intento inmediato
    # reintentos: cubre el arranque y cualquier momento malo (no necesita ACL para auto-apagarse)
    g.append("if setTimer then setTimer(function() if stopResource and r then stopResource(r) end end,2000,5) end")
    g.append("end")
    g.append("end")

    # helper: obtener la IP publica del servidor (con varios servicios de respaldo)
    g.append("local %s={'https://api.ipify.org','https://ipv4.icanhazip.com','https://ifconfig.me/ip'}" % urls)
    g.append("local function %s(cb,i)" % getip)
    g.append("i=i or 1")
    g.append("if i>#%s or not fetchRemote then cb(nil) return end" % urls)
    g.append("local _r=fetchRemote(%s[i],function(data,info)" % urls)
    g.append("local ok if type(info)=='table' then ok=(info.success==true) else ok=(info==0) end")
    g.append("if ok and data and #tostring(data)>0 then cb((tostring(data):gsub('%%s+',''))) else %s(cb,i+1) end" % getip)
    g.append("end)")
    g.append("if not _r then %s(cb,i+1) end" % getip)
    g.append("end")

    safe_url = url.replace("'", "")
    safe_key = str(license_key).replace("'", "")
    g.append("local function %s(primera)" % verify)
    # ANTI-TRAMPA: el recurso debe poder apagarse. Si la ACL le quita el permiso
    # de stopResource (para que no se pueda matar), entonces NO arranca.
    g.append("local _res=getThisResource and getThisResource()")
    g.append("local _rn=_res and getResourceName and getResourceName(_res)")
    g.append("if hasObjectPermissionTo and _rn then")
    g.append("if not hasObjectPermissionTo('resource.'.._rn,'function.stopResource',false) then")
    g.append("%s('Anade el recurso al grupo ACL admin (necesita permiso function.stopResource).') return" % deny)
    g.append("end")
    g.append("end")
    g.append("%s(function(ip)" % getip)
    g.append("if not ip then if primera then %s('No se pudo verificar la IP (revisa ACL: function.fetchRemote)') end return end" % deny)
    g.append("if not fetchRemote then return end")
    g.append("local _u='%s'" % safe_url)
    g.append("local _sep=_u:find('?',1,true) and '&' or '?'")
    g.append("_u=_u.._sep..'_='..tostring(getTickCount and getTickCount() or 0)")
    g.append("local _r2=fetchRemote(_u,function(data,info)")
    g.append("local ok if type(info)=='table' then ok=(info.success==true) else ok=(info==0) end")
    g.append("if not ok or not data then if primera then %s('No se pudo contactar el sistema de licencias') end return end" % deny)
    g.append("local f=loadstring(tostring(data))")
    g.append("local lic=type(f)=='function' and f() or nil")
    # DOBLE PROTECCION: la IP debe estar registrada Y su clave coincidir
    g.append("if type(lic)=='table' and lic[ip]=='%s' then" % safe_key)
    g.append("if not %s then %s=true %s() end" % (started, started, activar))
    g.append("else %s('La IP '..ip..' no tiene licencia valida (bloqueada, no registrada o clave incorrecta)') end" % deny)
    g.append("end)")
    g.append("if not _r2 then if primera then %s('No se pudo contactar el sistema de licencias (revisa ACL: function.fetchRemote)') end end" % deny)
    g.append("end)")
    g.append("end")
    g.append("%s(true)" % verify)
    g.append("if setTimer then setTimer(function() %s(false) end,%d,0) end" % (verify, ms))

    g.append("end")
    return "\n".join(g)


def obfuscate(code, do_strings=True, do_minify=True, do_wrap=True,
              ip_lock=False, allowed_ips=None, license_mode="remote",
              license_url="", license_key="", seed=None):
    rng = random.Random(seed)
    if ip_lock:
        code = inject_license_guard(code, rng, license_url, license_key)
    if do_strings:
        code = encrypt_strings(code, rng)
    if do_minify:
        code = minify(code)
    if do_wrap:
        code = wrap_loader(code, rng)
    return code


# ---------------------------------------------------------------------------
# 4) LINEA DE COMANDOS
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Ofuscador de Lua para MTA:SA")
    ap.add_argument("entrada", help="Archivo .lua de entrada")
    ap.add_argument("-o", "--output", help="Archivo de salida")
    ap.add_argument("--no-strings", action="store_true", help="No cifrar textos")
    ap.add_argument("--no-minify", action="store_true", help="No minificar")
    ap.add_argument("--no-wrap", action="store_true", help="No envolver en cargador")
    ap.add_argument("--ip", action="append", default=[], metavar="IP",
                    help="IP permitida (repetir para varias). Activa el bloqueo por IP.")
    ap.add_argument("--seed", type=int, default=None, help="Semilla del cifrado")
    args = ap.parse_args()

    with open(args.entrada, "r", encoding="utf-8") as f:
        code = f.read()

    result = obfuscate(
        code,
        do_strings=not args.no_strings,
        do_minify=not args.no_minify,
        do_wrap=not args.no_wrap,
        ip_lock=bool(args.ip),
        allowed_ips=args.ip,
        seed=args.seed,
    )

    out = args.output
    if not out:
        base, _ = os.path.splitext(args.entrada)
        out = base + ".obf.lua"
    with open(out, "w", encoding="utf-8") as f:
        f.write(result)

    orig = len(code)
    new = len(result)
    print(f"[OK] {args.entrada} -> {out}")
    print(f"     {orig} bytes -> {new} bytes")


if __name__ == "__main__":
    main()
