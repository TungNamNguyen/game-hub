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

from games import GameError, SeatedRoom

ROUNDS_PER_MATCH = 5
MAX_DUEL_ROUNDS = 25
MAX_STREAK_ROUNDS = 50
GUESS_SECONDS = 60.0
PANIC_SECONDS = 15.0
REVEAL_SECONDS = 8.0
GRACE_SECONDS = 0.5
EARTH_RADIUS_KM = 6371.071
DEFAULT_WORLD_MAX_ERROR_KM = 14916.862
# Lưu ở thư mục assets/ để tách biệt dữ liệu tĩnh với data/ (vốn bị .dockerignore chặn)
GEO_DATA_PATH = Path(__file__).resolve().parent / "assets" / "geo_locations.json"

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
        "GU", "MP", "AS",
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
        (-38.5, -24.0, 140.5, 153.5), # Đông Úc (NSW, VIC, QLD, ACT)
        (-43.5, -40.8, 144.8, 148.2), # Tasmania
        (-35.5, -26.0, 134.0, 140.5), # Nam Úc
        (-35.0, -18.0, 114.5, 124.0), # Tây Úc
        (-25.0, -12.0, 129.5, 138.0), # Bắc Úc (NT & Alice Springs)
        (-41.8, -34.6, 172.8, 178.4), # Đảo Bắc New Zealand
        (-46.6, -40.8, 167.2, 174.2), # Đảo Nam New Zealand
    ],
}
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
    "au": "Úc", "nz": "New Zealand", "pf": "French Polynesia",
}

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

# Bộ đệm tọa độ Street View động theo thời gian thực (luôn giữ sẵn để vào vòng 0ms).
_DYNAMIC_SV_LOCK = threading.RLock()
_DYNAMIC_SV_CACHE: dict[str, list[dict]] = {m: [] for m in _ALL_GEO_MODES}
_DYNAMIC_SV_INFLIGHT: set[str] = set()


def probe_google_streetview(lat: float, lng: float, radius: int = 50000, timeout: float = 1.5) -> dict | None:
    """Truy vấn Google MapsJsInternalService/SingleImageSearch để lấy 100% ảnh Street View thật toàn cầu."""
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
    except Exception:
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


def fetch_random_streetview(mode: str = "world", attempts: int = 6, timeout: float = 1.4) -> dict | None:
    """Sinh một tọa độ ngẫu nhiên trong vùng bản đồ rồi bắt dính đường Street View gần nhất."""
    boxes = STREETVIEW_LAND_BOXES.get(mode) or STREETVIEW_LAND_BOXES["world"]
    search_radius = 18000 if mode == "vietnam" else 45000
    for _ in range(attempts):
        lat_min, lat_max, lng_min, lng_max = random.choice(boxes)
        lat = random.uniform(lat_min, lat_max)
        lng = random.uniform(lng_min, lng_max)
        res = probe_google_streetview(lat, lng, radius=search_radius, timeout=timeout)
        if res:
            if not is_valid_country_for_mode(mode, res.get("country_code", ""), res.get("address", "")):
                continue
            s_lat, s_lng = res["lat"], res["lng"]
            cc = (res.get("country_code") or "").strip().lower()
            region = ""
            if mode != "vietnam" and cc:
                region = REGION_ALIASES.get(cc, cc.upper())
            if not region:
                region = infer_region_from_coords(s_lat, s_lng, mode)
            label = res["address"] or (f"{region} (Toàn cầu 360°)" if region else "Toạ độ Street View toàn cầu")
            return {
                "lat": s_lat,
                "lng": s_lng,
                "heading": res["heading"] or random.randint(0, 359),
                "pano": res["pano"],
                "name": label,
                "country": region,
                "hint": "100% Google Street View ngẫu nhiên thời gian thực",
                "dynamic": True,
                "difficulty": "global",
            }
    return None


def warm_dynamic_sv_cache(mode: str, target_count: int = 16) -> None:
    """Nạp trước song song nhiều tọa độ Street View thật vào RAM để vào vòng 0ms độ trễ."""
    if mode not in _ALL_GEO_MODES:
        mode = "world"
    with _DYNAMIC_SV_LOCK:
        if len(_DYNAMIC_SV_CACHE.get(mode, [])) >= target_count or mode in _DYNAMIC_SV_INFLIGHT:
            return
        _DYNAMIC_SV_INFLIGHT.add(mode)

    def _worker() -> None:
        try:
            with _DYNAMIC_SV_LOCK:
                need = max(0, target_count - len(_DYNAMIC_SV_CACHE.get(mode, [])))
            if need <= 0:
                return
            # Dùng 4 luồng song song để nạp đầy bộ đệm chỉ trong ~0.4-0.8s
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
        finally:
            with _DYNAMIC_SV_LOCK:
                _DYNAMIC_SV_INFLIGHT.discard(mode)

    threading.Thread(target=_worker, daemon=True, name=f"geo-sv-{mode}").start()


# Nạp trước toàn bộ 8 khu vực ngay khi khởi động server để mọi khu vực vào trận 0ms
for _boot_mode in _ALL_GEO_MODES:
    warm_dynamic_sv_cache(_boot_mode, target_count=10 if _boot_mode in ("world", "vietnam") else 6)


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
            "panic_rule": "ALL_ACTIVE_MEMBERS",  # ALL_ACTIVE_MEMBERS | FIRST_MEMBER
            "hp_a": 6000,                 # 3000 | 6000 | 12000
            "hp_b": 6000,
            "dynamic_sv": True,
        }
        self.teams: dict[str, str] = {
            m: ("A" if int(m) % 2 == 1 else "B") for m in self.SEATS
        }
        self.session_seen_coords: set[tuple[float, float]] = set()
        self.reset_match()
        # Nạp sẵn bộ đệm Street View ngay khi tạo phòng để bấm Bắt đầu vào 0ms
        warm_dynamic_sv_cache(self.mode, target_count=16)

    def _seat_label(self, mark: str) -> str:
        return f"Ghế {mark}"

    def _seated_marks(self) -> list[str]:
        return [m for m in self.SEATS if self.seat(m) is not None]

    def _team_marks(self, team: str) -> list[str]:
        return [m for m in self._seated_marks() if self.teams.get(m) == team]

    def reset_match(self) -> None:
        self.phase: str = "waiting"  # waiting | guessing | round_result | finished
        self.round_idx: int = 0
        self.total_rounds: int = ROUNDS_PER_MATCH
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
        """Cho phép người chơi tự bấm Bắt đầu khi sẵn sàng."""
        if self.in_progress():
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

    def _draw_location(self, used_coords: set[tuple[float, float]]) -> dict:
        if self._is_global_dynamic():
            picked: dict | None = None
            with _DYNAMIC_SV_LOCK:
                cache = _DYNAMIC_SV_CACHE.get(self.mode, [])
                while cache:
                    cand = cache.pop(0)
                    key = (cand["lat"], cand["lng"])
                    if key not in used_coords and key not in self.session_seen_coords:
                        picked = {**cand, "difficulty": "global"}
                        break
            warm_dynamic_sv_cache(self.mode, target_count=12)
            if picked is not None:
                return picked
            # Nếu bộ đệm tạm cạn, gọi trực tiếp Google RPC trước khi lùi về dự phòng
            for _ in range(2):
                live = fetch_random_streetview(self.mode, attempts=8, timeout=1.6)
                if live:
                    key = (live["lat"], live["lng"])
                    if key not in used_coords and key not in self.session_seen_coords:
                        warm_dynamic_sv_cache(self.mode, target_count=12)
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
        return random.choice(candidates)

    def _start_match(self) -> None:
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
            else ROUNDS_PER_MATCH
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
            if missing > 0:
                with ThreadPoolExecutor(max_workers=min(5, missing), thread_name_prefix="geo-burst") as ex:
                    futs = [ex.submit(fetch_random_streetview, self.mode, 8, 1.6) for _ in range(missing)]
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
        if len(deck) < (target_len if not self._is_global_dynamic() else min(target_len, ROUNDS_PER_MATCH)):
            pool = self._pool_for_config()
            fresh = [x for x in pool if (x["lat"], x["lng"]) not in self.session_seen_coords]
            if len(fresh) < target_len:
                self.session_seen_coords.clear()
                fresh = list(pool)
            random.shuffle(fresh)
            need = target_len if not self._is_global_dynamic() else min(target_len, ROUNDS_PER_MATCH)
            for item in fresh:
                if len(deck) >= need:
                    break
                key = (item["lat"], item["lng"])
                if key not in used:
                    deck.append(item)
                    used.add(key)
                    self.session_seen_coords.add(key)
            while len(deck) < need:
                loc = self._draw_location(used)
                key = (loc["lat"], loc["lng"])
                used.add(key)
                self.session_seen_coords.add(key)
                deck.append(loc)

        self.winner = ""
        self.reset_match()
        self.deck = deck
        self.total_rounds = target_len
        self.status = self.START_STATUS
        self.rematch.clear()
        self._begin_round(0)

    def _begin_round(self, idx: int) -> None:
        while idx >= len(self.deck):
            used = {(x["lat"], x["lng"]) for x in self.deck}
            loc = self._draw_location(used)
            self.session_seen_coords.add((loc["lat"], loc["lng"]))
            self.deck.append(loc)
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
            active_team = [
                m for m in self._team_marks(team)
                if (p := self.seat(m)) is not None and p.connected
            ]
            if not active_team:
                active_team = self._team_marks(team)
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
        self.round_history.append({
            "round": self.round_idx + 1,
            "target": {
                "name": target["name"],
                "lat": target["lat"],
                "lng": target["lng"],
                "hint": target.get("hint", ""),
                "image": target.get("image", ""),
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

    def _advance_or_finish(self) -> None:
        fmt = self.config.get("format")
        if fmt == "duel":
            if self.hp_a <= 0 or self.hp_b <= 0 or self.zero_streak >= 3 or self.round_idx + 1 >= self.total_rounds:
                if self.zero_streak >= 3:
                    self.abandoned = True
                self._finish_match()
                return
            self._begin_round(self.round_idx + 1)
            return

        if fmt == "streak":
            seated = self._seated_marks()
            alive = [m for m in seated if m not in self.eliminated]
            if not alive or (len(seated) >= 2 and len(alive) <= 1) or self.round_idx + 1 >= self.total_rounds:
                self._finish_match()
                return
            self._begin_round(self.round_idx + 1)
            return

        if self.round_idx + 1 < self.total_rounds:
            self._begin_round(self.round_idx + 1)
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

    def vote_rematch(self, uid: str) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Chỉ người đang ngồi mới xin đánh lại được.")
        if self.status != "finished":
            raise GameError("Ván chưa xong.")
        self.rematch.add(player.mark)
        self.touched = time.time()
        seated = set(self._seated_marks())
        if len(seated) >= 1 and self.rematch >= seated:
            self._start_match()
        else:
            self.system(f"{player.name} muốn chơi ván mới.")

    def tick(self) -> bool:
        if not self.in_progress() or not self.deadline:
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
            self._advance_or_finish()
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

    def handle(self, uid: str, action: str, msg: dict) -> None:
        player = self.players.get(uid)
        if player is None or not player.mark:
            raise GameError("Bạn cần ngồi vào ghế để thao tác.")

        if action == "config":
            if self.in_progress():
                raise GameError("Không thể đổi cài đặt khi ván đang diễn ra.")
            self._apply_config(msg)
            self.system(
                f"{player.name} chỉnh phòng: {self.config['format'].upper()}, "
                f"{self.config['difficulty']}, {self.config['move_rule']}, {self.config['round_time']}s."
            )
            return

        if action == "switch_team":
            if self.in_progress():
                raise GameError("Không thể đổi đội khi ván đang diễn ra.")
            target_team = msg.get("team")
            if target_team not in ("A", "B"):
                cur = self.teams.get(player.mark, "A")
                target_team = "B" if cur == "A" else "A"
            self.teams[player.mark] = target_team
            self.touched = time.time()
            self.system(f"{player.name} chuyển sang Đội {target_team}.")
            return

        if action == "start":
            if self.in_progress():
                raise GameError("Ván đang diễn ra.")
            self._start_match()
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
            if not self.in_progress():
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
            self._advance_or_finish()
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
                "panicRule": self.config.get("panic_rule", "ALL_ACTIVE_MEMBERS"),
                "hpA": self.config.get("hp_a", 6000),
                "hpB": self.config.get("hp_b", 6000),
                "dynamicSv": bool(self.config.get("dynamic_sv", True)),
            },
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
            } if reveal_target else None,
            "duelSummary": self.last_duel_summary if self.phase in ("round_result", "finished") else None,
            "roundResults": self.round_results if self.phase in ("round_result", "finished") else [],
            "roundHistory": self.round_history if self.phase == "finished" else [],
            "leaderboard": self._leaderboard(),
            "seatedCount": len(self._seated_marks()),
            "canStart": can_start,
        }
