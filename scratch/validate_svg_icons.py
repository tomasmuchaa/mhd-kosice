import xml.etree.ElementTree as ET

def get_line_font_size(line_str):
    l = len(str(line_str or ''))
    if l <= 2: return 16
    if l == 3: return 13
    return 10.5

# Test model icons definitions in JS/SVG
test_models = {
    # Električky
    "Vario LF2+": "vario",
    "Pragoimex Vario LF": "vario",
    "ČKD Tatra KT8D5.RN2": "kt8d5",
    "ČKD Tatra T6A5": "t6a5",
    "Električka DPMK": "tram",
    # Elektrobusy
    "SOR NS 18 Electric": "sor-ns18-electric",
    "SOR EBN 11": "sor-ebn",
    "SOR EBN 10.5": "sor-ebn",
    # Plynové
    "SOR NSG 18": "sor-nsg18",
    "SOR NSG 12": "sor-nsg12",
    "SOR NBG 12 City": "sor-nbg12",
    # Naftové SOR
    "SOR NB 18 City": "sor-nb18",
    "SOR NB 12 City": "sor-nb12",
    "SOR BN 9,5": "sor-bn95",
    "SOR C 10,5": "sor-c105",
    # Solaris
    "Solaris Urbino 18,75 III": "solaris-u1875",
    "Solaris Urbino 18 III": "solaris-u18",
    "Solaris Urbino 15 II / III": "solaris-u15",
    "Solaris Urbino 12 IV": "solaris-u12-iv",
    "Solaris Urbino 12 III Hybrid": "solaris-u12-hybrid",
    "Solaris Urbino 12": "solaris-u12",
    # Minibus a historické
    "Iveco Rosero First FCLLI": "rosero",
    "Ikarus 280.08/A": "ikarus",
    "Karosa B 832.1654": "karosa",
    "Autobus DPMK": "standard"
}

print(f"Pripravených {len(test_models)} modelov na validáciu.")
