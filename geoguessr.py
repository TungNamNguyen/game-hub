"""Địa Đồ (GeoGuessr) — Trò chơi đoán tọa độ địa lý (1-6 người: Chơi đơn, Đua điểm FFA, Đấu Sinh Tử 1v1 & Team Boss Mode)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import random
import threading
import time
import urllib.request

from games import GameError, SeatedRoom, bot_uid

ROUNDS_PER_MATCH = 5
ALLOWED_ROUND_COUNTS = (5, 10, 15, 20)
MAX_DUEL_ROUNDS = 25
MAX_STREAK_ROUNDS = 50
GUESS_SECONDS = 60.0
PANIC_SECONDS = 15.0
REVEAL_SECONDS = 8.0
GRACE_SECONDS = 0.15
EARTH_RADIUS_KM = 6371.071
DEFAULT_WORLD_MAX_ERROR_KM = 14916.862
# Lưu ở thư mục assets/ để tách biệt dữ liệu tĩnh với data/ (vốn bị .dockerignore chặn)
GEO_DATA_PATH = Path(__file__).resolve().parent / "assets" / "geo_locations.json"

GEO_BOT_NAMES = ("Phượt Thủ", "Hoa Tiêu", "Thổ Địa", "Nhà Bản Đồ", "Lữ Khách")

ALLOWED_ROUND_TIMES = (30, 45, 60, 90, 120)
DIFFICULTY_PRESETS: dict[str, dict] = {
    "global": {"round_time": 60, "move_rule": "MOVING", "error_scale": 1.0},
    "landmark": {"round_time": 60, "move_rule": "MOVING", "error_scale": 1.0},
}


def normalize_difficulty(raw: str | None) -> str:
    """Chuẩn hoá chế độ chơi về 'global' (Toàn Cầu 100%) hoặc 'landmark' (Địa Danh)."""
    if raw in ("landmark", "easy"):
        return "landmark"
    return "global"


DIRECTIONS_VI = (
    "Bắc", "Đông Bắc", "Đông", "Đông Nam",
    "Nam", "Tây Nam", "Tây", "Tây Bắc",
)

# Mã quốc gia ISO-2 hợp lệ cho từng bản đồ để chặn tuyệt đối lỗi lọt biên giới
# (ví dụ Kratié 'KH' của Campuchia lọt vào chế độ Việt Nam).
MODE_ISO_COUNTRIES: dict[str, set[str]] = {
    "vietnam": {"VN"},
    "asia": {
        "VN", "JP", "KR", "TW", "HK", "MO", "TH", "MY", "SG", "ID", "PH",
        "KH", "LA", "MM", "IN", "LK", "NP", "BT", "BD", "PK", "KZ", "KG",
        "UZ", "MN", "AE", "QA", "OM", "JO", "IL", "TR", "AM", "GE", "AZ",
        "CN", "RU",
    },
    "europe": {
        "GB", "UK", "IE", "FR", "ES", "PT", "IT", "DE", "NL", "BE", "LU",
        "CH", "AT", "DK", "NO", "SE", "FI", "IS", "PL", "CZ", "SK", "HU",
        "RO", "BG", "GR", "HR", "SI", "RS", "BA", "ME", "MK", "AL", "LT",
        "LV", "EE", "UA", "BY", "MD", "AD", "MC", "SM", "MT", "CY", "FO",
        "LI", "VA",
    },
    "north_america": {
        "US", "CA", "MX", "GT", "BZ", "HN", "SV", "NI", "CR", "PA", "DO",
        "PR", "VI", "BM", "BS", "JM", "TT", "GL", "PM", "CU",
    },
    "south_america": {
        "BR", "AR", "CL", "CO", "PE", "EC", "BO", "PY", "UY", "VE", "GY",
        "SR", "GF", "FK",
    },
    "africa": {
        "ZA", "KE", "TZ", "UG", "RW", "NG", "GH", "SN", "EG", "TN", "MA",
        "BW", "NA", "SZ", "LS", "MG", "MU", "RE", "ST", "MZ", "ZM", "MW",
        "ET", "DZ",
    },
    "oceania": {
        "AU", "NZ", "FJ", "PG", "SB", "VU", "NC", "PF", "WS", "TO", "CK",
        "GU", "MP", "AS", "PN", "UM", "CX", "CC", "NF", "HI",
    },
}

_VN_FOREIGN_TOKENS = (
    "kratié", "kratie", "mondulkiri", "ratanakiri", "svay rieng", "prey veng",
    "tboung khmum", "kampong cham", "kandal", "takeo", "kampot", "phnom penh",
    "stung treng", "siem reap", "cambodia", "campuchia", "savannakhet",
    "champasak", "attapeu", "sekong", "salavan", "khammouane", "bolikhamxai",
    "xiangkhouang", "houaphanh", "luang prabang", "phongsaly", "laos",
    "yunnan", "guangxi", "china", "trung quốc",
)


def is_valid_country_for_mode(mode: str, country_code: str, address: str = "") -> bool:
    """Kiểm tra mã quốc gia ISO-2 và địa chỉ thực tế khớp với chế độ bản đồ."""
    cc = (country_code or "").strip().upper()
    if mode == "vietnam":
        if cc != "VN":
            return False
        addr_low = (address or "").lower()
        return not any(tok in addr_low for tok in _VN_FOREIGN_TOKENS)
    allowed = MODE_ISO_COUNTRIES.get(mode)
    if allowed:
        if not cc or cc not in allowed:
            return False
    return True


def _vn_box(lat: float, lng: float, d: float = 0.08) -> tuple[float, float, float, float]:
    return (round(lat - d, 4), round(lat + d, 4), round(lng - d, 4), round(lng + d, 4))


# Các vùng tọa độ có mật độ Google Street View 360° chuẩn cao phủ kín 63 tỉnh VN & 6 châu lục.
STREETVIEW_LAND_BOXES: dict[str, list[tuple[float, float, float, float]]] = {
    # 63 cụm tọa độ bám sát nội địa các tỉnh/thành Việt Nam (tránh trùm sang KH/LA/CN)
    "vietnam": [
        _vn_box(21.028, 105.854, 0.14),   # Hà Nội
        _vn_box(20.844, 106.688, 0.12),   # Hải Phòng
        _vn_box(20.959, 107.042, 0.12),   # Hạ Long - Quảng Ninh
        _vn_box(21.186, 106.076, 0.10),   # Bắc Ninh
        _vn_box(21.273, 106.195, 0.10),   # Bắc Giang
        _vn_box(21.594, 105.848, 0.12),   # Thái Nguyên
        _vn_box(21.309, 105.402, 0.10),   # Phú Thọ
        _vn_box(21.310, 105.605, 0.09),   # Vĩnh Phúc
        _vn_box(20.937, 106.315, 0.09),   # Hải Dương
        _vn_box(20.646, 106.051, 0.09),   # Hưng Yên
        _vn_box(20.545, 105.912, 0.08),   # Hà Nam
        _vn_box(20.438, 106.162, 0.10),   # Nam Định
        _vn_box(20.446, 106.336, 0.10),   # Thái Bình
        _vn_box(20.251, 105.974, 0.10),   # Ninh Bình
        _vn_box(20.817, 105.337, 0.10),   # Hòa Bình
        _vn_box(21.326, 103.914, 0.10),   # Sơn La
        _vn_box(21.386, 103.023, 0.08),   # Điện Biên
        _vn_box(22.386, 103.470, 0.07),   # Lai Châu
        _vn_box(22.485, 103.975, 0.08),   # Lào Cai - Sa Pa
        _vn_box(21.722, 104.911, 0.10),   # Yên Bái
        _vn_box(22.823, 104.983, 0.07),   # Hà Giang
        _vn_box(22.665, 106.257, 0.07),   # Cao Bằng
        _vn_box(22.147, 105.834, 0.08),   # Bắc Kạn
        _vn_box(21.823, 106.761, 0.08),   # Lạng Sơn
        _vn_box(21.816, 105.214, 0.10),   # Tuyên Quang
        _vn_box(19.806, 105.785, 0.14),   # Thanh Hóa
        _vn_box(18.679, 105.681, 0.14),   # Vinh - Nghệ An
        _vn_box(18.342, 105.905, 0.10),   # Hà Tĩnh
        _vn_box(17.468, 106.622, 0.09),   # Đồng Hới - Quảng Bình
        _vn_box(16.816, 107.100, 0.08),   # Đông Hà - Quảng Trị
        _vn_box(16.463, 107.590, 0.12),   # Huế
        _vn_box(16.054, 108.202, 0.12),   # Đà Nẵng
        _vn_box(15.880, 108.338, 0.12),   # Hội An - Quảng Nam
        _vn_box(15.121, 108.804, 0.11),   # Quảng Ngãi
        _vn_box(13.782, 109.219, 0.12),   # Quy Nhơn - Bình Định
        _vn_box(13.095, 109.296, 0.10),   # Tuy Hòa - Phú Yên
        _vn_box(12.238, 109.196, 0.12),   # Nha Trang - Khánh Hòa
        _vn_box(11.564, 108.988, 0.10),   # Phan Rang - Ninh Thuận
        _vn_box(10.928, 108.102, 0.14),   # Phan Thiết - Mũi Né
        _vn_box(14.354, 108.007, 0.07),   # Kon Tum
        _vn_box(13.983, 108.000, 0.09),   # Pleiku - Gia Lai
        _vn_box(12.666, 108.037, 0.12),   # Buôn Ma Thuột - Đắk Lắk
        _vn_box(12.002, 107.684, 0.07),   # Gia Nghĩa - Đắk Nông
        _vn_box(11.940, 108.458, 0.14),   # Đà Lạt - Lâm Đồng
        _vn_box(11.535, 106.883, 0.08),   # Đồng Xoài - Bình Phước
        _vn_box(11.310, 106.098, 0.08),   # Tây Ninh
        _vn_box(10.980, 106.651, 0.12),   # Bình Dương
        _vn_box(10.946, 106.842, 0.14),   # Biên Hòa - Đồng Nai
        _vn_box(10.346, 107.084, 0.12),   # Vũng Tàu - Bà Rịa
        _vn_box(10.776, 106.700, 0.16),   # TP. Hồ Chí Minh
        _vn_box(10.535, 106.413, 0.10),   # Tân An - Long An
        _vn_box(10.360, 106.360, 0.10),   # Mỹ Tho - Tiền Giang
        _vn_box(10.243, 106.375, 0.10),   # Bến Tre
        _vn_box(9.934, 106.345, 0.10),    # Trà Vinh
        _vn_box(10.253, 105.972, 0.10),   # Vĩnh Long
        _vn_box(10.460, 105.632, 0.10),   # Cao Lãnh - Đồng Tháp
        _vn_box(10.386, 105.435, 0.10),   # Long Xuyên - An Giang
        _vn_box(10.045, 105.746, 0.12),   # Cần Thơ
        _vn_box(9.784, 105.470, 0.09),    # Hậu Giang
        _vn_box(10.012, 105.080, 0.10),   # Rạch Giá - Kiên Giang
        _vn_box(10.214, 103.963, 0.09),   # Phú Quốc
        _vn_box(9.603, 105.973, 0.10),    # Sóc Trăng
        _vn_box(9.294, 105.724, 0.10),    # Bạc Liêu
        _vn_box(9.176, 105.152, 0.12),    # Cà Mau
    ],
    "asia": [
        (10.0, 21.8, 105.0, 109.2),   # Việt Nam
        (1.2, 7.2, 100.0, 104.2),     # Malaysia & Singapore
        (7.5, 20.0, 98.2, 105.4),     # Thái Lan
        (11.0, 14.0, 103.0, 106.8),   # Campuchia
        (17.5, 20.5, 101.8, 103.0),   # Lào
        (-8.6, 5.5, 95.5, 119.5),     # Indonesia (Sumatra, Java, Bali, Borneo)
        (6.5, 18.5, 120.0, 126.2),    # Philippines
        (22.0, 25.2, 120.1, 121.9),   # Đài Loan
        (22.15, 22.5, 113.85, 114.35),# Hồng Kông & Macau
        (31.0, 45.2, 129.5, 145.5),   # Nhật Bản (Kyushu, Honshu, Hokkaido)
        (34.5, 38.2, 126.3, 129.4),   # Hàn Quốc
        (8.2, 32.5, 70.0, 91.5),      # Ấn Độ
        (6.0, 9.8, 79.6, 81.8),       # Sri Lanka
        (21.5, 26.2, 88.2, 92.2),     # Bangladesh
        (26.8, 28.4, 83.5, 87.5),     # Nepal & Bhutan
        (41.5, 51.5, 52.0, 82.0),     # Kazakhstan
        (39.8, 43.0, 70.0, 78.5),     # Kyrgyzstan
        (46.0, 50.0, 95.0, 115.0),    # Mông Cổ
        (23.5, 26.2, 50.8, 56.4),     # UAE & Qatar & Oman
        (29.5, 33.4, 34.4, 36.8),     # Jordan & Israel
        (36.2, 41.8, 27.0, 44.5),     # Thổ Nhĩ Kỳ
    ],
    "europe": [
        (50.0, 58.6, -6.2, 1.8),      # Anh & Scotland
        (51.4, 55.2, -10.2, -6.0),    # Ireland
        (42.5, 50.9, -4.5, 7.8),      # Pháp & Bỉ & Hà Lan & Luxembourg
        (36.1, 43.6, -9.4, 3.2),      # Tây Ban Nha & Bồ Đào Nha
        (37.5, 46.5, 7.0, 18.2),      # Ý
        (47.3, 54.8, 6.0, 14.8),      # Đức
        (45.8, 48.9, 6.0, 17.0),      # Thụy Sĩ & Áo
        (54.6, 57.7, 8.1, 12.6),      # Đan Mạch
        (58.0, 70.5, 5.0, 29.0),      # Na Uy & Thụy Điển
        (60.0, 68.5, 21.0, 30.8),     # Phần Lan
        (63.4, 66.2, -24.0, -14.0),   # Iceland
        (49.0, 54.6, 14.2, 23.8),     # Ba Lan
        (47.5, 51.0, 12.2, 22.4),     # Séc, Slovakia, Hungary
        (43.8, 48.2, 20.5, 29.5),     # Romania & Bulgaria
        (36.5, 41.6, 20.0, 26.5),     # Hy Lạp
        (41.5, 46.6, 13.6, 22.8),     # Croatia, Slovenia, Serbia, Balkan
        (54.0, 59.5, 21.0, 28.0),     # Baltic (Litva, Latvia, Estonia)
        (46.0, 51.8, 23.0, 36.5),     # Ukraine
    ],
    "north_america": [
        (32.5, 42.0, -124.2, -114.5), # California & Bờ Tây Mỹ
        (42.0, 48.8, -124.3, -116.5), # Oregon & Washington
        (31.5, 48.5, -114.0, -96.0),  # Miền Núi & Trung Tây Mỹ
        (26.0, 36.5, -106.0, -88.0),  # Texas & Miền Nam Mỹ
        (25.2, 36.5, -88.0, -75.5),   # Florida & Đông Nam Mỹ
        (36.5, 47.0, -88.0, -67.2),   # Ngũ Hồ, New York & New England
        (58.0, 65.0, -152.0, -142.0), # Alaska
        (19.2, 22.2, -160.0, -155.0), # Hawaii
        (43.5, 53.5, -125.0, -110.0), # Tây Canada (BC, Alberta)
        (43.0, 50.5, -84.0, -60.5),   # Đông Canada (Ontario, Quebec, Atlantic)
        (16.0, 32.2, -116.5, -87.0),  # Mexico
        (14.0, 16.5, -92.0, -89.0),   # Guatemala
        (8.4, 11.2, -85.8, -79.2),    # Costa Rica & Panama
        (17.8, 19.9, -71.8, -65.5),   # Cộng hòa Dominican & Puerto Rico
    ],
    "south_america": [
        (-24.0, -1.0, -52.0, -35.0),  # Brazil (Đông Bắc, Rio, São Paulo, Minas)
        (-33.5, -23.0, -56.5, -48.0), # Nam Brazil & Uruguay
        (-39.0, -22.0, -68.5, -57.5), # Argentina (Bắc & Pampas)
        (-54.8, -39.0, -73.5, -65.0), # Patagonia (Argentina & Chile)
        (-39.0, -18.5, -73.2, -68.5), # Miền Trung & Bắc Chile
        (-18.0, -0.5, -81.0, -69.5),  # Peru & Ecuador
        (-22.0, -11.0, -69.0, -58.0), # Bolivia
        (0.5, 11.2, -77.5, -72.0),    # Colombia
    ],
    "africa": [
        (-34.6, -23.5, 18.0, 32.0),   # Nam Phi
        (-26.5, -18.0, 22.0, 27.5),   # Botswana & Eswatini & Lesotho
        (-24.5, -17.5, 14.0, 21.0),   # Namibia
        (-7.5, 4.2, 33.8, 41.2),      # Kenya & Tanzania & Uganda & Rwanda
        (12.2, 16.2, -17.5, -11.5),   # Senegal
        (5.0, 11.0, -3.0, 12.0),      # Ghana & Nigeria
        (29.5, 37.1, -9.5, 11.2),     # Morocco & Tunisia
        (25.0, 31.2, 29.8, 33.0),     # Ai Cập
    ],
    "oceania": [
        # Úc — Đất liền & vùng trọng điểm
        (-38.5, -24.0, 140.5, 153.5), # Đông Úc (NSW, VIC, QLD, ACT)
        (-24.0, -15.5, 144.5, 152.5), # Bắc Queensland (Cairns, Townsville, Mackay)
        (-43.5, -40.8, 144.8, 148.2), # Tasmania
        (-35.5, -26.0, 134.0, 140.5), # Nam Úc (Adelaide, Barossa, Flinders)
        (-35.0, -18.0, 114.5, 124.0), # Tây Úc (Perth, Margaret River, Broome)
        (-25.0, -12.0, 129.5, 138.0), # Bắc Úc (Darwin, Kakadu, Alice Springs, Uluru)
        # New Zealand — Đảo Bắc & Đảo Nam
        (-41.8, -34.6, 172.8, 178.4), # Đảo Bắc New Zealand (Auckland, Rotorua, Wellington)
        (-46.6, -40.8, 167.2, 174.2), # Đảo Nam New Zealand (Christchurch, Queenstown, Dunedin)
        # Các quốc đảo & lãnh thổ hải ngoại Châu Đại Dương (100% xác thực có Street View 360° chính thức)
        (13.26, 13.58, 144.65, 144.92),     # Guam (Tumon, Hagåtña, Umatac, Inarajan)
        (15.10, 15.29, 145.69, 145.82),     # Saipan — Quần đảo Bắc Mariana
        (14.94, 15.08, 145.58, 145.66),     # Tinian — Quần đảo Bắc Mariana
        (14.12, 14.20, 145.13, 145.28),     # Rota — Quần đảo Bắc Mariana
        (-14.37, -14.25, -170.84, -170.56), # American Samoa — Đảo Tutuila (Pago Pago, Tafuna, Leone)
        (-14.19, -14.15, -169.69, -169.60), # American Samoa — Quần đảo Manuʻa (Ofu & Olosega)
        (-14.25, -14.20, -169.52, -169.42), # American Samoa — Quần đảo Manuʻa (Đảo Taʻū)
        (21.25, 21.70, -158.25, -157.65),   # Hawaii (Polynesia) — Đảo Oahu
        (20.62, 21.02, -156.68, -156.00),   # Hawaii (Polynesia) — Đảo Maui
        (19.40, 20.15, -156.05, -154.90),   # Hawaii (Polynesia) — Đảo Lớn (Big Island)
        (21.88, 22.23, -159.75, -159.30),   # Hawaii (Polynesia) — Đảo Kauai
        (-16.28, -16.22, 168.10, 168.17),   # Vanuatu — Đảo núi lửa Ambrym
        (-25.08, -25.05, -130.12, -130.08), # Quần đảo Pitcairn — Adamstown
        (28.19, 28.22, -177.39, -177.36),   # Midway Atoll — Sand Island
        (-10.50, -10.41, 105.56, 105.71),   # Đảo Christmas (Úc / Ấn Độ Dương)
        (-12.20, -12.11, 96.81, 96.91),     # Quần đảo Cocos (Keeling)
        (-36.06, -35.56, 136.53, 138.13),   # Đảo Kangaroo (Nam Úc)
        (-32.02, -31.99, 115.45, 115.56),   # Đảo Rottnest (Tây Úc)
        (-19.18, -19.10, 146.79, 146.88),   # Đảo Magnetic (Queensland)
        (-38.53, -38.44, 145.10, 145.36),   # Đảo Phillip (Victoria)
        (-43.49, -43.05, 147.17, 147.43),   # Đảo Bruny (Tasmania)
        (-40.15, -39.58, 143.82, 144.15),   # Đảo King (Tasmania)
        (-40.25, -39.72, 147.80, 148.35),   # Đảo Flinders (Tasmania)
        (-36.84, -36.75, 174.98, 175.18),   # Đảo Waiheke (New Zealand)
        (-46.96, -46.84, 168.05, 168.20),   # Đảo Stewart / Rakiura (New Zealand)
    ],
}

# Siêu dữ liệu (mã quốc gia mặc định, bán kính quét m, trọng số chọn khung) cho Châu Đại Dương:
# Tổng trọng số = 100.0 -> Úc (38.0%) + New Zealand (22.0%) = 60.0%; Quốc đảo & Lãnh thổ = 40.0%.
STREETVIEW_BOX_META: dict[tuple[float, float, float, float], tuple[str, int, float]] = {
    # Úc đất liền + 7 đảo ven bờ = 38.0%
    (-38.5, -24.0, 140.5, 153.5): ("AU", 45000, 11.0),
    (-24.0, -15.5, 144.5, 152.5): ("AU", 45000, 4.5),
    (-43.5, -40.8, 144.8, 148.2): ("AU", 40000, 4.0),
    (-35.5, -26.0, 134.0, 140.5): ("AU", 45000, 4.5),
    (-35.0, -18.0, 114.5, 124.0): ("AU", 45000, 5.5),
    (-25.0, -12.0, 129.5, 138.0): ("AU", 45000, 3.5),
    (-36.06, -35.56, 136.53, 138.13): ("AU", 15000, 1.0),
    (-32.02, -31.99, 115.45, 115.56): ("AU", 6000, 0.9),
    (-19.18, -19.10, 146.79, 146.88): ("AU", 8000, 0.7),
    (-38.53, -38.44, 145.10, 145.36): ("AU", 10000, 0.7),
    (-43.49, -43.05, 147.17, 147.43): ("AU", 12000, 0.7),
    (-40.15, -39.58, 143.82, 144.15): ("AU", 15000, 0.5),
    (-40.25, -39.72, 147.80, 148.35): ("AU", 15000, 0.5),
    # New Zealand 2 đảo chính + 2 đảo ven bờ = 22.0%
    (-41.8, -34.6, 172.8, 178.4): ("NZ", 40000, 10.5),
    (-46.6, -40.8, 167.2, 174.2): ("NZ", 40000, 9.5),
    (-36.84, -36.75, 174.98, 175.18): ("NZ", 8000, 1.0),
    (-46.96, -46.84, 168.05, 168.20): ("NZ", 10000, 1.0),
    # Quốc đảo & Lãnh thổ Thái Bình Dương / Ấn Độ Dương = 40.0%
    (13.26, 13.58, 144.65, 144.92): ("GU", 9000, 5.5),
    (15.10, 15.29, 145.69, 145.82): ("MP", 9000, 3.5),
    (14.94, 15.08, 145.58, 145.66): ("MP", 8000, 1.5),
    (14.12, 14.20, 145.13, 145.28): ("MP", 8000, 1.5),
    (-14.37, -14.25, -170.84, -170.56): ("AS", 9000, 4.5),
    (-14.19, -14.15, -169.69, -169.60): ("AS", 8000, 1.5),
    (-14.25, -14.20, -169.52, -169.42): ("AS", 8000, 1.5),
    (21.25, 21.70, -158.25, -157.65): ("HI", 10000, 2.5),
    (20.62, 21.02, -156.68, -156.00): ("HI", 12000, 2.0),
    (19.40, 20.15, -156.05, -154.90): ("HI", 15000, 2.0),
    (21.88, 22.23, -159.75, -159.30): ("HI", 10000, 1.5),
    (-16.28, -16.22, 168.10, 168.17): ("VU", 10000, 3.0),
    (-25.08, -25.05, -130.12, -130.08): ("PN", 8000, 2.5),
    (28.19, 28.22, -177.39, -177.36): ("UM", 6000, 2.0),
    (-10.50, -10.41, 105.56, 105.71): ("CX", 8000, 2.5),
    (-12.20, -12.11, 96.81, 96.91): ("CC", 8000, 2.5),
}
_MICRO_ISLAND_CCS = frozenset({"GU", "MP", "AS", "HI", "VU", "PN", "UM", "CX", "CC"})
STREETVIEW_LAND_BOXES["world"] = [
    box
    for k in ("europe", "north_america", "south_america", "asia", "africa", "oceania")
    for box in STREETVIEW_LAND_BOXES[k]
]

REGION_ALIASES: dict[str, str] = {
    "seoul": "Hàn Quốc", "bangkok": "Thái Lan", "dubai": "UAE", "tây tạng": "Trung Quốc",
    "hà nội": "Việt Nam", "tp.hcm": "Việt Nam", "rio de janeiro": "Brazil",
    "uk": "Anh", "united kingdom": "Anh", "gb": "Anh", "us": "Mỹ", "usa": "Mỹ",
    "vn": "Việt Nam", "jp": "Nhật Bản", "kr": "Hàn Quốc", "cn": "Trung Quốc", "tw": "Đài Loan",
    "hk": "Hồng Kông", "mo": "Macau", "th": "Thái Lan", "my": "Malaysia", "sg": "Singapore",
    "id": "Indonesia", "ph": "Philippines", "kh": "Campuchia", "la": "Lào", "mm": "Myanmar",
    "in": "Ấn Độ", "lk": "Sri Lanka", "np": "Nepal", "ae": "UAE", "tr": "Thổ Nhĩ Kỳ",
    "il": "Israel", "jo": "Jordan", "kz": "Kazakhstan", "mn": "Mông Cổ", "kg": "Kyrgyzstan",
    "fr": "Pháp", "de": "Đức", "it": "Ý", "es": "Tây Ban Nha", "pt": "Bồ Đào Nha",
    "nl": "Hà Lan", "be": "Bỉ", "ch": "Thụy Sĩ", "at": "Áo", "ie": "Ireland",
    "se": "Thụy Điển", "no": "Na Uy", "fi": "Phần Lan", "dk": "Đan Mạch", "is": "Iceland",
    "pl": "Ba Lan", "cz": "Séc", "sk": "Slovakia", "hu": "Hungary", "ro": "Romania",
    "bg": "Bulgaria", "gr": "Hy Lạp", "hr": "Croatia", "si": "Slovenia", "rs": "Serbia",
    "ru": "Nga", "ua": "Ukraine", "lt": "Lithuania", "lv": "Latvia", "ee": "Estonia",
    "ad": "Andorra", "by": "Belarus", "ca": "Canada", "mx": "Mexico", "cr": "Costa Rica",
    "do": "Dominican Republic", "gt": "Guatemala", "pa": "Panama", "pr": "Puerto Rico",
    "br": "Brazil", "ar": "Argentina", "cl": "Chile", "co": "Colombia", "pe": "Peru",
    "ec": "Ecuador", "bo": "Bolivia", "uy": "Uruguay", "za": "Nam Phi", "eg": "Ai Cập",
    "ke": "Kenya", "tz": "Tanzania", "ug": "Uganda", "gh": "Ghana", "ng": "Nigeria",
    "sn": "Senegal", "bw": "Botswana", "na": "Namibia", "tn": "Tunisia", "ma": "Morocco",
    "au": "Úc", "nz": "New Zealand", "pf": "French Polynesia", "hi": "Hawaii",
    "gu": "Guam", "mp": "Quần đảo Bắc Mariana", "as": "American Samoa",
    "vu": "Vanuatu", "pn": "Quần đảo Pitcairn", "um": "Midway Atoll",
    "cx": "Đảo Christmas", "cc": "Quần đảo Cocos", "nf": "Đảo Norfolk",
    "fj": "Fiji", "nc": "New Caledonia", "ws": "Samoa", "to": "Tonga",
    "ck": "Quần đảo Cook", "pg": "Papua New Guinea", "sb": "Quần đảo Solomon",
}

# Siêu dữ liệu địa lý chuẩn (Chủ quyền & Tiểu vùng địa lý) cho các quốc gia & lãnh thổ
COUNTRY_GEO_INFO: dict[str, tuple[str, str]] = {
    "Úc": ("Quốc gia Độc lập", "Australasia · Châu Đại Dương"),
    "New Zealand": ("Quốc gia Độc lập", "Australasia / Polynesia · Châu Đại Dương"),
    "Guam": ("Lãnh thổ Hải ngoại Hoa Kỳ", "Micronesia · Tây Thái Bình Dương"),
    "Quần đảo Bắc Mariana": ("Thịnh vượng chung thuộc Hoa Kỳ", "Micronesia · Tây Thái Bình Dương"),
    "American Samoa": ("Lãnh thổ Hải ngoại Hoa Kỳ", "Polynesia · Nam Thái Bình Dương"),
    "Hawaii": ("Tiểu bang Hoa Kỳ", "Polynesia · Bắc Thái Bình Dương"),
    "Vanuatu": ("Quốc gia Độc lập", "Melanesia · Nam Thái Bình Dương"),
    "Quần đảo Pitcairn": ("Lãnh thổ Hải ngoại Anh", "Polynesia · Nam Thái Bình Dương"),
    "Midway Atoll": ("Lãnh thổ Hải ngoại Hoa Kỳ", "Polynesia · Bắc Thái Bình Dương"),
    "Đảo Christmas": ("Lãnh thổ Hải ngoại Úc", "Ấn Độ Dương · Châu Đại Dương"),
    "Quần đảo Cocos": ("Lãnh thổ Hải ngoại Úc", "Ấn Độ Dương · Châu Đại Dương"),
    "French Polynesia": ("Lãnh thổ Hải ngoại Pháp", "Polynesia · Nam Thái Bình Dương"),
    "New Caledonia": ("Lãnh thổ Hải ngoại Pháp", "Melanesia · Nam Thái Bình Dương"),
    "Fiji": ("Quốc gia Độc lập", "Melanesia · Nam Thái Bình Dương"),
    "Samoa": ("Quốc gia Độc lập", "Polynesia · Nam Thái Bình Dương"),
    "Tonga": ("Quốc gia Độc lập", "Polynesia · Nam Thái Bình Dương"),
    "Việt Nam": ("Quốc gia Độc lập", "Đông Nam Á"),
}

# Danh mục địa danh / đảo / thị trấn chi tiết để bổ sung Metadata cho tọa độ thiếu tên đường:
# (tên thị trấn/khu vực, tên đảo/bang, quốc gia/lãnh thổ, lat, lng, bán kính khớp km)
GEO_GAZETTEER: tuple[tuple[str, str, str, float, float, float], ...] = (
    # Guam
    ("Vịnh Tumon (Tamuning)", "Đảo Guam", "Guam", 13.5122, 144.8035, 6.0),
    ("Thủ phủ Hagåtña", "Đảo Guam", "Guam", 13.4763, 144.7502, 7.0),
    ("Dededo (Bắc Guam)", "Đảo Guam", "Guam", 13.5178, 144.8391, 9.0),
    ("Yigo (Cực Bắc Guam)", "Đảo Guam", "Guam", 13.5361, 144.8886, 10.0),
    ("Làng cổ Umatac (Tây Nam Guam)", "Đảo Guam", "Guam", 13.2966, 144.6615, 8.0),
    ("Làng Inarajan (Đông Nam Guam)", "Đảo Guam", "Guam", 13.2742, 144.7484, 9.0),
    ("Vịnh Merizo (Cực Nam Guam)", "Đảo Guam", "Guam", 13.2658, 144.6691, 8.0),
    ("Mangilao / Barrigada", "Đảo Guam", "Guam", 13.4480, 144.8010, 8.0),
    # Northern Mariana Islands
    ("Garapan & Micro Beach", "Đảo Saipan", "Quần đảo Bắc Mariana", 15.2072, 145.7186, 6.0),
    ("Marpi & Vách đá Banzai Cliff", "Đảo Saipan", "Quần đảo Bắc Mariana", 15.2760, 145.8080, 7.0),
    ("Capitol Hill / Mount Tapochau", "Đảo Saipan", "Quần đảo Bắc Mariana", 15.1890, 145.7460, 7.0),
    ("Susupe / San Antonio (Nam Saipan)", "Đảo Saipan", "Quần đảo Bắc Mariana", 15.1350, 145.7060, 8.0),
    ("Làng San Jose", "Đảo Tinian", "Quần đảo Bắc Mariana", 14.9698, 145.6228, 16.0),
    ("Làng Songsong", "Đảo Rota", "Quần đảo Bắc Mariana", 14.1380, 145.1404, 18.0),
    # American Samoa
    ("Cảng Pago Pago (Eastern District)", "Đảo Tutuila", "American Samoa", -14.2756, -170.7020, 8.0),
    ("Tafuna (Western District)", "Đảo Tutuila", "American Samoa", -14.3315, -170.7185, 8.0),
    ("Làng cổ Leone", "Đảo Tutuila", "American Samoa", -14.3422, -170.7850, 8.0),
    ("Đảo Ofu & Olosega", "Quần đảo Manuʻa", "American Samoa", -14.1720, -169.6400, 12.0),
    ("Làng Luma / Faleasao", "Đảo Taʻū (Quần đảo Manuʻa)", "American Samoa", -14.2250, -169.4700, 15.0),
    # Hawaii (Polynesia)
    ("Honolulu / Waikiki", "Đảo Oahu", "Hawaii", 21.2900, -157.8400, 18.0),
    ("Bờ biển North Shore (Haleiwa)", "Đảo Oahu", "Hawaii", 21.5928, -158.1034, 22.0),
    ("Kahului / Wailuku", "Đảo Maui", "Hawaii", 20.8893, -156.4729, 25.0),
    ("Road to Hana / Haleakalā", "Đảo Maui", "Hawaii", 20.7600, -156.1800, 28.0),
    ("Kailua-Kona", "Đảo Lớn (Big Island)", "Hawaii", 19.6400, -155.9969, 45.0),
    ("Thành phố Hilo", "Đảo Lớn (Big Island)", "Hawaii", 19.7241, -155.0868, 45.0),
    ("Lihue / Kapaʻa / Waimea", "Đảo Kauai", "Hawaii", 22.0500, -159.5000, 35.0),
    # Vanuatu, Pitcairn, Midway, Christmas, Cocos
    ("Vành núi lửa Ambrym (Tỉnh Malampa)", "Đảo Ambrym", "Vanuatu", -16.2500, 168.1350, 25.0),
    ("Thủ phủ Adamstown & Vịnh Bounty", "Đảo Pitcairn", "Quần đảo Pitcairn", -25.0667, -130.1000, 15.0),
    ("Đảo Sand (Sand Island)", "Rạn san hô Midway", "Midway Atoll", 28.2072, -177.3735, 15.0),
    ("Flying Fish Cove / Settlement", "Đảo Christmas", "Đảo Christmas", -10.4275, 105.6774, 22.0),
    ("West Island / Home Island", "Quần đảo Cocos (Keeling)", "Quần đảo Cocos", -12.1872, 96.8280, 22.0),
    # Australian & NZ Offshore Islands
    ("Kingscote / Vivonne Bay", "Đảo Kangaroo (Nam Úc)", "Úc", -35.7800, 137.2100, 65.0),
    ("Thomson Bay / Wadjemup", "Đảo Rottnest (Tây Úc)", "Úc", -32.0051, 115.5118, 12.0),
    ("Nelly Bay / Horseshoe Bay", "Đảo Magnetic (Queensland)", "Úc", -19.1400, 146.8400, 12.0),
    ("Cowes / Ventnor", "Đảo Phillip (Victoria)", "Úc", -38.4820, 145.2335, 18.0),
    ("South Bruny / The Neck", "Đảo Bruny (Tasmania)", "Úc", -43.3200, 147.2900, 32.0),
    ("Currie / Pearshape", "Đảo King (Tasmania)", "Úc", -39.8800, 143.9500, 40.0),
    ("Whitemark / Memana", "Đảo Flinders (Tasmania)", "Úc", -40.0200, 148.0200, 45.0),
    ("Oneroa / Palm Beach", "Đảo Waiheke (Auckland)", "New Zealand", -36.7910, 175.0481, 16.0),
    ("Halfmoon Bay / Oban", "Đảo Stewart / Rakiura", "New Zealand", -46.8979, 168.1272, 30.0),
)

CURATED_LOCATIONS: dict[str, list[dict]] = {   'asia': [   {   'hint': 'Tháp truyền thông màu đỏ trắng biểu tượng Tokyo',
                    'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/5/58/Tokyo_Tower_2023.jpg/1280px-Tokyo_Tower_2023.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                    'lat': 35.65861,
                    'lng': 139.74556,
                    'name': 'Tháp Tokyo, Nhật Bản'},
                {   'hint': 'Hoàng cung lớn nhất triều đại Joseon ở Hàn Quốc',
                    'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/6/63/%EA%B4%91%ED%99%94%EB%AC%B8_%EC%9B%94%EB%8C%80.jpg/1280px-%EA%B4%91%ED%99%94%EB%AC%B8_%EC%9B%94%EB%8C%80.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                    'lat': 37.57988,
                    'lng': 126.9768,
                    'name': 'Cung điện Gyeongbokgung, Seoul'},
                {   'hint': 'Quần thể đền đài cổ đại lớn nhất thế giới',
                    'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/4/41/Angkor_Wat.jpg/1280px-Angkor_Wat.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                    'lat': 13.4125,
                    'lng': 103.86667,
                    'name': 'Đền Angkor Wat, Campuchia'},
                {   'hint': 'Lăng mộ đá cẩm thạch trắng bên sông Yamuna',
                    'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/1/1d/Taj_Mahal_%28Edited%29.jpeg/1280px-Taj_Mahal_%28Edited%29.jpeg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                    'lat': 27.175,
                    'lng': 78.0419,
                    'name': 'Đền Taj Mahal, Ấn Độ'},
                {   'hint': 'Ngọn núi lửa phủ tuyết biểu tượng xứ Phù Tang',
                    'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/f/f8/View_of_Mount_Fuji_from_%C5%8Cwakudani_20211202.jpg/1280px-View_of_Mount_Fuji_from_%C5%8Cwakudani_20211202.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                    'lat': 35.36083,
                    'lng': 138.7275,
                    'name': 'Núi Phú Sĩ, Nhật Bản'},
                {   'hint': 'Ngôi chùa Bình Minh bên bờ sông Chao Phraya',
                    'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/2/2a/%E0%B9%80%E0%B8%88%E0%B8%94%E0%B8%B5%E0%B8%A2%E0%B9%8C%E0%B8%9B%E0%B8%A3%E0%B8%B0%E0%B8%98%E0%B8%B2%E0%B8%99%E0%B8%97%E0%B8%A3%E0%B8%87%E0%B8%9B%E0%B8%A3%E0%B8%B2%E0%B8%87%E0%B8%84%E0%B9%8C%E0%B8%A7%E0%B8%B1%E0%B8%94%E0%B8%AD%E0%B8%A3%E0%B8%B8%E0%B8%932.jpg/1280px-%E0%B9%80%E0%B8%88%E0%B8%94%E0%B8%B5%E0%B8%A2%E0%B9%8C%E0%B8%9B%E0%B8%A3%E0%B8%B0%E0%B8%98%E0%B8%B2%E0%B8%99%E0%B8%97%E0%B8%A3%E0%B8%87%E0%B8%9B%E0%B8%A3%E0%B8%B2%E0%B8%87%E0%B8%84%E0%B9%8C%E0%B8%A7%E0%B8%B1%E0%B8%94%E0%B8%AD%E0%B8%A3%E0%B8%B8%E0%B8%932.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                    'lat': 13.74361,
                    'lng': 100.48889,
                    'name': 'Chùa Wat Arun, Bangkok'},
                {   'hint': 'Khinh khí cầu bay trên những thung lũng đá kỳ ảo',
                    'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/5/59/Cappadocia_balloon_trip%2C_Ortahisar_Castle_%2811893715185%29.jpg/1280px-Cappadocia_balloon_trip%2C_Ortahisar_Castle_%2811893715185%29.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                    'lat': 38.61833,
                    'lng': 34.86722,
                    'name': 'Thung lũng Cappadocia, Thổ Nhĩ Kỳ'},
                {   'hint': 'Cung điện nằm trên đồi Marpo Ri ở Lhasa',
                    'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/b/b6/Potala_Palace_HQ.jpg/1280px-Potala_Palace_HQ.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                    'lat': 29.65778,
                    'lng': 91.11694,
                    'name': 'Cung điện Potala, Tây Tạng'},
                {   'hint': 'Tòa nhà cao nhất thế giới tại Dubai',
                    'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/9/90/Burj_Khalifa_%28worlds_tallest_building%29_and_the_Dubai_skyline_%2825781049892%29.jpg/1280px-Burj_Khalifa_%28worlds_tallest_building%29_and_the_Dubai_skyline_%2825781049892%29.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                    'lat': 25.1972,
                    'lng': 55.2742,
                    'name': 'Tháp Burj Khalifa, Dubai'},
                {   'hint': 'Ngôi chùa dát vàng rực rỡ tại Yangon',
                    'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/c/c4/Shwedagon_Pagoda_2017.jpg/1280px-Shwedagon_Pagoda_2017.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                    'lat': 16.79835,
                    'lng': 96.1497,
                    'name': 'Chùa Shwedagon, Myanmar'}],
    'vietnam': [   {   'hint': 'Hồ Gươm trái tim thủ đô Hà Nội',
                       'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/7/79/Thap_Rua.jpg/1280px-Thap_Rua.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                       'lat': 21.02889,
                       'lng': 105.8525,
                       'name': 'Hồ Hoàn Kiếm, Hà Nội'},
                   {   'hint': 'Hàng nghìn đảo đá vôi kỳ vĩ trên vịnh Bắc Bộ',
                       'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/7/79/Ha_Long_Bay_in_2019.jpg/1280px-Ha_Long_Bay_in_2019.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                       'lat': 20.9,
                       'lng': 107.2,
                       'name': 'Vịnh Hạ Long'},
                   {   'hint': 'Biểu tượng sầm uất giữa trung tâm Sài Gòn',
                       'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/f/f5/Ben_Thanh%2C_Ciudad_Ho_Chi_Minh%2C_Vietnam%2C_2013-08-14%2C_DD_01.JPG/1280px-Ben_Thanh%2C_Ciudad_Ho_Chi_Minh%2C_Vietnam%2C_2013-08-14%2C_DD_01.JPG?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                       'lat': 10.77252,
                       'lng': 106.69802,
                       'name': 'Chợ Bến Thành, TP.HCM'},
                   {   'hint': 'Hoàng thành triều Nguyễn bên sông Hương',
                       'image': 'https://upload.wikimedia.org/wikipedia/commons/b/b9/%C4%90%E1%BA%A1i_n%E1%BB%99i.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail_unscaled',
                       'lat': 16.46972,
                       'lng': 107.57778,
                       'name': 'Kinh thành Huế'},
                   {   'hint': 'Ruộng bậc thang vàng óng trên sườn núi Tây Bắc',
                       'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/6/66/Mu_Cang_Chai_Town_-_Yen_Bai_-_Vietnam.jpg/1280px-Mu_Cang_Chai_Town_-_Yen_Bai_-_Vietnam.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                       'lat': 21.833,
                       'lng': 104.167,
                       'name': 'Mù Cang Chải, Yên Bái'},
                   {   'hint': 'Kiến trúc gạch đỏ nổi tiếng trung tâm Quận 1',
                       'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/d/d7/Bas%C3%ADlica_de_Nuestra_Se%C3%B1ora%2C_Ciudad_Ho_Chi_Minh%2C_Vietnam%2C_2013-08-14%2C_DD_03.JPG/1280px-Bas%C3%ADlica_de_Nuestra_Se%C3%B1ora%2C_Ciudad_Ho_Chi_Minh%2C_Vietnam%2C_2013-08-14%2C_DD_03.JPG?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                       'lat': 10.77972,
                       'lng': 106.69917,
                       'name': 'Nhà thờ Đức Bà Sài Gòn'},
                   {   'hint': 'Quần thể danh thắng núi đá vôi và sông nước',
                       'image': 'https://upload.wikimedia.org/wikipedia/commons/0/08/Muaxuantamcoc.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail_unscaled',
                       'lat': 20.25667,
                       'lng': 105.89639,
                       'name': 'Tràng An, Ninh Bình'},
                   {   'hint': 'Cây cầu hình rồng bắc qua sông Hàn',
                       'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/4/4a/C%E1%BA%A7u_R%E1%BB%93ng.jpg/1280px-C%E1%BA%A7u_R%E1%BB%93ng.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                       'lat': 16.06111,
                       'lng': 108.22667,
                       'name': 'Cầu Rồng Đà Nẵng'},
                   {   'hint': 'Công trình kiến trúc Pháp cổ điển tại trung tâm Hà Nội',
                       'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/5/52/Hanoi_Opera_House%2C_24_December_2016.jpg/1280px-Hanoi_Opera_House%2C_24_December_2016.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                       'lat': 21.02417,
                       'lng': 105.85778,
                       'name': 'Nhà hát Lớn Hà Nội'},
                   {   'hint': 'Quần thể tháp Chăm cổ kính nhìn ra cửa sông Cái',
                       'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/b/b0/Ganesh_Tempel_Po_Nagar_Nha_Trang.jpg/1280px-Ganesh_Tempel_Po_Nagar_Nha_Trang.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                       'lat': 12.26528,
                       'lng': 109.19556,
                       'name': 'Tháp Chàm Po Nagar, Nha Trang'}],
    'world': [   {   'hint': 'Công trình sắt biểu tượng của kinh đô ánh sáng',
                     'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/8/85/Tour_Eiffel_Wikimedia_Commons_%28cropped%29.jpg/1280px-Tour_Eiffel_Wikimedia_Commons_%28cropped%29.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                     'lat': 48.85822,
                     'lng': 2.2945,
                     'name': 'Tháp Eiffel, Paris'},
                 {   'hint': 'Khán đài cổ đại giữa lòng thủ đô Rome',
                     'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/d/de/Colosseo_2020.jpg/1280px-Colosseo_2020.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                     'lat': 41.8903,
                     'lng': 12.4922,
                     'name': 'Đấu trường La Mã Colosseum'},
                 {   'hint': 'Biểu tượng tự do trên đảo Liberty, vịnh New York',
                     'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/8/89/Front_view_of_Statue_of_Liberty_%28cropped%29.jpg/1280px-Front_view_of_Statue_of_Liberty_%28cropped%29.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                     'lat': 40.68917,
                     'lng': -74.04444,
                     'name': 'Tượng Nữ thần Tự do, New York'},
                 {   'hint': 'Kiến trúc cánh buồm trắng bên cảng Sydney',
                     'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/e/e1/Sydney_Opera_House_2026.jpg/1280px-Sydney_Opera_House_2026.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                     'lat': -33.85681,
                     'lng': 151.21514,
                     'name': 'Nhà hát Opera Sydney, Úc'},
                 {   'hint': 'Kỳ quan cổ đại duy nhất còn tồn tại',
                     'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/e/e7/Great_Pyramid_of_Giza_-_Pyramid_of_Khufu.jpg/1280px-Great_Pyramid_of_Giza_-_Pyramid_of_Khufu.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                     'lat': 29.97917,
                     'lng': 31.13417,
                     'name': 'Kim tự tháp Giza, Ai Cập'},
                 {   'hint': 'Cây cầu treo màu đỏ cam bắc qua eo biển',
                     'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/b/bf/Golden_Gate_Bridge_as_seen_from_Battery_East.jpg/1280px-Golden_Gate_Bridge_as_seen_from_Battery_East.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                     'lat': 37.81972,
                     'lng': -122.47861,
                     'name': 'Cầu Cổng Vàng, San Francisco'},
                 {   'hint': 'Giao lộ rực rỡ biển quảng cáo ở Manhattan',
                     'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/4/47/New_york_times_square-terabass.jpg/1280px-New_york_times_square-terabass.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                     'lat': 40.7575,
                     'lng': -73.9858,
                     'name': 'Quảng trường Thời đại, New York'},
                 {   'hint': 'Tháp chuông nổi tiếng với độ nghiêng đặc trưng',
                     'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/4/4b/Italy_-_Pisa_-_Leaning_Tower.jpg/1280px-Italy_-_Pisa_-_Leaning_Tower.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                     'lat': 43.72306,
                     'lng': 10.39639,
                     'name': 'Tháp nghiêng Pisa, Ý'},
                 {   'hint': 'Đền thờ nữ thần Athena trên đỉnh Acropolis',
                     'image': 'https://upload.wikimedia.org/wikipedia/commons/d/da/The_Parthenon_in_Athens.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail_unscaled',
                     'lat': 37.9715,
                     'lng': 23.7266,
                     'name': 'Đền Parthenon, Athens'},
                 {   'hint': 'Hẻm núi hùng vĩ do sông Colorado tạo nên',
                     'image': 'https://thumb.wikimedia.org/wikipedia/commons/thumb/3/31/Canyon_River_Tree_%28165872763%29.jpeg/1280px-Canyon_River_Tree_%28165872763%29.jpeg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail',
                     'lat': 36.3,
                     'lng': -112.75,
                     'name': 'Hẻm núi Grand Canyon, Mỹ'}]}


def _load_location_pools() -> tuple[dict[str, list[dict]], dict[str, list[dict]], dict[str, dict[str, list[dict]]]]:
    """Tải kho Landmark và kho đường phố dự phòng từ assets/geo_locations.json."""
    landmarks: dict[str, list[dict]] = {}
    fallbacks: dict[str, list[dict]] = {}
    if GEO_DATA_PATH.exists():
        try:
            with open(GEO_DATA_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "landmarks" in data:
                landmarks = {k: list(v) for k, v in (data.get("landmarks") or {}).items() if isinstance(v, list)}
                fallbacks = {k: list(v) for k, v in (data.get("fallback_streets") or {}).items() if isinstance(v, list)}
            elif isinstance(data, dict) and "world" in data:
                for mode, sec in data.items():
                    if isinstance(sec, dict):
                        landmarks[mode] = list(sec.get("easy") or [])
                        fallbacks[mode] = list(sec.get("medium") or []) + list(sec.get("hard") or [])
        except Exception:
            pass
    for mode, locs in CURATED_LOCATIONS.items():
        if not landmarks.get(mode):
            landmarks[mode] = list(locs)
        if not fallbacks.get(mode):
            fallbacks[mode] = list(locs)
    compat_pools = {
        mode: {
            "landmark": landmarks.get(mode, []),
            "global": fallbacks.get(mode) or landmarks.get(mode, []),
        }
        for mode in set(landmarks.keys()) | set(fallbacks.keys())
    }
    return landmarks, fallbacks, compat_pools


LANDMARK_POOLS, FALLBACK_STREET_POOLS, LOCATION_POOLS = _load_location_pools()


def perfect_threshold_km(max_error_km: float) -> float:
    """Ngưỡng khoảng cách đạt 5000 điểm tuyệt đối (25m với bản đồ Thế giới)."""
    return max(0.025, (max_error_km / DEFAULT_WORLD_MAX_ERROR_KM) * 0.025)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Khoảng cách đường chim bay (km) giữa hai tọa độ trên Trái Đất."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(dlmb / 2.0) ** 2)
    )
    clamped_a = min(1.0, max(0.0, a))
    c = 2.0 * math.atan2(math.sqrt(clamped_a), math.sqrt(1.0 - clamped_a))
    return EARTH_RADIUS_KM * c


def score_distance(dist_km: float, max_error_km: float = DEFAULT_WORLD_MAX_ERROR_KM) -> int:
    """Tính điểm GeoGuessr (0..5000) theo hàm mũ chuẩn: 5000 * exp(-10 * d / D)."""
    if not math.isfinite(dist_km) or dist_km < 0:
        return 0
    if dist_km <= perfect_threshold_km(max_error_km):
        return 5000
    pts = round(5000.0 * math.exp((-10.0 * dist_km) / max(1.0, max_error_km)))
    return max(0, min(5000, pts))


def round_multiplier(round_num: int) -> float:
    """Hệ số nhân sát thương Duels: V1-V4 = 1.0x, từ V5 tăng +0.5x mỗi vòng."""
    if round_num <= 4:
        return 1.0
    return round(1.0 + (round_num - 4) * 0.5, 1)


def compass_direction(lat1: float, lng1: float, lat2: float, lng2: float) -> tuple[float, str]:
    """Tính góc phương vị (0..360°) và hướng 8 gió tiếng Việt từ điểm đoán tới đáp án."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlmb = math.radians(lng2 - lng1)
    y = math.sin(dlmb) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlmb)
    deg = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    idx = int(((deg + 22.5) % 360.0) // 45.0)
    return round(deg, 1), DIRECTIONS_VI[idx]


def extract_region(loc: dict, mode: str) -> str:
    """Chuẩn hóa tên Quốc gia (Thế giới/Châu Á) hoặc Địa phương (Việt Nam) để chấm Streak."""
    if loc.get("country"):
        raw = str(loc["country"]).strip()
        return REGION_ALIASES.get(raw.lower(), raw)
    name = str(loc.get("name", "")).strip()
    if not name:
        return "Không rõ"
    parts = [p.strip() for p in name.split(",") if p.strip()]
    if mode == "vietnam":
        token = parts[0] if parts else name
        # Ví dụ "Khu vực gần Vinh" -> "Vinh"
        if token.lower().startswith("khu vực "):
            token = token[8:].strip()
        return token
    token = parts[-1] if parts else name
    return REGION_ALIASES.get(token.lower(), token)


def infer_region_from_coords(lat: float, lng: float, mode: str) -> str:
    """Ước lượng quốc gia / địa phương gần nhất từ toàn bộ dữ liệu địa danh & đường phố."""
    best_dist = float("inf")
    best_name = ""
    pools_to_scan = [
        LANDMARK_POOLS.get(mode) or [],
        FALLBACK_STREET_POOLS.get(mode) or [],
    ]
    if mode not in LANDMARK_POOLS:
        pools_to_scan.append(LANDMARK_POOLS.get("world") or [])
    for lst in pools_to_scan:
        for item in lst:
            d = haversine_km(lat, lng, item["lat"], item["lng"])
            if d < best_dist:
                best_dist = d
                best_name = extract_region(item, mode)
    return best_name


_SV_RPC_URL = "https://maps.googleapis.com/$rpc/google.internal.maps.mapsjs.v1.MapsJsInternalService/SingleImageSearch"
_ALL_GEO_MODES = (
    "world", "vietnam", "asia", "europe",
    "north_america", "south_america", "africa", "oceania",
)

# Circuit Breaker cho Google Street View RPC:
# Sau 3 lần lỗi mạng/timeout liên tiếp, ngưng gọi Google 5 phút (300s) và dùng thẳng kho tĩnh.
_SV_CB_THRESHOLD = 3
_SV_CB_COOLDOWN_SEC = 300.0
_SV_CB_LOCK = threading.Lock()
_sv_cb_failures: int = 0
_sv_cb_open_until: float = 0.0


def is_sv_circuit_open() -> bool:
    """True nếu Google Street View RPC đang trong thời gian tạm ngưng (circuit breaker mở)."""
    with _SV_CB_LOCK:
        return time.monotonic() < _sv_cb_open_until


def _sv_record_network_failure() -> None:
    global _sv_cb_failures, _sv_cb_open_until
    with _SV_CB_LOCK:
        _sv_cb_failures += 1
        if _sv_cb_failures >= _SV_CB_THRESHOLD:
            _sv_cb_open_until = time.monotonic() + _SV_CB_COOLDOWN_SEC


def _sv_record_network_success() -> None:
    global _sv_cb_failures, _sv_cb_open_until
    with _SV_CB_LOCK:
        _sv_cb_failures = 0
        _sv_cb_open_until = 0.0


def reset_sv_circuit() -> None:
    """Đặt lại trạng thái circuit breaker (dùng cho kiểm thử hoặc khôi phục thủ công)."""
    _sv_record_network_success()


# Bộ đệm tọa độ Street View động theo thời gian thực (luôn giữ sẵn để vào vòng 0ms).
_DYNAMIC_SV_LOCK = threading.RLock()
_DYNAMIC_SV_CACHE: dict[str, list[dict]] = {m: [] for m in _ALL_GEO_MODES}
_DYNAMIC_SV_INFLIGHT: set[str] = set()


def format_coords_dms(lat: float, lng: float) -> str:
    """Định dạng tọa độ gọn đẹp dạng 28.2078°N, 177.3724°W."""
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lng >= 0 else "W"
    return f"{abs(lat):.4f}°{ns}, {abs(lng):.4f}°{ew}"


def _lookup_gazetteer(lat: float, lng: float) -> tuple[str, str, str, float, str] | None:
    """Tìm mục gần nhất trong GEO_GAZETTEER nếu tọa độ nằm trong bán kính khớp."""
    best: tuple[float, tuple[str, str, str, float, float, float]] | None = None
    for entry in GEO_GAZETTEER:
        d = haversine_km(lat, lng, entry[3], entry[4])
        if d <= entry[5] and (best is None or d < best[0]):
            best = (d, entry)
    if best is None:
        return None
    dist_km, (place_name, island_name, country_name, g_lat, g_lng, _) = best
    _, dir_vi = compass_direction(g_lat, g_lng, lat, lng)
    return place_name, island_name, country_name, dist_km, dir_vi


def _infer_vietnam_subregion(lat: float, lng: float) -> str:
    if lat >= 21.3 and lng < 105.0:
        return "Tây Bắc Bộ · Việt Nam"
    if lat >= 21.1 and lng >= 105.0:
        return "Đông Bắc Bộ · Việt Nam"
    if 19.9 <= lat < 21.3:
        return "Đồng bằng sông Hồng · Việt Nam"
    if 16.0 <= lat < 19.9:
        return "Bắc Trung Bộ · Việt Nam"
    if 11.4 <= lat < 16.0 and lng < 108.55:
        return "Tây Nguyên · Việt Nam"
    if 10.8 <= lat < 16.0:
        return "Duyên hải Nam Trung Bộ · Việt Nam"
    if 10.45 <= lat < 11.6 and lng >= 106.0:
        return "Đông Nam Bộ · Việt Nam"
    return "Đồng bằng sông Cửu Long · Việt Nam"


def enrich_location_metadata(loc: dict, mode: str = "world") -> dict:
    """Bổ sung đầy đủ siêu dữ liệu địa lý (Quốc gia, Chủ quyền, Tiểu vùng, Đảo/Bang, Điểm gần nhất, Tọa độ).

    Đồng thời loại bỏ hoàn toàn hậu tố cụt lủn '(Toàn cầu 360°)' và đảm bảo tên địa điểm
    luôn mang ngữ cảnh rõ ràng về Đảo/Vùng & Quốc gia.
    """
    lat = float(loc.get("lat", 0.0))
    lng = float(loc.get("lng", 0.0))
    raw_name = str(loc.get("name", "") or "").strip()
    # Dọn các nhãn placeholder cũ nếu có
    for suffix in ("(Toàn cầu 360°)", "(Châu Đại Dương 360°)"):
        if raw_name.endswith(suffix):
            raw_name = raw_name[: -len(suffix)].strip()

    gaz = _lookup_gazetteer(lat, lng)
    country = str(loc.get("country", "") or "").strip()
    if country:
        country = REGION_ALIASES.get(country.lower(), country)
    if not country and gaz:
        country = gaz[2]
    if not country:
        country = extract_region(loc, mode)

    island = gaz[1] if gaz else ""
    nearest_place = ""
    if gaz:
        p_name, _, _, dist_km, dir_vi = gaz
        if dist_km <= 1.2:
            nearest_place = p_name
        else:
            nearest_place = f"Gần {p_name} (~{dist_km:.1f} km về phía {dir_vi})"

    sovereign, subregion = COUNTRY_GEO_INFO.get(country, ("Quốc gia Độc lập", ""))
    if mode == "vietnam" or country == "Việt Nam":
        sovereign = "Quốc gia Độc lập"
        subregion = _infer_vietnam_subregion(lat, lng)
    elif not subregion:
        mode_sub = {
            "asia": "Châu Á",
            "europe": "Châu Âu",
            "north_america": "Bắc Mỹ",
            "south_america": "Nam Mỹ",
            "africa": "Châu Phi",
            "oceania": "Châu Đại Dương",
        }.get(mode, "")
        subregion = mode_sub

    # Dựng tên hiển thị giàu ngữ cảnh (không bao giờ chỉ có 'Midway Atoll (Toàn cầu 360°)')
    display_name = raw_name
    if not display_name or display_name.lower() == country.lower():
        if gaz:
            p_name, isl_name, c_name, _, _ = gaz
            if isl_name and isl_name.lower() not in p_name.lower() and isl_name.lower() != c_name.lower():
                display_name = f"{p_name}, {isl_name} · {c_name}"
            elif c_name.lower() not in p_name.lower():
                display_name = f"{p_name} · {c_name}"
            else:
                display_name = p_name
        else:
            display_name = f"{country} ({subregion})" if subregion else (country or "Địa điểm 360°")
    else:
        # Nếu địa chỉ Google trả về chưa nhắc tên đảo/quốc gia -> gắn thêm cho rõ
        low = display_name.lower()
        extras: list[str] = []
        if island and island.lower() not in low and island.lower() != country.lower():
            # Tránh lặp nếu tên đảo chính đã nằm trong display_name (ví dụ 'Tasmania')
            short_isl = island.split("(")[0].strip()
            if short_isl.lower() not in low:
                extras.append(short_isl)
        if country and country.lower() not in low and country != "Việt Nam":
            extras.append(country)
        if extras:
            if len(extras) == 2:
                display_name = f"{display_name} ({extras[0]}) · {extras[1]}"
            else:
                display_name = f"{display_name} · {extras[0]}"

    coords_text = format_coords_dms(lat, lng)
    meta = {
        "country": country,
        "sovereign": sovereign,
        "subregion": subregion,
        "island": island,
        "nearestPlace": nearest_place,
        "coordsText": coords_text,
    }
    return {**loc, "name": display_name, "country": country, "meta": meta}


def _pick_land_box(
    mode: str,
    recent_regions: list[str] | tuple[str, ...] | None = None,
) -> tuple[tuple[float, float, float, float], str, int]:
    """Chọn một khung tọa độ theo trọng số tự nhiên.

    Với ``oceania``: Úc + New Zealand ~60%, các quốc đảo & lãnh thổ ~40%.
    Nếu một đảo nhỏ vừa xuất hiện trong 3 vòng gần nhất (``recent_regions``),
    giảm nhẹ trọng số của đảo đó (×0.35 — Soft Cooldown) để vẫn giữ tính random
    tự nhiên mà tránh lặp liên tiếp cùng một đảo nhỏ.
    """
    boxes = STREETVIEW_LAND_BOXES.get(mode) or STREETVIEW_LAND_BOXES["world"]
    default_radius = 18000 if mode == "vietnam" else 45000
    recent_set = {r.upper() for r in (recent_regions or ())[-3:]}
    if mode == "oceania":
        weights = []
        for b in boxes:
            cc, _, w = STREETVIEW_BOX_META.get(b, ("", default_radius, 1.0))
            if cc in _MICRO_ISLAND_CCS and cc in recent_set:
                w = max(0.2, w * 0.35)
            weights.append(w)
        box = random.choices(boxes, weights=weights, k=1)[0]
    elif mode == "world":
        # Tránh các khung đảo nhỏ của oceania chiếm tỷ trọng quá lớn trong bản đồ thế giới
        weights = [
            0.2 if (b in STREETVIEW_BOX_META and STREETVIEW_BOX_META[b][0] in _MICRO_ISLAND_CCS) else 1.0
            for b in boxes
        ]
        box = random.choices(boxes, weights=weights, k=1)[0]
    else:
        box = random.choice(boxes)
    meta = STREETVIEW_BOX_META.get(box)
    if meta:
        return box, meta[0], meta[1]
    return box, "", default_radius


def probe_google_streetview(lat: float, lng: float, radius: int = 50000, timeout: float = 1.5) -> dict | None:
    """Truy vấn Google MapsJsInternalService/SingleImageSearch để lấy 100% ảnh Street View thật toàn cầu."""
    if is_sv_circuit_open():
        return None
    payload = json.dumps([
        ["apiv3"],
        [[None, None, round(lat, 6), round(lng, 6)], int(radius)],
        [None, ["vi", "VN"], None, None, None, None, None, None, [2], None, [[[2, True, 2]]]],
        [[1, 2, 3, 4, 8, 6]],
    ]).encode("utf-8")
    req = urllib.request.Request(
        _SV_RPC_URL,
        data=payload,
        headers={
            "Content-Type": "application/json+protobuf",
            "User-Agent": "Mozilla/5.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read(32768).decode("utf-8", errors="ignore"))
        _sv_record_network_success()
    except Exception:
        _sv_record_network_failure()
        return None

    try:
        # Cấu trúc phản hồi: data[1][5][0][1] chứa [ [null,null,lat,lng], ..., [heading,...], indoor_info, country_code ]
        node = data[1]
        # Chỉ nhận Panorama 360° chuẩn (type == 2), loại bỏ hoàn toàn ảnh 2D [10, 3]
        if not (isinstance(node[1], list) and node[1] and node[1][0] == 2):
            return None
        loc_block = node[5][0][1]
        # Nếu loc_block[3] != None tức là ảnh bên trong tòa nhà / tầng lầu -> loại bỏ
        if len(loc_block) > 3 and loc_block[3] is not None:
            return None
        coords = loc_block[0]
        snap_lat = float(coords[2])
        snap_lng = float(coords[3])
        if not (-85.0 <= snap_lat <= 85.0 and -180.0 <= snap_lng <= 180.0):
            return None
        heading = 0
        if len(loc_block) > 2 and isinstance(loc_block[2], list) and loc_block[2]:
            heading = int(round(float(loc_block[2][0]))) % 360
        country_code = ""
        if len(loc_block) > 4 and isinstance(loc_block[4], str):
            country_code = loc_block[4].strip()
        address = ""
        if len(node) > 3 and isinstance(node[3], list) and len(node[3]) > 2 and isinstance(node[3][2], list):
            parts = [p[0] for p in node[3][2] if isinstance(p, list) and p and isinstance(p[0], str)]
            address = ", ".join(parts)
        pano_id = node[1][1] if len(node[1]) > 1 and isinstance(node[1][1], str) else ""
        # Chỉ chấp nhận Official Street View Pano ID 22 ký tự (loại ảnh photosphere cá nhân CAoS... dễ bị đen/hỏng)
        if len(pano_id) != 22 or pano_id.startswith("CAoS"):
            return None
        return {
            "lat": round(snap_lat, 5),
            "lng": round(snap_lng, 5),
            "heading": heading,
            "pano": pano_id,
            "address": address,
            "country_code": country_code,
        }
    except Exception:
        return None


def fetch_random_streetview(
    mode: str = "world",
    attempts: int = 6,
    timeout: float = 1.4,
    recent_regions: list[str] | tuple[str, ...] | None = None,
) -> dict | None:
    """Sinh một tọa độ ngẫu nhiên trong vùng bản đồ rồi bắt dính đường Street View gần nhất."""
    if is_sv_circuit_open():
        return None
    for _ in range(attempts):
        if is_sv_circuit_open():
            return None
        (lat_min, lat_max, lng_min, lng_max), default_cc, search_radius = _pick_land_box(
            mode, recent_regions=recent_regions
        )
        lat = random.uniform(lat_min, lat_max)
        lng = random.uniform(lng_min, lng_max)
        res = probe_google_streetview(lat, lng, radius=search_radius, timeout=timeout)
        if res:
            raw_cc = (res.get("country_code") or "").strip().upper()
            # Quần đảo Hawaii trong bản đồ Châu Đại Dương trả mã US -> gắn mã HI để phân tách với lục địa Mỹ
            if default_cc == "HI" and raw_cc in ("", "US"):
                raw_cc = "HI"
            elif not raw_cc and default_cc:
                raw_cc = default_cc
            if not is_valid_country_for_mode(mode, raw_cc, res.get("address", "")):
                continue
            s_lat, s_lng = res["lat"], res["lng"]
            cc = raw_cc.lower()
            region = ""
            if mode != "vietnam" and cc:
                region = REGION_ALIASES.get(cc, cc.upper())
            if not region:
                region = infer_region_from_coords(s_lat, s_lng, mode)
            base_loc = {
                "lat": s_lat,
                "lng": s_lng,
                "heading": res["heading"] or random.randint(0, 359),
                "pano": res["pano"],
                "name": res["address"],
                "country": region,
                "cc": raw_cc,
                "hint": "Google Street View 360° thời gian thực",
                "dynamic": True,
                "difficulty": "global",
            }
            return enrich_location_metadata(base_loc, mode)
    return None


def warm_dynamic_sv_cache(mode: str, target_count: int = 16) -> None:
    """Nạp trước song song nhiều tọa độ Street View thật vào RAM để vào vòng 0ms độ trễ."""
    if is_sv_circuit_open():
        return
    if mode not in _ALL_GEO_MODES:
        mode = "world"
    with _DYNAMIC_SV_LOCK:
        if len(_DYNAMIC_SV_CACHE.get(mode, [])) >= target_count or mode in _DYNAMIC_SV_INFLIGHT:
            return
        _DYNAMIC_SV_INFLIGHT.add(mode)

    def _worker() -> None:
        try:
            if is_sv_circuit_open():
                return
            with _DYNAMIC_SV_LOCK:
                need = max(0, target_count - len(_DYNAMIC_SV_CACHE.get(mode, [])))
            if need <= 0:
                return
            # Dùng 4 luồng song song để nạp đầy bộ đệm chỉ trong ~0.4-0.8s
            try:
                with ThreadPoolExecutor(max_workers=4, thread_name_prefix=f"geo-{mode}") as pool:
                    futures = [pool.submit(fetch_random_streetview, mode, 6, 1.4) for _ in range(need)]
                    for fut in futures:
                        try:
                            loc = fut.result(timeout=6.0)
                        except Exception:
                            loc = None
                        if loc:
                            with _DYNAMIC_SV_LOCK:
                                _DYNAMIC_SV_CACHE.setdefault(mode, []).append(loc)
            except RuntimeError:
                # Tránh traceback khi interpreter đang tắt
                return
        finally:
            with _DYNAMIC_SV_LOCK:
                _DYNAMIC_SV_INFLIGHT.discard(mode)

    threading.Thread(target=_worker, daemon=True, name=f"geo-sv-{mode}").start()


def warm_all_sv_caches() -> None:
    """Nạp trước các khu vực phổ biến khi server khởi động (gọi từ lifespan, không chạy lúc import)."""
    if is_sv_circuit_open():
        return
    for boot_mode in _ALL_GEO_MODES:
        warm_dynamic_sv_cache(boot_mode, target_count=10 if boot_mode in ("world", "vietnam") else 6)


class GeoRoom(SeatedRoom):
    CHANNEL = "geo"
    SEATS = ("1", "2", "3", "4", "5", "6")
    HAS_CLOCK = True
    START_STATUS = "playing"
    DEFAULT_MODE = "world"
    MODES = {
        "world": {"label": "Thế giới", "max_error_km": DEFAULT_WORLD_MAX_ERROR_KM},
        "vietnam": {"label": "Việt Nam", "max_error_km": 1650.0},
        "asia": {"label": "Châu Á", "max_error_km": 8500.0},
        "europe": {"label": "Châu Âu", "max_error_km": 4800.0},
        "north_america": {"label": "Bắc Mỹ", "max_error_km": 6500.0},
        "south_america": {"label": "Nam Mỹ", "max_error_km": 6200.0},
        "africa": {"label": "Châu Phi", "max_error_km": 7500.0},
        "oceania": {"label": "Châu Đại Dương", "max_error_km": 5200.0},
    }

    def __init__(self, code: str, mode: str) -> None:
        super().__init__(code, mode)
        self.config: dict = {
            "format": "classic",          # classic | duel | streak
            "difficulty": "global",       # global (100% Street View) | landmark (Địa danh)
            "move_rule": "MOVING",        # MOVING | NM | NMPZ
            "round_time": 60,             # 30 | 45 | 60 | 90 | 120
            "rounds": ROUNDS_PER_MATCH,   # 5 | 10 | 15 | 20 (cho chế độ classic / solo)
            "panic_rule": "ALL_ACTIVE_MEMBERS",  # ALL_ACTIVE_MEMBERS | FIRST_MEMBER
            "hp_a": 6000,                 # 3000 | 6000 | 12000
            "hp_b": 6000,
            "dynamic_sv": True,
        }
        self.teams: dict[str, str] = {
            m: ("A" if int(m) % 2 == 1 else "B") for m in self.SEATS
        }
        self.session_seen_coords: set[tuple[float, float]] = set()
        self.session_recent_regions: list[str] = []
        self.loading_round: bool = False
        self.reset_match()
        # Nạp sẵn bộ đệm Street View ngay khi tạo phòng để bấm Bắt đầu vào 0ms
        warm_dynamic_sv_cache(self.mode, target_count=16)

    def _seat_label(self, mark: str) -> str:
        return f"Ghế {mark}"

    def _seated_marks(self) -> list[str]:
        return [m for m in self.SEATS if self.seat(m) is not None]

    def _team_marks(self, team: str) -> list[str]:
        return [m for m in self._seated_marks() if self.teams.get(m) == team]

    def _human_seated_marks(self) -> list[str]:
        return [
            m for m in self._seated_marks()
            if (p := self.seat(m)) is not None and not p.bot
        ]

    # ---- quản lý máy (Bot) cho mọi chế độ Địa Đồ --------------------------- #
    def add_bot(self, level: str = "normal", mark: str = "") -> Player:
        """Thêm máy cho phòng chơi đơn (/api/rooms/solo).

        Chừa ghế "1" (Đội A) cho người tạo phòng và đặt máy vào ghế "2" (Đội B)
        để có thể chơi ngay cả Classic, Streak lẫn Đấu Sinh Tử (Duel 1v1).
        """
        if self.bot_players():
            raise GameError("Phòng này đã có máy.")
        free = self.free_marks()
        if not mark:
            if not self._human_seated_marks():
                if "2" in free:
                    mark = "2"
                elif len(free) >= 2:
                    mark = free[1]
                else:
                    raise GameError("Không còn ghế cho máy.")
            elif free:
                mark = free[0]
            else:
                raise GameError("Không còn ghế cho máy.")
        elif mark not in free:
            raise GameError("Ghế đó đã có người.")
        lvl = level if level in ("easy", "normal", "hard") else "normal"
        name = f"{GEO_BOT_NAMES[0]} (Máy)"
        return self._seat_bot(mark, lvl, name, slot=0)

    def add_single_bot(self, level: str = "normal", mark: str = "") -> Player:
        """Thêm từng máy vào một ghế trống cụ thể hoặc ghế trống tiếp theo."""
        if self.in_progress():
            raise GameError("Không thể thêm máy khi ván đang chạy.")
        free = self.free_marks()
        if not free:
            raise GameError("Bàn đã đủ 6 người.")
        if mark:
            if mark not in free:
                raise GameError("Ghế đó đã có người.")
            target = mark
        else:
            target = free[0]
        slot = 0
        while bot_uid(slot) in self.players:
            slot += 1
        lvl = level if level in ("easy", "normal", "hard") else "normal"
        name = f"{GEO_BOT_NAMES[slot % len(GEO_BOT_NAMES)]} (Máy)"
        return self._seat_bot(target, lvl, name, slot=slot)

    def remove_bot_seat(self, mark: str) -> None:
        """Gỡ máy khỏi ghế khi phòng đang chờ."""
        if self.in_progress():
            raise GameError("Không thể gỡ máy khi ván đang chạy.")
        p = self.seat(mark)
        if p is None or not p.bot:
            raise GameError("Ghế này không có máy.")
        self.players.pop(p.uid, None)
        self.rematch.discard(mark)
        self.drafts.pop(mark, None)
        self.guesses.pop(mark, None)
        self.system(f"Đã gỡ {p.name} khỏi {self._seat_label(mark)}.")
        if self.status == "finished":
            self.status = "waiting"
        self.touched = time.time()

    def bot_pending(self, mark: str) -> bool:
        if not self.in_progress() or self.phase != "guessing" or self.loading_round:
            return False
        if self.config.get("format") == "streak" and mark in self.eliminated:
            return False
        return mark not in self.guesses

    def reset_match(self) -> None:
        self.phase: str = "waiting"  # waiting | guessing | round_result | finished
        self.round_idx: int = 0
        self.total_rounds: int = int(self.config.get("rounds", ROUNDS_PER_MATCH))
        self.deck: list[dict] = []
        self.drafts: dict[str, dict] = {}
        self.guesses: dict[str, dict] = {}
        self.round_results: list[dict] = []
        self.last_duel_summary: dict | None = None
        self.round_history: list[dict] = []
        self.points: dict[str, int] = {m: 0 for m in self.SEATS}
        self.streaks: dict[str, int] = {m: 0 for m in self.SEATS}
        self.best_streaks: dict[str, int] = {m: 0 for m in self.SEATS}
        self.eliminated: set[str] = set()
        self.hp_a: int = int(self.config.get("hp_a", 6000))
        self.hp_b: int = int(self.config.get("hp_b", 6000))
        self.deadline: float = 0.0
        self.round_started_at: float = 0.0
        self.panic_triggered: bool = False
        self.panic_team: str = ""
        self.zero_streak: int = 0
        self.abandoned: bool = False

    def _try_start(self) -> None:
        """Cho phép người chơi tự bấm Bắt đầu khi sẵn sàng (không auto-start khi có Bot)."""
        if self.in_progress() or self.bot_players():
            return
        if len(self._seated_marks()) == len(self.SEATS):
            if self.config["format"] == "duel":
                if self._team_marks("A") and self._team_marks("B"):
                    self._start_match()
            else:
                self._start_match()

    def _pool_for_config(self) -> list[dict]:
        diff = normalize_difficulty(self.config.get("difficulty", "global"))
        if diff == "landmark":
            pool = list(LANDMARK_POOLS.get(self.mode) or LANDMARK_POOLS.get("world") or [])
        else:
            pool = list(
                FALLBACK_STREET_POOLS.get(self.mode)
                or LANDMARK_POOLS.get(self.mode)
                or FALLBACK_STREET_POOLS.get("world")
                or []
            )
        if not pool:
            pool = list(CURATED_LOCATIONS.get(self.mode) or CURATED_LOCATIONS["world"])
        return pool

    def _is_global_dynamic(self) -> bool:
        return (
            normalize_difficulty(self.config.get("difficulty", "global")) == "global"
            and self.config.get("dynamic_sv", True)
        )

    def _balanced_static_sample(self, candidates: list[dict], count: int) -> list[dict]:
        """Chọn điểm từ kho tĩnh có cân bằng theo quốc gia/khu vực (tránh Mỹ/Úc chiếm 21%)."""
        if not candidates or count <= 0:
            return []
        by_region: dict[str, list[dict]] = {}
        for item in candidates:
            reg = extract_region(item, self.mode) or "Khác"
            by_region.setdefault(reg, []).append(item)
        for lst in by_region.values():
            random.shuffle(lst)

        picked: list[dict] = []
        used_keys: set[tuple[float, float]] = set()
        while len(picked) < count and by_region:
            regs = list(by_region.keys())
            # Trọng số căn bậc hai số lượng điểm giúp nước lớn không áp đảo tuyệt đối
            weights = [math.sqrt(len(by_region[r])) for r in regs]
            chosen_reg = random.choices(regs, weights=weights, k=1)[0]
            bucket = by_region[chosen_reg]
            item = bucket.pop()
            if not bucket:
                by_region.pop(chosen_reg, None)
            key = (item["lat"], item["lng"])
            if key not in used_keys:
                used_keys.add(key)
                picked.append(item)
        return picked

    def _available_dynamic_cache_count(self) -> int:
        with _DYNAMIC_SV_LOCK:
            cache = _DYNAMIC_SV_CACHE.get(self.mode, [])
            return sum(
                1 for cand in cache
                if (cand["lat"], cand["lng"]) not in self.session_seen_coords
            )

    def needs_network_fetch_for(self, kind: str, msg: dict | None = None) -> int:
        """Trả về số địa điểm động cần gọi Google trước khi thực thi ``kind`` (0 = không cần gọi mạng)."""
        if self.loading_round or not self._is_global_dynamic() or is_sv_circuit_open():
            return 0
        if kind == "start":
            if self.in_progress() or len(self._seated_marks()) < 1:
                return 0
            if self.config.get("format") == "duel" and (not self._team_marks("A") or not self._team_marks("B")):
                return 0
            fmt = self.config.get("format", "classic")
            target_len = (
                MAX_DUEL_ROUNDS if fmt == "duel"
                else MAX_STREAK_ROUNDS if fmt == "streak"
                else int(self.config.get("rounds", ROUNDS_PER_MATCH))
            )
            initial_need = min(target_len, ROUNDS_PER_MATCH)
            avail = self._available_dynamic_cache_count()
            return max(0, initial_need - avail)
        if kind == "rematch":
            if self.status != "finished":
                return 0
            seated = set(self._seated_marks())
            if len(seated) >= 1 and len(self.rematch) + 1 >= len(seated):
                avail = self._available_dynamic_cache_count()
                return max(0, ROUNDS_PER_MATCH - avail)
            return 0
        if kind == "next":
            if not self.in_progress() or self.phase != "round_result":
                return 0
            next_idx = self.round_idx + 1
            if next_idx < len(self.deck):
                return 0
            return 0 if self._available_dynamic_cache_count() >= 1 else 1
        return 0

    def needs_network_fetch_on_tick(self) -> int:
        """Trả về số địa điểm động cần tải trước khi ``tick()`` chuyển sang vòng tiếp theo."""
        if self.loading_round or not self.in_progress() or not self.deadline:
            return 0
        if self.phase != "round_result" or time.time() < self.deadline:
            return 0
        if not self._is_global_dynamic() or is_sv_circuit_open():
            return 0
        if self.round_idx + 1 < len(self.deck):
            return 0
        return 0 if self._available_dynamic_cache_count() >= 1 else 1

    def _record_recent_region(self, loc: dict) -> None:
        cc = str(loc.get("cc") or "").strip().upper()
        if not cc:
            c_low = str(loc.get("country") or "").strip().lower()
            for k, v in REGION_ALIASES.items():
                if len(k) == 2 and v.lower() == c_low:
                    cc = k.upper()
                    break
        if cc:
            self.session_recent_regions.append(cc)
            if len(self.session_recent_regions) > 8:
                del self.session_recent_regions[:-8]

    def prefetch_dynamic_locations(self, count: int) -> None:
        """Chạy trong worker thread (``asyncio.to_thread``) để nạp tọa độ Google mà không chặn event loop."""
        if count <= 0 or is_sv_circuit_open():
            return
        mode = self.mode
        recent = list(self.session_recent_regions[-3:])
        workers = max(1, min(5, count))
        try:
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="geo-async") as ex:
                futs = [ex.submit(fetch_random_streetview, mode, 6, 1.5, recent) for _ in range(count)]
                for fut in futs:
                    try:
                        loc = fut.result(timeout=6.0)
                    except Exception:
                        loc = None
                    if loc:
                        with _DYNAMIC_SV_LOCK:
                            _DYNAMIC_SV_CACHE.setdefault(mode, []).append(loc)
        except RuntimeError:
            return

    def _draw_location(self, used_coords: set[tuple[float, float]], allow_live_fetch: bool = True) -> dict:
        if self._is_global_dynamic():
            picked: dict | None = None
            recent_micro = {r for r in self.session_recent_regions[-3:] if r in _MICRO_ISLAND_CCS}
            with _DYNAMIC_SV_LOCK:
                cache = _DYNAMIC_SV_CACHE.get(self.mode, [])
                fallback_idx: int | None = None
                for i, cand in enumerate(cache):
                    key = (cand["lat"], cand["lng"])
                    if key in used_coords or key in self.session_seen_coords:
                        continue
                    cc = str(cand.get("cc") or "").upper()
                    if cc in recent_micro and fallback_idx is None:
                        fallback_idx = i
                        continue
                    picked = {**cache.pop(i), "difficulty": "global"}
                    break
                if picked is None and fallback_idx is not None:
                    picked = {**cache.pop(fallback_idx), "difficulty": "global"}
            warm_dynamic_sv_cache(self.mode, target_count=12)
            if picked is not None:
                enriched = enrich_location_metadata(picked, self.mode)
                self._record_recent_region(enriched)
                return enriched
            # Nếu bộ đệm tạm cạn và circuit breaker đóng, gọi trực tiếp Google RPC trước khi lùi về dự phòng
            if allow_live_fetch and not is_sv_circuit_open():
                for _ in range(2):
                    if is_sv_circuit_open():
                        break
                    live = fetch_random_streetview(
                        self.mode, attempts=6, timeout=1.5, recent_regions=self.session_recent_regions
                    )
                    if live:
                        key = (live["lat"], live["lng"])
                        if key not in used_coords and key not in self.session_seen_coords:
                            warm_dynamic_sv_cache(self.mode, target_count=12)
                            self._record_recent_region(live)
                            return live

        pool = self._pool_for_config()
        candidates = [
            x for x in pool
            if (x["lat"], x["lng"]) not in used_coords and (x["lat"], x["lng"]) not in self.session_seen_coords
        ]
        if not candidates:
            candidates = [x for x in pool if (x["lat"], x["lng"]) not in used_coords]
        if not candidates:
            candidates = pool
        sampled = self._balanced_static_sample(candidates, 1)
        chosen = sampled[0] if sampled else random.choice(candidates)
        enriched = enrich_location_metadata(chosen, self.mode)
        self._record_recent_region(enriched)
        return enriched

    def _start_match(self, allow_live_fetch: bool = True) -> None:
        seated = self._seated_marks()
        if len(seated) < 1:
            raise GameError("Cần ít nhất 1 người chơi ngồi vào ghế để bắt đầu.")
        fmt = self.config.get("format", "classic")
        if fmt == "duel":
            if not self._team_marks("A") or not self._team_marks("B"):
                raise GameError("Chế độ Đấu Sinh Tử (Duel/Team) cần ít nhất 1 người ở Đội A và 1 người ở Đội B.")

        target_len = (
            MAX_DUEL_ROUNDS if fmt == "duel"
            else MAX_STREAK_ROUNDS if fmt == "streak"
            else int(self.config.get("rounds", ROUNDS_PER_MATCH))
        )

        deck: list[dict] = []
        used: set[tuple[float, float]] = set()

        # Chế độ Toàn Cầu (global): 100% lấy từ Google Street View thực tế.
        # Lấy từ bộ đệm RAM đã nạp sẵn (0ms); nếu còn thiếu cho 5 vòng đầu, nạp song song trực tiếp.
        if self._is_global_dynamic():
            initial_need = min(target_len, ROUNDS_PER_MATCH)
            with _DYNAMIC_SV_LOCK:
                cache = _DYNAMIC_SV_CACHE.get(self.mode, [])
                while cache and len(deck) < target_len:
                    cand = cache.pop(0)
                    key = (cand["lat"], cand["lng"])
                    if key not in used and key not in self.session_seen_coords:
                        deck.append({**cand, "difficulty": "global"})
                        used.add(key)
                        self.session_seen_coords.add(key)

            missing = initial_need - len(deck)
            if missing > 0 and allow_live_fetch and not is_sv_circuit_open():
                with ThreadPoolExecutor(max_workers=min(5, missing), thread_name_prefix="geo-burst") as ex:
                    futs = [ex.submit(fetch_random_streetview, self.mode, 6, 1.5) for _ in range(missing)]
                    for fut in futs:
                        try:
                            loc = fut.result(timeout=6.0)
                        except Exception:
                            loc = None
                        if loc:
                            key = (loc["lat"], loc["lng"])
                            if key not in used:
                                deck.append(loc)
                                used.add(key)
                                self.session_seen_coords.add(key)
            warm_dynamic_sv_cache(self.mode, target_count=12)

        # Chỉ dùng pool tĩnh cho chế độ Landmark, hoặc khi mạng không kết nối được Google
        need = target_len if not self._is_global_dynamic() else min(target_len, ROUNDS_PER_MATCH)
        if len(deck) < need:
            pool = self._pool_for_config()
            fresh = [x for x in pool if (x["lat"], x["lng"]) not in self.session_seen_coords]
            if len(fresh) < need:
                self.session_seen_coords.clear()
                fresh = list(pool)
            still_need = need - len(deck)
            for item in self._balanced_static_sample(fresh, still_need * 2):
                if len(deck) >= need:
                    break
                key = (item["lat"], item["lng"])
                if key not in used:
                    deck.append(item)
                    used.add(key)
                    self.session_seen_coords.add(key)
            while len(deck) < need:
                loc = self._draw_location(used, allow_live_fetch=False)
                key = (loc["lat"], loc["lng"])
                used.add(key)
                self.session_seen_coords.add(key)
                deck.append(loc)

        self.winner = ""
        self.reset_match()
        self.deck = [enrich_location_metadata(item, self.mode) for item in deck]
        for item in self.deck:
            self._record_recent_region(item)
        self.total_rounds = target_len
        self.status = self.START_STATUS
        self.rematch.clear()
        self._begin_round(0, allow_live_fetch=allow_live_fetch)

    def _begin_round(self, idx: int, allow_live_fetch: bool = True) -> None:
        while idx >= len(self.deck):
            used = {(x["lat"], x["lng"]) for x in self.deck}
            loc = self._draw_location(used, allow_live_fetch=allow_live_fetch)
            self.session_seen_coords.add((loc["lat"], loc["lng"]))
            self.deck.append(loc)
        if self._is_global_dynamic():
            warm_dynamic_sv_cache(self.mode, target_count=12)
        self.round_idx = idx
        self.phase = "guessing"
        self.drafts = {}
        self.guesses = {}
        self.round_results = []
        self.last_duel_summary = None
        self.panic_triggered = False
        self.panic_team = ""
        now = time.time()
        round_sec = float(self.config.get("round_time", GUESS_SECONDS))
        self.round_started_at = now
        self.deadline = now + round_sec
        self.touched = now
        mult = round_multiplier(idx + 1) if self.config["format"] == "duel" else 1.0
        mult_txt = f" | Sát thương ×{mult}" if self.config["format"] == "duel" else ""
        label_r = f"Vòng {idx + 1}" if self.config["format"] == "duel" else f"Vòng {idx + 1}/{self.total_rounds}"
        self.system(f"{label_r} bắt đầu! ({int(round_sec)}s, {self.config['move_rule']}{mult_txt})")

    def _max_error_km(self) -> float:
        base = float((self.MODES.get(self.mode) or self.MODES["world"]).get("max_error_km", DEFAULT_WORLD_MAX_ERROR_KM))
        diff = normalize_difficulty(self.config.get("difficulty", "global"))
        scale = float((DIFFICULTY_PRESETS.get(diff) or DIFFICULTY_PRESETS["global"])["error_scale"])
        return base * scale

    def _current_target(self) -> dict | None:
        if 0 <= self.round_idx < len(self.deck):
            return self.deck[self.round_idx]
        return None

    def _trigger_panic(self, team_label: str, now: float) -> None:
        if self.panic_triggered:
            return
        remaining = self.deadline - now
        if remaining > PANIC_SECONDS:
            self.deadline = now + PANIC_SECONDS
        self.panic_triggered = True
        self.panic_team = team_label
        left_show = int(max(1, min(remaining, PANIC_SECONDS)))
        self.system(f"⚡ Đồng hồ Panic kích hoạt! Chỉ còn {left_show}s!")

    def _check_panic_and_completion(self, actor_mark: str, now: float) -> None:
        seated = self._seated_marks()
        if not seated:
            return
        fmt = self.config.get("format", "classic")
        active_marks = [m for m in seated if m not in self.eliminated] if fmt == "streak" else seated
        if not active_marks:
            active_marks = seated
        # Nếu mọi người chơi đang hoạt động đều đã Lock -> kết thúc vòng ngay lập tức
        if all(m in self.guesses for m in active_marks):
            self._resolve_round()
            return

        if len(active_marks) < 2:
            return

        # Bot chốt tọa độ sớm không được kích hoạt đồng hồ Panic 15s cướp thời gian của người chơi thật.
        actor_player = self.seat(actor_mark)
        has_humans = bool(self._human_seated_marks())
        if actor_player is not None and actor_player.bot and has_humans:
            return

        if fmt in ("classic", "streak"):
            self._trigger_panic("FFA", now)
            return

        # Chế độ Duel / Team
        rule = self.config.get("panic_rule", "ALL_ACTIVE_MEMBERS")
        actor_team = self.teams.get(actor_mark, "A")
        if rule == "FIRST_MEMBER":
            self._trigger_panic(actor_team, now)
            return

        # ALL_ACTIVE_MEMBERS: tất cả thành viên đang kết nối của một đội phải Lock
        for team in ("A", "B"):
            team_marks = self._team_marks(team)
            # Bỏ qua đội toàn Bot để tránh Bot ép Panic 15s lên người chơi đội đối diện
            if has_humans and not any((p := self.seat(m)) is not None and not p.bot for m in team_marks):
                continue
            active_team = [
                m for m in team_marks
                if (p := self.seat(m)) is not None and p.connected
            ]
            if not active_team:
                active_team = team_marks
            if active_team and all(m in self.guesses for m in active_team):
                self._trigger_panic(team, now)
                break

    def _resolve_round(self) -> None:
        target = self._current_target()
        if target is None or self.phase != "guessing":
            return
        max_err = self._max_error_km()
        fmt = self.config.get("format", "classic")
        target_region = extract_region(target, self.mode)
        near_streak_km = 45.0 if self.mode == "vietnam" else 90.0
        results: list[dict] = []

        for mark in self._seated_marks():
            p = self.seat(mark)
            if p is None:
                continue
            locked = self.guesses.get(mark)
            draft = self.drafts.get(mark)
            effective = locked if locked is not None else draft
            auto_locked = locked is None and draft is not None
            team = self.teams.get(mark, "A")

            if effective is not None:
                dist = haversine_km(effective["lat"], effective["lng"], target["lat"], target["lng"])
                bearing_deg, dir_vi = compass_direction(effective["lat"], effective["lng"], target["lat"], target["lng"])
                pts = score_distance(dist, max_err)
                self.points[mark] = self.points.get(mark, 0) + pts
                guessed_region = infer_region_from_coords(effective["lat"], effective["lng"], self.mode)
                region_match = (
                    guessed_region.lower() == target_region.lower()
                    or dist <= near_streak_km
                )
                if fmt == "streak" and mark not in self.eliminated:
                    if region_match:
                        self.streaks[mark] = self.streaks.get(mark, 0) + 1
                        self.best_streaks[mark] = max(self.best_streaks.get(mark, 0), self.streaks[mark])
                    else:
                        self.eliminated.add(mark)
                results.append({
                    "mark": mark,
                    "team": team,
                    "name": p.name,
                    "color": p.color,
                    "lat": effective["lat"],
                    "lng": effective["lng"],
                    "distKm": round(dist, 2),
                    "bearingDeg": bearing_deg,
                    "dirVi": dir_vi,
                    "guessedRegion": guessed_region,
                    "regionMatch": region_match,
                    "streak": self.streaks.get(mark, 0),
                    "eliminated": mark in self.eliminated,
                    "points": pts,
                    "totalPoints": self.points[mark],
                    "guessed": True,
                    "autoLocked": auto_locked,
                    "isTeamBest": False,
                })
            else:
                if fmt == "streak" and mark not in self.eliminated:
                    self.eliminated.add(mark)
                results.append({
                    "mark": mark,
                    "team": team,
                    "name": p.name,
                    "color": p.color,
                    "lat": None,
                    "lng": None,
                    "distKm": None,
                    "bearingDeg": None,
                    "dirVi": "",
                    "guessedRegion": "",
                    "regionMatch": False,
                    "streak": self.streaks.get(mark, 0),
                    "eliminated": mark in self.eliminated,
                    "points": 0,
                    "totalPoints": self.points.get(mark, 0),
                    "guessed": False,
                    "autoLocked": False,
                    "isTeamBest": False,
                })

        duel_summary: dict | None = None
        if fmt == "duel":
            def best_for(team: str) -> dict | None:
                cands = [r for r in results if r["team"] == team and r["guessed"]]
                if not cands:
                    return None
                cands.sort(key=lambda r: (-r["points"], r["distKm"] if r["distKm"] is not None else 999999.0))
                cands[0]["isTeamBest"] = True
                return cands[0]

            best_a = best_for("A")
            best_b = best_for("B")
            score_a = best_a["points"] if best_a else 0
            score_b = best_b["points"] if best_b else 0
            mult = round_multiplier(self.round_idx + 1)
            dmg = round(abs(score_a - score_b) * mult)
            damaged_team = "NONE"
            if score_a > score_b:
                self.hp_b = max(0, self.hp_b - dmg)
                damaged_team = "B"
            elif score_b > score_a:
                self.hp_a = max(0, self.hp_a - dmg)
                damaged_team = "A"

            if score_a == 0 and score_b == 0:
                self.zero_streak += 1
            else:
                self.zero_streak = 0

            duel_summary = {
                "round": self.round_idx + 1,
                "multiplier": mult,
                "scoreA": score_a,
                "scoreB": score_b,
                "bestNameA": best_a["name"] if best_a else None,
                "bestNameB": best_b["name"] if best_b else None,
                "damage": dmg,
                "damagedTeam": damaged_team,
                "hpA": self.hp_a,
                "hpB": self.hp_b,
            }
            self.last_duel_summary = duel_summary

        results.sort(key=lambda r: (-r["points"], r["distKm"] if r["distKm"] is not None else 999999.0))
        self.round_results = results
        target_meta = target.get("meta") or enrich_location_metadata(target, self.mode).get("meta")
        self.round_history.append({
            "round": self.round_idx + 1,
            "target": {
                "name": target["name"],
                "lat": target["lat"],
                "lng": target["lng"],
                "hint": target.get("hint", ""),
                "image": target.get("image", ""),
                "meta": target_meta,
            },
            "results": results,
            "duel": duel_summary,
        })
        self.phase = "round_result"
        now = time.time()
        self.deadline = now + REVEAL_SECONDS
        self.touched = now

        if fmt == "duel" and duel_summary:
            if duel_summary["damagedTeam"] != "NONE":
                self.system(
                    f"Đáp án vòng {self.round_idx + 1}: {target['name']}. "
                    f"Đội {duel_summary['damagedTeam']} mất {duel_summary['damage']} HP (×{duel_summary['multiplier']})!"
                )
            else:
                self.system(f"Đáp án vòng {self.round_idx + 1}: {target['name']}. Hai đội hòa điểm vòng này.")
        elif results and results[0]["guessed"]:
            top = results[0]
            auto_txt = " [tự chốt nháp]" if top["autoLocked"] else ""
            self.system(
                f"Đáp án vòng {self.round_idx + 1}: {target['name']}. "
                f"{top['name']} gần nhất ({top['distKm']} km, +{top['points']} điểm{auto_txt})."
            )
        else:
            self.system(f"Đáp án vòng {self.round_idx + 1}: {target['name']}.")

    def _advance_or_finish(self, allow_live_fetch: bool = True) -> None:
        fmt = self.config.get("format")
        if fmt == "duel":
            if self.hp_a <= 0 or self.hp_b <= 0 or self.zero_streak >= 3 or self.round_idx + 1 >= self.total_rounds:
                if self.zero_streak >= 3:
                    self.abandoned = True
                self._finish_match()
                return
            self._begin_round(self.round_idx + 1, allow_live_fetch=allow_live_fetch)
            return

        if fmt == "streak":
            seated = self._seated_marks()
            alive = [m for m in seated if m not in self.eliminated]
            humans = self._human_seated_marks()
            humans_alive = [m for m in humans if m not in self.eliminated]
            # Nếu có người chơi thật và tất cả người chơi thật đều đã bị loại -> kết thúc luôn
            if (
                not alive
                or (humans and not humans_alive)
                or (len(seated) >= 2 and len(alive) <= 1)
                or self.round_idx + 1 >= self.total_rounds
            ):
                self._finish_match()
                return
            self._begin_round(self.round_idx + 1, allow_live_fetch=allow_live_fetch)
            return

        if self.round_idx + 1 < self.total_rounds:
            self._begin_round(self.round_idx + 1, allow_live_fetch=allow_live_fetch)
        else:
            self._finish_match()

    def _finish_match(self) -> None:
        self.phase = "finished"
        self.deadline = 0.0
        seated = self._seated_marks()
        if not seated:
            self.status = "waiting"
            self.winner = ""
            return
        self.status = "finished"
        self.rematch.clear()

        if self.config.get("format") == "streak":
            ranked = sorted(
                seated,
                key=lambda m: (self.best_streaks.get(m, 0), self.points.get(m, 0)),
                reverse=True,
            )
            top_streak = self.best_streaks.get(ranked[0], 0)
            top_pts = self.points.get(ranked[0], 0)
            winners = [
                m for m in seated
                if self.best_streaks.get(m, 0) == top_streak and self.points.get(m, 0) == top_pts
            ]
            if len(seated) == 1:
                self.winner = ranked[0]
                self.scores[ranked[0]] = self.scores.get(ranked[0], 0) + 1
                self.system(f"🔥 Chuỗi cuối cùng: {top_streak} khu vực liên tiếp!")
            elif len(winners) > 1:
                self.winner = "draw"
                self.scores["draw"] = self.scores.get("draw", 0) + 1
                self.system(f"Hòa nhau với chuỗi {top_streak}!")
            else:
                win_mark = winners[0]
                self.winner = win_mark
                self.scores[win_mark] = self.scores.get(win_mark, 0) + 1
                champ = self.seat(win_mark)
                self.system(f"🔥 {champ.name if champ else win_mark} thắng với chuỗi {top_streak} khu vực!")
            self.touched = time.time()
            return

        if self.config.get("format") == "duel":
            if self.abandoned:
                self.winner = "draw"
                self.scores["draw"] = self.scores.get("draw", 0) + 1
                self.system("Trận đấu bị hủy do cả 2 đội không đoán 3 vòng liên tiếp.")
            elif self.hp_a > self.hp_b:
                self.winner = "TEAM_A"
                for m in self._team_marks("A"):
                    self.scores[m] = self.scores.get(m, 0) + 1
                self.system(f"🏆 Đội A chiến thắng với {self.hp_a} HP còn lại!")
            elif self.hp_b > self.hp_a:
                self.winner = "TEAM_B"
                for m in self._team_marks("B"):
                    self.scores[m] = self.scores.get(m, 0) + 1
                self.system(f"🏆 Đội B chiến thắng với {self.hp_b} HP còn lại!")
            else:
                self.winner = "draw"
                self.scores["draw"] = self.scores.get("draw", 0) + 1
                self.system(f"Hai đội hòa nhau ở mức {self.hp_a} HP!")
            self.touched = time.time()
            return

        best_pts = max(self.points.get(m, 0) for m in seated)
        winners = [m for m in seated if self.points.get(m, 0) == best_pts]
        if len(winners) > 1:
            self.winner = "draw"
            self.scores["draw"] = self.scores.get("draw", 0) + 1
            names = ", ".join(self.seat(m).name for m in winners if self.seat(m))
            self.system(f"Hòa nhau với {best_pts} điểm: {names}!")
        else:
            win_mark = winners[0]
            self.winner = win_mark
            self.scores[win_mark] = self.scores.get(win_mark, 0) + 1
            win_player = self.seat(win_mark)
            win_name = win_player.name if win_player else f"Ghế {win_mark}"
            self.system(f"{win_name} vô địch Địa Đồ với {best_pts} điểm!")
        self.touched = time.time()

    def stand(self, uid: str) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            return
        mark, player.mark = player.mark, ""
        self.rematch.discard(mark)
        self.drafts.pop(mark, None)
        self.guesses.pop(mark, None)
        self.system(f"{player.name} rời ghế {self._seat_label(mark)}.")
        if self.in_progress():
            seated = self._seated_marks()
            need_cancel = len(seated) < 1 or (
                self.config.get("format") == "duel"
                and (not self._team_marks("A") or not self._team_marks("B"))
            )
            if need_cancel:
                self.status = "waiting"
                self.winner = ""
                self.reset_match()
                self.system("Ván bị hủy vì thiếu người chơi ở đội.")
            elif self.phase == "guessing" and all(m in self.guesses for m in seated):
                self._resolve_round()
        elif self.status == "finished":
            self.status = "waiting"
        self.touched = time.time()

    def resign(self, uid: str) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Bạn không ở trong ván.")
        if not self.in_progress():
            raise GameError("Ván chưa bắt đầu.")
        self.stand(uid)

    def vote_rematch(self, uid: str, allow_live_fetch: bool = True) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Chỉ người đang ngồi mới xin đánh lại được.")
        if self.status != "finished":
            raise GameError("Ván chưa xong.")
        if self.loading_round:
            return
        self.rematch.add(player.mark)
        self.touched = time.time()
        seated = set(self._seated_marks())
        if len(seated) >= 1 and self.rematch >= seated:
            self._start_match(allow_live_fetch=allow_live_fetch)
        else:
            self.system(f"{player.name} muốn chơi ván mới.")

    def tick(self, allow_live_fetch: bool = True) -> bool:
        if self.loading_round or not self.in_progress() or not self.deadline:
            return False
        now = time.time()
        if self.phase == "guessing":
            if now < self.deadline + GRACE_SECONDS:
                return False
            self._resolve_round()
            return True
        if self.phase == "round_result":
            if now < self.deadline:
                return False
            self._advance_or_finish(allow_live_fetch=allow_live_fetch)
            return True
        return False

    def progress_token(self) -> tuple:
        return (
            self.status,
            self.phase,
            self.round_idx,
            len(self.guesses),
            len(self.drafts),
            self.hp_a,
            self.hp_b,
            self.winner,
        )

    def _validate_coords(self, msg: dict) -> tuple[float, float]:
        try:
            lat = float(msg.get("lat"))
            lng = float(msg.get("lng"))
        except (TypeError, ValueError):
            raise GameError("Tọa độ không hợp lệ.")
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            raise GameError("Tọa độ ngoài phạm vi Trái Đất.")
        return round(lat, 5), round(lng, 5)

    def apply_initial_config(self, cfg: dict) -> None:
        self._apply_config(cfg)

    def _apply_config(self, msg: dict) -> None:
        new_mode = msg.get("mode")
        if new_mode in self.MODES and new_mode != self.mode:
            self.mode = new_mode
            self.session_seen_coords.clear()
            warm_dynamic_sv_cache(self.mode, target_count=16)
        fmt = msg.get("format")
        if fmt in ("classic", "duel", "streak"):
            self.config["format"] = fmt
        raw_diff = msg.get("difficulty")
        explicit_rt = msg.get("roundTime") if msg.get("roundTime") is not None else msg.get("round_time")
        if raw_diff in ("global", "landmark", "easy", "medium", "hard", "mixed"):
            diff = normalize_difficulty(raw_diff)
            self.config["difficulty"] = diff
            if explicit_rt is None:
                self.config["round_time"] = DIFFICULTY_PRESETS[diff]["round_time"]
        mv = msg.get("moveRule") or msg.get("move_rule")
        if mv in ("MOVING", "NM", "NMPZ"):
            self.config["move_rule"] = mv
        if explicit_rt in ALLOWED_ROUND_TIMES:
            self.config["round_time"] = int(explicit_rt)
        raw_rounds = (
            msg.get("rounds")
            if msg.get("rounds") is not None
            else msg.get("roundCount")
            if msg.get("roundCount") is not None
            else msg.get("questionCount")
        )
        if raw_rounds is not None:
            try:
                rv = int(raw_rounds)
                if rv in ALLOWED_ROUND_COUNTS:
                    self.config["rounds"] = rv
                    if not self.in_progress() and self.config.get("format", "classic") == "classic":
                        self.total_rounds = rv
            except (TypeError, ValueError):
                pass
        pr = msg.get("panicRule") or msg.get("panic_rule")
        if pr in ("ALL_ACTIVE_MEMBERS", "FIRST_MEMBER"):
            self.config["panic_rule"] = pr
        if "dynamicSv" in msg or "dynamic_sv" in msg:
            raw_dyn = msg.get("dynamicSv") if "dynamicSv" in msg else msg.get("dynamic_sv")
            self.config["dynamic_sv"] = bool(raw_dyn)
        for key_in, key_cfg in (("hpA", "hp_a"), ("hpB", "hp_b")):
            hp_val = msg.get(key_in)
            if hp_val in (3000, 6000, 12000):
                self.config[key_cfg] = int(hp_val)
        self.hp_a = self.config["hp_a"]
        self.hp_b = self.config["hp_b"]
        self.touched = time.time()

    def handle(self, uid: str, action: str, msg: dict, allow_live_fetch: bool = True) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Bạn cần ngồi vào ghế để thao tác.")

        if action == "config":
            if self.in_progress():
                raise GameError("Không thể đổi cài đặt khi ván đang diễn ra.")
            self._apply_config(msg)
            rounds_txt = f", {self.config['rounds']} vòng" if self.config.get("format") == "classic" else ""
            self.system(
                f"{player.name} chỉnh phòng: {self.config['format'].upper()}, "
                f"{self.config['difficulty']}, {self.config['move_rule']}, {self.config['round_time']}s{rounds_txt}."
            )
            return

        if action == "add_bot":
            if self.in_progress():
                raise GameError("Không thể thêm máy khi ván đang diễn ra.")
            level = str(msg.get("level", "normal"))
            mark = str(msg.get("mark", ""))
            self.add_single_bot(level=level, mark=mark)
            return

        if action == "remove_bot":
            if self.in_progress():
                raise GameError("Không thể gỡ máy khi ván đang diễn ra.")
            self.remove_bot_seat(str(msg.get("mark", "")))
            return

        if action == "switch_team":
            if self.in_progress():
                raise GameError("Không thể đổi đội khi ván đang diễn ra.")
            req_mark = str(msg.get("mark", "")).strip()
            target_mark = player.mark
            target_name = player.name
            if req_mark and req_mark != player.mark:
                target_p = self.seat(req_mark)
                if target_p is None or not target_p.bot:
                    raise GameError("Chỉ có thể đổi đội cho chính bạn hoặc cho Máy.")
                target_mark = req_mark
                target_name = target_p.name
            target_team = msg.get("team")
            if target_team not in ("A", "B"):
                cur = self.teams.get(target_mark, "A")
                target_team = "B" if cur == "A" else "A"
            self.teams[target_mark] = target_team
            self.touched = time.time()
            self.system(f"{target_name} chuyển sang Đội {target_team}.")
            return

        if action == "start":
            if self.loading_round:
                return
            if self.in_progress():
                raise GameError("Ván đang diễn ra.")
            self._start_match(allow_live_fetch=allow_live_fetch)
            return

        if action == "draft":
            if not self.in_progress() or self.phase != "guessing":
                return
            lat, lng = self._validate_coords(msg)
            now = time.time()
            self.drafts[player.mark] = {"lat": lat, "lng": lng, "ts": now}
            self.touched = now
            return

        if action == "guess":
            if not self.in_progress() or self.phase != "guessing":
                raise GameError("Hiện chưa tới lúc đoán tọa độ.")
            lat, lng = self._validate_coords(msg)
            now = time.time()
            coord = {"lat": lat, "lng": lng, "ts": now}
            self.drafts[player.mark] = coord
            self.guesses[player.mark] = coord
            self.touched = now
            self._check_panic_and_completion(player.mark, now)
            return

        if action == "next":
            if self.loading_round or not self.in_progress():
                return
            req_round = msg.get("round")
            if req_round is not None:
                try:
                    if int(req_round) != self.round_idx + 1:
                        return
                except (TypeError, ValueError):
                    pass
            if self.phase != "round_result":
                return
            self._advance_or_finish(allow_live_fetch=allow_live_fetch)
            return

        raise GameError("Hành động không hợp lệ.")

    def _leaderboard(self) -> list[dict]:
        board = []
        is_streak = self.config.get("format") == "streak"
        for m in self._seated_marks():
            p = self.seat(m)
            if p is None:
                continue
            board.append({
                "mark": m,
                "team": self.teams.get(m, "A"),
                "name": p.name,
                "color": p.color,
                "points": self.points.get(m, 0),
                "streak": self.best_streaks.get(m, 0),
                "eliminated": m in self.eliminated,
            })
        if is_streak:
            board.sort(key=lambda x: (-x["streak"], -x["points"]))
        else:
            board.sort(key=lambda x: -x["points"])
        return board

    def match_view(self, uid: str) -> dict:
        player = self.players.get(uid)
        my_mark = player.mark if player else ""
        my_team = self.teams.get(my_mark, "") if my_mark else ""
        target = self._current_target()
        reveal_target = self.phase in ("round_result", "finished") and target is not None
        my_guess = self.guesses.get(my_mark) if my_mark else None
        my_draft = self.drafts.get(my_mark) if my_mark else None

        team_drafts: list[dict] = []
        if (
            self.phase == "guessing"
            and self.config.get("format") == "duel"
            and my_team in ("A", "B")
        ):
            for m in self._team_marks(my_team):
                if m == my_mark:
                    continue
                p = self.seat(m)
                d = self.guesses.get(m) or self.drafts.get(m)
                if p and d:
                    team_drafts.append({
                        "mark": m,
                        "name": p.name,
                        "color": p.color,
                        "lat": d["lat"],
                        "lng": d["lng"],
                        "locked": m in self.guesses,
                    })

        fmt = self.config.get("format", "classic")
        can_start = (
            self.status in ("waiting", "finished")
            and len(self._seated_marks()) >= 1
            and (fmt != "duel" or (bool(self._team_marks("A")) and bool(self._team_marks("B"))))
        )

        return {
            "phase": self.phase,
            "format": fmt,
            "moveRule": self.config.get("move_rule", "MOVING"),
            "config": {
                "format": fmt,
                "mode": self.mode,
                "difficulty": normalize_difficulty(self.config.get("difficulty", "global")),
                "moveRule": self.config.get("move_rule", "MOVING"),
                "roundTime": self.config.get("round_time", 60),
                "rounds": int(self.config.get("rounds", ROUNDS_PER_MATCH)),
                "panicRule": self.config.get("panic_rule", "ALL_ACTIVE_MEMBERS"),
                "hpA": self.config.get("hp_a", 6000),
                "hpB": self.config.get("hp_b", 6000),
                "dynamicSv": bool(self.config.get("dynamic_sv", True)),
            },
            "loadingRound": self.loading_round,
            "difficulty": normalize_difficulty(self.config.get("difficulty", "global")),
            "streaks": dict(self.best_streaks),
            "eliminated": sorted(self.eliminated),
            "targetRegion": extract_region(target, self.mode) if reveal_target else "",
            "teams": {m: self.teams.get(m, "A") for m in self.SEATS},
            "hpA": self.hp_a,
            "hpB": self.hp_b,
            "maxHpA": self.config.get("hp_a", 6000),
            "maxHpB": self.config.get("hp_b", 6000),
            "multiplier": round_multiplier(self.round_idx + 1) if fmt == "duel" else 1.0,
            "panicTriggered": self.panic_triggered,
            "panicTeam": self.panic_team,
            "round": self.round_idx + 1 if self.deck else 0,
            "totalRounds": self.total_rounds,
            "serverNow": time.time(),
            "deadline": self.deadline,
            "image": target.get("image", "") if target else "",
            "streetView": {
                "lat": target["lat"],
                "lng": target["lng"],
                "heading": target.get("heading", 0),
                "pano": target.get("pano", ""),
            } if target else None,
            "guessedMarks": sorted(self.guesses.keys()),
            "myDraft": {"lat": my_draft["lat"], "lng": my_draft["lng"]} if my_draft else None,
            "myGuess": {"lat": my_guess["lat"], "lng": my_guess["lng"]} if my_guess else None,
            "teamDrafts": team_drafts,
            "target": {
                "name": target["name"],
                "lat": target["lat"],
                "lng": target["lng"],
                "hint": target.get("hint", ""),
                "meta": target.get("meta") or enrich_location_metadata(target, self.mode).get("meta"),
            } if reveal_target else None,
            "duelSummary": self.last_duel_summary if self.phase in ("round_result", "finished") else None,
            "roundResults": self.round_results if self.phase in ("round_result", "finished") else [],
            "roundHistory": self.round_history if self.phase == "finished" else [],
            "leaderboard": self._leaderboard(),
            "seatedCount": len(self._seated_marks()),
            "canStart": can_start,
        }
