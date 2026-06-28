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

# Importamos el motor de ofuscacion (debe estar en la misma carpeta)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mta_obfuscator as ob

INPUT_DIR = os.path.join(HERE, "input")
OUTPUT_DIR = os.path.join(HERE, "output")
CONFIG_FILE = os.path.join(HERE, "config.json")

DEFAULT_CONFIG = {
    "strings": True,
    "minify": True,
    "wrap": True,
    "ip_lock": False,
    "allowed_ips": [],
}

# --------------------------------------------------------------------------

def cargar_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg = dict(DEFAULT_CONFIG)
            cfg.update(data)
            return cfg
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)

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

def compilar_archivo(cfg, nombre):
    ruta = os.path.join(INPUT_DIR, nombre)
    with open(ruta, "r", encoding="utf-8") as f:
        code = f.read()
    result = ob.obfuscate(
        code,
        do_strings=cfg["strings"],
        do_minify=cfg["minify"],
        do_wrap=cfg["wrap"],
        ip_lock=cfg["ip_lock"],
        allowed_ips=cfg["allowed_ips"],
    )
    salida = os.path.join(OUTPUT_DIR, nombre)
    with open(salida, "w", encoding="utf-8") as f:
        f.write(result)
    return len(code), len(result), salida

def compilar_todo(cfg):
    archivos = listar_lua()
    if not archivos:
        print("\n  No hay archivos .lua en la carpeta input/")
        print("  Copia ahi tus scripts y vuelve a intentar.")
        pausa(); return
    if cfg["ip_lock"] and not cfg["allowed_ips"]:
        print("\n  AVISO: el bloqueo por IP esta activado pero NO hay IPs permitidas.")
        print("  Ningun servidor podria arrancar el script. Anade tu IP primero (opcion 4).")
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
        o, n, salida = compilar_archivo(cfg, archivos[idx])
        print("\n  [OK] %s  (%d -> %d bytes)" % (archivos[idx], o, n))
        print("  Guardado en: %s" % salida)
    pausa()

# --------------------------------------------------------------------------

def menu_capas(cfg):
    while True:
        os.system("clear")
        print("==== CAPAS DE PROTECCION ====\n")
        print("  1) Cifrar textos (strings) .......... [%s]" % onoff(cfg["strings"]))
        print("  2) Minificar (quitar espacios) ...... [%s]" % onoff(cfg["minify"]))
        print("  3) Cargador cifrado (loadstring) .... [%s]" % onoff(cfg["wrap"]))
        print("\n  0) Volver")
        op = input("\n  Opcion: ").strip()
        if op == "1": cfg["strings"] = not cfg["strings"]
        elif op == "2": cfg["minify"] = not cfg["minify"]
        elif op == "3": cfg["wrap"] = not cfg["wrap"]
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

def menu_ip(cfg):
    while True:
        os.system("clear")
        print("==== BLOQUEO POR IP (licencia) ====\n")
        print("  Estado: [%s]" % onoff(cfg["ip_lock"]))
        print("  IPs permitidas (%d):" % len(cfg["allowed_ips"]))
        if cfg["allowed_ips"]:
            for ip in cfg["allowed_ips"]:
                print("     - %s" % ip)
        else:
            print("     (ninguna)")
        print("\n  1) Activar / desactivar bloqueo")
        print("  2) Anadir una IP")
        print("  3) Quitar una IP")
        print("  0) Volver")
        op = input("\n  Opcion: ").strip()
        if op == "1":
            cfg["ip_lock"] = not cfg["ip_lock"]
        elif op == "2":
            ip = input("  IP del servidor a permitir: ").strip()
            if es_ip_valida(ip):
                if ip not in cfg["allowed_ips"]:
                    cfg["allowed_ips"].append(ip)
                    print("  Anadida: %s" % ip)
                else:
                    print("  Esa IP ya estaba.")
            else:
                print("  IP no valida (ejemplo correcto: 203.0.113.7)")
            pausa()
        elif op == "3":
            if not cfg["allowed_ips"]:
                print("  No hay IPs que quitar."); pausa()
            else:
                for i, ip in enumerate(cfg["allowed_ips"], 1):
                    print("   %d) %s" % (i, ip))
                sel = input("  Numero a quitar: ").strip()
                if sel.isdigit() and 1 <= int(sel) <= len(cfg["allowed_ips"]):
                    quitada = cfg["allowed_ips"].pop(int(sel) - 1)
                    print("  Quitada: %s" % quitada)
                pausa()
        elif op == "0":
            guardar_config(cfg); return
        guardar_config(cfg)

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
        print("  IP-lock : [%s]  (%d IPs permitidas)" %
              (onoff(cfg["ip_lock"]).strip(), len(cfg["allowed_ips"])))
        print("\n-----------------------------------------")
        print("  1) Compilar TODO lo de input/")
        print("  2) Compilar un archivo concreto")
        print("  3) Configurar capas de proteccion")
        print("  4) Bloqueo por IP (licencia)")
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
