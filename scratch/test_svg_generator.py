import xml.etree.ElementTree as ET

def get_line_font_size(line_str):
    l = len(str(line_str or ''))
    if l <= 2: return 16
    if l == 3: return 13
    return 10.5

def escape_xml(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

svg_generators = {}

# 1. Vario LF2+ / Vario LF
def render_vario_lf(line="9", delay_color="#facc15"):
    font_size = get_line_font_size(line)
    safe_line = escape_xml(line)
    clip_id = "clip-vario"
    delay_style = f"fill: {delay_color} !important;" if delay_color and delay_color != "transparent" else "display: none;"
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 48" width="44" height="48" class="veh-front-svg">
      <defs>
        <clipPath id="{clip_id}">
          <polygon points="8.5,14 35.5,14 34,34 10,34"/>
        </clipPath>
      </defs>
      <g stroke="#334155" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none">
        <path d="M 18 10 L 25 3 L 28 5"/>
        <line x1="15" y1="3" x2="33" y2="3" stroke="#0f172a" stroke-width="2.6"/>
        <line x1="20" y1="7" x2="26" y2="7" stroke-width="1.4"/>
      </g>
      <polygon points="6,11 38,11 36,41 8,41" fill="#eab308" stroke="#fde047" stroke-width="2.5" stroke-linejoin="round"/>
      <rect x="3" y="16" width="2.5" height="7" rx="1.2" fill="#1e293b"/>
      <rect x="38.5" y="16" width="2.5" height="7" rx="1.2" fill="#1e293b"/>
      <polygon points="8.5,14 35.5,14 34,34 10,34" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
      <rect class="veh-delay-bar" x="8.5" y="14" width="27" height="5.5" fill="{delay_color}" clip-path="url(#{clip_id})" style="{delay_style}"/>
      <text x="22" y="26.5" text-anchor="middle" dominant-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="{font_size}px" fill="#0f172a">{safe_line}</text>
      <path d="M 8 36 L 22 38.5 L 36 36 L 36 41 L 8 41 Z" fill="#1e3a8a" opacity="0.95"/>
      <ellipse cx="12" cy="37.5" rx="2.5" ry="1.6" transform="rotate(-15 12 37.5)" fill="#fef08a" stroke="#ca8a04" stroke-width="0.7"/>
      <circle cx="16" cy="38" r="1.3" fill="#ffffff" stroke="#ca8a04" stroke-width="0.6"/>
      <ellipse cx="32" cy="37.5" rx="2.5" ry="1.6" transform="rotate(15 32 37.5)" fill="#fef08a" stroke="#ca8a04" stroke-width="0.7"/>
      <circle cx="28" cy="38" r="1.3" fill="#ffffff" stroke="#ca8a04" stroke-width="0.6"/>
      <rect x="14" y="42" width="16" height="2" rx="1" fill="#1e293b"/>
      <rect x="8" y="42" width="4.5" height="4.5" rx="1" fill="#475569" stroke="#0f172a" stroke-width="1"/>
      <line x1="7.5" y1="46.5" x2="13" y2="46.5" stroke="#0f172a" stroke-width="1.5" stroke-linecap="round"/>
      <rect x="31.5" y="42" width="4.5" height="4.5" rx="1" fill="#475569" stroke="#0f172a" stroke-width="1"/>
      <line x1="31" y1="46.5" x2="36.5" y2="46.5" stroke="#0f172a" stroke-width="1.5" stroke-linecap="round"/>
    </svg>
    """
svg_generators["vario"] = render_vario_lf

# 2. ČKD Tatra KT8D5.RN2
def render_kt8d5(line="R1", delay_color="#ef4444"):
    font_size = get_line_font_size(line)
    safe_line = escape_xml(line)
    clip_id = "clip-kt8d5"
    delay_style = f"fill: {delay_color} !important;" if delay_color and delay_color != "transparent" else "display: none;"
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 46 48" width="46" height="48" class="veh-front-svg">
      <defs>
        <clipPath id="{clip_id}">
          <rect x="7.5" y="14" width="31" height="20" rx="1.5"/>
        </clipPath>
      </defs>
      <g stroke="#334155" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none">
        <path d="M 17 11 L 23 3 L 29 11"/>
        <line x1="19" y1="8" x2="27" y2="8" stroke-width="1.5"/>
        <line x1="13" y1="3" x2="33" y2="3" stroke="#0f172a" stroke-width="2.8"/>
      </g>
      <rect x="5" y="11" width="36" height="31" rx="2" fill="#eab308" stroke="#fde047" stroke-width="2.5"/>
      <rect x="2" y="15" width="2.5" height="8" rx="0.8" fill="#1e293b"/>
      <line x1="4.5" y1="17" x2="5" y2="17" stroke="#0f172a" stroke-width="1.5"/>
      <rect x="41.5" y="15" width="2.5" height="8" rx="0.8" fill="#1e293b"/>
      <line x1="41" y1="17" x2="41.5" y2="17" stroke="#0f172a" stroke-width="1.5"/>
      <rect x="7.5" y="14" width="31" height="20" rx="1.5" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
      <line x1="12" y1="14" x2="12" y2="34" stroke="#94a3b8" stroke-width="0.9"/>
      <line x1="34" y1="14" x2="34" y2="34" stroke="#94a3b8" stroke-width="0.9"/>
      <rect class="veh-delay-bar" x="7.5" y="14" width="31" height="5.5" fill="{delay_color}" clip-path="url(#{clip_id})" style="{delay_style}"/>
      <text x="23" y="26.5" text-anchor="middle" dominant-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="{font_size}px" fill="#0f172a">{safe_line}</text>
      <rect x="5" y="35" width="36" height="6.5" rx="1" fill="#b91c1c" stroke="#991b1b" stroke-width="1"/>
      <rect x="8.5" y="36.5" width="4.5" height="3" rx="0.8" fill="#fef08a" stroke="#ca8a04" stroke-width="0.7"/>
      <rect x="13.5" y="37" width="2" height="2" rx="0.5" fill="#f97316"/>
      <rect x="33" y="36.5" width="4.5" height="3" rx="0.8" fill="#fef08a" stroke="#ca8a04" stroke-width="0.7"/>
      <rect x="30.5" y="37" width="2" height="2" rx="0.5" fill="#f97316"/>
      <rect x="19" y="37" width="8" height="2.5" rx="0.8" fill="#1e293b"/>
      <rect x="14" y="42" width="18" height="2" rx="1" fill="#1e293b"/>
      <rect x="8" y="42" width="4.5" height="4.5" rx="1" fill="#475569" stroke="#0f172a" stroke-width="1"/>
      <line x1="7.5" y1="46.5" x2="13" y2="46.5" stroke="#0f172a" stroke-width="1.5" stroke-linecap="round"/>
      <rect x="33.5" y="42" width="4.5" height="4.5" rx="1" fill="#475569" stroke="#0f172a" stroke-width="1"/>
      <line x1="33" y1="46.5" x2="38.5" y2="46.5" stroke="#0f172a" stroke-width="1.5" stroke-linecap="round"/>
    </svg>
    """
svg_generators["kt8d5"] = render_kt8d5

# 3. ČKD Tatra T6A5
def render_t6a5(line="6", delay_color="transparent"):
    font_size = get_line_font_size(line)
    safe_line = escape_xml(line)
    clip_id = "clip-t6a5"
    delay_style = f"fill: {delay_color} !important;" if delay_color and delay_color != "transparent" else "display: none;"
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 48" width="44" height="48" class="veh-front-svg">
      <defs>
        <clipPath id="{clip_id}">
          <rect x="8" y="14" width="28" height="20" rx="2.5"/>
        </clipPath>
      </defs>
      <g stroke="#334155" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none">
        <path d="M 17 11 L 22 4 L 27 11"/>
        <line x1="14" y1="4" x2="30" y2="4" stroke="#0f172a" stroke-width="2.6"/>
      </g>
      <polygon points="7,11 37,11 35.5,41 8.5,41" fill="#eab308" stroke="#ca8a04" stroke-width="2.5" stroke-linejoin="round"/>
      <rect x="3.5" y="15" width="2.5" height="7.5" rx="1" fill="#1e293b"/>
      <rect x="38" y="15" width="2.5" height="7.5" rx="1" fill="#1e293b"/>
      <rect x="8" y="14" width="28" height="20" rx="2.5" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
      <rect class="veh-delay-bar" x="8" y="14" width="28" height="5.5" fill="{delay_color}" clip-path="url(#{clip_id})" style="{delay_style}"/>
      <text x="22" y="26.5" text-anchor="middle" dominant-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="{font_size}px" fill="#0f172a">{safe_line}</text>
      <rect x="16" y="37" width="12" height="2.5" rx="1" fill="#1e293b"/>
      <circle cx="11.5" cy="37.5" r="2.2" fill="#fef08a" stroke="#ca8a04" stroke-width="0.8"/>
      <circle cx="14.5" cy="37.5" r="1.1" fill="#f97316"/>
      <circle cx="32.5" cy="37.5" r="2.2" fill="#fef08a" stroke="#ca8a04" stroke-width="0.8"/>
      <circle cx="29.5" cy="37.5" r="1.1" fill="#f97316"/>
      <rect x="14" y="42" width="16" height="2" rx="1" fill="#1e293b"/>
      <rect x="8" y="42" width="4.5" height="4.5" rx="1" fill="#475569" stroke="#0f172a" stroke-width="1"/>
      <line x1="7.5" y1="46.5" x2="13" y2="46.5" stroke="#0f172a" stroke-width="1.5" stroke-linecap="round"/>
      <rect x="31.5" y="42" width="4.5" height="4.5" rx="1" fill="#475569" stroke="#0f172a" stroke-width="1"/>
      <line x1="31" y1="46.5" x2="36.5" y2="46.5" stroke="#0f172a" stroke-width="1.5" stroke-linecap="round"/>
    </svg>
    """
svg_generators["t6a5"] = render_t6a5

# 4. Električka DPMK všeobecná
def render_general_tram(line="2", delay_color="transparent"):
    font_size = get_line_font_size(line)
    safe_line = escape_xml(line)
    clip_id = "clip-gen-tram"
    delay_style = f"fill: {delay_color} !important;" if delay_color and delay_color != "transparent" else "display: none;"
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 48" width="44" height="48" class="veh-front-svg">
      <defs>
        <clipPath id="{clip_id}">
          <rect x="8.5" y="14" width="27" height="20" rx="3.5"/>
        </clipPath>
      </defs>
      <g stroke="#334155" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none">
        <line x1="13" y1="3" x2="31" y2="3" stroke-width="2.6" stroke="#1e293b"/>
        <path d="M 17 11 L 22 4 L 28 11"/>
        <line x1="19" y1="8" x2="25" y2="8" stroke-width="1.6"/>
      </g>
      <rect x="6" y="11" width="32" height="31" rx="4" fill="#eab308" stroke="#fde047" stroke-width="2.5"/>
      <rect x="3" y="15" width="2.5" height="7" rx="1" fill="#1e293b"/>
      <rect x="38.5" y="15" width="2.5" height="7" rx="1" fill="#1e293b"/>
      <rect x="8.5" y="14" width="27" height="20" rx="3.5" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
      <rect class="veh-delay-bar" x="8.5" y="14" width="27" height="5.5" fill="{delay_color}" clip-path="url(#{clip_id})" style="{delay_style}"/>
      <text x="22" y="26.5" text-anchor="middle" dominant-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="{font_size}px" fill="#0f172a">{safe_line}</text>
      <rect x="16.5" y="36.5" width="11" height="3" rx="1.5" fill="#1e293b"/>
      <circle cx="11.5" cy="37.5" r="2.2" fill="#fef08a" stroke="#ca8a04" stroke-width="0.8"/>
      <circle cx="32.5" cy="37.5" r="2.2" fill="#fef08a" stroke="#ca8a04" stroke-width="0.8"/>
      <rect x="14" y="42" width="16" height="2" rx="1" fill="#1e293b"/>
      <rect x="8" y="42" width="4.5" height="4.5" rx="1" fill="#475569" stroke="#0f172a" stroke-width="1"/>
      <line x1="7.5" y1="46.5" x2="13" y2="46.5" stroke="#0f172a" stroke-width="1.5" stroke-linecap="round"/>
      <rect x="31.5" y="42" width="4.5" height="4.5" rx="1" fill="#475569" stroke="#0f172a" stroke-width="1"/>
      <line x1="31" y1="46.5" x2="36.5" y2="46.5" stroke="#0f172a" stroke-width="1.5" stroke-linecap="round"/>
    </svg>
    """
svg_generators["general-tram"] = render_general_tram

# 5. SOR NS 18 Electric
def render_sor_ns18_electric(line="71", delay_color="#f97316"):
    font_size = get_line_font_size(line)
    safe_line = escape_xml(line)
    clip_id = "clip-ns18-elec"
    delay_style = f"fill: {delay_color} !important;" if delay_color and delay_color != "transparent" else "display: none;"
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 46" width="48" height="46" class="veh-front-svg">
      <defs>
        <clipPath id="{clip_id}">
          <rect x="9" y="8" width="30" height="23" rx="6"/>
        </clipPath>
      </defs>
      <rect x="13" y="1" width="22" height="4.5" rx="2.2" fill="#15803d" stroke="#4ade80" stroke-width="1.2"/>
      <line x1="16" y1="3.2" x2="32" y2="3.2" stroke="#86efac" stroke-width="1.2" stroke-linecap="round"/>
      <path d="M 25 0.2 L 22.5 2.8 L 24.5 2.8 L 23 5.4 L 26 2.5 L 24 2.5 Z" fill="#fde047" stroke="#ca8a04" stroke-width="0.3"/>
      <rect x="7" y="40" width="7" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="34" y="40" width="7" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="5" y="5" width="38" height="36" rx="9" fill="#16a34a" stroke="#4ade80" stroke-width="2.5"/>
      <rect x="1.5" y="11" width="3.8" height="9" rx="1.8" fill="#0f172a" stroke="#4ade80" stroke-width="1"/>
      <line x1="5" y1="13" x2="2.5" y2="13" stroke="#15803d" stroke-width="1.5"/>
      <rect x="42.7" y="11" width="3.8" height="9" rx="1.8" fill="#0f172a" stroke="#4ade80" stroke-width="1"/>
      <line x1="43" y1="13" x2="45.5" y2="13" stroke="#15803d" stroke-width="1.5"/>
      <rect x="9" y="8" width="30" height="23" rx="6" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
      <rect class="veh-delay-bar" x="9" y="8" width="30" height="6" fill="{delay_color}" clip-path="url(#{clip_id})" style="{delay_style}"/>
      <text x="24" y="22.5" text-anchor="middle" dominant-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="{font_size}px" fill="#0f172a">{safe_line}</text>
      <rect x="17" y="33.5" width="14" height="3.5" rx="1.7" fill="#0f172a"/>
      <circle cx="24" cy="35.2" r="1.3" fill="#4ade80"/>
      <path d="M 9.5 34 Q 13 33.2 16 34.5" stroke="#fef08a" stroke-width="2.2" stroke-linecap="round" fill="none"/>
      <path d="M 38.5 34 Q 35 33.2 32 34.5" stroke="#fef08a" stroke-width="2.2" stroke-linecap="round" fill="none"/>
    </svg>
    """
svg_generators["sor-ns18-electric"] = render_sor_ns18_electric

# 6. SOR EBN 10.5 & 11
def render_sor_ebn(line="19", delay_color="#facc15"):
    font_size = get_line_font_size(line)
    safe_line = escape_xml(line)
    clip_id = "clip-ebn"
    delay_style = f"fill: {delay_color} !important;" if delay_color and delay_color != "transparent" else "display: none;"
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 46" width="44" height="46" class="veh-front-svg">
      <defs>
        <clipPath id="{clip_id}">
          <rect x="8" y="9" width="28" height="22" rx="4"/>
        </clipPath>
      </defs>
      <!-- Ikonický vysoký zaoblený hrb SOR EBN so symbolom blesku -->
      <path d="M 9 9 Q 22 1.5 35 9 Z" fill="#15803d" stroke="#4ade80" stroke-width="1.4"/>
      <path d="M 23 2.5 L 21 5 L 22.8 5 L 21.5 7.5 L 24.5 4.8 L 22.8 4.8 Z" fill="#fde047" stroke="#ca8a04" stroke-width="0.3"/>
      <rect x="7" y="39" width="6" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="31" y="39" width="6" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="5" y="7" width="34" height="34" rx="6" fill="#16a34a" stroke="#4ade80" stroke-width="2.5"/>
      <rect x="1.5" y="11" width="3.5" height="8" rx="1.5" fill="#0f172a" stroke="#4ade80" stroke-width="1"/>
      <rect x="39" y="11" width="3.5" height="8" rx="1.5" fill="#0f172a" stroke="#4ade80" stroke-width="1"/>
      <rect x="8" y="9" width="28" height="22" rx="4" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
      <rect class="veh-delay-bar" x="8" y="9" width="28" height="6" fill="{delay_color}" clip-path="url(#{clip_id})" style="{delay_style}"/>
      <text x="22" y="22" text-anchor="middle" dominant-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="{font_size}px" fill="#0f172a">{safe_line}</text>
      <!-- Okrúhle svetlá SOR EBN -->
      <rect x="15" y="32.5" width="14" height="3.5" rx="1.7" fill="#0f172a"/>
      <circle cx="10" cy="34" r="2.2" fill="#fef08a" stroke="#ca8a04" stroke-width="0.7"/>
      <circle cx="34" cy="34" r="2.2" fill="#fef08a" stroke="#ca8a04" stroke-width="0.7"/>
    </svg>
    """
svg_generators["sor-ebn"] = render_sor_ebn

# 7. SOR NSG 18 (kĺbový plynový CNG)
def render_sor_nsg18(line="72", delay_color="transparent"):
    font_size = get_line_font_size(line)
    safe_line = escape_xml(line)
    clip_id = "clip-nsg18"
    delay_style = f"fill: {delay_color} !important;" if delay_color and delay_color != "transparent" else "display: none;"
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 46" width="48" height="46" class="veh-front-svg">
      <defs>
        <clipPath id="{clip_id}">
          <rect x="9" y="9" width="30" height="22" rx="6"/>
        </clipPath>
      </defs>
      <!-- Mohutný strešný klenutý kryt plynových nádrží CNG s označením -->
      <path d="M 12 7 Q 24 0.5 36 7 Z" fill="#047857" stroke="#34d399" stroke-width="1.4"/>
      <rect x="18" y="3" width="12" height="3" rx="1" fill="#065f46"/>
      <text x="24" y="5" text-anchor="middle" dominant-baseline="central" font-size="2.4px" font-weight="900" fill="#a7f3d0" font-family="'JetBrains Mono', sans-serif">CNG</text>
      <rect x="7" y="40" width="7" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="34" y="40" width="7" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="5" y="6" width="38" height="35" rx="8" fill="#059669" stroke="#34d399" stroke-width="2.5"/>
      <rect x="1.5" y="11" width="3.8" height="9" rx="1.8" fill="#0f172a" stroke="#34d399" stroke-width="1"/>
      <rect x="42.7" y="11" width="3.8" height="9" rx="1.8" fill="#0f172a" stroke="#34d399" stroke-width="1"/>
      <rect x="9" y="9" width="30" height="22" rx="6" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
      <rect class="veh-delay-bar" x="9" y="9" width="30" height="6" fill="{delay_color}" clip-path="url(#{clip_id})" style="{delay_style}"/>
      <text x="24" y="22" text-anchor="middle" dominant-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="{font_size}px" fill="#0f172a">{safe_line}</text>
      <!-- Prehnuté LED svetlomety SOR NS -->
      <rect x="17" y="33" width="14" height="3.5" rx="1.7" fill="#0f172a"/>
      <circle cx="24" cy="34.7" r="1.2" fill="#34d399"/>
      <path d="M 9.5 33.5 Q 13 32.7 16 34" stroke="#fef08a" stroke-width="2.2" stroke-linecap="round" fill="none"/>
      <path d="M 38.5 33.5 Q 35 32.7 32 34" stroke="#fef08a" stroke-width="2.2" stroke-linecap="round" fill="none"/>
    </svg>
    """
svg_generators["sor-nsg18"] = render_sor_nsg18

# 8. SOR NSG 12 (štandardný plynový CNG)
def render_sor_nsg12(line="54", delay_color="#facc15"):
    font_size = get_line_font_size(line)
    safe_line = escape_xml(line)
    clip_id = "clip-nsg12"
    delay_style = f"fill: {delay_color} !important;" if delay_color and delay_color != "transparent" else "display: none;"
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 46" width="44" height="46" class="veh-front-svg">
      <defs>
        <clipPath id="{clip_id}">
          <rect x="8" y="9" width="28" height="22" rx="5"/>
        </clipPath>
      </defs>
      <!-- Klenutý kryt plynových nádrží CNG -->
      <path d="M 11 7 Q 22 1 33 7 Z" fill="#047857" stroke="#34d399" stroke-width="1.4"/>
      <rect x="17" y="3" width="10" height="3" rx="1" fill="#065f46"/>
      <text x="22" y="5" text-anchor="middle" dominant-baseline="central" font-size="2.2px" font-weight="900" fill="#a7f3d0" font-family="'JetBrains Mono', sans-serif">CNG</text>
      <rect x="7" y="39" width="6" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="31" y="39" width="6" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="5" y="6" width="34" height="34" rx="7" fill="#059669" stroke="#34d399" stroke-width="2.5"/>
      <rect x="1.5" y="11" width="3.5" height="8" rx="1.6" fill="#0f172a" stroke="#34d399" stroke-width="1"/>
      <rect x="39" y="11" width="3.5" height="8" rx="1.6" fill="#0f172a" stroke="#34d399" stroke-width="1"/>
      <rect x="8" y="9" width="28" height="22" rx="5" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
      <rect class="veh-delay-bar" x="8" y="9" width="28" height="6" fill="{delay_color}" clip-path="url(#{clip_id})" style="{delay_style}"/>
      <text x="22" y="22" text-anchor="middle" dominant-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="{font_size}px" fill="#0f172a">{safe_line}</text>
      <rect x="15" y="32.5" width="14" height="3.5" rx="1.7" fill="#0f172a"/>
      <circle cx="22" cy="34.2" r="1.2" fill="#34d399"/>
      <path d="M 8.5 33 Q 11 32.5 13.5 33.5" stroke="#fef08a" stroke-width="2" stroke-linecap="round" fill="none"/>
      <path d="M 35.5 33 Q 33 32.5 30.5 33.5" stroke="#fef08a" stroke-width="2" stroke-linecap="round" fill="none"/>
    </svg>
    """
svg_generators["sor-nsg12"] = render_sor_nsg12

# 9. SOR NB 18 City (chrbtica DPMK – 4 svetlá, klíma)
def render_sor_nb18(line="12", delay_color="transparent"):
    font_size = get_line_font_size(line)
    safe_line = escape_xml(line)
    clip_id = "clip-nb18"
    delay_style = f"fill: {delay_color} !important;" if delay_color and delay_color != "transparent" else "display: none;"
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 45" width="48" height="45" class="veh-front-svg">
      <defs>
        <clipPath id="{clip_id}">
          <rect x="8" y="7" width="32" height="23" rx="4"/>
        </clipPath>
      </defs>
      <!-- A/C klimatizačný box na streche s mriežkou -->
      <rect x="15" y="1" width="18" height="4" rx="2" fill="#3b82f6" stroke="#0f172a" stroke-width="1"/>
      <line x1="18" y1="3" x2="30" y2="3" stroke="#ffffff" stroke-width="1" stroke-linecap="round" opacity="0.7"/>
      <rect x="7" y="38" width="7" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="34" y="38" width="7" height="4" rx="1.5" fill="#0f172a"/>
      <!-- Tmavomodrá kĺbová karoséria DPMK -->
      <rect x="5" y="4" width="38" height="35" rx="5" fill="#1d4ed8" stroke="#3b82f6" stroke-width="2.5"/>
      <!-- Výrazné spätné zrkadlá s ramenami -->
      <rect x="0.5" y="7" width="4.2" height="11" rx="2" fill="#0f172a" stroke="#3b82f6" stroke-width="1.2"/>
      <path d="M 5 8 Q 2 8 2 10" fill="none" stroke="#334155" stroke-width="1.8"/>
      <rect x="43.3" y="7" width="4.2" height="11" rx="2" fill="#0f172a" stroke="#3b82f6" stroke-width="1.2"/>
      <path d="M 43 8 Q 46 8 46 10" fill="none" stroke="#334155" stroke-width="1.8"/>
      <rect x="8" y="7" width="32" height="23" rx="4" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
      <rect class="veh-delay-bar" x="8" y="7" width="32" height="6" fill="{delay_color}" clip-path="url(#{clip_id})" style="{delay_style}"/>
      <text x="24" y="21.5" text-anchor="middle" dominant-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="{font_size}px" fill="#0f172a">{safe_line}</text>
      <!-- Čierna mriežka chladiča a 2 PÁRY ŽLTÝCH SVETLOMETOV (4 svetlá) SOR NB -->
      <rect x="17" y="32" width="14" height="4" rx="1.8" fill="#0f172a"/>
      <rect x="8.5" y="32.5" width="2.8" height="3.2" rx="0.8" fill="#fef08a"/>
      <rect x="12" y="32.5" width="2.8" height="3.2" rx="0.8" fill="#fef08a"/>
      <rect x="33.2" y="32.5" width="2.8" height="3.2" rx="0.8" fill="#fef08a"/>
      <rect x="36.7" y="32.5" width="2.8" height="3.2" rx="0.8" fill="#fef08a"/>
    </svg>
    """
svg_generators["sor-nb18"] = render_sor_nb18

# 10. SOR NB 12 City
def render_sor_nb12(line="31", delay_color="#facc15"):
    font_size = get_line_font_size(line)
    safe_line = escape_xml(line)
    clip_id = "clip-nb12"
    delay_style = f"fill: {delay_color} !important;" if delay_color and delay_color != "transparent" else "display: none;"
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 44" width="44" height="44" class="veh-front-svg">
      <defs>
        <clipPath id="{clip_id}">
          <rect x="8" y="7" width="28" height="23" rx="4"/>
        </clipPath>
      </defs>
      <rect x="7" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="31" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="5" y="4" width="34" height="35" rx="6" fill="#0284c7" stroke="#38bdf8" stroke-width="2.5"/>
      <rect x="1.5" y="9" width="3.5" height="8" rx="1.5" fill="#1e293b" stroke="#38bdf8" stroke-width="1"/>
      <rect x="39" y="9" width="3.5" height="8" rx="1.5" fill="#1e293b" stroke="#38bdf8" stroke-width="1"/>
      <rect x="8" y="7" width="28" height="23" rx="4" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
      <rect class="veh-delay-bar" x="8" y="7" width="28" height="6" fill="{delay_color}" clip-path="url(#{clip_id})" style="{delay_style}"/>
      <text x="22" y="21.5" text-anchor="middle" dominant-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="{font_size}px" fill="#0f172a">{safe_line}</text>
      <!-- Dvojité svetlomety SOR NB vľavo aj vpravo -->
      <rect x="15" y="32" width="14" height="4" rx="1.8" fill="#0f172a"/>
      <rect x="8.5" y="32.5" width="2.6" height="3" rx="0.8" fill="#fef08a"/>
      <rect x="11.8" y="32.5" width="2.6" height="3" rx="0.8" fill="#fef08a"/>
      <rect x="29.6" y="32.5" width="2.6" height="3" rx="0.8" fill="#fef08a"/>
      <rect x="32.9" y="32.5" width="2.6" height="3" rx="0.8" fill="#fef08a"/>
    </svg>
    """
svg_generators["sor-nb12"] = render_sor_nb12

# 11. SOR NBG 12 City (plynový NB)
def render_sor_nbg12(line="20", delay_color="transparent"):
    font_size = get_line_font_size(line)
    safe_line = escape_xml(line)
    clip_id = "clip-nbg12"
    delay_style = f"fill: {delay_color} !important;" if delay_color and delay_color != "transparent" else "display: none;"
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 46" width="44" height="46" class="veh-front-svg">
      <defs>
        <clipPath id="{clip_id}">
          <rect x="8" y="9" width="28" height="22" rx="4"/>
        </clipPath>
      </defs>
      <!-- CNG kryt na streche SOR NBG -->
      <path d="M 11 7 Q 22 1.5 33 7 Z" fill="#0891b2" stroke="#06b6d4" stroke-width="1.2"/>
      <rect x="17" y="3.5" width="10" height="2.5" rx="1" fill="#155e75"/>
      <text x="22" y="5" text-anchor="middle" dominant-baseline="central" font-size="2px" font-weight="900" fill="#a5f3fc" font-family="'JetBrains Mono', sans-serif">CNG</text>
      <rect x="7" y="39" width="6" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="31" y="39" width="6" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="5" y="6" width="34" height="34" rx="6" fill="#0284c7" stroke="#06b6d4" stroke-width="2.5"/>
      <rect x="1.5" y="10" width="3.5" height="8" rx="1.5" fill="#1e293b" stroke="#06b6d4" stroke-width="1"/>
      <rect x="39" y="10" width="3.5" height="8" rx="1.5" fill="#1e293b" stroke="#06b6d4" stroke-width="1"/>
      <rect x="8" y="9" width="28" height="22" rx="4" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
      <rect class="veh-delay-bar" x="8" y="9" width="28" height="6" fill="{delay_color}" clip-path="url(#{clip_id})" style="{delay_style}"/>
      <text x="22" y="22" text-anchor="middle" dominant-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="{font_size}px" fill="#0f172a">{safe_line}</text>
      <rect x="15" y="32.5" width="14" height="3.8" rx="1.8" fill="#0f172a"/>
      <rect x="8.5" y="33" width="2.6" height="2.8" rx="0.8" fill="#fef08a"/>
      <rect x="11.8" y="33" width="2.6" height="2.8" rx="0.8" fill="#fef08a"/>
      <rect x="29.6" y="33" width="2.6" height="2.8" rx="0.8" fill="#fef08a"/>
      <rect x="32.9" y="33" width="2.6" height="2.8" rx="0.8" fill="#fef08a"/>
    </svg>
    """
svg_generators["sor-nbg12"] = render_sor_nbg12

# 12. SOR BN 9,5 (midibus)
def render_sor_bn95(line="22", delay_color="transparent"):
    font_size = get_line_font_size(line)
    safe_line = escape_xml(line)
    clip_id = "clip-bn95"
    delay_style = f"fill: {delay_color} !important;" if delay_color and delay_color != "transparent" else "display: none;"
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 44" width="40" height="44" class="veh-front-svg">
      <defs>
        <clipPath id="{clip_id}">
          <rect x="7" y="7" width="26" height="22" rx="3.5"/>
        </clipPath>
      </defs>
      <rect x="6" y="37" width="5.5" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="28.5" y="37" width="5.5" height="4" rx="1.5" fill="#0f172a"/>
      <!-- Zúžená karoséria midibusu SOR BN -->
      <rect x="4.5" y="4" width="31" height="34" rx="5" fill="#38bdf8" stroke="#8b5cf6" stroke-width="2.3"/>
      <rect x="1.5" y="9" width="3" height="7.5" rx="1.2" fill="#1e293b" stroke="#8b5cf6" stroke-width="0.9"/>
      <rect x="35.5" y="9" width="3" height="7.5" rx="1.2" fill="#1e293b" stroke="#8b5cf6" stroke-width="0.9"/>
      <rect x="7" y="7" width="26" height="22" rx="3.5" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
      <rect class="veh-delay-bar" x="7" y="7" width="26" height="5.5" fill="{delay_color}" clip-path="url(#{clip_id})" style="{delay_style}"/>
      <text x="20" y="21" text-anchor="middle" dominant-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="{font_size}px" fill="#0f172a">{safe_line}</text>
      <rect x="13" y="31.5" width="14" height="3.5" rx="1.7" fill="#0f172a"/>
      <circle cx="8" cy="33" r="1.9" fill="#fef08a" stroke="#ca8a04" stroke-width="0.7"/>
      <circle cx="32" cy="33" r="1.9" fill="#fef08a" stroke="#ca8a04" stroke-width="0.7"/>
    </svg>
    """
svg_generators["sor-bn95"] = render_sor_bn95

# 13. SOR C 10,5 (linkový / prímestský)
def render_sor_c105(line="RA4", delay_color="#f97316"):
    font_size = get_line_font_size(line)
    safe_line = escape_xml(line)
    clip_id = "clip-c105"
    delay_style = f"fill: {delay_color} !important;" if delay_color and delay_color != "transparent" else "display: none;"
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 44" width="44" height="44" class="veh-front-svg">
      <defs>
        <clipPath id="{clip_id}">
          <rect x="8" y="7" width="28" height="20" rx="3.5"/>
        </clipPath>
      </defs>
      <rect x="7" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="31" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
      <!-- Sivomodrá karoséria, vysokopodlažný vyšší nárazník -->
      <rect x="5" y="4" width="34" height="35" rx="5" fill="#38bdf8" stroke="#64748b" stroke-width="2.5"/>
      <rect x="1.5" y="9" width="3.5" height="8" rx="1.5" fill="#1e293b"/>
      <rect x="39" y="9" width="3.5" height="8" rx="1.5" fill="#1e293b"/>
      <rect x="8" y="7" width="28" height="20" rx="3.5" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
      <rect class="veh-delay-bar" x="8" y="7" width="28" height="5.5" fill="{delay_color}" clip-path="url(#{clip_id})" style="{delay_style}"/>
      <text x="22" y="19" text-anchor="middle" dominant-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="{font_size}px" fill="#0f172a">{safe_line}</text>
      <!-- Masívny linkový nárazník SOR C -->
      <rect x="5" y="29" width="34" height="8" rx="2" fill="#475569"/>
      <rect x="14" y="31" width="16" height="4" rx="1.5" fill="#0f172a"/>
      <circle cx="9.5" cy="33" r="2.2" fill="#fef08a" stroke="#ca8a04" stroke-width="0.8"/>
      <circle cx="34.5" cy="33" r="2.2" fill="#fef08a" stroke="#ca8a04" stroke-width="0.8"/>
    </svg>
    """
svg_generators["sor-c105"] = render_sor_c105

# 14. Solaris Urbino 18 III & 18,75 III (asymetrické čelné sklo Solaris)
def render_solaris_u18(line="15", delay_color="transparent", is_extra_long=False):
    font_size = get_line_font_size(line)
    safe_line = escape_xml(line)
    clip_id = "clip-sol-u18"
    delay_style = f"fill: {delay_color} !important;" if delay_color and delay_color != "transparent" else "display: none;"
    border_color = "#000000" if is_extra_long else "#94a3b8"
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 45" width="48" height="45" class="veh-front-svg">
      <defs>
        <clipPath id="{clip_id}">
          <path d="M 8 7 L 40 7 L 40 32 L 28 32 L 28 29 L 8 29 Z"/>
        </clipPath>
      </defs>
      <!-- Aerodynamický A/C box Solaris na streche -->
      <rect x="16" y="1" width="16" height="4" rx="2" fill="#be123c" stroke="#0f172a" stroke-width="1"/>
      <rect x="7" y="38" width="7" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="34" y="38" width="7" height="4" rx="1.5" fill="#0f172a"/>
      <!-- Bordová karoséria Solaris Urbino 18 -->
      <rect x="5" y="4" width="38" height="35" rx="5" fill="#881337" stroke="{border_color}" stroke-width="2.5"/>
      <!-- Zrkadlo Solaris s oblúkovým horným závesom vpravo -->
      <rect x="0.8" y="8" width="4" height="10" rx="1.8" fill="#0f172a" stroke="#94a3b8" stroke-width="1"/>
      <rect x="43.2" y="8" width="4" height="10" rx="1.8" fill="#0f172a" stroke="#94a3b8" stroke-width="1"/>
      <path d="M 43 8 Q 46 6 46 8" fill="none" stroke="#0f172a" stroke-width="1.8"/>
      <!-- IKONICKÉ ASYMETRICKÉ ČELNÉ SKLO SOLARIS (klesá doprava k chodníku!) -->
      <path d="M 8 7 L 40 7 L 40 32 L 28 32 L 28 29 L 8 29 Z" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
      <rect class="veh-delay-bar" x="8" y="7" width="32" height="6" fill="{delay_color}" clip-path="url(#{clip_id})" style="{delay_style}"/>
      <text x="23" y="20.5" text-anchor="middle" dominant-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="{font_size}px" fill="#0f172a">{safe_line}</text>
      <!-- Vertikálne šošovky svetiel Solaris nad sebou a stredový prelis -->
      <rect x="17" y="31.5" width="14" height="4.5" rx="2" fill="#0f172a"/>
      <!-- Vľavo šošovky nad sebou -->
      <circle cx="10" cy="31.5" r="1.6" fill="#fef08a" stroke="#ca8a04" stroke-width="0.5"/>
      <circle cx="10" cy="34.5" r="1.4" fill="#fef08a" stroke="#ca8a04" stroke-width="0.5"/>
      <!-- Vpravo šošovky nad sebou -->
      <circle cx="38" cy="31.5" r="1.6" fill="#fef08a" stroke="#ca8a04" stroke-width="0.5"/>
      <circle cx="38" cy="34.5" r="1.4" fill="#fef08a" stroke="#ca8a04" stroke-width="0.5"/>
    </svg>
    """
svg_generators["solaris-u18"] = render_solaris_u18

# 15. Solaris Urbino 15 II / III (trojnápravový)
def render_solaris_u15(line="51", delay_color="transparent"):
    font_size = get_line_font_size(line)
    safe_line = escape_xml(line)
    clip_id = "clip-sol-u15"
    delay_style = f"fill: {delay_color} !important;" if delay_color and delay_color != "transparent" else "display: none;"
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 46 45" width="46" height="45" class="veh-front-svg">
      <defs>
        <clipPath id="{clip_id}">
          <path d="M 8 7 L 38 7 L 38 32 L 27 32 L 27 29 L 8 29 Z"/>
        </clipPath>
      </defs>
      <rect x="16" y="1" width="14" height="4" rx="2" fill="#f59e0b" stroke="#0f172a" stroke-width="1"/>
      <rect x="7" y="38" width="6.5" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="32.5" y="38" width="6.5" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="5" y="4" width="36" height="35" rx="5" fill="#881337" stroke="#f59e0b" stroke-width="2.5"/>
      <rect x="1" y="8" width="3.8" height="9.5" rx="1.8" fill="#0f172a" stroke="#f59e0b" stroke-width="1"/>
      <rect x="41.2" y="8" width="3.8" height="9.5" rx="1.8" fill="#0f172a" stroke="#f59e0b" stroke-width="1"/>
      <path d="M 8 7 L 38 7 L 38 32 L 27 32 L 27 29 L 8 29 Z" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
      <rect class="veh-delay-bar" x="8" y="7" width="30" height="6" fill="{delay_color}" clip-path="url(#{clip_id})" style="{delay_style}"/>
      <text x="22" y="20.5" text-anchor="middle" dominant-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="{font_size}px" fill="#0f172a">{safe_line}</text>
      <rect x="16" y="31.5" width="14" height="4.5" rx="2" fill="#0f172a"/>
      <circle cx="10" cy="31.5" r="1.6" fill="#fef08a"/>
      <circle cx="10" cy="34.5" r="1.4" fill="#fef08a"/>
      <circle cx="36" cy="31.5" r="1.6" fill="#fef08a"/>
      <circle cx="36" cy="34.5" r="1.4" fill="#fef08a"/>
    </svg>
    """
svg_generators["solaris-u15"] = render_solaris_u15

# 16. Solaris Urbino 12 IV (New Urbino – ostré línie)
def render_solaris_u12_iv(line="27", delay_color="transparent"):
    font_size = get_line_font_size(line)
    safe_line = escape_xml(line)
    clip_id = "clip-sol-u12-iv"
    delay_style = f"fill: {delay_color} !important;" if delay_color and delay_color != "transparent" else "display: none;"
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 44" width="44" height="44" class="veh-front-svg">
      <defs>
        <clipPath id="{clip_id}">
          <polygon points="8,7 36,7 36,31 25,31 25,28 8,28"/>
        </clipPath>
      </defs>
      <rect x="7" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="31" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
      <!-- Ostré hranaté línie karosérie New Urbino IV -->
      <polygon points="5,4 39,4 39,38 5,38" fill="#dc2626" stroke="#991b1b" stroke-width="2.5"/>
      <rect x="1.5" y="8" width="3.5" height="9" rx="1" fill="#0f172a" stroke="#991b1b" stroke-width="1"/>
      <rect x="39" y="8" width="3.5" height="9" rx="1" fill="#0f172a" stroke="#991b1b" stroke-width="1"/>
      <!-- Lomená hrana čelného skla New Urbino -->
      <polygon points="8,7 36,7 36,31 25,31 25,28 8,28" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
      <rect class="veh-delay-bar" x="8" y="7" width="28" height="6" fill="{delay_color}" clip-path="url(#{clip_id})" style="{delay_style}"/>
      <text x="21" y="20" text-anchor="middle" dominant-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="{font_size}px" fill="#0f172a">{safe_line}</text>
      <!-- Šikmé klinové LED svetlomety New Urbino IV -->
      <rect x="15" y="32" width="14" height="4" rx="1.5" fill="#0f172a"/>
      <polygon points="8,33 13,31.5 13,34" fill="#fef08a" stroke="#ca8a04" stroke-width="0.5"/>
      <polygon points="36,33 31,31.5 31,34" fill="#fef08a" stroke="#ca8a04" stroke-width="0.5"/>
    </svg>
    """
svg_generators["solaris-u12-iv"] = render_solaris_u12_iv

# 17. Solaris Urbino 12 III Hybrid
def render_solaris_u12_hybrid(line="36", delay_color="transparent"):
    font_size = get_line_font_size(line)
    safe_line = escape_xml(line)
    clip_id = "clip-sol-hybrid"
    delay_style = f"fill: {delay_color} !important;" if delay_color and delay_color != "transparent" else "display: none;"
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 46" width="44" height="46" class="veh-front-svg">
      <defs>
        <clipPath id="{clip_id}">
          <path d="M 8 9 L 36 9 L 36 33 L 25 33 L 25 30 L 8 30 Z"/>
        </clipPath>
      </defs>
      <!-- Hybridná strešná nadstavba so zeleným ekologickým pruhom -->
      <rect x="12" y="1.5" width="20" height="4.5" rx="2" fill="#16a34a" stroke="#0f172a" stroke-width="1"/>
      <line x1="15" y1="3.5" x2="29" y2="3.5" stroke="#86efac" stroke-width="1.2" stroke-linecap="round"/>
      <rect x="7" y="39" width="6" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="31" y="39" width="6" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="5" y="6" width="34" height="34" rx="6" fill="#dc2626" stroke="#16a34a" stroke-width="2.5"/>
      <rect x="1.5" y="10" width="3.5" height="8" rx="1.5" fill="#0f172a" stroke="#16a34a" stroke-width="1"/>
      <rect x="39" y="10" width="3.5" height="8" rx="1.5" fill="#0f172a" stroke="#16a34a" stroke-width="1"/>
      <path d="M 8 9 L 36 9 L 36 33 L 25 33 L 25 30 L 8 30 Z" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
      <rect class="veh-delay-bar" x="8" y="9" width="28" height="6" fill="{delay_color}" clip-path="url(#{clip_id})" style="{delay_style}"/>
      <text x="21" y="22" text-anchor="middle" dominant-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="{font_size}px" fill="#0f172a">{safe_line}</text>
      <rect x="15" y="32.5" width="14" height="4" rx="1.8" fill="#0f172a"/>
      <circle cx="10" cy="32.5" r="1.5" fill="#fef08a"/>
      <circle cx="10" cy="35" r="1.3" fill="#fef08a"/>
      <circle cx="34" cy="32.5" r="1.5" fill="#fef08a"/>
      <circle cx="34" cy="35" r="1.3" fill="#fef08a"/>
    </svg>
    """
svg_generators["solaris-u12-hybrid"] = render_solaris_u12_hybrid

# 18. Solaris Urbino 12 III štandardný
def render_solaris_u12(line="25", delay_color="transparent"):
    font_size = get_line_font_size(line)
    safe_line = escape_xml(line)
    clip_id = "clip-sol-u12"
    delay_style = f"fill: {delay_color} !important;" if delay_color and delay_color != "transparent" else "display: none;"
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 44" width="44" height="44" class="veh-front-svg">
      <defs>
        <clipPath id="{clip_id}">
          <path d="M 8 7 L 36 7 L 36 31 L 25 31 L 25 28 L 8 28 Z"/>
        </clipPath>
      </defs>
      <rect x="7" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="31" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="5" y="4" width="34" height="35" rx="6" fill="#dc2626" stroke="#991b1b" stroke-width="2.5"/>
      <rect x="1.5" y="9" width="3.5" height="8" rx="1.5" fill="#0f172a" stroke="#991b1b" stroke-width="1"/>
      <rect x="39" y="9" width="3.5" height="8" rx="1.5" fill="#0f172a" stroke="#991b1b" stroke-width="1"/>
      <path d="M 8 7 L 36 7 L 36 31 L 25 31 L 25 28 L 8 28 Z" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
      <rect class="veh-delay-bar" x="8" y="7" width="28" height="6" fill="{delay_color}" clip-path="url(#{clip_id})" style="{delay_style}"/>
      <text x="21" y="20" text-anchor="middle" dominant-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="{font_size}px" fill="#0f172a">{safe_line}</text>
      <rect x="15" y="31.5" width="14" height="4" rx="1.8" fill="#0f172a"/>
      <circle cx="10" cy="31.5" r="1.5" fill="#fef08a"/>
      <circle cx="10" cy="34" r="1.3" fill="#fef08a"/>
      <circle cx="34" cy="31.5" r="1.5" fill="#fef08a"/>
      <circle cx="34" cy="34" r="1.3" fill="#fef08a"/>
    </svg>
    """
svg_generators["solaris-u12"] = render_solaris_u12

# 19. Iveco Rosero First FCLLI (minibus)
def render_rosero(line="23", delay_color="transparent"):
    font_size = get_line_font_size(line)
    safe_line = escape_xml(line)
    clip_id = "clip-rosero"
    delay_style = f"fill: {delay_color} !important;" if delay_color and delay_color != "transparent" else "display: none;"
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 44" width="40" height="44" class="veh-front-svg">
      <defs>
        <clipPath id="{clip_id}">
          <rect x="7" y="7" width="26" height="21" rx="3.5"/>
        </clipPath>
      </defs>
      <rect x="6" y="37" width="5.5" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="28.5" y="37" width="5.5" height="4" rx="1.5" fill="#0f172a"/>
      <!-- Úzka maska dodávky Daily -->
      <rect x="5" y="4" width="30" height="34" rx="5" fill="#0284c7" stroke="#38bdf8" stroke-width="2.3"/>
      <rect x="1.5" y="9" width="3.5" height="8" rx="1.2" fill="#0f172a"/>
      <rect x="35" y="9" width="3.5" height="8" rx="1.2" fill="#0f172a"/>
      <rect x="7" y="7" width="26" height="21" rx="3.5" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
      <rect class="veh-delay-bar" x="7" y="7" width="26" height="5.5" fill="{delay_color}" clip-path="url(#{clip_id})" style="{delay_style}"/>
      <text x="20" y="20" text-anchor="middle" dominant-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="{font_size}px" fill="#0f172a">{safe_line}</text>
      <!-- Mriežka Iveco Daily s chrómovými lamelami -->
      <rect x="13" y="30.5" width="14" height="4.5" rx="1.5" fill="#1e293b"/>
      <line x1="15" y1="32" x2="25" y2="32" stroke="#94a3b8" stroke-width="0.8"/>
      <line x1="15" y1="33.5" x2="25" y2="33.5" stroke="#94a3b8" stroke-width="0.8"/>
      <!-- Šikmé svetlá Iveco Daily -->
      <polygon points="8,32 12,30.8 12,33.5" fill="#fef08a"/>
      <polygon points="32,32 28,30.8 28,33.5" fill="#fef08a"/>
    </svg>
    """
svg_generators["rosero"] = render_rosero

# 20. Ikarus 280.08/A (historický delené okno)
def render_ikarus280(line="H", delay_color="transparent"):
    font_size = get_line_font_size(line)
    safe_line = escape_xml(line)
    clip_id = "clip-ikarus"
    delay_style = f"fill: {delay_color} !important;" if delay_color and delay_color != "transparent" else "display: none;"
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 44" width="48" height="44" class="veh-front-svg">
      <defs>
        <clipPath id="{clip_id}">
          <g>
            <rect x="8" y="7" width="14.5" height="23" rx="2"/>
            <rect x="25.5" y="7" width="14.5" height="23" rx="2"/>
          </g>
        </clipPath>
      </defs>
      <!-- Vetracie strešné poklopy bez A/C -->
      <rect x="15" y="2" width="6" height="2" rx="0.5" fill="#b45309"/>
      <rect x="27" y="2" width="6" height="2" rx="0.5" fill="#b45309"/>
      <rect x="7" y="38" width="7" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="34" y="38" width="7" height="4" rx="1.5" fill="#0f172a"/>
      <!-- Tmavohnedá hranatá karoséria Ikarus -->
      <rect x="5" y="4" width="38" height="35" rx="3" fill="#78350f" stroke="#f59e0b" stroke-width="2.5"/>
      <rect x="1" y="9" width="3.5" height="8" rx="1" fill="#0f172a"/>
      <rect x="43.5" y="9" width="3.5" height="8" rx="1" fill="#0f172a"/>
      <!-- DELENÉ DVOJDIELNE ČELNÉ SKLO SO STĹPIKOM V STREDE! -->
      <rect x="8" y="7" width="14.5" height="23" rx="2" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
      <rect x="25.5" y="7" width="14.5" height="23" rx="2" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
      <rect x="23" y="6" width="2" height="25" fill="#0f172a"/>
      <rect class="veh-delay-bar" x="8" y="7" width="32" height="6" fill="{delay_color}" clip-path="url(#{clip_id})" style="{delay_style}"/>
      <text x="24" y="21.5" text-anchor="middle" dominant-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="{font_size}px" fill="#0f172a">{safe_line}</text>
      <!-- Hranatá mriežka chladiča a okrúhle svetlá Ikarus -->
      <rect x="16" y="31.5" width="16" height="4.5" rx="1" fill="#0f172a"/>
      <line x1="18" y1="33" x2="30" y2="33" stroke="#cbd5e1" stroke-width="0.8"/>
      <circle cx="11" cy="33.5" r="2.2" fill="#fef08a" stroke="#ca8a04" stroke-width="0.8"/>
      <circle cx="8" cy="33.5" r="1.1" fill="#f97316"/>
      <circle cx="37" cy="33.5" r="2.2" fill="#fef08a" stroke="#ca8a04" stroke-width="0.8"/>
      <circle cx="40" cy="33.5" r="1.1" fill="#f97316"/>
    </svg>
    """
svg_generators["ikarus"] = render_ikarus280

# 21. Karosa B 832.1654 (historický)
def render_karosa_b832(line="H", delay_color="transparent"):
    font_size = get_line_font_size(line)
    safe_line = escape_xml(line)
    clip_id = "clip-karosa"
    delay_style = f"fill: {delay_color} !important;" if delay_color and delay_color != "transparent" else "display: none;"
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 44" width="44" height="44" class="veh-front-svg">
      <defs>
        <clipPath id="{clip_id}">
          <rect x="8" y="7" width="28" height="21" rx="2"/>
        </clipPath>
      </defs>
      <rect x="7" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="31" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
      <!-- Hranatá maska Karosa 700/800 s bielym pruhom -->
      <rect x="5" y="4" width="34" height="35" rx="3" fill="#c2410c" stroke="#ffffff" stroke-width="2.5"/>
      <rect x="1.5" y="9" width="3" height="8" rx="1" fill="#0f172a"/>
      <rect x="39.5" y="9" width="3" height="8" rx="1" fill="#0f172a"/>
      <rect x="8" y="7" width="28" height="21" rx="2" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
      <rect class="veh-delay-bar" x="8" y="7" width="28" height="5.5" fill="{delay_color}" clip-path="url(#{clip_id})" style="{delay_style}"/>
      <text x="22" y="20" text-anchor="middle" dominant-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="{font_size}px" fill="#0f172a">{safe_line}</text>
      <!-- Masívny nárazník a obdĺžnikové svetlá Karosa -->
      <rect x="5" y="30" width="34" height="7.5" rx="1" fill="#0f172a"/>
      <rect x="8" y="31.5" width="4.5" height="3" rx="0.5" fill="#fef08a" stroke="#ca8a04" stroke-width="0.6"/>
      <rect x="13" y="32" width="2" height="2" rx="0.3" fill="#f97316"/>
      <rect x="31.5" y="31.5" width="4.5" height="3" rx="0.5" fill="#fef08a" stroke="#ca8a04" stroke-width="0.6"/>
      <rect x="29" y="32" width="2" height="2" rx="0.3" fill="#f97316"/>
    </svg>
    """
svg_generators["karosa"] = render_karosa_b832

# 22. Autobus DPMK všeobecný
def render_general_bus(line="10", delay_color="transparent"):
    font_size = get_line_font_size(line)
    safe_line = escape_xml(line)
    clip_id = "clip-gen-bus"
    delay_style = f"fill: {delay_color} !important;" if delay_color and delay_color != "transparent" else "display: none;"
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 44" width="44" height="44" class="veh-front-svg">
      <defs>
        <clipPath id="{clip_id}">
          <rect x="8" y="7" width="28" height="23" rx="4"/>
        </clipPath>
      </defs>
      <rect x="7" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="31" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
      <rect x="5" y="4" width="34" height="35" rx="6" fill="#2563eb" stroke="#60a5fa" stroke-width="2.5"/>
      <rect x="1.5" y="9" width="3.5" height="8" rx="1.5" fill="#1e293b" stroke="#60a5fa" stroke-width="1"/>
      <rect x="39" y="9" width="3.5" height="8" rx="1.5" fill="#1e293b" stroke="#60a5fa" stroke-width="1"/>
      <rect x="8" y="7" width="28" height="23" rx="4" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
      <rect class="veh-delay-bar" x="8" y="7" width="28" height="6" fill="{delay_color}" clip-path="url(#{clip_id})" style="{delay_style}"/>
      <text x="22" y="21.5" text-anchor="middle" dominant-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="{font_size}px" fill="#0f172a">{safe_line}</text>
      <rect x="15" y="32" width="14" height="4" rx="2" fill="#0f172a"/>
      <rect x="8.5" y="32" width="4.5" height="3.5" rx="1.5" fill="#fef08a" stroke="#ca8a04" stroke-width="0.8"/>
      <rect x="31" y="32" width="4.5" height="3.5" rx="1.5" fill="#fef08a" stroke="#ca8a04" stroke-width="0.8"/>
    </svg>
    """
svg_generators["general-bus"] = render_general_bus

print(f"Testujem všetkých {len(svg_generators)} XML generátorov...")
all_ok = True
for k, fn in svg_generators.items():
    raw_svg = fn()
    try:
        ET.fromstring(raw_svg)
        print(f"  [OK] {k}")
    except Exception as e:
        print(f"  [CHYBA] v {k}: {e}")
        all_ok = False

if all_ok:
    print(f"\nVŠETKÝCH {len(svg_generators)} SVG IKON JE 100% VALÍDNYCH A PRIPRAVENÝCH!")
