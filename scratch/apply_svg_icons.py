# -*- coding: utf-8 -*-
"""
Tento skript vygeneruje kompletný JavaScript blok pre všetkých 22 jedinečných SVG ikoniek
pre všetky modely vozidiel košickej MHD (DPMK) a nasadí ho do mapa.html.
"""
import re

js_code = r'''    // =========================================================================
    // JEDINEČNÉ FRONT-VIEW SVG IKONY PRE KAŽDÝ POJAZDNÝ MODEL VOZIDLA DPMK KOŠICE
    // =========================================================================

    // Určenie kľúča modelu vozidla pre priradenie unikátnej SVG prednej masky
    function getVehicleModelKey(v) {
      const cat = getVehicleCategory(v) || {};
      if (cat.id) {
        if (cat.id === 'tram-vario') return 'tram-vario';
        if (cat.id === 'tram-kt8') return 'tram-kt8';
        if (cat.id === 'tram-t6') return 'tram-t6';
        if (cat.id === 'tram') return 'tram';
        if (cat.id === 'solaris-u1875') return 'solaris-u1875';
        if (cat.id === 'solaris-u18') return 'solaris-u18';
        if (cat.id === 'solaris-u15') return 'solaris-u15';
        if (cat.id === 'solaris-u12-iv') return 'solaris-u12-iv';
        if (cat.id === 'solaris-u12-hybrid') return 'solaris-u12-hybrid';
        if (cat.id === 'solaris-u12') return 'solaris-u12';
        if (cat.id === 'sor-ns18') return 'sor-ns18';
        if (cat.id === 'sor-nsg18') return 'sor-nsg18';
        if (cat.id === 'sor-nsg12') return 'sor-nsg12';
        if (cat.id === 'sor-ebn') return 'sor-ebn';
        if (cat.id === 'sor-nb18') return 'sor-nb18';
        if (cat.id === 'sor-nb12') return 'sor-nb12';
        if (cat.id === 'sor-nbg12') return 'sor-nbg12';
        if (cat.id === 'sor-bn95') return 'sor-bn95';
        if (cat.id === 'sor-c105') return 'sor-c105';
        if (cat.id === 'rosero') return 'rosero';
        if (cat.id === 'ikarus') return 'ikarus';
        if (cat.id === 'karosa') return 'karosa';
      }
      return 'bus-default';
    }

    // Určenie typu masky vozidla (spätná kompatibilita)
    function getVehicleShapeType(v, cat) {
      if (cat.id && cat.id.startsWith('tram')) return 'tram';
      const fleet = v.fleet_info || v || {};
      const model = String(fleet.model || v.model || '').toLowerCase();
      if (cat.id === 'sor-electric' || cat.id === 'sor-ns18' || cat.id === 'sor-ebn' || /ebn|elektro|electric/i.test(model)) {
        return 'electric';
      }
      const longCatIds = ['sor-nb18', 'sor-nsg18', 'solaris-u1875', 'solaris-u18', 'solaris-u15', 'ikarus'];
      if (longCatIds.includes(cat.id)) return 'articulated';
      if (/18|15|18[,.]75|k[lĺ]bov|articulated|capacity|280/i.test(model)) return 'articulated';
      return 'standard';
    }

    // Dynamická veľkosť písma linky podľa dĺžky reťazca
    function getLineFontSize(lineStr) {
      const len = String(lineStr || '').length;
      if (len <= 2) return 16;
      if (len === 3) return 13;
      return 10.5;
    }

    // Výpočet farby indikačnej lišty meškania (4-stupňová stupnica)
    function getDelayBarColor(delayMinutes) {
      if (typeof delayMinutes === 'string' && ['#facc15', '#f97316', '#ef4444', 'transparent'].includes(delayMinutes)) {
        return delayMinutes;
      }
      const delay = (delayMinutes !== undefined && delayMinutes !== null) ? Number(delayMinutes) : 0;
      if (isNaN(delay) || delay <= 0) return 'transparent'; // 0 minút: transparentná
      if (delay <= 3) return '#facc15';                      // 1-3 minúty: žltá
      if (delay <= 5) return '#f97316';                      // 4-5 minút: oranžová
      return '#ef4444';                                      // >5 minút: červená
    }

    function escapeXml(str) {
      return String(str || '?').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // 1. Vario LF2+ / Vario LF (Pragoimex) - skosená kabína, modrý klinový nárazník DPMK, šikmé svetlá
    function renderVarioLfSvg(line, delayColorOrMinutes = '') {
      const delayColor = getDelayBarColor(delayColorOrMinutes);
      const fontSize = getLineFontSize(line);
      const safeLine = escapeXml(line);
      const clipId = 'ws-clip-vario-' + Math.random().toString(36).substr(2, 7);
      return `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 48" width="44" height="48" class="veh-front-svg">
          <defs>
            <clipPath id="${clipId}">
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
          <rect class="veh-delay-bar" x="8.5" y="14" width="27" height="5.5" fill="${delayColor}" clip-path="url(#${clipId})" style="fill: ${delayColor} !important; ${(!delayColor || delayColor === 'transparent') ? 'display: none;' : ''}"/>
          <text x="22" y="26.5" text-anchor="middle" dominant-baseline="central" alignment-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="${fontSize}px" fill="#0f172a" style="fill: #0f172a !important; font-size: ${fontSize}px !important; font-weight: 900 !important;" letter-spacing="-0.5px">${safeLine}</text>
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
      `;
    }

    // 2. ČKD Tatra KT8D5.RN2 - široká trojčlánková, diamantový pantograf, 3-dielne okno, červený masívny nárazník
    function renderKt8d5Svg(line, delayColorOrMinutes = '') {
      const delayColor = getDelayBarColor(delayColorOrMinutes);
      const fontSize = getLineFontSize(line);
      const safeLine = escapeXml(line);
      const clipId = 'ws-clip-kt8d5-' + Math.random().toString(36).substr(2, 7);
      return `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 46 48" width="46" height="48" class="veh-front-svg">
          <defs>
            <clipPath id="${clipId}">
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
          <rect class="veh-delay-bar" x="7.5" y="14" width="31" height="5.5" fill="${delayColor}" clip-path="url(#${clipId})" style="fill: ${delayColor} !important; ${(!delayColor || delayColor === 'transparent') ? 'display: none;' : ''}"/>
          <text x="23" y="26.5" text-anchor="middle" dominant-baseline="central" alignment-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="${fontSize}px" fill="#0f172a" style="fill: #0f172a !important; font-size: ${fontSize}px !important; font-weight: 900 !important;" letter-spacing="-0.5px">${safeLine}</text>
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
      `;
    }

    // 3. ČKD Tatra T6A5 - klasická hranatá sólo električka, 2 okrúhle svetlomety
    function renderT6a5Svg(line, delayColorOrMinutes = '') {
      const delayColor = getDelayBarColor(delayColorOrMinutes);
      const fontSize = getLineFontSize(line);
      const safeLine = escapeXml(line);
      const clipId = 'ws-clip-t6a5-' + Math.random().toString(36).substr(2, 7);
      return `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 48" width="44" height="48" class="veh-front-svg">
          <defs>
            <clipPath id="${clipId}">
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
          <rect class="veh-delay-bar" x="8" y="14" width="28" height="5.5" fill="${delayColor}" clip-path="url(#${clipId})" style="fill: ${delayColor} !important; ${(!delayColor || delayColor === 'transparent') ? 'display: none;' : ''}"/>
          <text x="22" y="26.5" text-anchor="middle" dominant-baseline="central" alignment-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="${fontSize}px" fill="#0f172a" style="fill: #0f172a !important; font-size: ${fontSize}px !important; font-weight: 900 !important;" letter-spacing="-0.5px">${safeLine}</text>
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
      `;
    }

    // 4. Električka DPMK všeobecná
    function renderGeneralTramSvg(line, delayColorOrMinutes = '') {
      const delayColor = getDelayBarColor(delayColorOrMinutes);
      const fontSize = getLineFontSize(line);
      const safeLine = escapeXml(line);
      const clipId = 'ws-clip-gtram-' + Math.random().toString(36).substr(2, 7);
      return `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 48" width="44" height="48" class="veh-front-svg">
          <defs>
            <clipPath id="${clipId}">
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
          <rect class="veh-delay-bar" x="8.5" y="14" width="27" height="5.5" fill="${delayColor}" clip-path="url(#${clipId})" style="fill: ${delayColor} !important; ${(!delayColor || delayColor === 'transparent') ? 'display: none;' : ''}"/>
          <text x="22" y="26.5" text-anchor="middle" dominant-baseline="central" alignment-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="${fontSize}px" fill="#0f172a" style="fill: #0f172a !important; font-size: ${fontSize}px !important; font-weight: 900 !important;" letter-spacing="-0.5px">${safeLine}</text>
          <rect x="16.5" y="36.5" width="11" height="3" rx="1.5" fill="#1e293b"/>
          <circle cx="11.5" cy="37.5" r="2.2" fill="#fef08a" stroke="#ca8a04" stroke-width="0.8"/>
          <circle cx="32.5" cy="37.5" r="2.2" fill="#fef08a" stroke="#ca8a04" stroke-width="0.8"/>
          <rect x="14" y="42" width="16" height="2" rx="1" fill="#1e293b"/>
          <rect x="8" y="42" width="4.5" height="4.5" rx="1" fill="#475569" stroke="#0f172a" stroke-width="1"/>
          <line x1="7.5" y1="46.5" x2="13" y2="46.5" stroke="#0f172a" stroke-width="1.5" stroke-linecap="round"/>
          <rect x="31.5" y="42" width="4.5" height="4.5" rx="1" fill="#475569" stroke="#0f172a" stroke-width="1"/>
          <line x1="31" y1="46.5" x2="36.5" y2="46.5" stroke="#0f172a" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      `;
    }

    // 5. SOR NS 18 Electric - 48px aerodynamická Kotas karoséria, zelená, nabíjací zberač s bleskom ⚡, prehnuté LED svetlá
    function renderSorNs18ElectricSvg(line, delayColorOrMinutes = '') {
      const delayColor = getDelayBarColor(delayColorOrMinutes);
      const fontSize = getLineFontSize(line);
      const safeLine = escapeXml(line);
      const clipId = 'ws-clip-ns18e-' + Math.random().toString(36).substr(2, 7);
      return `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 46" width="48" height="46" class="veh-front-svg">
          <defs>
            <clipPath id="${clipId}">
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
          <rect class="veh-delay-bar" x="9" y="8" width="30" height="6" fill="${delayColor}" clip-path="url(#${clipId})" style="fill: ${delayColor} !important; ${(!delayColor || delayColor === 'transparent') ? 'display: none;' : ''}"/>
          <text x="24" y="22.5" text-anchor="middle" dominant-baseline="central" alignment-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="${fontSize}px" fill="#0f172a" style="fill: #0f172a !important; font-size: ${fontSize}px !important; font-weight: 900 !important;" letter-spacing="-0.5px">${safeLine}</text>
          <rect x="17" y="33.5" width="14" height="3.5" rx="1.7" fill="#0f172a"/>
          <circle cx="24" cy="35.2" r="1.3" fill="#4ade80"/>
          <path d="M 9.5 34 Q 13 33.2 16 34.5" stroke="#fef08a" stroke-width="2.2" stroke-linecap="round" fill="none"/>
          <path d="M 38.5 34 Q 35 33.2 32 34.5" stroke="#fef08a" stroke-width="2.2" stroke-linecap="round" fill="none"/>
        </svg>
      `;
    }

    // 6. SOR EBN 10.5 & 11 - ikonický vysoký zaoblený hrb na streche so symbolom blesku ⚡, okrúhle svetlá
    function renderSorEbnSvg(line, delayColorOrMinutes = '') {
      const delayColor = getDelayBarColor(delayColorOrMinutes);
      const fontSize = getLineFontSize(line);
      const safeLine = escapeXml(line);
      const clipId = 'ws-clip-ebn-' + Math.random().toString(36).substr(2, 7);
      return `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 46" width="44" height="46" class="veh-front-svg">
          <defs>
            <clipPath id="${clipId}">
              <rect x="8" y="9" width="28" height="22" rx="4"/>
            </clipPath>
          </defs>
          <path d="M 9 9 Q 22 1.5 35 9 Z" fill="#15803d" stroke="#4ade80" stroke-width="1.4"/>
          <path d="M 23 2.5 L 21 5 L 22.8 5 L 21.5 7.5 L 24.5 4.8 L 22.8 4.8 Z" fill="#fde047" stroke="#ca8a04" stroke-width="0.3"/>
          <rect x="7" y="39" width="6" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="31" y="39" width="6" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="5" y="7" width="34" height="34" rx="6" fill="#16a34a" stroke="#4ade80" stroke-width="2.5"/>
          <rect x="1.5" y="11" width="3.5" height="8" rx="1.5" fill="#0f172a" stroke="#4ade80" stroke-width="1"/>
          <rect x="39" y="11" width="3.5" height="8" rx="1.5" fill="#0f172a" stroke="#4ade80" stroke-width="1"/>
          <rect x="8" y="9" width="28" height="22" rx="4" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
          <rect class="veh-delay-bar" x="8" y="9" width="28" height="6" fill="${delayColor}" clip-path="url(#${clipId})" style="fill: ${delayColor} !important; ${(!delayColor || delayColor === 'transparent') ? 'display: none;' : ''}"/>
          <text x="22" y="22" text-anchor="middle" dominant-baseline="central" alignment-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="${fontSize}px" fill="#0f172a" style="fill: #0f172a !important; font-size: ${fontSize}px !important; font-weight: 900 !important;" letter-spacing="-0.5px">${safeLine}</text>
          <rect x="15" y="32.5" width="14" height="3.5" rx="1.7" fill="#0f172a"/>
          <circle cx="10" cy="34" r="2.2" fill="#fef08a" stroke="#ca8a04" stroke-width="0.7"/>
          <circle cx="34" cy="34" r="2.2" fill="#fef08a" stroke="#ca8a04" stroke-width="0.7"/>
        </svg>
      `;
    }

    // 7. SOR NSG 18 - kĺbový plynový CNG, mohutná strešná klenba nádrží CNG, LED svetlá
    function renderSorNsg18Svg(line, delayColorOrMinutes = '') {
      const delayColor = getDelayBarColor(delayColorOrMinutes);
      const fontSize = getLineFontSize(line);
      const safeLine = escapeXml(line);
      const clipId = 'ws-clip-nsg18-' + Math.random().toString(36).substr(2, 7);
      return `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 46" width="48" height="46" class="veh-front-svg">
          <defs>
            <clipPath id="${clipId}">
              <rect x="9" y="9" width="30" height="22" rx="6"/>
            </clipPath>
          </defs>
          <path d="M 12 7 Q 24 0.5 36 7 Z" fill="#047857" stroke="#34d399" stroke-width="1.4"/>
          <rect x="18" y="3" width="12" height="3" rx="1" fill="#065f46"/>
          <text x="24" y="5" text-anchor="middle" dominant-baseline="central" font-size="2.4px" font-weight="900" fill="#a7f3d0" font-family="'JetBrains Mono', sans-serif">CNG</text>
          <rect x="7" y="40" width="7" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="34" y="40" width="7" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="5" y="6" width="38" height="35" rx="8" fill="#059669" stroke="#34d399" stroke-width="2.5"/>
          <rect x="1.5" y="11" width="3.8" height="9" rx="1.8" fill="#0f172a" stroke="#34d399" stroke-width="1"/>
          <rect x="42.7" y="11" width="3.8" height="9" rx="1.8" fill="#0f172a" stroke="#34d399" stroke-width="1"/>
          <rect x="9" y="9" width="30" height="22" rx="6" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
          <rect class="veh-delay-bar" x="9" y="9" width="30" height="6" fill="${delayColor}" clip-path="url(#${clipId})" style="fill: ${delayColor} !important; ${(!delayColor || delayColor === 'transparent') ? 'display: none;' : ''}"/>
          <text x="24" y="22" text-anchor="middle" dominant-baseline="central" alignment-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="${fontSize}px" fill="#0f172a" style="fill: #0f172a !important; font-size: ${fontSize}px !important; font-weight: 900 !important;" letter-spacing="-0.5px">${safeLine}</text>
          <rect x="17" y="33" width="14" height="3.5" rx="1.7" fill="#0f172a"/>
          <circle cx="24" cy="34.7" r="1.2" fill="#34d399"/>
          <path d="M 9.5 33.5 Q 13 32.7 16 34" stroke="#fef08a" stroke-width="2.2" stroke-linecap="round" fill="none"/>
          <path d="M 38.5 33.5 Q 35 32.7 32 34" stroke="#fef08a" stroke-width="2.2" stroke-linecap="round" fill="none"/>
        </svg>
      `;
    }

    // 8. SOR NSG 12 - štandardný plynový CNG, strešná klenba CNG, LED svetlá
    function renderSorNsg12Svg(line, delayColorOrMinutes = '') {
      const delayColor = getDelayBarColor(delayColorOrMinutes);
      const fontSize = getLineFontSize(line);
      const safeLine = escapeXml(line);
      const clipId = 'ws-clip-nsg12-' + Math.random().toString(36).substr(2, 7);
      return `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 46" width="44" height="46" class="veh-front-svg">
          <defs>
            <clipPath id="${clipId}">
              <rect x="8" y="9" width="28" height="22" rx="5"/>
            </clipPath>
          </defs>
          <path d="M 11 7 Q 22 1 33 7 Z" fill="#047857" stroke="#34d399" stroke-width="1.4"/>
          <rect x="17" y="3" width="10" height="3" rx="1" fill="#065f46"/>
          <text x="22" y="5" text-anchor="middle" dominant-baseline="central" font-size="2.2px" font-weight="900" fill="#a7f3d0" font-family="'JetBrains Mono', sans-serif">CNG</text>
          <rect x="7" y="39" width="6" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="31" y="39" width="6" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="5" y="6" width="34" height="34" rx="7" fill="#059669" stroke="#34d399" stroke-width="2.5"/>
          <rect x="1.5" y="11" width="3.5" height="8" rx="1.6" fill="#0f172a" stroke="#34d399" stroke-width="1"/>
          <rect x="39" y="11" width="3.5" height="8" rx="1.6" fill="#0f172a" stroke="#34d399" stroke-width="1"/>
          <rect x="8" y="9" width="28" height="22" rx="5" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
          <rect class="veh-delay-bar" x="8" y="9" width="28" height="6" fill="${delayColor}" clip-path="url(#${clipId})" style="fill: ${delayColor} !important; ${(!delayColor || delayColor === 'transparent') ? 'display: none;' : ''}"/>
          <text x="22" y="22" text-anchor="middle" dominant-baseline="central" alignment-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="${fontSize}px" fill="#0f172a" style="fill: #0f172a !important; font-size: ${fontSize}px !important; font-weight: 900 !important;" letter-spacing="-0.5px">${safeLine}</text>
          <rect x="15" y="32.5" width="14" height="3.5" rx="1.7" fill="#0f172a"/>
          <circle cx="22" cy="34.2" r="1.2" fill="#34d399"/>
          <path d="M 8.5 33 Q 11 32.5 13.5 33.5" stroke="#fef08a" stroke-width="2" stroke-linecap="round" fill="none"/>
          <path d="M 35.5 33 Q 33 32.5 30.5 33.5" stroke="#fef08a" stroke-width="2" stroke-linecap="round" fill="none"/>
        </svg>
      `;
    }

    // 9. SOR NB 18 City - chrbtica DPMK, tmavomodrá, strešná A/C, 2 PÁRY ŽLTÝCH SVETIEL (4 svetlá)
    function renderSorNb18Svg(line, delayColorOrMinutes = '') {
      const delayColor = getDelayBarColor(delayColorOrMinutes);
      const fontSize = getLineFontSize(line);
      const safeLine = escapeXml(line);
      const clipId = 'ws-clip-nb18-' + Math.random().toString(36).substr(2, 7);
      return `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 45" width="48" height="45" class="veh-front-svg">
          <defs>
            <clipPath id="${clipId}">
              <rect x="8" y="7" width="32" height="23" rx="4"/>
            </clipPath>
          </defs>
          <rect x="15" y="1" width="18" height="4" rx="2" fill="#3b82f6" stroke="#0f172a" stroke-width="1"/>
          <line x1="18" y1="3" x2="30" y2="3" stroke="#ffffff" stroke-width="1" stroke-linecap="round" opacity="0.7"/>
          <rect x="7" y="38" width="7" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="34" y="38" width="7" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="5" y="4" width="38" height="35" rx="5" fill="#1d4ed8" stroke="#3b82f6" stroke-width="2.5"/>
          <rect x="0.5" y="7" width="4.2" height="11" rx="2" fill="#0f172a" stroke="#3b82f6" stroke-width="1.2"/>
          <path d="M 5 8 Q 2 8 2 10" fill="none" stroke="#334155" stroke-width="1.8"/>
          <rect x="43.3" y="7" width="4.2" height="11" rx="2" fill="#0f172a" stroke="#3b82f6" stroke-width="1.2"/>
          <path d="M 43 8 Q 46 8 46 10" fill="none" stroke="#334155" stroke-width="1.8"/>
          <rect x="8" y="7" width="32" height="23" rx="4" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
          <rect class="veh-delay-bar" x="8" y="7" width="32" height="6" fill="${delayColor}" clip-path="url(#${clipId})" style="fill: ${delayColor} !important; ${(!delayColor || delayColor === 'transparent') ? 'display: none;' : ''}"/>
          <text x="24" y="21.5" text-anchor="middle" dominant-baseline="central" alignment-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="${fontSize}px" fill="#0f172a" style="fill: #0f172a !important; font-size: ${fontSize}px !important; font-weight: 900 !important;" letter-spacing="-0.5px">${safeLine}</text>
          <rect x="17" y="32" width="14" height="4" rx="1.8" fill="#0f172a"/>
          <rect x="8.5" y="32.5" width="2.8" height="3.2" rx="0.8" fill="#fef08a"/>
          <rect x="12" y="32.5" width="2.8" height="3.2" rx="0.8" fill="#fef08a"/>
          <rect x="33.2" y="32.5" width="2.8" height="3.2" rx="0.8" fill="#fef08a"/>
          <rect x="36.7" y="32.5" width="2.8" height="3.2" rx="0.8" fill="#fef08a"/>
        </svg>
      `;
    }

    // 10. SOR NB 12 City - štandardný, svetlomodrá, 4 žlté svetlomety
    function renderSorNb12Svg(line, delayColorOrMinutes = '') {
      const delayColor = getDelayBarColor(delayColorOrMinutes);
      const fontSize = getLineFontSize(line);
      const safeLine = escapeXml(line);
      const clipId = 'ws-clip-nb12-' + Math.random().toString(36).substr(2, 7);
      return `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 44" width="44" height="44" class="veh-front-svg">
          <defs>
            <clipPath id="${clipId}">
              <rect x="8" y="7" width="28" height="23" rx="4"/>
            </clipPath>
          </defs>
          <rect x="7" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="31" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="5" y="4" width="34" height="35" rx="6" fill="#0284c7" stroke="#38bdf8" stroke-width="2.5"/>
          <rect x="1.5" y="9" width="3.5" height="8" rx="1.5" fill="#1e293b" stroke="#38bdf8" stroke-width="1"/>
          <rect x="39" y="9" width="3.5" height="8" rx="1.5" fill="#1e293b" stroke="#38bdf8" stroke-width="1"/>
          <rect x="8" y="7" width="28" height="23" rx="4" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
          <rect class="veh-delay-bar" x="8" y="7" width="28" height="6" fill="${delayColor}" clip-path="url(#${clipId})" style="fill: ${delayColor} !important; ${(!delayColor || delayColor === 'transparent') ? 'display: none;' : ''}"/>
          <text x="22" y="21.5" text-anchor="middle" dominant-baseline="central" alignment-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="${fontSize}px" fill="#0f172a" style="fill: #0f172a !important; font-size: ${fontSize}px !important; font-weight: 900 !important;" letter-spacing="-0.5px">${safeLine}</text>
          <rect x="15" y="32" width="14" height="4" rx="1.8" fill="#0f172a"/>
          <rect x="8.5" y="32.5" width="2.6" height="3" rx="0.8" fill="#fef08a"/>
          <rect x="11.8" y="32.5" width="2.6" height="3" rx="0.8" fill="#fef08a"/>
          <rect x="29.6" y="32.5" width="2.6" height="3" rx="0.8" fill="#fef08a"/>
          <rect x="32.9" y="32.5" width="2.6" height="3" rx="0.8" fill="#fef08a"/>
        </svg>
      `;
    }

    // 11. SOR NBG 12 City - plynový NB, tyrkysový akcent, strešná nadstavba CNG
    function renderSorNbg12Svg(line, delayColorOrMinutes = '') {
      const delayColor = getDelayBarColor(delayColorOrMinutes);
      const fontSize = getLineFontSize(line);
      const safeLine = escapeXml(line);
      const clipId = 'ws-clip-nbg12-' + Math.random().toString(36).substr(2, 7);
      return `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 46" width="44" height="46" class="veh-front-svg">
          <defs>
            <clipPath id="${clipId}">
              <rect x="8" y="9" width="28" height="22" rx="4"/>
            </clipPath>
          </defs>
          <path d="M 11 7 Q 22 1.5 33 7 Z" fill="#0891b2" stroke="#06b6d4" stroke-width="1.2"/>
          <rect x="17" y="3.5" width="10" height="2.5" rx="1" fill="#155e75"/>
          <text x="22" y="5" text-anchor="middle" dominant-baseline="central" font-size="2px" font-weight="900" fill="#a5f3fc" font-family="'JetBrains Mono', sans-serif">CNG</text>
          <rect x="7" y="39" width="6" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="31" y="39" width="6" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="5" y="6" width="34" height="34" rx="6" fill="#0284c7" stroke="#06b6d4" stroke-width="2.5"/>
          <rect x="1.5" y="10" width="3.5" height="8" rx="1.5" fill="#1e293b" stroke="#06b6d4" stroke-width="1"/>
          <rect x="39" y="10" width="3.5" height="8" rx="1.5" fill="#1e293b" stroke="#06b6d4" stroke-width="1"/>
          <rect x="8" y="9" width="28" height="22" rx="4" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
          <rect class="veh-delay-bar" x="8" y="9" width="28" height="6" fill="${delayColor}" clip-path="url(#${clipId})" style="fill: ${delayColor} !important; ${(!delayColor || delayColor === 'transparent') ? 'display: none;' : ''}"/>
          <text x="22" y="22" text-anchor="middle" dominant-baseline="central" alignment-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="${fontSize}px" fill="#0f172a" style="fill: #0f172a !important; font-size: ${fontSize}px !important; font-weight: 900 !important;" letter-spacing="-0.5px">${safeLine}</text>
          <rect x="15" y="32.5" width="14" height="3.8" rx="1.8" fill="#0f172a"/>
          <rect x="8.5" y="33" width="2.6" height="2.8" rx="0.8" fill="#fef08a"/>
          <rect x="11.8" y="33" width="2.6" height="2.8" rx="0.8" fill="#fef08a"/>
          <rect x="29.6" y="33" width="2.6" height="2.8" rx="0.8" fill="#fef08a"/>
          <rect x="32.9" y="33" width="2.6" height="2.8" rx="0.8" fill="#fef08a"/>
        </svg>
      `;
    }

    // 12. SOR BN 9,5 - úzky midibus 40px, fialový lem, kompaktné okrúhle svetlá
    function renderSorBn95Svg(line, delayColorOrMinutes = '') {
      const delayColor = getDelayBarColor(delayColorOrMinutes);
      const fontSize = getLineFontSize(line);
      const safeLine = escapeXml(line);
      const clipId = 'ws-clip-bn95-' + Math.random().toString(36).substr(2, 7);
      return `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 44" width="40" height="44" class="veh-front-svg">
          <defs>
            <clipPath id="${clipId}">
              <rect x="7" y="7" width="26" height="22" rx="3.5"/>
            </clipPath>
          </defs>
          <rect x="6" y="37" width="5.5" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="28.5" y="37" width="5.5" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="4.5" y="4" width="31" height="34" rx="5" fill="#38bdf8" stroke="#8b5cf6" stroke-width="2.3"/>
          <rect x="1.5" y="9" width="3" height="7.5" rx="1.2" fill="#1e293b" stroke="#8b5cf6" stroke-width="0.9"/>
          <rect x="35.5" y="9" width="3" height="7.5" rx="1.2" fill="#1e293b" stroke="#8b5cf6" stroke-width="0.9"/>
          <rect x="7" y="7" width="26" height="22" rx="3.5" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
          <rect class="veh-delay-bar" x="7" y="7" width="26" height="5.5" fill="${delayColor}" clip-path="url(#${clipId})" style="fill: ${delayColor} !important; ${(!delayColor || delayColor === 'transparent') ? 'display: none;' : ''}"/>
          <text x="20" y="21" text-anchor="middle" dominant-baseline="central" alignment-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="${fontSize}px" fill="#0f172a" style="fill: #0f172a !important; font-size: ${fontSize}px !important; font-weight: 900 !important;" letter-spacing="-0.5px">${safeLine}</text>
          <rect x="13" y="31.5" width="14" height="3.5" rx="1.7" fill="#0f172a"/>
          <circle cx="8" cy="33" r="1.9" fill="#fef08a" stroke="#ca8a04" stroke-width="0.7"/>
          <circle cx="32" cy="33" r="1.9" fill="#fef08a" stroke="#ca8a04" stroke-width="0.7"/>
        </svg>
      `;
    }

    // 13. SOR C 10,5 - prímestský / linkový, sivomodrý, vysokopodlažný vysoký nárazník
    function renderSorC105Svg(line, delayColorOrMinutes = '') {
      const delayColor = getDelayBarColor(delayColorOrMinutes);
      const fontSize = getLineFontSize(line);
      const safeLine = escapeXml(line);
      const clipId = 'ws-clip-c105-' + Math.random().toString(36).substr(2, 7);
      return `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 44" width="44" height="44" class="veh-front-svg">
          <defs>
            <clipPath id="${clipId}">
              <rect x="8" y="7" width="28" height="20" rx="3.5"/>
            </clipPath>
          </defs>
          <rect x="7" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="31" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="5" y="4" width="34" height="35" rx="5" fill="#38bdf8" stroke="#64748b" stroke-width="2.5"/>
          <rect x="1.5" y="9" width="3.5" height="8" rx="1.5" fill="#1e293b"/>
          <rect x="39" y="9" width="3.5" height="8" rx="1.5" fill="#1e293b"/>
          <rect x="8" y="7" width="28" height="20" rx="3.5" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
          <rect class="veh-delay-bar" x="8" y="7" width="28" height="5.5" fill="${delayColor}" clip-path="url(#${clipId})" style="fill: ${delayColor} !important; ${(!delayColor || delayColor === 'transparent') ? 'display: none;' : ''}"/>
          <text x="22" y="19" text-anchor="middle" dominant-baseline="central" alignment-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="${fontSize}px" fill="#0f172a" style="fill: #0f172a !important; font-size: ${fontSize}px !important; font-weight: 900 !important;" letter-spacing="-0.5px">${safeLine}</text>
          <rect x="5" y="29" width="34" height="8" rx="2" fill="#475569"/>
          <rect x="14" y="31" width="16" height="4" rx="1.5" fill="#0f172a"/>
          <circle cx="9.5" cy="33" r="2.2" fill="#fef08a" stroke="#ca8a04" stroke-width="0.8"/>
          <circle cx="34.5" cy="33" r="2.2" fill="#fef08a" stroke="#ca8a04" stroke-width="0.8"/>
        </svg>
      `;
    }

    // 14. Solaris Urbino 18 & 18,75 III - ikonické asymetrické čelné sklo (klesá vpravo), vertikálne šošovky svetiel
    function renderSolarisU18Svg(line, delayColorOrMinutes = '', isExtraLong = false) {
      const delayColor = getDelayBarColor(delayColorOrMinutes);
      const fontSize = getLineFontSize(line);
      const safeLine = escapeXml(line);
      const borderColor = isExtraLong ? '#000000' : '#94a3b8';
      const clipId = 'ws-clip-sol-u18-' + Math.random().toString(36).substr(2, 7);
      return `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 45" width="48" height="45" class="veh-front-svg">
          <defs>
            <clipPath id="${clipId}">
              <path d="M 8 7 L 40 7 L 40 32 L 28 32 L 28 29 L 8 29 Z"/>
            </clipPath>
          </defs>
          <rect x="16" y="1" width="16" height="4" rx="2" fill="#be123c" stroke="#0f172a" stroke-width="1"/>
          <rect x="7" y="38" width="7" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="34" y="38" width="7" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="5" y="4" width="38" height="35" rx="5" fill="#881337" stroke="${borderColor}" stroke-width="2.5"/>
          <rect x="0.8" y="8" width="4" height="10" rx="1.8" fill="#0f172a" stroke="#94a3b8" stroke-width="1"/>
          <rect x="43.2" y="8" width="4" height="10" rx="1.8" fill="#0f172a" stroke="#94a3b8" stroke-width="1"/>
          <path d="M 43 8 Q 46 6 46 8" fill="none" stroke="#0f172a" stroke-width="1.8"/>
          <path d="M 8 7 L 40 7 L 40 32 L 28 32 L 28 29 L 8 29 Z" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
          <rect class="veh-delay-bar" x="8" y="7" width="32" height="6" fill="${delayColor}" clip-path="url(#${clipId})" style="fill: ${delayColor} !important; ${(!delayColor || delayColor === 'transparent') ? 'display: none;' : ''}"/>
          <text x="23" y="20.5" text-anchor="middle" dominant-baseline="central" alignment-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="${fontSize}px" fill="#0f172a" style="fill: #0f172a !important; font-size: ${fontSize}px !important; font-weight: 900 !important;" letter-spacing="-0.5px">${safeLine}</text>
          <rect x="17" y="31.5" width="14" height="4.5" rx="2" fill="#0f172a"/>
          <circle cx="10" cy="31.5" r="1.6" fill="#fef08a" stroke="#ca8a04" stroke-width="0.5"/>
          <circle cx="10" cy="34.5" r="1.4" fill="#fef08a" stroke="#ca8a04" stroke-width="0.5"/>
          <circle cx="38" cy="31.5" r="1.6" fill="#fef08a" stroke="#ca8a04" stroke-width="0.5"/>
          <circle cx="38" cy="34.5" r="1.4" fill="#fef08a" stroke="#ca8a04" stroke-width="0.5"/>
        </svg>
      `;
    }

    // 15. Solaris Urbino 15 II / III - 46px trojnápravový, asymetrické okno, zlatý lem
    function renderSolarisU15Svg(line, delayColorOrMinutes = '') {
      const delayColor = getDelayBarColor(delayColorOrMinutes);
      const fontSize = getLineFontSize(line);
      const safeLine = escapeXml(line);
      const clipId = 'ws-clip-sol-u15-' + Math.random().toString(36).substr(2, 7);
      return `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 46 45" width="46" height="45" class="veh-front-svg">
          <defs>
            <clipPath id="${clipId}">
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
          <rect class="veh-delay-bar" x="8" y="7" width="30" height="6" fill="${delayColor}" clip-path="url(#${clipId})" style="fill: ${delayColor} !important; ${(!delayColor || delayColor === 'transparent') ? 'display: none;' : ''}"/>
          <text x="22" y="20.5" text-anchor="middle" dominant-baseline="central" alignment-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="${fontSize}px" fill="#0f172a" style="fill: #0f172a !important; font-size: ${fontSize}px !important; font-weight: 900 !important;" letter-spacing="-0.5px">${safeLine}</text>
          <rect x="16" y="31.5" width="14" height="4.5" rx="2" fill="#0f172a"/>
          <circle cx="10" cy="31.5" r="1.6" fill="#fef08a"/>
          <circle cx="10" cy="34.5" r="1.4" fill="#fef08a"/>
          <circle cx="36" cy="31.5" r="1.6" fill="#fef08a"/>
          <circle cx="36" cy="34.5" r="1.4" fill="#fef08a"/>
        </svg>
      `;
    }

    // 16. Solaris Urbino 12 IV (New Urbino) - ostré agresívne línie 4. generácie, klinové LED svetlá
    function renderSolarisU12IvSvg(line, delayColorOrMinutes = '') {
      const delayColor = getDelayBarColor(delayColorOrMinutes);
      const fontSize = getLineFontSize(line);
      const safeLine = escapeXml(line);
      const clipId = 'ws-clip-sol-u12iv-' + Math.random().toString(36).substr(2, 7);
      return `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 44" width="44" height="44" class="veh-front-svg">
          <defs>
            <clipPath id="${clipId}">
              <polygon points="8,7 36,7 36,31 25,31 25,28 8,28"/>
            </clipPath>
          </defs>
          <rect x="7" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="31" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
          <polygon points="5,4 39,4 39,38 5,38" fill="#dc2626" stroke="#991b1b" stroke-width="2.5"/>
          <rect x="1.5" y="8" width="3.5" height="9" rx="1" fill="#0f172a" stroke="#991b1b" stroke-width="1"/>
          <rect x="39" y="8" width="3.5" height="9" rx="1" fill="#0f172a" stroke="#991b1b" stroke-width="1"/>
          <polygon points="8,7 36,7 36,31 25,31 25,28 8,28" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
          <rect class="veh-delay-bar" x="8" y="7" width="28" height="6" fill="${delayColor}" clip-path="url(#${clipId})" style="fill: ${delayColor} !important; ${(!delayColor || delayColor === 'transparent') ? 'display: none;' : ''}"/>
          <text x="21" y="20" text-anchor="middle" dominant-baseline="central" alignment-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="${fontSize}px" fill="#0f172a" style="fill: #0f172a !important; font-size: ${fontSize}px !important; font-weight: 900 !important;" letter-spacing="-0.5px">${safeLine}</text>
          <rect x="15" y="32" width="14" height="4" rx="1.5" fill="#0f172a"/>
          <polygon points="8,33 13,31.5 13,34" fill="#fef08a" stroke="#ca8a04" stroke-width="0.5"/>
          <polygon points="36,33 31,31.5 31,34" fill="#fef08a" stroke="#ca8a04" stroke-width="0.5"/>
        </svg>
      `;
    }

    // 17. Solaris Urbino 12 III Hybrid - hybridná strešná nadstavba so zeleným eko pásikom, asymetrické okno
    function renderSolarisU12HybridSvg(line, delayColorOrMinutes = '') {
      const delayColor = getDelayBarColor(delayColorOrMinutes);
      const fontSize = getLineFontSize(line);
      const safeLine = escapeXml(line);
      const clipId = 'ws-clip-sol-hyb-' + Math.random().toString(36).substr(2, 7);
      return `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 46" width="44" height="46" class="veh-front-svg">
          <defs>
            <clipPath id="${clipId}">
              <path d="M 8 9 L 36 9 L 36 33 L 25 33 L 25 30 L 8 30 Z"/>
            </clipPath>
          </defs>
          <rect x="12" y="1.5" width="20" height="4.5" rx="2" fill="#16a34a" stroke="#0f172a" stroke-width="1"/>
          <line x1="15" y1="3.5" x2="29" y2="3.5" stroke="#86efac" stroke-width="1.2" stroke-linecap="round"/>
          <rect x="7" y="39" width="6" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="31" y="39" width="6" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="5" y="6" width="34" height="34" rx="6" fill="#dc2626" stroke="#16a34a" stroke-width="2.5"/>
          <rect x="1.5" y="10" width="3.5" height="8" rx="1.5" fill="#0f172a" stroke="#16a34a" stroke-width="1"/>
          <rect x="39" y="10" width="3.5" height="8" rx="1.5" fill="#0f172a" stroke="#16a34a" stroke-width="1"/>
          <path d="M 8 9 L 36 9 L 36 33 L 25 33 L 25 30 L 8 30 Z" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
          <rect class="veh-delay-bar" x="8" y="9" width="28" height="6" fill="${delayColor}" clip-path="url(#${clipId})" style="fill: ${delayColor} !important; ${(!delayColor || delayColor === 'transparent') ? 'display: none;' : ''}"/>
          <text x="21" y="22" text-anchor="middle" dominant-baseline="central" alignment-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="${fontSize}px" fill="#0f172a" style="fill: #0f172a !important; font-size: ${fontSize}px !important; font-weight: 900 !important;" letter-spacing="-0.5px">${safeLine}</text>
          <rect x="15" y="32.5" width="14" height="4" rx="1.8" fill="#0f172a"/>
          <circle cx="10" cy="32.5" r="1.5" fill="#fef08a"/>
          <circle cx="10" cy="35" r="1.3" fill="#fef08a"/>
          <circle cx="34" cy="32.5" r="1.5" fill="#fef08a"/>
          <circle cx="34" cy="35" r="1.3" fill="#fef08a"/>
        </svg>
      `;
    }

    // 18. Solaris Urbino 12 III štandardný - červená karoséria, asymetrické okno, zvislé svetlá
    function renderSolarisU12Svg(line, delayColorOrMinutes = '') {
      const delayColor = getDelayBarColor(delayColorOrMinutes);
      const fontSize = getLineFontSize(line);
      const safeLine = escapeXml(line);
      const clipId = 'ws-clip-sol-u12-' + Math.random().toString(36).substr(2, 7);
      return `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 44" width="44" height="44" class="veh-front-svg">
          <defs>
            <clipPath id="${clipId}">
              <path d="M 8 7 L 36 7 L 36 31 L 25 31 L 25 28 L 8 28 Z"/>
            </clipPath>
          </defs>
          <rect x="7" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="31" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="5" y="4" width="34" height="35" rx="6" fill="#dc2626" stroke="#991b1b" stroke-width="2.5"/>
          <rect x="1.5" y="9" width="3.5" height="8" rx="1.5" fill="#0f172a" stroke="#991b1b" stroke-width="1"/>
          <rect x="39" y="9" width="3.5" height="8" rx="1.5" fill="#0f172a" stroke="#991b1b" stroke-width="1"/>
          <path d="M 8 7 L 36 7 L 36 31 L 25 31 L 25 28 L 8 28 Z" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
          <rect class="veh-delay-bar" x="8" y="7" width="28" height="6" fill="${delayColor}" clip-path="url(#${clipId})" style="fill: ${delayColor} !important; ${(!delayColor || delayColor === 'transparent') ? 'display: none;' : ''}"/>
          <text x="21" y="20" text-anchor="middle" dominant-baseline="central" alignment-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="${fontSize}px" fill="#0f172a" style="fill: #0f172a !important; font-size: ${fontSize}px !important; font-weight: 900 !important;" letter-spacing="-0.5px">${safeLine}</text>
          <rect x="15" y="31.5" width="14" height="4" rx="1.8" fill="#0f172a"/>
          <circle cx="10" cy="31.5" r="1.5" fill="#fef08a"/>
          <circle cx="10" cy="34" r="1.3" fill="#fef08a"/>
          <circle cx="34" cy="31.5" r="1.5" fill="#fef08a"/>
          <circle cx="34" cy="34" r="1.3" fill="#fef08a"/>
        </svg>
      `;
    }

    // 19. Iveco Rosero First FCLLI - minibus 40px, predok dodávky Daily, chrómové lamely v mriežke
    function renderRoseroSvg(line, delayColorOrMinutes = '') {
      const delayColor = getDelayBarColor(delayColorOrMinutes);
      const fontSize = getLineFontSize(line);
      const safeLine = escapeXml(line);
      const clipId = 'ws-clip-rosero-' + Math.random().toString(36).substr(2, 7);
      return `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 44" width="40" height="44" class="veh-front-svg">
          <defs>
            <clipPath id="${clipId}">
              <rect x="7" y="7" width="26" height="21" rx="3.5"/>
            </clipPath>
          </defs>
          <rect x="6" y="37" width="5.5" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="28.5" y="37" width="5.5" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="5" y="4" width="30" height="34" rx="5" fill="#0284c7" stroke="#38bdf8" stroke-width="2.3"/>
          <rect x="1.5" y="9" width="3.5" height="8" rx="1.2" fill="#0f172a"/>
          <rect x="35" y="9" width="3.5" height="8" rx="1.2" fill="#0f172a"/>
          <rect x="7" y="7" width="26" height="21" rx="3.5" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
          <rect class="veh-delay-bar" x="7" y="7" width="26" height="5.5" fill="${delayColor}" clip-path="url(#${clipId})" style="fill: ${delayColor} !important; ${(!delayColor || delayColor === 'transparent') ? 'display: none;' : ''}"/>
          <text x="20" y="20" text-anchor="middle" dominant-baseline="central" alignment-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="${fontSize}px" fill="#0f172a" style="fill: #0f172a !important; font-size: ${fontSize}px !important; font-weight: 900 !important;" letter-spacing="-0.5px">${safeLine}</text>
          <rect x="13" y="30.5" width="14" height="4.5" rx="1.5" fill="#1e293b"/>
          <line x1="15" y1="32" x2="25" y2="32" stroke="#94a3b8" stroke-width="0.8"/>
          <line x1="15" y1="33.5" x2="25" y2="33.5" stroke="#94a3b8" stroke-width="0.8"/>
          <polygon points="8,32 12,30.8 12,33.5" fill="#fef08a"/>
          <polygon points="32,32 28,30.8 28,33.5" fill="#fef08a"/>
        </svg>
      `;
    }

    // 20. Ikarus 280.08/A - kĺbový historický 48px, DELENÉ DVOJDIELNE ČELNÉ SKLO SO STĹPIKOM, vetracie poklopy
    function renderIkarus280Svg(line, delayColorOrMinutes = '') {
      const delayColor = getDelayBarColor(delayColorOrMinutes);
      const fontSize = getLineFontSize(line);
      const safeLine = escapeXml(line);
      const clipId = 'ws-clip-ikarus-' + Math.random().toString(36).substr(2, 7);
      return `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 44" width="48" height="44" class="veh-front-svg">
          <defs>
            <clipPath id="${clipId}">
              <g>
                <rect x="8" y="7" width="14.5" height="23" rx="2"/>
                <rect x="25.5" y="7" width="14.5" height="23" rx="2"/>
              </g>
            </clipPath>
          </defs>
          <rect x="15" y="2" width="6" height="2" rx="0.5" fill="#b45309"/>
          <rect x="27" y="2" width="6" height="2" rx="0.5" fill="#b45309"/>
          <rect x="7" y="38" width="7" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="34" y="38" width="7" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="5" y="4" width="38" height="35" rx="3" fill="#78350f" stroke="#f59e0b" stroke-width="2.5"/>
          <rect x="1" y="9" width="3.5" height="8" rx="1" fill="#0f172a"/>
          <rect x="43.5" y="9" width="3.5" height="8" rx="1" fill="#0f172a"/>
          <rect x="8" y="7" width="14.5" height="23" rx="2" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
          <rect x="25.5" y="7" width="14.5" height="23" rx="2" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
          <rect x="23" y="6" width="2" height="25" fill="#0f172a"/>
          <rect class="veh-delay-bar" x="8" y="7" width="32" height="6" fill="${delayColor}" clip-path="url(#${clipId})" style="fill: ${delayColor} !important; ${(!delayColor || delayColor === 'transparent') ? 'display: none;' : ''}"/>
          <text x="24" y="21.5" text-anchor="middle" dominant-baseline="central" alignment-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="${fontSize}px" fill="#0f172a" style="fill: #0f172a !important; font-size: ${fontSize}px !important; font-weight: 900 !important;" letter-spacing="-0.5px">${safeLine}</text>
          <rect x="16" y="31.5" width="16" height="4.5" rx="1" fill="#0f172a"/>
          <line x1="18" y1="33" x2="30" y2="33" stroke="#cbd5e1" stroke-width="0.8"/>
          <circle cx="11" cy="33.5" r="2.2" fill="#fef08a" stroke="#ca8a04" stroke-width="0.8"/>
          <circle cx="8" cy="33.5" r="1.1" fill="#f97316"/>
          <circle cx="37" cy="33.5" r="2.2" fill="#fef08a" stroke="#ca8a04" stroke-width="0.8"/>
          <circle cx="40" cy="33.5" r="1.1" fill="#f97316"/>
        </svg>
      `;
    }

    // 21. Karosa B 832.1654 - historický tehlovočervený hranatý, biely lem, obdĺžnikové svetlá
    function renderKarosaB832Svg(line, delayColorOrMinutes = '') {
      const delayColor = getDelayBarColor(delayColorOrMinutes);
      const fontSize = getLineFontSize(line);
      const safeLine = escapeXml(line);
      const clipId = 'ws-clip-karosa-' + Math.random().toString(36).substr(2, 7);
      return `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 44" width="44" height="44" class="veh-front-svg">
          <defs>
            <clipPath id="${clipId}">
              <rect x="8" y="7" width="28" height="21" rx="2"/>
            </clipPath>
          </defs>
          <rect x="7" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="31" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="5" y="4" width="34" height="35" rx="3" fill="#c2410c" stroke="#ffffff" stroke-width="2.5"/>
          <rect x="1.5" y="9" width="3" height="8" rx="1" fill="#0f172a"/>
          <rect x="39.5" y="9" width="3" height="8" rx="1" fill="#0f172a"/>
          <rect x="8" y="7" width="28" height="21" rx="2" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
          <rect class="veh-delay-bar" x="8" y="7" width="28" height="5.5" fill="${delayColor}" clip-path="url(#${clipId})" style="fill: ${delayColor} !important; ${(!delayColor || delayColor === 'transparent') ? 'display: none;' : ''}"/>
          <text x="22" y="20" text-anchor="middle" dominant-baseline="central" alignment-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="${fontSize}px" fill="#0f172a" style="fill: #0f172a !important; font-size: ${fontSize}px !important; font-weight: 900 !important;" letter-spacing="-0.5px">${safeLine}</text>
          <rect x="5" y="30" width="34" height="7.5" rx="1" fill="#0f172a"/>
          <rect x="8" y="31.5" width="4.5" height="3" rx="0.5" fill="#fef08a" stroke="#ca8a04" stroke-width="0.6"/>
          <rect x="13" y="32" width="2" height="2" rx="0.3" fill="#f97316"/>
          <rect x="31.5" y="31.5" width="4.5" height="3" rx="0.5" fill="#fef08a" stroke="#ca8a04" stroke-width="0.6"/>
          <rect x="29" y="32" width="2" height="2" rx="0.3" fill="#f97316"/>
        </svg>
      `;
    }

    // 22. Autobus DPMK všeobecný (fallback)
    function renderGeneralBusSvg(line, delayColorOrMinutes = '', bodyColor = '#2563eb', strokeColor = '#60a5fa') {
      const delayColor = getDelayBarColor(delayColorOrMinutes);
      const fontSize = getLineFontSize(line);
      const safeLine = escapeXml(line);
      const validBodyColor = bodyColor || '#2563eb';
      const validStrokeColor = strokeColor || '#60a5fa';
      const clipId = 'ws-clip-gbus-' + Math.random().toString(36).substr(2, 7);
      return `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 44" width="44" height="44" class="veh-front-svg">
          <defs>
            <clipPath id="${clipId}">
              <rect x="8" y="7" width="28" height="23" rx="4"/>
            </clipPath>
          </defs>
          <rect x="7" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="31" y="38" width="6" height="4" rx="1.5" fill="#0f172a"/>
          <rect x="5" y="4" width="34" height="35" rx="6" fill="${validBodyColor}" stroke="${validStrokeColor}" stroke-width="2.5"/>
          <rect x="1.5" y="9" width="3.5" height="8" rx="1.5" fill="#1e293b" stroke="${validStrokeColor}" stroke-width="1"/>
          <rect x="39" y="9" width="3.5" height="8" rx="1.5" fill="#1e293b" stroke="${validStrokeColor}" stroke-width="1"/>
          <rect x="8" y="7" width="28" height="23" rx="4" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>
          <rect class="veh-delay-bar" x="8" y="7" width="28" height="6" fill="${delayColor}" clip-path="url(#${clipId})" style="fill: ${delayColor} !important; ${(!delayColor || delayColor === 'transparent') ? 'display: none;' : ''}"/>
          <text x="22" y="21.5" text-anchor="middle" dominant-baseline="central" alignment-baseline="central" font-family="'JetBrains Mono', -apple-system, sans-serif" font-weight="900" font-size="${fontSize}px" fill="#0f172a" style="fill: #0f172a !important; font-size: ${fontSize}px !important; font-weight: 900 !important;" letter-spacing="-0.5px">${safeLine}</text>
          <rect x="15" y="32" width="14" height="4" rx="2" fill="#0f172a"/>
          <rect x="8.5" y="32" width="4.5" height="3.5" rx="1.5" fill="#fef08a" stroke="#ca8a04" stroke-width="0.8"/>
          <rect x="31" y="32" width="4.5" height="3.5" rx="1.5" fill="#fef08a" stroke="#ca8a04" stroke-width="0.8"/>
        </svg>
      `;
    }

    // Spätná kompatibilita pre volania pôvodných funkcií
    function renderTramSvg(b, s, line, d) { return renderGeneralTramSvg(line, d); }
    function renderElectricBusSvg(b, s, line, d) { return renderSorEbnSvg(line, d); }
    function renderShortBusSvg(b, s, line, d) { return renderGeneralBusSvg(line, d, b, s); }
    function renderLongBusSvg(b, s, line, d) { return renderSorNb18Svg(line, d); }

    // Tvorba dynamickej front-view SVG ikony vozidla pre konkrétny model
    function createVehicleMarkerIcon(v, isStale) {
      const cat = getVehicleCategory(v) || {};
      const line = String(v.line || '?');
      const modelKey = getVehicleModelKey(v);

      // 4-stupňová stupnica meškania pre indikačnú lištu podľa referencie image_d62ae7.png
      const delayMinutes = (v.delay_minutes !== undefined && v.delay_minutes !== null) ? Number(v.delay_minutes) : 0;
      let delayColor = 'transparent';
      if (!isNaN(delayMinutes) && delayMinutes > 0) {
        if (delayMinutes <= 3) {
          delayColor = '#facc15';
        } else if (delayMinutes <= 5) {
          delayColor = '#f97316';
        } else {
          delayColor = '#ef4444';
        }
      }

      let svgHtml = '';
      let iconSize = [44, 44];
      let iconAnchor = [22, 22];
      let popupAnchor = [0, -24];

      switch (modelKey) {
        case 'tram-vario':
          svgHtml = renderVarioLfSvg(line, delayColor);
          iconSize = [44, 48];
          iconAnchor = [22, 28];
          popupAnchor = [0, -28];
          break;
        case 'tram-kt8':
          svgHtml = renderKt8d5Svg(line, delayColor);
          iconSize = [46, 48];
          iconAnchor = [23, 28];
          popupAnchor = [0, -28];
          break;
        case 'tram-t6':
          svgHtml = renderT6a5Svg(line, delayColor);
          iconSize = [44, 48];
          iconAnchor = [22, 28];
          popupAnchor = [0, -28];
          break;
        case 'tram':
          svgHtml = renderGeneralTramSvg(line, delayColor);
          iconSize = [44, 48];
          iconAnchor = [22, 28];
          popupAnchor = [0, -28];
          break;
        case 'sor-ns18':
          svgHtml = renderSorNs18ElectricSvg(line, delayColor);
          iconSize = [48, 46];
          iconAnchor = [24, 23];
          popupAnchor = [0, -25];
          break;
        case 'sor-ebn':
          svgHtml = renderSorEbnSvg(line, delayColor);
          iconSize = [44, 46];
          iconAnchor = [22, 23];
          popupAnchor = [0, -25];
          break;
        case 'sor-nsg18':
          svgHtml = renderSorNsg18Svg(line, delayColor);
          iconSize = [48, 46];
          iconAnchor = [24, 23];
          popupAnchor = [0, -25];
          break;
        case 'sor-nsg12':
          svgHtml = renderSorNsg12Svg(line, delayColor);
          iconSize = [44, 46];
          iconAnchor = [22, 23];
          popupAnchor = [0, -25];
          break;
        case 'sor-nb18':
          svgHtml = renderSorNb18Svg(line, delayColor);
          iconSize = [48, 45];
          iconAnchor = [24, 22.5];
          popupAnchor = [0, -24];
          break;
        case 'sor-nb12':
          svgHtml = renderSorNb12Svg(line, delayColor);
          iconSize = [44, 44];
          iconAnchor = [22, 22];
          popupAnchor = [0, -24];
          break;
        case 'sor-nbg12':
          svgHtml = renderSorNbg12Svg(line, delayColor);
          iconSize = [44, 46];
          iconAnchor = [22, 23];
          popupAnchor = [0, -25];
          break;
        case 'sor-bn95':
          svgHtml = renderSorBn95Svg(line, delayColor);
          iconSize = [40, 44];
          iconAnchor = [20, 22];
          popupAnchor = [0, -24];
          break;
        case 'sor-c105':
          svgHtml = renderSorC105Svg(line, delayColor);
          iconSize = [44, 44];
          iconAnchor = [22, 22];
          popupAnchor = [0, -24];
          break;
        case 'solaris-u1875':
          svgHtml = renderSolarisU18Svg(line, delayColor, true);
          iconSize = [48, 45];
          iconAnchor = [24, 22.5];
          popupAnchor = [0, -24];
          break;
        case 'solaris-u18':
          svgHtml = renderSolarisU18Svg(line, delayColor, false);
          iconSize = [48, 45];
          iconAnchor = [24, 22.5];
          popupAnchor = [0, -24];
          break;
        case 'solaris-u15':
          svgHtml = renderSolarisU15Svg(line, delayColor);
          iconSize = [46, 45];
          iconAnchor = [23, 22.5];
          popupAnchor = [0, -24];
          break;
        case 'solaris-u12-iv':
          svgHtml = renderSolarisU12IvSvg(line, delayColor);
          iconSize = [44, 44];
          iconAnchor = [22, 22];
          popupAnchor = [0, -24];
          break;
        case 'solaris-u12-hybrid':
          svgHtml = renderSolarisU12HybridSvg(line, delayColor);
          iconSize = [44, 46];
          iconAnchor = [22, 23];
          popupAnchor = [0, -25];
          break;
        case 'solaris-u12':
          svgHtml = renderSolarisU12Svg(line, delayColor);
          iconSize = [44, 44];
          iconAnchor = [22, 22];
          popupAnchor = [0, -24];
          break;
        case 'rosero':
          svgHtml = renderRoseroSvg(line, delayColor);
          iconSize = [40, 44];
          iconAnchor = [20, 22];
          popupAnchor = [0, -24];
          break;
        case 'ikarus':
          svgHtml = renderIkarus280Svg(line, delayColor);
          iconSize = [48, 44];
          iconAnchor = [24, 22];
          popupAnchor = [0, -24];
          break;
        case 'karosa':
          svgHtml = renderKarosaB832Svg(line, delayColor);
          iconSize = [44, 44];
          iconAnchor = [22, 22];
          popupAnchor = [0, -24];
          break;
        default:
          svgHtml = renderGeneralBusSvg(line, delayColor, cat.color, cat.borderColor);
          iconSize = [44, 44];
          iconAnchor = [22, 22];
          popupAnchor = [0, -24];
          break;
      }

      const stopInfo = (v.is_on_stop && v.current_stop_name) ? ` • Stojí na: ${v.current_stop_name}` : '';
      const tooltipTitle = `Linka ${line} • ${cat.name || 'Vozidlo'}${stopInfo} • ${v.destination || 'Neznámy smer'}`;

      return L.divIcon({
        className: 'custom-modern-veh-icon',
        html: `
          <div class="modern-veh-marker ${isStale ? 'veh-stale' : ''}" title="${tooltipTitle}">
            ${svgHtml}
          </div>
        `,
        iconSize: iconSize,
        iconAnchor: iconAnchor,
        popupAnchor: popupAnchor
      });
    }'''

with open(r"C:\Users\tomas\mhd_kosice\mapa.html", "r", encoding="utf-8") as f:
    content = f.read()

# Nájdeme štart: "// Určenie typu masky vozidla"
# a koniec: "    function buildPopupHtml(v) {"
start_marker = "    // Určenie typu masky vozidla (Električka, Elektrobus, Dlhý kĺbový autobus, Štandardný krátky autobus)"
end_marker = "    function buildPopupHtml(v) {"

start_pos = content.find(start_marker)
end_pos = content.find(end_marker)

if start_pos == -1 or end_pos == -1:
    print(f"CHYBA: Markery sa nenašli! start_pos={start_pos}, end_pos={end_pos}")
else:
    new_content = content[:start_pos] + js_code + "\n\n" + content[end_pos:]
    with open(r"C:\Users\tomas\mhd_kosice\mapa.html", "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Úspešne vložené do mapa.html!")
