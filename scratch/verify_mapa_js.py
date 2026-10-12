# -*- coding: utf-8 -*-
import sys
import re
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding='utf-8')

with open(r"C:\Users\tomas\mhd_kosice\mapa.html", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Kontrola, či sa nachádzajú všetky funkcie generátorov
required_functions = [
    "getVehicleModelKey",
    "getVehicleShapeType",
    "getLineFontSize",
    "getDelayBarColor",
    "escapeXml",
    "renderVarioLfSvg",
    "renderKt8d5Svg",
    "renderT6a5Svg",
    "renderGeneralTramSvg",
    "renderSorNs18ElectricSvg",
    "renderSorEbnSvg",
    "renderSorNsg18Svg",
    "renderSorNsg12Svg",
    "renderSorNb18Svg",
    "renderSorNb12Svg",
    "renderSorNbg12Svg",
    "renderSorBn95Svg",
    "renderSorC105Svg",
    "renderSolarisU18Svg",
    "renderSolarisU15Svg",
    "renderSolarisU12IvSvg",
    "renderSolarisU12HybridSvg",
    "renderSolarisU12Svg",
    "renderRoseroSvg",
    "renderIkarus280Svg",
    "renderKarosaB832Svg",
    "renderGeneralBusSvg",
    "createVehicleMarkerIcon"
]

all_found = True
for fn in required_functions:
    if f"function {fn}(" not in content:
        print(f"CHÝBA funkcia: {fn}")
        all_found = False
    else:
        print(f"[OK] Nájdená: {fn}")

if all_found:
    print("\nVšetky funkcie sú v poriadku prítomné!")

# 2. Kontrola vyváženosti zátvoriek v JS kóde
# Vyhľadáme hlavný blok
start = content.find("function getVehicleModelKey(v) {")
end = content.find("function buildPopupHtml(v) {")
if start != -1 and end != -1:
    js_chunk = content[start:end]
    open_curly = js_chunk.count('{')
    close_curly = js_chunk.count('}')
    print(f"\nAnalýza syntaxe bloku JS: {{ = {open_curly}, }} = {close_curly}")
    if open_curly == close_curly:
        print("[OK] Zložené zátvorky sú dokonale vyvážené!")
    else:
        print("[CHYBA] Nevyvážené zložené zátvorky!")

    open_round = js_chunk.count('(')
    close_round = js_chunk.count(')')
    print(f"Okrúhle zátvorky: ( = {open_round}, ) = {close_round}")
    if open_round == close_round:
        print("[OK] Okrúhle zátvorky sú dokonale vyvážené!")
    else:
        print("[CHYBA] Nevyvážené okrúhle zátvorky!")
