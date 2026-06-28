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
    "license_mode": "local", # "local" (incrustada) o "remote" (URL)
    "license_url": "",       # URL del archivo de licencias (modo remoto)
    "bytecode": True,
    "obf_level": 3,
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
            return cfg
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)

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
        # NO aplicamos strings/minify/wrap porque solo inflan el bytecode.
        # Lo unico que inyectamos (si toca) es el guardia de IP.
        pre = ob.obfuscate(
            code,
            do_strings=False,
            do_minify=False,
            do_wrap=False,
            ip_lock=cfg["ip_lock"],
            allowed_ips=ips_activas(cfg),
            license_mode=cfg.get("license_mode", "local"),
            license_url=cfg.get("license_url", ""),
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
        allowed_ips=ips_activas(cfg),
        license_mode=cfg.get("license_mode", "local"),
        license_url=cfg.get("license_url", ""),
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
    modo = cfg.get("license_mode", "local")
    if cfg["ip_lock"] and modo == "local" and not ips_activas(cfg):
        print("\n  AVISO: el bloqueo por IP esta activado (modo local) pero NO hay")
        print("  IPs con permiso. Ningun servidor podria arrancar. Anade tu IP (opcion 4).")
        if input("  Compilar igualmente? (s/n): ").strip().lower() != "s":
            return
    if cfg["ip_lock"] and modo == "remote" and not cfg.get("license_url"):
        print("\n  AVISO: modo remoto activado pero sin URL de licencias configurada.")
        if input("  Compilar igualmente? (s/n): ").strip().lower() != "s":
            return
    print("")
    for nombre in archivos:
        try:
            o, n, salida = compilar_archivo(cfg, nombre)
            print("  [OK] %-25s %6d -> %6d bytes" % (nombre, o, n))
        except Exception as e:
            print("  [ERROR] %-25s %s" % (nombre, e))
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

def exportar_licencias(cfg):
    """Genera el archivo de licencias para el modo remoto."""
    pares = []
    coment = ["-- Archivo de licencias (modo remoto). Editalo y subelo a tu URL.",
              "-- Para bloquear: cambia true por false en la IP correspondiente.", ""]
    for e in cfg.get("licenses", []):
        permitido = "false" if e.get("blocked") else "true"
        pares.append('["%s"]=%s' % (e["ip"], permitido))
        estado = "BLOQUEADO" if e.get("blocked") else "activa"
        coment.append("-- %-16s %-10s %-18s %s" % (
            e["ip"], estado, e.get("key", "-"), e.get("name", "")))
    contenido = "\n".join(coment) + "\nreturn {" + ",".join(pares) + "}\n"
    with open(LICENSE_FILE, "w", encoding="utf-8") as f:
        f.write(contenido)
    return LICENSE_FILE

import random as _random
import datetime as _dt

def generar_id_licencia():
    """Genera un ID de licencia unico, tipo HX-XXXX-XXXX-XXXX."""
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    grupos = ["".join(_random.choice(chars) for _ in range(4)) for _ in range(3)]
    return "HX-" + "-".join(grupos)

def menu_ip(cfg):
    while True:
        os.system("clear")
        modo = cfg.get("license_mode", "local")
        print("==== PANEL DE LICENCIAS (control por IP) ====\n")
        print("  Bloqueo: [%s]    Modo: %s" % (onoff(cfg["ip_lock"]).strip(), modo.upper()))
        if modo == "remote":
            print("  URL    : %s" % (cfg.get("license_url") or "(sin configurar)"))
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
        print("  6) Modo de licencia (local / remoto)")
        print("  7) Generar archivo de licencias (modo remoto)")
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
                    "ip": ip,
                    "name": nombre,
                    "blocked": False,
                    "key": generar_id_licencia(),
                    "created": _dt.date.today().isoformat(),
                }
                cfg["licenses"].append(lic)
                print("\n  Licencia generada:")
                print("    IP      : %s" % ip)
                print("    Nombre  : %s" % (nombre or "(sin nombre)"))
                print("    Licencia: %s" % lic["key"])
                if cfg.get("license_mode") == "remote":
                    print("\n  Recuerda regenerar y subir el archivo de licencias (opcion 7).")
                pausa()

        elif op == "3":
            e = _elegir_licencia(cfg, "bloquear/desbloquear")
            if e:
                e["blocked"] = not e.get("blocked")
                print("  %s -> %s" % (e["ip"], "BLOQUEADO" if e["blocked"] else "activo"))
                if cfg.get("license_mode") == "remote":
                    print("  (recuerda regenerar y subir el archivo de licencias, opcion 7)")
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
                print("  Quitado: %s" % e["ip"]); pausa()

        elif op == "6":
            print("\n  1) LOCAL  (la lista va dentro del archivo; bloquear = recompilar)")
            print("  2) REMOTO (consulta una URL tuya; bloquear = editar la lista, sin recompilar)")
            m = input("  Elige modo: ").strip()
            if m == "1":
                cfg["license_mode"] = "local"
            elif m == "2":
                cfg["license_mode"] = "remote"
                url = input("  URL del archivo de licencias (https://...): ").strip()
                if url:
                    cfg["license_url"] = url
            pausa()

        elif op == "7":
            ruta = exportar_licencias(cfg)
            print("\n  Archivo generado: %s" % ruta)
            print("  Subelo a la URL que configuraste (ej: tu repo de GitHub).")
            print("  Para bloquear a alguien luego: cambias su estado aqui,")
            print("  regeneras este archivo y lo vuelves a subir. Sin recompilar.")
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
        print("  Licencia: [%s] modo %s  (%d activos, %d bloqueados)" %
              (onoff(cfg["ip_lock"]).strip(), cfg.get("license_mode", "local").upper(),
               activos, bloqueados))
        print("\n-----------------------------------------")
        print("  1) Compilar TODO lo de input/")
        print("  2) Compilar un archivo concreto")
        print("  3) Configurar capas de proteccion")
        print("  4) Panel de licencias (control por IP)")
        print("  5) Ver carpeta de entrada")
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
        elif op == "0":
            print("\n  Hasta luego.\n"); return


if __name__ == "__main__":
    try:
        menu_principal()
    except KeyboardInterrupt:
        print("\n  Cancelado.\n")
