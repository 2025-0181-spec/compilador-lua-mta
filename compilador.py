#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Menu del compilador/ofuscador de Lua para MTA (para tu VPS Ubuntu)
==================================================================
- Sueltas tus .lua en la carpeta  input/
- Los resultados protegidos salen en  output/
- Desde el menu activas capas y gestionas las IPs permitidas (licencia)

Arrancar:   python3 compilador.py
"""

import os
import sys
import json
import subprocess

# Importamos el motor de ofuscacion (debe estar en la misma carpeta)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mta_obfuscator as ob

INPUT_DIR = os.path.join(HERE, "input")
OUTPUT_DIR = os.path.join(HERE, "output")
CONFIG_FILE = os.path.join(HERE, "config.json")

# URL del compilador OFICIAL de MTA (devuelve bytecode = el "warning de binario")
MTA_LUAC_URL = "https://luac.multitheftauto.com/"

# Valores por defecto: receta PROFESIONAL y LIGERA
#   minificar + bytecode oficial nivel 3.
# Las capas pesadas (strings/wrap) van apagadas porque inflan el archivo
# y son redundantes una vez tienes bytecode. Puedes activarlas si quieres.
DEFAULT_CONFIG = {
    "strings": False,
    "minify": True,
    "wrap": False,
    "ip_lock": False,
    "licenses": [],          # [{"ip": "1.2.3.4", "name": "Servidor X", "blocked": False}]
    "license_mode": "remote", # "local" (incrustada) o "remote" (URL)
    "license_url": "https://raw.githubusercontent.com/2025-0181-spec/compilador-lua-mta/main/licencias.lua",
    "bytecode": True,
    "obf_level": 3,
    "license_key": "",       # clave del sistema (doble proteccion); se genera sola
    "repo_raw": "https://raw.githubusercontent.com/2025-0181-spec/compilador-lua-mta/main",
    "gh_token": "",
    "gh_owner": "2025-0181-spec",
    "gh_repo": "compilador-lua-mta",
    "gh_branch": "main",
    "gh_path": "licencias.lua",
}

# --------------------------------------------------------------------------

def cargar_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg = dict(DEFAULT_CONFIG)
            cfg.update(data)
            # Migracion del formato viejo (allowed_ips -> licenses)
            if "allowed_ips" in data and not data.get("licenses"):
                cfg["licenses"] = [
                    {"ip": ip, "name": "", "blocked": False}
                    for ip in data["allowed_ips"]
                ]
            cfg.pop("allowed_ips", None)
            cfg.pop("test_mode", None)
            if not cfg.get("license_key"):
                import secrets
                cfg["license_key"] = "SYS-" + secrets.token_hex(10).upper()
                guardar_config(cfg)
            return cfg
        except Exception:
            pass
    base = dict(DEFAULT_CONFIG)
    import secrets
    base["license_key"] = "SYS-" + secrets.token_hex(10).upper()
    return base

def ips_activas(cfg):
    """Lista de IPs con permiso (no bloqueadas)."""
    return [e["ip"] for e in cfg.get("licenses", []) if not e.get("blocked")]

def guardar_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def asegurar_carpetas():
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

def listar_lua():
    if not os.path.isdir(INPUT_DIR):
        return []
    return sorted(f for f in os.listdir(INPUT_DIR) if f.lower().endswith(".lua"))

def onoff(b):
    return "ON " if b else "OFF"

def pausa():
    input("\n  (Pulsa ENTER para continuar)")

# --------------------------------------------------------------------------

def _es_mensaje_de_error(data):
    """True si la respuesta es un mensaje de error de TEXTO (no bytecode)."""
    if not data:
        return True
    if data[:1] == b"\x1b":
        return False              # bytecode estandar de Lua
    if b"\x00" in data:
        return False              # tiene bytes nulos -> es binario (bytecode)
    try:
        t = data.decode("utf-8")
    except UnicodeDecodeError:
        return False              # no es texto valido -> es binario
    # Si es texto imprimible, es un mensaje de error del compilador
    imprimibles = sum(1 for ch in t if ch.isprintable() or ch in "\r\n\t")
    return imprimibles >= 0.90 * max(1, len(t))


def compilar_bytecode(src_text, out_path, level):
    """Envia el codigo al compilador OFICIAL de MTA y guarda el bytecode.

    Devuelve (ok, mensaje). El bytecode es binario; si la respuesta es texto
    legible, se trata de un error del compilador y lo devolvemos.
    """
    tmp = out_path + ".src.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src_text)
    try:
        cmd = [
            "curl", "-s", "-X", "POST",
            "-F", "compile=1",
            "-F", "debug=0",
            "-F", "obfuscate=%d" % int(level),
            "-F", "luasource=@%s" % tmp,
            MTA_LUAC_URL,
            "-o", out_path,
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=90)
        if r.returncode != 0:
            return False, "curl fallo: " + r.stderr.decode("utf-8", "replace")[:200]
        if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
            return False, "El compilador devolvio una respuesta vacia (sin internet?)"
        with open(out_path, "rb") as f:
            data = f.read()
        if _es_mensaje_de_error(data):
            msg = data.decode("utf-8", "replace").strip()
            return False, "El compilador rechazo el script: " + msg[:200]
        # Es binario => bytecode valido (curl ya lo dejo escrito en out_path)
        return True, ""
    except FileNotFoundError:
        return False, "No se encontro 'curl'. Instalalo con: apt install curl -y"
    except subprocess.TimeoutExpired:
        return False, "El compilador tardo demasiado (timeout)."
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def compilar_archivo(cfg, nombre):
    ruta = os.path.join(INPUT_DIR, nombre)
    with open(ruta, "r", encoding="utf-8") as f:
        code = f.read()
    salida = os.path.join(OUTPUT_DIR, nombre)

    if cfg.get("bytecode"):
        # MODO PROFESIONAL (como Hyper): codigo limpio -> compilador oficial.
        # Solo se inyecta el guardia de licencia (si el bloqueo esta activo).
        pre = ob.obfuscate(
            code,
            do_strings=False,
            do_minify=False,
            do_wrap=False,
            ip_lock=cfg["ip_lock"],
            license_url=cfg.get("license_url", ""),
            license_key=cfg.get("license_key", ""),
        )
        ok, msg = compilar_bytecode(pre, salida, cfg.get("obf_level", 3))
        if not ok:
            with open(salida, "w", encoding="utf-8") as f:
                f.write(pre)
            raise RuntimeError(msg + " (se guardo sin bytecode)")
        return len(code), os.path.getsize(salida), salida

    # MODO OFFLINE (sin internet): capas de texto locales
    result = ob.obfuscate(
        code,
        do_strings=cfg["strings"],
        do_minify=cfg["minify"],
        do_wrap=cfg["wrap"],
        ip_lock=cfg["ip_lock"],
        license_url=cfg.get("license_url", ""),
        license_key=cfg.get("license_key", ""),
    )
    with open(salida, "w", encoding="utf-8") as f:
        f.write(result)
    return len(code), len(result), salida

def compilar_todo(cfg):
    archivos = listar_lua()
    if not archivos:
        print("\n  No hay archivos .lua en la carpeta input/")
        print("  Copia ahi tus scripts y vuelve a intentar.")
        pausa(); return
    if cfg["ip_lock"] and not cfg.get("license_url"):
        print("\n  AVISO: el bloqueo esta activado pero sin URL de licencias configurada.")
        if input("  Compilar igualmente? (s/n): ").strip().lower() != "s":
            return
    if cfg["ip_lock"] and not cfg.get("licenses"):
        print("\n  AVISO: no hay ningun servidor con licencia en el panel.")
        print("  Si compilas asi, ningun servidor podra arrancar el recurso.")
        if input("  Compilar igualmente? (s/n): ").strip().lower() != "s":
            return
    print("")
    marca = " [+bloqueo IP]" if cfg["ip_lock"] else ""
    for nombre in archivos:
        try:
            o, n, salida = compilar_archivo(cfg, nombre)
            print("  [OK] %-22s %6d -> %6d bytes%s" % (nombre, o, n, marca))
        except Exception as e:
            print("  [ERROR] %-22s %s" % (nombre, e))
    print("\n  Listo. Archivos protegidos en: %s" % OUTPUT_DIR)
    pausa()

def compilar_uno(cfg):
    archivos = listar_lua()
    if not archivos:
        print("\n  No hay archivos .lua en input/")
        pausa(); return
    print("\n  Archivos disponibles:")
    for i, a in enumerate(archivos, 1):
        print("   %d) %s" % (i, a))
    sel = input("\n  Numero del archivo (ENTER para cancelar): ").strip()
    if not sel.isdigit():
        return
    idx = int(sel) - 1
    if 0 <= idx < len(archivos):
        try:
            o, n, salida = compilar_archivo(cfg, archivos[idx])
            print("\n  [OK] %s  (%d -> %d bytes)" % (archivos[idx], o, n))
            print("  Guardado en: %s" % salida)
        except Exception as e:
            print("\n  [ERROR] %s: %s" % (archivos[idx], e))
    pausa()

# --------------------------------------------------------------------------

def menu_capas(cfg):
    while True:
        os.system("clear")
        print("==== CAPAS DE PROTECCION ====\n")
        print("  -- Compilacion oficial MTA (RECOMENDADO, como Hyper) --")
        print("  4) Compilar a bytecode oficial ...... [%s]" % onoff(cfg["bytecode"]))
        print("  5) Nivel de ofuscacion (0-3) ........ [%d]" % cfg.get("obf_level", 3))
        print("\n  -- Capas de TEXTO (solo se usan si el bytecode esta en OFF) --")
        print("  1) Cifrar textos (strings) .......... [%s]" % onoff(cfg["strings"]))
        print("  2) Minificar (quitar espacios) ...... [%s]" % onoff(cfg["minify"]))
        print("  3) Cargador cifrado (loadstring) .... [%s]" % onoff(cfg["wrap"]))
        if cfg["bytecode"]:
            print("\n  NOTA: con bytecode ON se compila el codigo LIMPIO (resultado")
            print("        compacto y profesional). Las capas 1-3 quedan ignoradas.")
        else:
            print("\n  NOTA: bytecode OFF = modo sin internet. Se usan las capas 1-3,")
            print("        pero cifrar textos y cargador INFLAN mucho el archivo.")
        print("\n  0) Volver")
        op = input("\n  Opcion: ").strip()
        if op == "1": cfg["strings"] = not cfg["strings"]
        elif op == "2": cfg["minify"] = not cfg["minify"]
        elif op == "3": cfg["wrap"] = not cfg["wrap"]
        elif op == "4": cfg["bytecode"] = not cfg["bytecode"]
        elif op == "5":
            v = input("  Nivel (0=ninguno, 3=maximo): ").strip()
            if v.isdigit() and 0 <= int(v) <= 3:
                cfg["obf_level"] = int(v)
        elif op == "0":
            guardar_config(cfg); return
        guardar_config(cfg)

def es_ip_valida(ip):
    partes = ip.split(".")
    if len(partes) != 4:
        return False
    for p in partes:
        if not p.isdigit() or not (0 <= int(p) <= 255):
            return False
    return True

LICENSE_FILE = os.path.join(HERE, "licencias.lua")

def contenido_licencias(cfg):
    """Construye el texto del archivo de licencias.
    Activa  -> la CLAVE del sistema (debe coincidir con la del recurso).
    Bloqueada -> false.
    """
    key = cfg.get("license_key", "")
    pares = []
    coment = ["-- Archivo de licencias (modo remoto). Generado por el panel.",
              "-- IP activa lleva la CLAVE del sistema; bloqueada = false.", ""]
    for e in cfg.get("licenses", []):
        valor = "false" if e.get("blocked") else ('"%s"' % key)
        pares.append('["%s"]=%s' % (e["ip"], valor))
        estado = "BLOQUEADO" if e.get("blocked") else "activa"
        coment.append("-- %-16s %-10s %-18s %s" % (
            e["ip"], estado, e.get("key", "-"), e.get("name", "")))
    return "\n".join(coment) + "\nreturn {" + ",".join(pares) + "}\n"

def exportar_licencias(cfg):
    contenido = contenido_licencias(cfg)
    with open(LICENSE_FILE, "w", encoding="utf-8") as f:
        f.write(contenido)
    return LICENSE_FILE

def _gh_headers(token):
    return ["-H", "Authorization: Bearer " + token,
            "-H", "Accept: application/vnd.github+json",
            "-H", "User-Agent: compilador-lua-mta"]

def subir_github(cfg):
    """Sube el archivo de licencias a GitHub usando la API (token)."""
    import base64
    token = cfg.get("gh_token", "")
    owner = cfg.get("gh_owner", "")
    repo = cfg.get("gh_repo", "")
    branch = cfg.get("gh_branch", "main")
    path = cfg.get("gh_path", "licencias.lua")
    if not (token and owner and repo):
        return False, "Falta configurar GitHub (opcion 7 del panel)."
    api = "https://api.github.com/repos/%s/%s/contents/%s" % (owner, repo, path)
    # 1) obtener el sha actual del archivo (si existe)
    sha = None
    get = subprocess.run(["curl", "-fsSL"] + _gh_headers(token) + [api + "?ref=" + branch],
                         capture_output=True)
    if get.returncode == 0:
        try:
            sha = json.loads(get.stdout.decode("utf-8")).get("sha")
        except Exception:
            sha = None
    # 2) subir el contenido nuevo
    contenido = contenido_licencias(cfg)
    body = {
        "message": "Actualizar licencias",
        "content": base64.b64encode(contenido.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha
    put = subprocess.run(
        ["curl", "-sS", "-X", "PUT"] + _gh_headers(token) + ["-d", json.dumps(body), api],
        capture_output=True)
    out = put.stdout.decode("utf-8", "replace")
    if '"content"' in out and '"sha"' in out:
        return True, "Lista subida a GitHub correctamente."
    # extraer mensaje de error de la API
    try:
        msg = json.loads(out).get("message", out[:150])
    except Exception:
        msg = out[:150]
    return False, "GitHub respondio: " + msg

import random as _random
import datetime as _dt

def generar_id_licencia():
    """Genera un ID de licencia unico, tipo HX-XXXX-XXXX-XXXX."""
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    grupos = ["".join(_random.choice(chars) for _ in range(4)) for _ in range(3)]
    return "HX-" + "-".join(grupos)

def _sync_github(cfg):
    """Si GitHub esta configurado, sube la lista automaticamente."""
    if cfg.get("gh_token"):
        ok, msg = subir_github(cfg)
        print("  %s %s" % ("[OK]" if ok else "[ERROR]", msg))
    else:
        exportar_licencias(cfg)
        print("  (lista guardada en licencias.lua; subela a GitHub o configura el token en opcion 7)")

def menu_ip(cfg):
    while True:
        os.system("clear")
        print("==== PANEL DE LICENCIAS (remoto) ====\n")
        print("  Bloqueo: [%s]" % onoff(cfg["ip_lock"]).strip())
        print("  URL    : %s" % (cfg.get("license_url") or "(sin configurar)"))
        print("  Clave   : %s  (doble proteccion: IP + clave)" % cfg.get("license_key", "(sin generar)"))
        gh = "conectado" if cfg.get("gh_token") else "NO configurado (subida manual)"
        print("  GitHub : %s" % gh)
        print("\n  Servidores con licencia (%d):" % len(cfg["licenses"]))
        if cfg["licenses"]:
            print("    %-3s %-16s %-10s %-18s %s" % ("#", "IP", "ESTADO", "LICENCIA", "NOMBRE"))
            for i, e in enumerate(cfg["licenses"], 1):
                estado = "BLOQUEADO" if e.get("blocked") else "activa"
                print("    %-3d %-16s %-10s %-18s %s" % (
                    i, e["ip"], estado, e.get("key", "-"), e.get("name", "")))
        else:
            print("    (ninguno)")
        print("\n  1) Activar / desactivar el bloqueo")
        print("  2) Anadir servidor (genera licencia)")
        print("  3) Bloquear / desbloquear un servidor")
        print("  4) Cambiar el nombre de un servidor")
        print("  5) Quitar un servidor (revoca su licencia)")
        print("  6) SUBIR la lista a GitHub ahora")
        print("  7) Configurar conexion con GitHub (token)")
        print("  0) Volver")
        op = input("\n  Opcion: ").strip()

        if op == "1":
            cfg["ip_lock"] = not cfg["ip_lock"]

        elif op == "2":
            ip = input("  IP del servidor: ").strip()
            if not es_ip_valida(ip):
                print("  IP no valida (ejemplo: 203.0.113.7)"); pausa()
            elif any(e["ip"] == ip for e in cfg["licenses"]):
                print("  Esa IP ya tiene licencia."); pausa()
            else:
                nombre = input("  Nombre para identificarla (ej: Servidor Juan): ").strip()
                lic = {
                    "ip": ip, "name": nombre, "blocked": False,
                    "key": generar_id_licencia(), "created": _dt.date.today().isoformat(),
                }
                cfg["licenses"].append(lic)
                guardar_config(cfg)
                print("\n  Licencia generada:")
                print("    IP      : %s" % ip)
                print("    Nombre  : %s" % (nombre or "(sin nombre)"))
                print("    Licencia: %s" % lic["key"])
                _sync_github(cfg)
                pausa()

        elif op == "3":
            e = _elegir_licencia(cfg, "bloquear/desbloquear")
            if e:
                e["blocked"] = not e.get("blocked")
                guardar_config(cfg)
                print("  %s -> %s" % (e["ip"], "BLOQUEADO" if e["blocked"] else "activo"))
                _sync_github(cfg)
                pausa()

        elif op == "4":
            e = _elegir_licencia(cfg, "renombrar")
            if e:
                e["name"] = input("  Nuevo nombre: ").strip()
                print("  Nombre actualizado."); pausa()

        elif op == "5":
            e = _elegir_licencia(cfg, "quitar")
            if e:
                cfg["licenses"].remove(e)
                guardar_config(cfg)
                print("  Quitado: %s" % e["ip"])
                _sync_github(cfg)
                pausa()

        elif op == "6":
            print("")
            _sync_github(cfg)
            pausa()

        elif op == "7":
            os.system("clear")
            print("==== CONEXION CON GITHUB ====\n")
            print("  Permite que el menu suba la lista a GitHub solo (sin entrar a la web).")
            print("  Necesitas un token con permiso de escritura en tu repo.")
            print("  Crealo en: github.com -> Settings -> Developer settings ->")
            print("             Personal access tokens (fine-grained) -> con permiso")
            print("             'Contents: Read and write' en tu repo.\n")
            print("  owner : %s" % cfg.get("gh_owner"))
            print("  repo  : %s" % cfg.get("gh_repo"))
            print("  branch: %s" % cfg.get("gh_branch"))
            print("  path  : %s" % cfg.get("gh_path"))
            print("  token : %s" % ("(guardado)" if cfg.get("gh_token") else "(vacio)"))
            print("\n  1) Pegar/cambiar token")
            print("  2) Cambiar owner/repo/branch")
            print("  0) Volver")
            s = input("\n  Opcion: ").strip()
            if s == "1":
                t = input("  Pega tu token (se guarda local, no se sube): ").strip()
                if t:
                    cfg["gh_token"] = t
                    print("  Token guardado.")
                pausa()
            elif s == "2":
                o = input("  owner (%s): " % cfg.get("gh_owner")).strip()
                r = input("  repo (%s): " % cfg.get("gh_repo")).strip()
                b = input("  branch (%s): " % cfg.get("gh_branch")).strip()
                if o: cfg["gh_owner"] = o
                if r: cfg["gh_repo"] = r
                if b: cfg["gh_branch"] = b
                pausa()

        elif op == "0":
            guardar_config(cfg); return
        guardar_config(cfg)


def _elegir_licencia(cfg, accion):
    if not cfg["licenses"]:
        print("  No hay servidores registrados."); pausa(); return None
    for i, e in enumerate(cfg["licenses"], 1):
        estado = "BLOQUEADO" if e.get("blocked") else "activo"
        print("   %d) %-16s %-10s %s" % (i, e["ip"], estado, e.get("name", "")))
    sel = input("  Numero a %s (ENTER cancela): " % accion).strip()
    if sel.isdigit() and 1 <= int(sel) <= len(cfg["licenses"]):
        return cfg["licenses"][int(sel) - 1]
    return None

# --------------------------------------------------------------------------

def actualizar_herramienta(cfg):
    os.system("clear")
    print("==== ACTUALIZAR HERRAMIENTA ====\n")
    repo = cfg.get("repo_raw", "")
    print("  URL actual del repo:")
    print("    %s\n" % (repo or "(sin configurar)"))
    nueva = input("  URL raw del repo (ENTER para usar la de arriba): ").strip()
    if nueva:
        repo = nueva.rstrip("/")
        cfg["repo_raw"] = repo
        guardar_config(cfg)
    if not repo:
        print("\n  No hay URL configurada."); pausa(); return
    print("\n  Descargando ultima version...")
    ok = True
    for f in ("mta_obfuscator.py", "compilador.py"):
        url = repo + "/" + f
        destino = os.path.join(HERE, f)
        r = subprocess.run(["curl", "-fsSL", "-o", destino, url], capture_output=True)
        if r.returncode == 0 and os.path.exists(destino) and os.path.getsize(destino) > 0:
            print("    [OK] %s" % f)
        else:
            ok = False
            print("    [ERROR] %s (revisa la URL y que el repo sea publico)" % f)
    if ok:
        print("\n  Actualizado. CIERRA y vuelve a abrir 'compilador' para usar lo nuevo.")
        print("  IMPORTANTE: recompila tus recursos para que apliquen los cambios.")
    pausa()


def menu_principal():
    asegurar_carpetas()
    cfg = cargar_config()
    while True:
        os.system("clear")
        archivos = listar_lua()
        print("=========================================")
        print("     COMPILADOR LUA  -  MTA:SA")
        print("=========================================\n")
        print("  Entrada : %s   (%d .lua)" % (INPUT_DIR, len(archivos)))
        print("  Salida  : %s" % OUTPUT_DIR)
        print("  Capas   : strings[%s] minify[%s] wrap[%s]" %
              (onoff(cfg["strings"]).strip(), onoff(cfg["minify"]).strip(), onoff(cfg["wrap"]).strip()))
        print("  Bytecode: [%s] nivel %d  (compilador oficial MTA)" %
              (onoff(cfg["bytecode"]).strip(), cfg.get("obf_level", 3)))
        activos = len([e for e in cfg["licenses"] if not e.get("blocked")])
        bloqueados = len(cfg["licenses"]) - activos
        print("  Licencia: [%s] remoto  (%d activos, %d bloqueados)" %
              (onoff(cfg["ip_lock"]).strip(), activos, bloqueados))
        print("\n-----------------------------------------")
        print("  1) Compilar TODO lo de input/")
        print("  2) Compilar un archivo concreto")
        print("  3) Configurar capas de proteccion")
        print("  4) Panel de licencias (control por IP)")
        print("  5) Ver carpeta de entrada")
        print("  6) Actualizar herramienta (descargar ultima version)")
        print("  0) Salir")
        op = input("\n  Opcion: ").strip()
        if op == "1": compilar_todo(cfg)
        elif op == "2": compilar_uno(cfg)
        elif op == "3": menu_capas(cfg)
        elif op == "4": menu_ip(cfg)
        elif op == "5":
            print("\n  Carpeta: %s" % INPUT_DIR)
            if archivos:
                for a in archivos: print("   - %s" % a)
            else:
                print("   (vacia: copia aqui tus .lua)")
            pausa()
        elif op == "6": actualizar_herramienta(cfg)
        elif op == "0":
            print("\n  Hasta luego.\n"); return


if __name__ == "__main__":
    try:
        menu_principal()
    except KeyboardInterrupt:
        print("\n  Cancelado.\n")
