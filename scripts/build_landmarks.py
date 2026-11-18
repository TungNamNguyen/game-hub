"""Tạo kho dữ liệu Landmark thực thụ (đa châu lục + 63 tỉnh thành Việt Nam) cho GeoGuessr.

Chạy script này để cập nhật `assets/geo_locations.json`:
- Giữ lại tập `fallback_streets` (các toạ độ đường phố đã xác thực từ bản cũ)
  làm lớp dự phòng khi máy chủ mất kết nối tới Google RPC.
- Xây dựng tập `landmarks` gồm hàng trăm địa danh nổi tiếng từ cấp kỳ quan
  thế giới (Tier 1) đến di tích, danh thắng, công trình văn hoá - lịch sử
  có tầm ảnh hưởng quốc gia / vùng miền (Tier 2 & Tier 3) cho 7 khu vực + `world`.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import io
import json
import math
from pathlib import Path
import urllib.request
from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parent.parent
GEO_DATA_PATH = ROOT / "assets" / "geo_locations.json"
SV_RPC_URL = "https://maps.googleapis.com/$rpc/google.internal.maps.mapsjs.v1.MapsJsInternalService/SingleImageSearch"

# (name, lat, lng, country, hint)
VIETNAM_LANDMARKS: list[tuple[str, float, float, str, str]] = [
    # --- Hà Nội & Đồng bằng sông Hồng ---
    ("Hồ Hoàn Kiếm & Tháp Rùa, Hà Nội", 21.02889, 105.85250, "Việt Nam", "Trái tim lịch sử giữa lòng Thủ đô Hà Nội"),
    ("Lăng Chủ tịch Hồ Chí Minh, Hà Nội", 21.03678, 105.83470, "Việt Nam", "Quảng trường Ba Đình lịch sử"),
    ("Văn Miếu - Quốc Tử Giám, Hà Nội", 21.02762, 105.83552, "Việt Nam", "Trường đại học đầu tiên của Việt Nam"),
    ("Chùa Một Cột, Hà Nội", 21.03587, 105.83361, "Việt Nam", "Ngôi chùa kiến trúc hoa sen độc bản"),
    ("Hoàng thành Thăng Long, Hà Nội", 21.03520, 105.84030, "Việt Nam", "Di sản văn hoá thế giới UNESCO"),
    ("Nhà hát Lớn Hà Nội", 21.02431, 105.85767, "Việt Nam", "Kiến trúc Tân cổ điển Pháp tại quảng trường Cách mạng Tháng Tám"),
    ("Nhà thờ Lớn Hà Nội", 21.02875, 105.84894, "Việt Nam", "Nhà thờ Chính toà Thánh Giuse phong cách Gothic"),
    ("Cầu Long Biên, Hà Nội", 21.04318, 105.85940, "Việt Nam", "Cây cầu thép lịch sử bắc qua sông Hồng"),
    ("Cầu Nhật Tân, Hà Nội", 21.09333, 105.82111, "Việt Nam", "Cầu dây văng 5 nhịp biểu tượng cửa ngõ Thủ đô"),
    ("Chùa Trấn Quốc, Hà Nội", 21.04783, 105.83688, "Việt Nam", "Ngôi chùa cổ nhất Thăng Long bên Hồ Tây"),
    ("Phủ Tây Hồ, Hà Nội", 21.05730, 105.81850, "Việt Nam", "Quần thể di tích tâm linh trên bán đảo Hồ Tây"),
    ("Bảo tàng Dân tộc học Việt Nam, Hà Nội", 21.04056, 105.79861, "Việt Nam", "Trưng bày văn hoá 54 dân tộc anh em"),
    ("Nhà tù Hỏa Lò, Hà Nội", 21.02528, 105.84667, "Việt Nam", "Di tích lịch sử nổi tiếng giữa phố cổ"),
    ("Chợ Đồng Xuân, Hà Nội", 21.03814, 105.84950, "Việt Nam", "Khu chợ đầu mối lâu đời nhất phố cổ Hà Nội"),
    ("Làng gốm Bát Tràng, Hà Nội", 20.97650, 105.91350, "Việt Nam", "Làng nghề gốm sứ truyền thống bên sông Hồng"),
    ("Làng cổ Đường Lâm, Sơn Tây", 21.15830, 105.45830, "Việt Nam", "Ngôi làng cổ đá ong đặc trưng xứ Đoài"),
    ("Chùa Hương, Mỹ Đức, Hà Nội", 20.61778, 105.74417, "Việt Nam", "Quần thể danh thắng suối Yến - động Hương Tích"),
    ("Nhà hát Lớn Hải Phòng", 20.85694, 106.68194, "Việt Nam", "Trung tâm văn hoá dải vườn hoa thành phố Cảng"),
    ("Bãi biển Đồ Sơn, Hải Phòng", 20.70690, 106.79450, "Việt Nam", "Khu nghỉ mát ven biển nổi tiếng miền Bắc"),
    ("Tượng đài Nữ tướng Lê Chân, Hải Phòng", 20.85861, 106.68111, "Việt Nam", "Tượng đài biểu tượng lịch sử giữa trung tâm Hải Phòng"),
    ("Bảo tàng Quảng Ninh, Hạ Long", 20.94694, 107.09583, "Việt Nam", "Toà nhà gương đen biểu tượng bên vịnh Hạ Long"),
    ("Đảo Tuần Châu, Hạ Long, Quảng Ninh", 20.92250, 106.98833, "Việt Nam", "Khu du lịch cảng tàu quốc tế cửa ngõ Vịnh Hạ Long"),
    ("Cầu Bãi Cháy, Hạ Long", 20.95972, 107.06806, "Việt Nam", "Cầu dây văng nối Hòn Gai và Bãi Cháy"),
    ("Khu danh thắng Yên Tử, Quảng Ninh", 21.16111, 106.71667, "Việt Nam", "Đất tổ Phật giáo Trúc Lâm Việt Nam"),
    ("Mũi Sa Vĩ, Móng Cái, Quảng Ninh", 21.48694, 108.06722, "Việt Nam", "Địa đầu Đông Bắc nơi đặt nét vẽ đầu tiên chữ S"),
    ("Quần thể danh thắng Tràng An, Ninh Bình", 20.25083, 105.91583, "Việt Nam", "Di sản hỗn hợp Văn hoá & Thiên nhiên thế giới"),
    ("Tam Cốc - Bích Động, Ninh Bình", 20.21639, 105.93250, "Việt Nam", "Vịnh Hạ Long trên cạn giữa cánh đồng lúa"),
    ("Chùa Bái Đính, Ninh Bình", 20.27389, 105.86417, "Việt Nam", "Quần thể chùa lớn bậc nhất Đông Nam Á"),
    ("Hang Múa, Ninh Bình", 20.23167, 105.93833, "Việt Nam", "Đỉnh Ngọa Long ngắm toàn cảnh Tam Cốc"),
    ("Cố đô Hoa Lư, Ninh Bình", 20.28167, 105.90806, "Việt Nam", "Kinh đô đầu tiên của nhà nước phong kiến tập quyền Việt Nam"),
    ("Nhà thờ Đá Phát Diệm, Ninh Bình", 20.09250, 106.09083, "Việt Nam", "Quần thể nhà thờ Công giáo kiến trúc đình chùa Việt"),
    ("Chùa Tam Chúc, Hà Nam", 20.56250, 105.80583, "Việt Nam", "Quần thể du lịch tâm linh giữa núi non hồ nước"),
    ("Đền Trần, Nam Định", 20.44944, 106.15639, "Việt Nam", "Nơi thờ các vị vua triều Trần lừng lẫy"),
    ("Chùa Keo, Thái Bình", 20.36222, 106.30056, "Việt Nam", "Ngôi chùa gỗ cổ gần 400 năm tuổi"),
    ("Khu di tích Côn Sơn - Kiếp Bạc, Hải Dương", 21.15194, 106.38806, "Việt Nam", "Di tích quốc gia đặc biệt gắn với Nguyễn Trãi và Trần Hưng Đạo"),
    ("Chùa Dâu, Bắc Ninh", 21.03417, 106.03833, "Việt Nam", "Ngôi chùa cổ nhất Việt Nam tại vùng đất Kinh Bắc"),
    ("Đền Đô, Từ Sơn, Bắc Ninh", 21.10667, 105.96194, "Việt Nam", "Nơi thờ 8 vị vua triều Lý"),
    ("Văn miếu Xích Đằng, Hưng Yên", 20.66500, 106.05472, "Việt Nam", "Biểu tượng hiếu học vùng Phố Hiến xưa"),
    # --- Trung du & Miền núi phía Bắc ---
    ("Đỉnh Fansipan, Sa Pa, Lào Cai", 22.30333, 103.77500, "Việt Nam", "Nóc nhà Đông Dương cao 3.143m"),
    ("Nhà thờ Đá Sa Pa, Lào Cai", 22.33583, 103.84194, "Việt Nam", "Biểu tượng trung tâm thị xã sương mù Sa Pa"),
    ("Đèo Ô Quy Hồ, Lào Cai - Lai Châu", 22.34528, 103.77056, "Việt Nam", "Một trong Tứ đại đỉnh đèo vùng Tây Bắc"),
    ("Ruộng bậc thang Mù Cang Chải, Yên Bái", 21.84917, 104.08806, "Việt Nam", "Danh thắng quốc gia đặc biệt mùa lúa chín"),
    ("Đèo Khau Phạ, Yên Bái", 21.74556, 104.24167, "Việt Nam", "Cung đèo uốn lượn nổi tiếng bay dù lượn"),
    ("Cột cờ Lũng Cú, Hà Giang", 23.36417, 105.31667, "Việt Nam", "Điểm cực Bắc thiêng liêng của Tổ quốc"),
    ("Đèo Mã Pí Lèng, Hà Giang", 23.24167, 105.41194, "Việt Nam", "Hẻm vực Tu Sản và dòng sông Nho Quế xanh ngọc"),
    ("Phố cổ Đồng Văn, Hà Giang", 23.27750, 105.36278, "Việt Nam", "Thị trấn cổ giữa cao nguyên đá"),
    ("Dinh thự Họ Vương (Vua Mèo), Hà Giang", 23.25583, 105.25806, "Việt Nam", "Kiến trúc cổ độc đáo tại thung lũng Sà Phìn"),
    ("Thác Bản Giốc, Cao Bằng", 22.85556, 106.72222, "Việt Nam", "Thác nước tự nhiên lớn bậc nhất Đông Nam Á"),
    ("Khu di tích Pác Bó, Cao Bằng", 22.97889, 106.05028, "Việt Nam", "Suối Lê-nin và hang Cốc Bó lịch sử"),
    ("Hồ Ba Bể, Bắc Kạn", 22.41667, 105.61667, "Việt Nam", "Hồ nước ngọt tự nhiên trên núi lớn nhất Việt Nam"),
    ("Khu di tích Đền Hùng, Phú Thọ", 21.36889, 105.32389, "Việt Nam", "Đất tổ cội nguồn dân tộc Việt Nam"),
    ("Thị trấn Tam Đảo, Vĩnh Phúc", 21.45639, 105.64389, "Việt Nam", "Khu nghỉ dưỡng trên núi quanh năm mây phủ"),
    ("Thiền viện Trúc Lâm Tây Thiên, Vĩnh Phúc", 21.45861, 105.58806, "Việt Nam", "Trung tâm Phật giáo lớn tại dãy Tam Đảo"),
    ("Cây đa Tân Trào, Tuyên Quang", 21.74222, 105.46806, "Việt Nam", "Thủ đô khu giải phóng lịch sử"),
    ("Mẫu Sơn, Lạng Sơn", 21.84833, 106.95639, "Việt Nam", "Đỉnh núi quanh năm sương mù vùng biên ải"),
    ("Hồ Núi Cốc, Thái Nguyên", 21.58000, 105.69667, "Việt Nam", "Hồ nhân tạo gắn liền truyền thuyết Nàng Công - Chàng Cốc"),
    ("Tượng đài Chiến thắng Điện Biên Phủ", 21.39167, 103.01694, "Việt Nam", "Đồi D1 giữa lòng chảo Điện Biên"),
    ("Đồi A1, Điện Biên Phủ", 21.38750, 103.01889, "Việt Nam", "Di tích chiến trường Điện Biên Phủ lừng lẫy"),
    ("Đèo Pha Đin, Sơn La - Điện Biên", 21.56444, 103.52417, "Việt Nam", "Cung đèo huyền thoại nối Sơn La và Điện Biên"),
    ("Cao nguyên Mộc Châu, Sơn La", 20.84806, 104.64000, "Việt Nam", "Đồi chè trái tim và thảo nguyên xanh"),
    ("Đập Thủy điện Hòa Bình", 20.80861, 105.32472, "Việt Nam", "Công trình thủy điện thế kỷ trên sông Đà"),
    ("Thung lũng Mai Châu (Bản Lác), Hòa Bình", 20.65444, 105.07028, "Việt Nam", "Bản làng người Thái giữa thung lũng xanh"),
    # --- Bắc Trung Bộ ---
    ("Thành Nhà Hồ, Thanh Hóa", 20.07778, 105.60472, "Việt Nam", "Kinh đô đá nguyên khối độc đáo Di sản UNESCO"),
    ("Bãi biển Sầm Sơn, Thanh Hóa", 19.74056, 105.90417, "Việt Nam", "Hòn Trống Mái và bãi biển nổi tiếng Bắc Trung Bộ"),
    ("Khu di tích Lam Kinh, Thanh Hóa", 19.91444, 105.41500, "Việt Nam", "Đất phát tích cuộc khởi nghĩa Lam Sơn"),
    ("Quảng trường Hồ Chí Minh, TP. Vinh", 18.67944, 105.68111, "Việt Nam", "Quảng trường trung tâm thành phố Vinh, Nghệ An"),
    ("Làng Sen Kim Liên, Nam Đàn, Nghệ An", 18.66944, 105.54500, "Việt Nam", "Quê hương Chủ tịch Hồ Chí Minh"),
    ("Bãi biển Cửa Lò, Nghệ An", 18.79889, 105.71694, "Việt Nam", "Bãi biển đẹp bậc nhất xứ Nghệ"),
    ("Ngã ba Đồng Lộc, Hà Tĩnh", 18.40417, 105.75111, "Việt Nam", "Địa danh lịch sử bất tử trên tuyến đường Trường Sơn"),
    ("Động Phong Nha, Quảng Bình", 17.58139, 106.28306, "Việt Nam", "Di sản thiên nhiên thế giới Phong Nha - Kẻ Bàng"),
    ("Động Thiên Đường, Quảng Bình", 17.51944, 106.22333, "Việt Nam", "Hoàng cung trong lòng đất kỳ vĩ"),
    ("Tượng đài Mẹ Suốt & Biển Nhật Lệ, Đồng Hới", 17.46889, 106.62889, "Việt Nam", "Biểu tượng kiên cường bên dòng sông Nhật Lệ"),
    ("Cầu Hiền Lương - Sông Bến Hải, Quảng Trị", 17.00389, 107.05083, "Việt Nam", "Vĩ tuyến 17 chứng nhân lịch sử chia cắt hai miền"),
    ("Thành cổ Quảng Trị", 16.75361, 107.18528, "Việt Nam", "Ký ức 81 ngày đêm mùa hè đỏ lửa 1972"),
    ("Địa đạo Vịnh Mốc, Quảng Trị", 17.07444, 107.11000, "Việt Nam", "Ngôi làng ngầm dưới lòng đất ven biển"),
    ("Kinh thành Huế (Đại Nội & Ngọ Môn)", 16.46944, 107.57806, "Việt Nam", "Quần thể di tích Cố đô Huế UNESCO"),
    ("Chùa Thiên Mụ, Huế", 16.45333, 107.54472, "Việt Nam", "Tháp Phước Duyên 7 tầng bên bờ sông Hương"),
    ("Cầu Trường Tiền, Huế", 16.46861, 107.58917, "Việt Nam", "Cây cầu 6 vài 12 nhịp biểu tượng xứ Huế"),
    ("Lăng Tự Đức, Huế", 16.43306, 107.56556, "Việt Nam", "Kiến trúc lăng tẩm nên thơ giữa rừng thông"),
    ("Lăng Khải Định, Huế", 16.39917, 107.59028, "Việt Nam", "Công trình giao thoa kiến trúc Á - Âu tinh xảo"),
    ("Vịnh Lăng Cô, Thừa Thiên Huế", 16.24167, 108.07500, "Việt Nam", "Một trong những vịnh biển đẹp nhất thế giới"),
    # --- Duyên hải Nam Trung Bộ ---
    ("Đèo Hải Vân (Hải Vân Quan)", 16.18861, 108.13194, "Việt Nam", "Thiên hạ đệ nhất hùng quan nối Huế và Đà Nẵng"),
    ("Cầu Rồng, Đà Nẵng", 16.06111, 108.22750, "Việt Nam", "Biểu tượng hiện đại của Đà Nẵng bắc qua sông Hàn"),
    ("Bãi biển Mỹ Khê, Đà Nẵng", 16.05972, 108.24833, "Việt Nam", "Một trong những bãi biển quyến rũ nhất hành tinh"),
    ("Chùa Linh Ứng, Bán đảo Sơn Trà, Đà Nẵng", 16.10056, 108.27750, "Việt Nam", "Tượng Phật Quan Âm cao 67m hướng ra Biển Đông"),
    ("Danh thắng Ngũ Hành Sơn, Đà Nẵng", 16.00222, 108.26361, "Việt Nam", "Năm ngọn núi đá vôi ven biển"),
    ("Cầu Quay Sông Hàn, Đà Nẵng", 16.07222, 108.22694, "Việt Nam", "Cây cầu quay đầu tiên do kỹ sư Việt Nam thiết kế"),
    ("Phố cổ Hội An (Chùa Cầu), Quảng Nam", 15.87722, 108.32611, "Việt Nam", "Thương cảng cổ Di sản Văn hoá Thế giới"),
    ("Thánh địa Mỹ Sơn, Quảng Nam", 15.76417, 108.12417, "Việt Nam", "Quần thể đền tháp Chăm Pa cổ kính"),
    ("Tượng đài Mẹ Việt Nam Anh Hùng, Tam Kỳ", 15.56667, 108.53222, "Việt Nam", "Công trình tượng đài quy mô lớn tại Núi Cấm"),
    ("Cầu Thị Nại, Quy Nhơn, Bình Định", 13.80694, 109.24833, "Việt Nam", "Cầu vượt biển dài bắc qua đầm Thị Nại"),
    ("Quảng trường 2/4 (Tháp Trầm Hương), Nha Trang", 12.23889, 109.19667, "Việt Nam", "Tháp Trầm Hương biểu tượng bên bờ biển Nha Trang"),
    ("Tháp Đôi, Quy Nhơn, Bình Định", 13.78806, 109.21222, "Việt Nam", "Cụm tháp Chăm độc đáo giữa lòng phố biển"),
    ("Eo Gió, Nhơn Lý, Quy Nhơn", 13.87639, 109.32083, "Việt Nam", "Cung đường ven biển ôm trọn vịnh đá hùng vĩ"),
    ("Ghềnh Đá Đĩa, Phú Yên", 13.35333, 109.29389, "Việt Nam", "Kỳ quan địa chất cột đá bazan hình lục giác"),
    ("Mũi Điện (Hải đăng Đại Lãnh), Phú Yên", 12.89389, 109.45500, "Việt Nam", "Nơi đón bình minh sớm trên đất liền Việt Nam"),
    ("Tháp Nghinh Phong, Tuy Hòa, Phú Yên", 13.09583, 109.32278, "Việt Nam", "Biểu tượng lấy cảm hứng từ Ghềnh Đá Đĩa và truyền thuyết Lạc Long Quân"),
    ("Tháp Bà Ponagar, Nha Trang", 12.26528, 109.19556, "Việt Nam", "Quần thể đền tháp Chăm Pa bên cửa sông Cái"),
    ("Chùa Long Sơn, Nha Trang", 12.25111, 109.18056, "Việt Nam", "Tượng Kim Thân Phật Tổ trên đỉnh đồi Trại Thủy"),
    ("Nhà thờ Đá Nha Trang", 12.24694, 109.18861, "Việt Nam", "Nhà thờ Chính toà Kitô Vua giữa trung tâm phố biển"),
    ("Viện Hải dương học Nha Trang", 12.20778, 109.21444, "Việt Nam", "Cơ sở nghiên cứu sinh vật biển lâu đời nhất Đông Nam Á"),
    ("Tháp Chàm Pô Klông Garai, Phan Rang", 11.59889, 108.95222, "Việt Nam", "Cụm tháp Chăm đẹp và nguyên vẹn bậc nhất Ninh Thuận"),
    ("Vịnh Vĩnh Hy, Ninh Thuận", 11.72083, 109.19722, "Việt Nam", "Vịnh biển hoang sơ ôm sát Vườn quốc gia Núi Chúa"),
    ("Đồi Cát Bay Mũi Né, Phan Thiết", 10.94917, 108.29389, "Việt Nam", "Tiểu sa mạc cát đổi hình dạng liên tục"),
    ("Hải đăng Kê Gà, Bình Thuận", 10.70028, 107.99167, "Việt Nam", "Ngọn hải đăng cổ và cao bậc nhất Việt Nam"),
    # --- Tây Nguyên ---
    ("Nhà thờ Gỗ Kon Tum", 14.35139, 108.01222, "Việt Nam", "Công trình kiến trúc gỗ cà chít trăm năm tuổi"),
    ("Cầu treo Kon Klor & Nhà Rông, Kon Tum", 14.34361, 108.02056, "Việt Nam", "Biểu tượng văn hoá Tây Nguyên bên sông Đăk Bla"),
    ("Biển Hồ (Hồ T'Nưng), Pleiku, Gia Lai", 14.05194, 108.00139, "Việt Nam", "Đôi mắt Pleiku nằm trên miệng núi lửa cổ"),
    ("Bảo tàng Thế giới Cà phê, Buôn Ma Thuột", 12.69083, 108.06083, "Việt Nam", "Kiến trúc nhà dài cách điệu giữa thủ phủ cà phê"),
    ("Ngã Sáu Ban Mê (Tượng đài Chiến thắng)", 12.67944, 108.04444, "Việt Nam", "Trung tâm thành phố Buôn Ma Thuột"),
    ("Thác Dray Nur, Đắk Lắk", 12.53694, 107.88806, "Việt Nam", "Ngọn thác hùng vĩ trên dòng sông Sêrêpôk"),
    ("Hồ Tà Đùng, Đắk Nông", 11.88333, 108.00833, "Việt Nam", "Vịnh Hạ Long thu nhỏ của vùng đất Tây Nguyên"),
    ("Quảng trường Lâm Viên, Đà Lạt", 11.94083, 108.44556, "Việt Nam", "Nụ hoa Atiso và bông hoa Dã Quỳ khổng lồ bên Hồ Xuân Hương"),
    ("Hồ Xuân Hương, Đà Lạt", 11.94167, 108.44167, "Việt Nam", "Hồ nước thơ mộng giữa lòng thành phố ngàn hoa"),
    ("Ga Đà Lạt", 11.94222, 108.45528, "Việt Nam", "Nhà ga xe lửa cổ kính nhất Đông Dương"),
    ("Nhà thờ Con Gà, Đà Lạt", 11.93694, 108.43694, "Việt Nam", "Nhà thờ Chính toà thành phố cao nguyên"),
    ("Đỉnh Langbiang, Lạc Dương, Lâm Đồng", 12.04583, 108.43750, "Việt Nam", "Nóc nhà cao nguyên Lâm Viên"),
    ("Thiền viện Trúc Lâm Đà Lạt", 11.90361, 108.43500, "Việt Nam", "Thiền viện tĩnh lặng bên hồ Tuyền Lâm"),
    # --- Đông Nam Bộ & TP. Hồ Chí Minh ---
    ("Chợ Bến Thành, TP.HCM", 10.77250, 106.69806, "Việt Nam", "Biểu tượng giao thương lâu đời trung tâm Sài Gòn"),
    ("Dinh Độc Lập, TP.HCM", 10.77694, 106.69528, "Việt Nam", "Hội trường Thống Nhất gắn liền dấu mốc 30/4/1975"),
    ("Nhà thờ Đức Bà Sài Gòn", 10.77972, 106.69889, "Việt Nam", "Vương cung thánh đường gạch đỏ Marseille"),
    ("Bưu điện Trung tâm TP.HCM", 10.78000, 106.70000, "Việt Nam", "Kiến trúc mái vòm cổ điển bên cạnh Nhà thờ Đức Bà"),
    ("Phố đi bộ Nguyễn Huệ & UBND TP.HCM", 10.77556, 106.70194, "Việt Nam", "Đại lộ trung tâm sầm uất bậc nhất Sài Gòn"),
    ("Bến Nhà Rồng, TP.HCM", 10.76833, 106.70694, "Việt Nam", "Nơi Bác Hồ ra đi tìm đường cứu nước năm 1911"),
    ("Tòa nhà Landmark 81, TP.HCM", 10.79500, 106.72194, "Việt Nam", "Toà nhà chọc trời cao nhất Việt Nam bên sông Sài Gòn"),
    ("Tháp tài chính Bitexco, TP.HCM", 10.77167, 106.70444, "Việt Nam", "Toà nhà hình búp sen với sân đỗ trực thăng"),
    ("Nhà hát Thành phố Hồ Chí Minh", 10.77667, 106.70306, "Việt Nam", "Nhà hát Opera kiến trúc Pháp tại Công trường Lam Sơn"),
    ("Địa đạo Củ Chi, TP.HCM", 11.14222, 106.46222, "Việt Nam", "Hệ thống hầm ngầm kỳ tích trong kháng chiến"),
    ("Núi Bà Đen, Tây Ninh", 11.37722, 106.17444, "Việt Nam", "Nóc nhà Nam Bộ cao 986m"),
    ("Tòa Thánh Tây Ninh", 11.30750, 106.14083, "Việt Nam", "Trung tâm kiến trúc rực rỡ của đạo Cao Đài"),
    ("Văn miếu Trấn Biên, Biên Hòa, Đồng Nai", 10.95556, 106.80917, "Việt Nam", "Văn miếu đầu tiên tại vùng đất Nam Bộ"),
    ("Vườn quốc gia Cát Tiên, Đồng Nai", 11.42500, 107.42500, "Việt Nam", "Khu dự trữ sinh quyển rừng nhiệt đới Đông Nam Bộ"),
    ("Tượng Chúa Kitô Vua (Núi Nhỏ), Vũng Tàu", 10.32639, 107.08444, "Việt Nam", "Bức tượng dang tay hướng biển trên đỉnh Tao Phùng"),
    ("Hải đăng Vũng Tàu", 10.33694, 107.07583, "Việt Nam", "Ngọn hải đăng cổ ngắm toàn cảnh thành phố biển"),
    ("Bạch Dinh, Vũng Tàu", 10.34889, 107.06861, "Việt Nam", "Dinh thự trắng cổ kính trên triền Núi Lớn"),
    ("Nhà hát Cao Văn Lầu (Nón Lá), Bạc Liêu", 9.29194, 105.72778, "Việt Nam", "Toà nhà hình ba chiếc nón lá bên quảng trường Hùng Vương"),
    # --- Đồng bằng Sông Cửu Long ---
    ("Chùa Vĩnh Tràng, Mỹ Tho, Tiền Giang", 10.36278, 106.37417, "Việt Nam", "Ngôi chùa cổ kết hợp kiến trúc Á - Âu đặc sắc"),
    ("Cầu Mỹ Thuận, Tiền Giang - Vĩnh Long", 10.27194, 105.90806, "Việt Nam", "Cây cầu dây văng đầu tiên bắc qua sông Tiền"),
    ("Cồn Phụng, Bến Tre", 10.33889, 106.34583, "Việt Nam", "Xứ dừa bên cù lao sông Tiền"),
    ("Ao Bà Om & Chùa Âng, Trà Vinh", 9.92194, 106.32278, "Việt Nam", "Thắng cảnh cổ kính đậm nét văn hoá Khmer Nam Bộ"),
    ("Bến Ninh Kiều, Cần Thơ", 10.03222, 105.78750, "Việt Nam", "Biểu tượng thơ mộng bên ngã ba sông Hậu"),
    ("Chợ nổi Cái Răng, Cần Thơ", 10.00222, 105.74583, "Việt Nam", "Di sản văn hoá phi vật thể chợ nổi trên sông"),
    ("Cầu Cần Thơ", 10.03722, 105.81111, "Việt Nam", "Cầu dây văng nhịp chính lớn bắc qua sông Hậu"),
    ("Nhà cổ Bình Thủy, Cần Thơ", 10.07139, 105.74194, "Việt Nam", "Ngôi nhà cổ Nam Bộ hơn 150 năm tuổi"),
    ("Khu di tích Nguyễn Sinh Sắc, Cao Lãnh, Đồng Tháp", 10.45333, 105.62000, "Việt Nam", "Nơi yên nghỉ của thân sinh Chủ tịch Hồ Chí Minh"),
    ("Làng hoa Sa Đéc, Đồng Tháp", 10.31250, 105.73611, "Việt Nam", "Thủ phủ hoa kiểng bên bờ sông Tiền"),
    ("Phố đi bộ Bùi Viện, TP.HCM", 10.76750, 106.69389, "Việt Nam", "Khu phố sầm uất về đêm tại Quận 1"),
    ("Rừng tràm Trà Sư, An Giang", 10.57611, 105.04306, "Việt Nam", "Hệ sinh thái rừng tràm ngập nước bạt ngàn"),
    ("Chùa Som Rong, Sóc Trăng", 9.59167, 105.98389, "Việt Nam", "Tượng Phật Thích Ca nhập niết bàn khổng lồ"),
    ("Nhà Công tử Bạc Liêu", 9.28694, 105.72444, "Việt Nam", "Ngôi biệt thự Pháp cổ nổi tiếng lục tỉnh Nam Kỳ"),
    ("Cánh đồng Điện gió Bạc Liêu", 9.20889, 105.79222, "Việt Nam", "Hàng trăm trụ tuabin gió vươn mình trên biển"),
    ("Mũi Cà Mau (Cột mốc GPS 0001)", 8.60417, 104.71667, "Việt Nam", "Điểm cực Nam đất liền của dải đất hình chữ S"),
    ("Cổng Tam Quan, Rạch Giá, Kiên Giang", 10.01167, 105.08444, "Việt Nam", "Biểu tượng cửa ngõ thành phố biển Rạch Giá"),
    ("Dinh Cậu, Phú Quốc, Kiên Giang", 10.21778, 103.95694, "Việt Nam", "Ngôi miếu linh thiêng trên ghềnh đá đảo Ngọc"),
    ("Cầu Hôn (Kiss Bridge), Phú Quốc", 10.02528, 104.00639, "Việt Nam", "Cây cầu biểu tượng hoàng hôn tại Nam đảo Phú Quốc"),
    # --- Mở rộng thêm các Landmark Việt Nam có góc nhìn phố/quảng trường rõ nét ---
    ("Phố cổ Tạ Hiện, Hà Nội", 21.03497, 105.85200, "Việt Nam", "Ngã tư quốc tế sầm uất bậc nhất khu phố cổ Hà Nội"),
    ("Cầu Chương Dương, Hà Nội", 21.03694, 105.86194, "Việt Nam", "Cây cầu lớn nối trung tâm Hoàn Kiếm với Long Biên"),
    ("Cột cờ Hà Nội (Bảo tàng Lịch sử Quân sự)", 21.03250, 105.83972, "Việt Nam", "Kỳ đài lịch sử hơn 200 năm trên đường Điện Biên Phủ"),
    ("Đường Thanh Niên & Chùa Trấn Quốc, Hà Nội", 21.04583, 105.83750, "Việt Nam", "Con đường Cổ Ngư lãng mạn giữa Hồ Tây và Hồ Trúc Bạch"),
    ("Sân vận động Quốc gia Mỹ Đình, Hà Nội", 21.02056, 105.76389, "Việt Nam", "Chảo lửa thể thao lớn nhất Việt Nam"),
    ("Trung tâm Hội nghị Quốc gia, Hà Nội", 21.00556, 105.78667, "Việt Nam", "Công trình kiến trúc lượn sóng trên đại lộ Thăng Long"),
    ("Cầu Hoàng Văn Thụ, Hải Phòng", 20.86917, 106.68222, "Việt Nam", "Cây cầu vòm thép hình cánh chim biển cửa ngõ Thủy Nguyên"),
    ("Quảng trường 30/10 & Cung Cá Heo, Hạ Long", 20.94611, 107.11056, "Việt Nam", "Cung Quy hoạch & Hội chợ bên bờ vịnh Hạ Long"),
    ("Quảng trường Hòa Bình, TP. Hòa Bình", 20.81667, 105.33750, "Việt Nam", "Quảng trường trung tâm thành phố bên sông Đà"),
    ("Quảng trường 26/3 (Cột mốc Km0), Hà Giang", 22.82333, 104.98389, "Việt Nam", "Điểm khởi đầu cung đường Đông Bắc huyền thoại"),
    ("Quảng trường Tây Bắc, TP. Sơn La", 21.32667, 103.91889, "Việt Nam", "Quảng trường trung tâm vùng núi Tây Bắc"),
    ("Quảng trường 7/5, TP. Điện Biên Phủ", 21.38528, 103.01556, "Việt Nam", "Quảng trường trung tâm thành phố Điện Biên Phủ"),
    ("Quảng trường Hùng Vương, Việt Trì, Phú Thọ", 21.32083, 105.40500, "Việt Nam", "Không gian văn hoá trung tâm thành phố Lễ hội"),
    ("Quảng trường 3/2, TP. Bắc Giang", 21.27389, 106.19444, "Việt Nam", "Trung tâm hành chính - văn hoá tỉnh Bắc Giang"),
    ("Trung tâm Văn hoá Kinh Bắc, TP. Bắc Ninh", 21.18167, 106.06639, "Việt Nam", "Công trình kiến trúc mang đậm dấu ấn Quan họ"),
    ("Quảng trường Nguyễn Tất Thành, Tuyên Quang", 21.82361, 105.21417, "Việt Nam", "Tượng đài Bác Hồ với nhân dân các dân tộc tỉnh Tuyên Quang"),
    ("Quảng trường Võ Nguyên Giáp, TP. Thái Nguyên", 21.59444, 105.84778, "Việt Nam", "Quảng trường trung tâm thủ đô gió ngàn"),
    ("Cầu Nhật Lệ 1, Đồng Hới, Quảng Bình", 17.46806, 106.62583, "Việt Nam", "Cây cầu thơ mộng nối trung tâm Đồng Hới với bán đảo Bảo Ninh"),
    ("Cầu Trần Thị Lý, Đà Nẵng", 16.05000, 108.23250, "Việt Nam", "Cầu dây văng hình cánh buồm căng gió vươn ra biển"),
    ("Tòa nhà Trung tâm Hành chính Đà Nẵng", 16.07778, 108.22444, "Việt Nam", "Toà nhà hình ngọn hải đăng bên sông Hàn"),
    ("Công viên Biển Đông, Đà Nẵng", 16.06889, 108.24528, "Việt Nam", "Quảng trường chim bồ câu bên bãi biển Mỹ Khê"),
    ("Chợ Hàn, Đà Nẵng", 16.06806, 108.22417, "Việt Nam", "Khu chợ truyền thống nổi tiếng bên sông Hàn"),
    ("Quảng trường Nguyễn Tất Thành, Quy Nhơn", 13.76889, 109.22333, "Việt Nam", "Quảng trường hướng biển trung tâm thành phố Quy Nhơn"),
    ("Tháp Chăm Bánh Ít, Bình Định", 13.86944, 109.13694, "Việt Nam", "Cụm 4 tháp Chăm cổ trên đỉnh đồi bên quốc lộ 1A"),
    ("Cầu Đà Rằng, Tuy Hòa, Phú Yên", 13.07722, 109.29833, "Việt Nam", "Cây cầu dài bắc qua dòng sông Ba"),
    ("Quảng trường 16/4, Phan Rang - Tháp Chàm", 11.56444, 108.99194, "Việt Nam", "Trung tâm văn hoá tỉnh Ninh Thuận"),
    ("Tháp Nước Phan Thiết, Bình Thuận", 10.92861, 108.10056, "Việt Nam", "Biểu tượng lịch sử bên dòng sông Cà Ty"),
    ("Quảng trường 17/3, Đắk Nông (Gia Nghĩa)", 11.99944, 107.68806, "Việt Nam", "Trung tâm thành phố trẻ Gia Nghĩa"),
    ("Quảng trường Đại Đoàn Kết, Pleiku, Gia Lai", 13.98000, 108.00528, "Việt Nam", "Nơi đặt tượng đài Bác Hồ với các dân tộc Tây Nguyên"),
    ("Cầu Ba Son (Thủ Thiêm 2), TP.HCM", 10.77889, 106.70861, "Việt Nam", "Cầu dây văng biểu tượng mới nối Quận 1 với Thủ Thiêm"),
    ("Chợ Bình Tây (Chợ Lớn), TP.HCM", 10.74944, 106.65111, "Việt Nam", "Khu chợ kiến trúc Á Đông cổ kính vùng Chợ Lớn"),
    ("Nhà thờ Tân Định (Nhà thờ Hồng), TP.HCM", 10.78889, 106.69083, "Việt Nam", "Ngôi thánh đường màu hồng nổi bật trên đường Hai Bà Trưng"),
    ("Chùa Bà Thiên Hậu, Quận 5, TP.HCM", 10.75333, 106.66111, "Việt Nam", "Ngôi miếu cổ hơn 260 năm của cộng đồng người Hoa"),
    ("Cầu Ánh Sao & Hồ Bán Nguyệt, Quận 7, TP.HCM", 10.72833, 106.71861, "Việt Nam", "Cây cầu đi bộ phát sáng nổi tiếng tại Phú Mỹ Hưng"),
    ("Khu du lịch Đại Nam (Cổng chính), Bình Dương", 11.04444, 106.62583, "Việt Nam", "Khu phức hợp giải trí - văn hoá lớn tại Bình Dương"),
    ("Quảng trường Hùng Vương, Bạc Liêu", 9.29139, 105.72778, "Việt Nam", "Biểu tượng cây đàn kìm cách điệu cao 18m"),
    ("Cầu Rạch Miễu, Tiền Giang - Bến Tre", 10.34083, 106.34222, "Việt Nam", "Cây cầu dây văng nối đôi bờ sông Tiền"),
    ("Chợ nổi Ngã Bảy (Phụng Hiệp), Hậu Giang", 9.81111, 105.82500, "Việt Nam", "Ngã bảy sông nước nổi tiếng miền Tây"),
    ("Cầu Cao Lãnh, Đồng Tháp", 10.42167, 105.62278, "Việt Nam", "Cầu dây văng lớn bắc qua sông Tiền tại Đồng Tháp"),
    ("Chùa Dơi (Mahatup), Sóc Trăng", 9.57806, 105.97444, "Việt Nam", "Ngôi chùa Khmer cổ với đàn dơi quạ hàng nghìn con"),
    # --- Đợt mở rộng lần 2: thêm địa danh đô thị & văn hoá khắp Việt Nam ---
    ("Ga Hà Nội (Phố Lê Duẩn)", 21.02431, 105.84111, "Việt Nam", "Nhà ga đầu mối đường sắt lâu đời nhất Thủ đô"),
    ("Lăng Chủ tịch & Quảng trường Hùng Vương, Bến Tre", 10.24111, 106.37528, "Việt Nam", "Công viên trung tâm TP. Bến Tre bên sông Bến Tre"),
    ("Cầu Vĩnh Tuy, Hà Nội", 20.99639, 105.87556, "Việt Nam", "Cây cầu huyết mạch phía Đông Nam Hà Nội"),
    ("Cầu Đông Trù, Hà Nội", 21.06417, 105.88250, "Việt Nam", "Cầu vòm ống thép nhồi bê tông bắc qua sông Đuống"),
    ("Học viện Nông nghiệp Việt Nam (Trâu Quỳ), Hà Nội", 21.00528, 105.93167, "Việt Nam", "Khuôn viên đại học xanh nổi tiếng vùng Gia Lâm"),
    ("Cầu Thê Húc & Đền Ngọc Sơn, Hà Nội", 21.03083, 105.85250, "Việt Nam", "Cây cầu gỗ sơn son dẫn vào đảo Ngọc Hồ Gươm"),
    ("Chùa Quán Sứ, Hà Nội", 21.02444, 105.84528, "Việt Nam", "Trụ sở Trung ương Giáo hội Phật giáo Việt Nam"),
    ("Nhà thờ Cửa Bắc, Hà Nội", 21.04083, 105.84194, "Việt Nam", "Ngôi thánh đường kiến trúc Đông Dương trên phố Phan Đình Phùng"),
    ("Tòa án Nhân dân Tối cao, Hà Nội", 21.02583, 105.84917, "Việt Nam", "Kiến trúc Pháp cổ trên phố Lý Thường Kiệt"),
    ("Bưu điện Hà Nội (Bờ Hồ)", 21.02806, 105.85417, "Việt Nam", "Tháp đồng hồ mang biểu tượng thời gian bên Hồ Hoàn Kiếm"),
    ("Cầu Bính, Hải Phòng", 20.87583, 106.66611, "Việt Nam", "Cây cầu dây văng đẹp bắc qua sông Cấm"),
    ("Ga Hải Phòng", 20.85556, 106.68778, "Việt Nam", "Nhà ga kiến trúc Pháp cổ hơn 120 năm tuổi"),
    ("Cổng Chào Tuần Châu, Hạ Long", 20.94694, 106.98944, "Việt Nam", "Trục đường xuyên biển ra đảo Tuần Châu"),
    ("Quảng trường Lam Sơn, TP. Thanh Hóa", 19.80694, 105.77639, "Việt Nam", "Quảng trường trung tâm thành phố Thanh Hóa"),
    ("Cầu Trường Thi & Đại lộ Lê Lợi, Thanh Hóa", 19.80722, 105.77361, "Việt Nam", "Đại lộ trung tâm sầm uất bậc nhất xứ Thanh"),
    ("Cầu Bến Thủy, Vinh - Hà Tĩnh", 18.64778, 105.70194, "Việt Nam", "Cây cầu nối đôi bờ sông Lam lịch sử"),
    ("Quảng trường Thành Sen, TP. Hà Tĩnh", 18.34250, 105.90583, "Việt Nam", "Trung tâm hành chính - văn hoá tỉnh Hà Tĩnh"),
    ("Quảng trường Hồ Chí Minh, Đồng Hới, Quảng Bình", 17.46833, 106.62139, "Việt Nam", "Không gian công viên và tượng đài trung tâm Đồng Hới"),
    ("Nhà thờ Phủ Cam, Huế", 16.45333, 107.58806, "Việt Nam", "Nhà thờ chính tòa Huế với kiến trúc vươn cao độc đáo"),
    ("Quảng trường Ngọ Môn (Kỳ Đài Huế)", 16.46750, 107.57861, "Việt Nam", "Cột cờ kinh đô Nguyễn hướng ra sông Hương"),
    ("Cầu Thuận Phước, Đà Nẵng", 16.09583, 108.22139, "Việt Nam", "Cầu treo dây võng bắc qua cửa biển vịnh Đà Nẵng"),
    ("Bảo tàng Điêu khắc Chăm, Đà Nẵng", 16.06083, 108.22333, "Việt Nam", "Bảo tàng lưu giữ bộ sưu tập nghệ thuật Chăm Pa lớn nhất"),
    ("Chùa Cầu & Phố Bạch Đằng, Hội An", 15.87700, 108.32640, "Việt Nam", "Cây cầu mái ngói cổ bên sông Hoài"),
    ("Quảng trường 24/3, Tam Kỳ, Quảng Nam", 15.56861, 108.47778, "Việt Nam", "Trung tâm thành phố Tam Kỳ"),
    ("Quảng trường Phạm Văn Đồng, Quảng Ngãi", 15.12028, 108.80472, "Việt Nam", "Quảng trường trung tâm thành phố Quảng Ngãi"),
    ("Cầu Trần Hưng Đạo, Tuy Hòa, Phú Yên", 13.08194, 109.30694, "Việt Nam", "Cây cầu hiện đại nối trung tâm Tuy Hòa"),
    ("Cầu Trần Phú, Nha Trang", 12.25639, 109.19667, "Việt Nam", "Cây cầu cửa biển ngắm toàn cảnh sông Cái và tháp Bà"),
    ("Chợ Đầm, Nha Trang", 12.25333, 109.19056, "Việt Nam", "Khu chợ kiến trúc hình hoa sen biểu tượng phố biển"),
    ("Chùa Linh Phước (Chùa Ve Chai), Đà Lạt", 11.94500, 108.49917, "Việt Nam", "Ngôi chùa khảm sành sứ độc đáo vùng Trại Mát"),
    ("Trường Cao đẳng Sư phạm Đà Lạt", 11.94639, 108.45556, "Việt Nam", "Dãy nhà gạch đỏ cong hình vòng cung di sản thế giới"),
    ("Chợ Đà Lạt (Khu Hòa Bình)", 11.94250, 108.43833, "Việt Nam", "Trung tâm mua sắm và bậc thang nổi tiếng giữa phố núi"),
    ("Cầu Bình Lợi & Đường Phạm Văn Đồng, TP.HCM", 10.82472, 106.71028, "Việt Nam", "Cầu vòm Nielsen hiện đại bắc qua sông Sài Gòn"),
    ("Cầu Phú Mỹ, TP.HCM", 10.74472, 106.74472, "Việt Nam", "Cầu dây văng lớn nhất cửa ngõ Nam Sài Gòn"),
    ("Bảo tàng Lịch sử TP.HCM & Thảo Cầm Viên", 10.78806, 106.70472, "Việt Nam", "Cụm kiến trúc Đông Dương cổ kính Quận 1"),
    ("Hồ Con Rùa (Công trường Quốc tế), TP.HCM", 10.78250, 106.69583, "Việt Nam", "Vòng xoay kiến trúc đài phun nước nổi tiếng trung tâm"),
    ("Cầu Thủ Thiêm 1, TP.HCM", 10.78667, 106.71778, "Việt Nam", "Cây cầu đầu tiên nối Bình Thạnh với khu đô thị Thủ Thiêm"),
    ("Chùa Hoằng Pháp, Hóc Môn, TP.HCM", 10.89389, 106.59194, "Việt Nam", "Ngôi chùa lớn thu hút hàng vạn phật tử miền Nam"),
    ("Quảng trường Tỉnh Bình Phước (Đồng Xoài)", 11.53528, 106.89306, "Việt Nam", "Trung tâm thành phố Đồng Xoài"),
    ("Quảng trường TP. Tân An, Long An", 10.53583, 106.40556, "Việt Nam", "Công viên trung tâm bên sông Vàm Cỏ Tây"),
    ("Quảng trường Trần Văn Thời / Hùng Vương, Cà Mau", 9.17694, 105.15250, "Việt Nam", "Biểu tượng trung tâm thành phố cực Nam"),
    ("Cầu Mỹ Lợi, Tiền Giang - Long An", 10.37111, 106.67806, "Việt Nam", "Cầu vượt sông Vàm Cỏ nối vùng Gò Công"),
    ("Quảng trường Trưng Vương, Long Xuyên, An Giang", 10.38639, 105.43528, "Việt Nam", "Tượng đài Bông Sen trung tâm thành phố Long Xuyên"),
    ("Cầu Vàm Cống, Đồng Tháp - Cần Thơ", 10.31194, 105.49028, "Việt Nam", "Cầu dây văng tráng lệ bắc qua sông Hậu"),
]

ASIA_LANDMARKS: list[tuple[str, float, float, str, str]] = [
    # Nhật Bản
    ("Tháp Tokyo, Nhật Bản", 35.65858, 139.74543, "Nhật Bản", "Tháp truyền thông màu đỏ trắng biểu tượng Tokyo"),
    ("Tokyo Skytree, Nhật Bản", 35.71006, 139.81070, "Nhật Bản", "Tháp truyền hình cao nhất Nhật Bản"),
    ("Chùa Senso-ji, Asakusa, Tokyo", 35.71476, 139.79665, "Nhật Bản", "Ngôi chùa cổ nhất Tokyo với cổng Kaminarimon"),
    ("Ngã tư Shibuya, Tokyo", 35.65949, 139.70055, "Nhật Bản", "Ngã tư đi bộ nhộn nhịp nhất thế giới"),
    ("Đền Meiji Jingu, Tokyo", 35.67640, 139.69933, "Nhật Bản", "Ngôi đền Thần Đạo giữa rừng cây Shibuya"),
    ("Núi Phú Sĩ (Kawaguchiko), Nhật Bản", 35.52278, 138.75500, "Nhật Bản", "Ngọn núi lửa phủ tuyết biểu tượng xứ Phù Tang"),
    ("Đền Fushimi Inari-taisha, Kyoto", 34.96714, 135.77267, "Nhật Bản", "Hàng nghìn cổng Torii đỏ son rực rỡ"),
    ("Chùa Vàng Kinkaku-ji, Kyoto", 35.03937, 135.72924, "Nhật Bản", "Ngôi chùa dát vàng bên hồ gương Kyoto"),
    ("Chùa Thanh Thủy Kiyomizu-dera, Kyoto", 34.99486, 135.78505, "Nhật Bản", "Ngôi chùa gỗ cổ trên triền núi cố đô"),
    ("Lâu đài Osaka, Nhật Bản", 34.68732, 135.52620, "Nhật Bản", "Toà thành biểu tượng thời Chiến Quốc Nhật Bản"),
    ("Khu phố Dotonbori, Osaka", 34.66873, 135.50130, "Nhật Bản", "Khu ẩm thực và biển hiệu Glico rực sáng bên kênh"),
    ("Lâu đài Himeji, Hyogo, Nhật Bản", 34.83945, 134.69390, "Nhật Bản", "Lâu đài Hạc Trắng Di sản UNESCO"),
    ("Đền Itsukushima (Cổng Torii trên biển), Hiroshima", 34.29600, 132.31980, "Nhật Bản", "Cổng đền nổi trên vịnh Miyajima"),
    ("Đài tưởng niệm Hòa bình Hiroshima", 34.39548, 132.45359, "Nhật Bản", "Mái vòm Bom Nguyên tử chứng nhân lịch sử"),
    ("Công viên Nara & Chùa Todai-ji, Nhật Bản", 34.68900, 135.83980, "Nhật Bản", "Tượng Đại Phật bằng đồng và đàn hươu tự do"),
    # Hàn Quốc
    ("Cung điện Gyeongbokgung, Seoul", 37.57962, 126.97704, "Hàn Quốc", "Hoàng cung lớn nhất triều đại Joseon"),
    ("Tháp N Seoul (Namsan), Hàn Quốc", 37.55117, 126.98823, "Hàn Quốc", "Ngọn tháp ngắm toàn cảnh thủ đô Seoul"),
    ("Làng cổ Bukchon Hanok, Seoul", 37.58260, 126.98300, "Hàn Quốc", "Khu nhà truyền thống Hanok giữa lòng Seoul"),
    ("Dongdaemun Design Plaza (DDP), Seoul", 37.56630, 127.00950, "Hàn Quốc", "Kiến trúc vị lai của Zaha Hadid"),
    ("Tháp Lotte World Tower, Seoul", 37.51250, 127.10250, "Hàn Quốc", "Toà tháp cao nhất Hàn Quốc"),
    ("Làng văn hoá Gamcheon, Busan", 35.09750, 129.01050, "Hàn Quốc", "Ngôi làng bậc thang đầy sắc màu bên sườn đồi"),
    ("Cầu Gwangan (Kim Cương), Busan", 35.15320, 129.11860, "Hàn Quốc", "Cầu vượt biển biểu tượng thành phố cảng Busan"),
    ("Đỉnh Seongsan Ilchulbong, Jeju", 33.45810, 126.94250, "Hàn Quốc", "Miệng núi lửa Bình Minh trên đảo Jeju"),
    # Trung Quốc / Đài Loan / Hồng Kông / Macau
    ("Vạn Lý Trường Thành (Badaling), Trung Quốc", 40.35400, 116.01700, "Trung Quốc", "Kỳ quan phòng thủ vĩ đại nhất nhân loại"),
    ("Tháp Taipei 101, Đài Loan", 25.03396, 121.56447, "Đài Loan", "Toà tháp hình đốt tre biểu tượng Đài Bắc"),
    ("Đài tưởng niệm Tưởng Giới Thạch, Đài Bắc", 25.03472, 121.52167, "Đài Loan", "Quảng trường Tự do mái ngói xanh trắng"),
    ("Làng cổ Cửu Phần (Jiufen), Đài Loan", 25.10970, 121.84520, "Đài Loan", "Phố đèn lồng đỏ trên triền núi nhìn ra biển"),
    ("Hồ Nhật Nguyệt, Đài Loan", 23.86400, 120.91600, "Đài Loan", "Hồ nước ngọt trên núi đẹp nhất Đài Loan"),
    ("Đầm Liên Trì (Long Hổ Tháp), Cao Hùng", 22.68111, 120.29611, "Đài Loan", "Cặp tháp rồng hổ nổi tiếng miền Nam Đài Loan"),
    ("Đỉnh Victoria Peak, Hồng Kông", 22.27590, 114.14550, "Hồng Kông", "Điểm ngắm toàn cảnh vịnh Victoria và cao ốc"),
    ("Tượng Đại Phật Thiên Tân, Đảo Lantau, Hồng Kông", 22.25400, 113.90500, "Hồng Kông", "Tượng Phật ngồi bằng đồng ngoài trời khổng lồ"),
    ("Di tích Nhà thờ Thánh Paul, Macau", 22.19778, 113.54083, "Macau", "Mặt tiền đá chạm khắc biểu tượng của Macau"),
    # Đông Nam Á
    ("Tượng Nhân sư Merlion & Vịnh Marina, Singapore", 1.28679, 103.85453, "Singapore", "Biểu tượng đầu sư tử mình cá bên vịnh Marina"),
    ("Marina Bay Sands, Singapore", 1.28340, 103.86070, "Singapore", "Tổ hợp 3 toà tháp nâng con thuyền trên không"),
    ("Gardens by the Bay, Singapore", 1.28157, 103.86361, "Singapore", "Khu vườn siêu cây Supertree Grove"),
    ("Đền Angkor Wat, Siem Reap, Campuchia", 13.41250, 103.86667, "Campuchia", "Quần thể đền đài cổ đại lớn nhất thế giới"),
    ("Đền Bayon (Angkor Thom), Campuchia", 13.44120, 103.85880, "Campuchia", "Ngôi đền với hàng trăm khuôn mặt đá bí ẩn"),
    ("Cung điện Hoàng gia Phnom Penh, Campuchia", 11.56390, 104.93110, "Campuchia", "Chùa Bạc và cung điện mái vàng bên sông Mê Kông"),
    ("Chùa Wat Arun (Chùa Bình Minh), Bangkok", 13.74361, 100.48889, "Thái Lan", "Ngôi chùa tháp khảm sứ bên bờ sông Chao Phraya"),
    ("Hoàng cung Thái Lan (Grand Palace), Bangkok", 13.75000, 100.49130, "Thái Lan", "Quần thể hoàng cung và Chùa Phật Ngọc lộng lẫy"),
    ("Chùa Trắng Wat Rong Khun, Chiang Rai", 19.82420, 99.76280, "Thái Lan", "Ngôi chùa nghệ thuật màu trắng tinh khôi"),
    ("Cố đô Ayutthaya (Wat Mahathat), Thái Lan", 14.35700, 100.56750, "Thái Lan", "Đầu tượng Phật nằm trong rễ cây cổ thụ"),
    ("Tượng Phật Lớn Big Buddha, Phuket, Thái Lan", 7.82760, 98.31290, "Thái Lan", "Tượng Phật đá cẩm thạch trắng trên đỉnh đồi Nakkerd"),
    ("Tháp đôi Petronas, Kuala Lumpur, Malaysia", 3.15785, 101.71165, "Malaysia", "Cặp tháp đôi cao nhất thế giới một thời"),
    ("Động Batu (Tượng Thần Murugan), Malaysia", 3.23790, 101.68400, "Malaysia", "Bậc thang 7 sắc cầu vồng dẫn lên hang động đá vôi"),
    ("Thánh đường Hồi giáo Hồng Putrajaya, Malaysia", 2.93610, 101.68920, "Malaysia", "Thánh đường mái vòm đá granite hồng bên hồ"),
    ("Cầu Penang, Malaysia", 5.35470, 100.34640, "Malaysia", "Cây cầu biểu tượng nối đảo Penang với đất liền"),
    ("Đền Borobudur, Trung Java, Indonesia", -7.60787, 110.20375, "Indonesia", "Ngôi đền Phật giáo lớn nhất thế giới"),
    ("Đền Prambanan, Yogyakarta, Indonesia", -7.75202, 110.49147, "Indonesia", "Quần thể đền Hindu cổ kỳ vĩ đảo Java"),
    ("Đền Tanah Lot, Bali, Indonesia", -8.62120, 115.08680, "Indonesia", "Ngôi đền cổ trên mỏm đá giữa sóng biển Bali"),
    ("Đền Uluwatu, Bali, Indonesia", -8.82910, 115.08490, "Indonesia", "Ngôi đền trên vách đá cao chênh vênh"),
    ("Đài tưởng niệm Quốc gia Monas, Jakarta", -6.17539, 106.82715, "Indonesia", "Ngọn tháp ngọn lửa vàng trung tâm thủ đô Indonesia"),
    ("Thành cổ Intramuros (Pháo đài Santiago), Manila", 14.59420, 120.97030, "Philippines", "Khu thành cổ Tây Ban Nha tại Manila"),
    ("Đồi Chocolate Hills, Bohol, Philippines", 9.82970, 124.13970, "Philippines", "Hàng nghìn ngọn đồi hình nón kỳ lạ"),
    ("Chùa Vàng Shwedagon, Yangon, Myanmar", 16.79833, 96.14944, "Myanmar", "Bảo tháp dát vàng ròng 2.500 năm tuổi"),
    ("Thánh địa That Luang, Vientiane, Lào", 17.97639, 102.63472, "Lào", "Biểu tượng quốc gia tháp vàng của nước Lào"),
    ("Khải Hoàn Môn Patuxai, Vientiane, Lào", 17.97056, 102.61861, "Lào", "Đài tưởng niệm giữa đại lộ Lan Xang"),
    ("Thánh đường Omar Ali Saifuddien, Brunei", 4.88970, 114.93920, "Brunei", "Thánh đường mái vòm vàng bên đầm nhân tạo"),
    # Nam Á, Trung Đông, Thổ Nhĩ Kỳ & Trung Á
    ("Đền Taj Mahal, Agra, Ấn Độ", 27.17500, 78.04190, "Ấn Độ", "Lăng mộ đá cẩm thạch trắng kỳ quan thế giới"),
    ("Cổng Ấn Độ (India Gate), New Delhi", 28.61291, 77.22951, "Ấn Độ", "Khải hoàn môn tưởng niệm chiến sĩ tại thủ đô Ấn Độ"),
    ("Pháo đài Đỏ (Red Fort), Delhi, Ấn Độ", 28.65616, 77.24102, "Ấn Độ", "Cung điện đá sa thạch đỏ thời Mughal"),
    ("Cung điện Gió Hawa Mahal, Jaipur, Ấn Độ", 26.92394, 75.82674, "Ấn Độ", "Mặt tiền 953 ô cửa sổ nhỏ màu hồng"),
    ("Cổng Thành Gateway of India, Mumbai", 18.92198, 72.83465, "Ấn Độ", "Cổng vòm chào đón bên bờ biển Ả Rập"),
    ("Đền Vàng Harmandir Sahib, Amritsar, Ấn Độ", 31.62000, 74.87648, "Ấn Độ", "Ngôi đền linh thiêng nhất của đạo Sikh giữa hồ"),
    ("Cung điện Mysore, Karnataka, Ấn Độ", 12.30516, 76.65517, "Ấn Độ", "Cung điện hoàng gia lộng lẫy bậc nhất Ấn Độ"),
    ("Pháo đài đá Sigiriya (Đá Sư Tử), Sri Lanka", 7.95703, 80.76026, "Sri Lanka", "Cung điện cổ trên đỉnh khối đá cao 200m"),
    ("Bảo tháp Boudhanath, Kathmandu, Nepal", 27.72150, 85.36200, "Nepal", "Một trong những bảo tháp Phật giáo lớn nhất thế giới"),
    ("Tháp Burj Khalifa, Dubai, UAE", 25.19720, 55.27438, "UAE", "Toà nhà cao nhất thế giới 828m"),
    ("Khách sạn Cánh Buồm Burj Al Arab, Dubai", 25.14119, 55.18525, "UAE", "Khách sạn hình cánh buồm trên đảo nhân tạo"),
    ("Bảo tàng Tương lai (Museum of the Future), Dubai", 25.21920, 55.28190, "UAE", "Toà nhà hình vòng xuyến khắc thư pháp Ả Rập"),
    ("Thánh đường Sheikh Zayed, Abu Dhabi, UAE", 24.41283, 54.47498, "UAE", "Thánh đường cẩm thạch trắng tráng lệ bậc nhất"),
    ("Thành cổ Petra (Al-Khazneh), Jordan", 30.32220, 35.45170, "Jordan", "Thành phố hoa hồng tạc thẳng vào vách núi đá"),
    ("Thành cổ Jerusalem (Bức tường Than Khóc), Israel", 31.77670, 35.23450, "Israel", "Thánh địa lịch sử ba tôn giáo lớn"),
    ("Hagia Sophia, Istanbul, Thổ Nhĩ Kỳ", 41.00858, 28.98018, "Thổ Nhĩ Kỳ", "Kiệt tác kiến trúc Byzantine mái vòm khổng lồ"),
    ("Thánh đường Xanh (Blue Mosque), Istanbul", 41.00541, 28.97681, "Thổ Nhĩ Kỳ", "Thánh đường 6 ngọn tháp phủ gạch Iznik xanh"),
    ("Tháp Galata, Istanbul, Thổ Nhĩ Kỳ", 41.02566, 28.97413, "Thổ Nhĩ Kỳ", "Ngọn tháp đá trung cổ nhìn ra eo biển Bosphorus"),
    ("Thung lũng khinh khí cầu Cappadocia, Thổ Nhĩ Kỳ", 38.64306, 34.82889, "Thổ Nhĩ Kỳ", "Vùng ống khói đá núi lửa kỳ ảo"),
    ("Lâu đài Bông Pamukkale, Thổ Nhĩ Kỳ", 37.92420, 29.12440, "Thổ Nhĩ Kỳ", "Ruộng bậc thang suối khoáng đá vôi trắng xóa"),
    ("Tháp Bayterek, Astana, Kazakhstan", 51.12830, 71.43050, "Kazakhstan", "Tháp trứng vàng biểu tượng thủ đô thảo nguyên"),
    ("Nhà hát Opera và Ba lê Almaty, Kazakhstan", 43.24940, 76.94560, "Kazakhstan", "Công trình văn hoá biểu tượng phía nam Kazakhstan"),
    # --- Mở rộng thêm Landmark Châu Á ---
    ("Sân vận động Quốc gia Tokyo, Nhật Bản", 35.67780, 139.71450, "Nhật Bản", "Sân vận động chính Thế vận hội Tokyo 2020"),
    ("Đền Kamakura (Tượng Đại Phật Kotoku-in), Nhật Bản", 35.31670, 139.53580, "Nhật Bản", "Tượng Phật A Di Đà bằng đồng ngoài trời từ thế kỷ 13"),
    ("Lâu đài Matsumoto (Lâu đài Quạ Đen), Nhật Bản", 36.23860, 137.96890, "Nhật Bản", "Một trong những lâu đài gỗ nguyên bản cổ nhất Nhật Bản"),
    ("Công viên Tưởng niệm Hoà bình Nagasaki, Nhật Bản", 32.77580, 129.86360, "Nhật Bản", "Tượng đài Hoà bình tưởng niệm thảm họa năm 1945"),
    ("Tháp Sapporo TV Tower, Hokkaido, Nhật Bản", 43.06110, 141.35640, "Nhật Bản", "Ngọn tháp biểu tượng tại công viên Odori"),
    ("Tháp Busan Diamond Tower (Công viên Yongdusan)", 35.10080, 129.03250, "Hàn Quốc", "Ngọn tháp ngắm toàn cảnh cảng Busan"),
    ("Sân vận động World Cup Seoul, Hàn Quốc", 37.56830, 126.89720, "Hàn Quốc", "Sân vận động diều truyền thống tổ chức World Cup 2002"),
    ("Cầu Incheon (Incheon Bridge), Hàn Quốc", 37.41390, 126.57190, "Hàn Quốc", "Cầu dây văng vượt biển nối sân bay Incheon"),
    ("Chợ đêm Shilin (Sĩ Lâm), Đài Bắc, Đài Loan", 25.08780, 121.52420, "Đài Loan", "Chợ đêm nổi tiếng và sầm uất bậc nhất Đài Loan"),
    ("Bảo tàng Cố cung Quốc gia, Đài Bắc, Đài Loan", 25.10236, 121.54849, "Đài Loan", "Nơi lưu giữ bộ sưu tập cổ vật Trung Hoa đồ sộ"),
    ("Sân vận động Quốc gia Singapore (National Stadium)", 1.30417, 103.87417, "Singapore", "Sân vận động mái vòm thu mở lớn nhất thế giới"),
    ("Vòng đu quay Singapore Flyer, Singapore", 1.28930, 103.86310, "Singapore", "Bánh xe quan sát khổng lồ bên vịnh Marina"),
    ("Đài tưởng niệm Chiến thắng (Victory Monument), Bangkok", 13.76490, 100.53830, "Thái Lan", "Ngọn tháp trung tâm giao thông thủ đô Bangkok"),
    ("Sân vận động Rajamangala, Bangkok, Thái Lan", 13.75560, 100.62220, "Thái Lan", "Sân vận động quốc gia lớn nhất Thái Lan"),
    ("Tháp Menara Kuala Lumpur (KL Tower), Malaysia", 3.15280, 101.70360, "Malaysia", "Tháp viễn thông trên đồi Bukit Nanas"),
    ("Quảng trường Độc lập (Dataran Merdeka), Kuala Lumpur", 3.14860, 101.69360, "Malaysia", "Cột cờ lịch sử và toà nhà Sultan Abdul Samad"),
    ("Sân vận động Quốc gia Bukit Jalil, Malaysia", 3.05470, 101.69140, "Malaysia", "Sân vận động sức chứa hàng đầu Đông Nam Á"),
    ("Nhà thờ Hồi giáo Istiqlal, Jakarta, Indonesia", -6.17020, 106.83140, "Indonesia", "Thánh đường Hồi giáo lớn nhất Đông Nam Á"),
    ("Sân vận động Gelora Bung Karno, Jakarta", -6.21860, 106.80190, "Indonesia", "Sân vận động biểu tượng thể thao Indonesia"),
    ("Công viên Rizal Park (Luneta), Manila, Philippines", 14.58260, 120.97870, "Philippines", "Đài tưởng niệm anh hùng dân tộc José Rizal"),
    ("Mall of Asia Arena & Vịnh Manila, Philippines", 14.53220, 120.98390, "Philippines", "Tổ hợp giải trí và vòng đu quay bên vịnh Manila"),
    ("Cầu Bosphorus (Cầu Liệt sĩ 15/7), Istanbul", 41.04528, 29.03417, "Thổ Nhĩ Kỳ", "Cây cầu treo vĩ đại nối liền hai châu lục Á và Âu"),
    ("Quảng trường Taksim, Istanbul, Thổ Nhĩ Kỳ", 41.03694, 28.98500, "Thổ Nhĩ Kỳ", "Trái tim hiện đại của thành phố Istanbul"),
    ("Đài tưởng niệm Anıtkabir, Ankara, Thổ Nhĩ Kỳ", 39.92528, 32.83694, "Thổ Nhĩ Kỳ", "Lăng mộ Mustafa Kemal Atatürk trên đồi thủ đô"),
    ("Lăng Humayun, New Delhi, Ấn Độ", 28.59328, 77.25075, "Ấn Độ", "Tiền thân kiến trúc Mughal của đền Taj Mahal"),
    ("Khách sạn Taj Mahal Palace, Mumbai, Ấn Độ", 18.92170, 72.83330, "Ấn Độ", "Khách sạn di sản mái vòm đỏ bên bờ biển Mumbai"),
    # --- Đợt mở rộng lần 2: thêm Landmark Châu Á ---
    ("Sân bay Quốc tế Kansai (Cầu Sky Gate), Osaka", 34.43200, 135.23040, "Nhật Bản", "Sân bay trên đảo nhân tạo nối bằng cầu hai tầng"),
    ("Tháp Kyoto Tower, Nhật Bản", 34.98750, 135.75920, "Nhật Bản", "Ngọn tháp ngọn hải đăng trắng đối diện Ga Kyoto"),
    ("Tòa thị chính Tokyo (TMG Building), Shinjuku", 35.68960, 139.69170, "Nhật Bản", "Toà tháp đôi chính quyền thành phố Tokyo"),
    ("Cầu Rainbow Bridge & Odaiba, Tokyo", 35.63660, 139.76320, "Nhật Bản", "Cây cầu treo trắng nổi tiếng vịnh Tokyo"),
    ("Ga Trung tâm Seoul (Seoul Station), Hàn Quốc", 37.55470, 126.97070, "Hàn Quốc", "Nhà ga gạch đỏ cổ và hiện đại giữa thủ đô Seoul"),
    ("Cung điện Changdeokgung, Seoul, Hàn Quốc", 37.57940, 126.99100, "Hàn Quốc", "Hoàng cung Di sản Thế giới UNESCO tại Seoul"),
    ("Bãi biển Haeundae (LCT Tower), Busan, Hàn Quốc", 35.15870, 129.16040, "Hàn Quốc", "Bãi biển đô thị nổi tiếng nhất Hàn Quốc"),
    ("Cầu Đại Loan Cao Hùng (Pier-2 / Great Harbor Bridge)", 22.61940, 120.28140, "Đài Loan", "Cây cầu xoay trắng hiện đại tại cảng Cao Hùng"),
    ("Phố đi bộ Bến Thượng Hải / Đường Nam Kinh, Đài Bắc Ximending", 25.04220, 121.50670, "Đài Loan", "Khu phố mua sắm ánh đèn sầm uất Tây Môn Đinh"),
    ("Cảng Clarke Quay, Singapore", 1.29060, 103.84650, "Singapore", "Khu phố nhà kho đầy màu sắc bên sông Singapore"),
    ("Chùa Phật Nha (Buddha Tooth Relic Temple), Chinatown, Singapore", 1.28150, 103.84420, "Singapore", "Ngôi chùa đỏ lộng lẫy trung tâm khu Chinatown"),
    ("Đài Dân chủ (Democracy Monument), Bangkok, Thái Lan", 13.75670, 100.50170, "Thái Lan", "Tượng đài giữa bùng binh đại lộ Ratchadamnoen"),
    ("Chùa Phật Nằm Wat Pho, Bangkok, Thái Lan", 13.74650, 100.49330, "Thái Lan", "Ngôi chùa cổ nổi tiếng bên cạnh Hoàng cung Thái Lan"),
    ("Quảng trường Putra Mosque & Cầu Seri Wawasan, Putrajaya", 2.93170, 101.68500, "Malaysia", "Cây cầu dây văng hình cánh buồm tại thủ đô hành chính"),
    ("Thánh đường Al-Azhar & Cung điện Hoàng gia Amman, Jordan", 31.94970, 35.93280, "Jordan", "Thánh đường mái vòm xanh nổi bật trung tâm Amman"),
    ("Cung điện Dolmabahçe, Istanbul, Thổ Nhĩ Kỳ", 41.03917, 29.00056, "Thổ Nhĩ Kỳ", "Cung điện Ottoman bên bờ eo biển Bosphorus"),
    ("Quảng trường Độc lập (Mustaqillik), Tashkent, Uzbekistan", 41.31640, 69.26830, "Uzbekistan", "Quảng trường trung tâm thủ đô Uzbekistan"),
]

EUROPE_LANDMARKS: list[tuple[str, float, float, str, str]] = [
    # Pháp
    ("Tháp Eiffel, Paris, Pháp", 48.85837, 2.29448, "Pháp", "Biểu tượng thép nổi tiếng nhất nước Pháp"),
    ("Bảo tàng Louvre (Kim tự tháp kính), Paris", 48.86061, 2.33764, "Pháp", "Bảo tàng nghệ thuật lớn nhất thế giới"),
    ("Khải Hoàn Môn (Arc de Triomphe), Paris", 48.87379, 2.29503, "Pháp", "Đài tưởng niệm tại đại lộ Champs-Élysées"),
    ("Nhà thờ Đức Bà Paris, Pháp", 48.85297, 2.34990, "Pháp", "Kiệt tác kiến trúc Gothic trên đảo Île de la Cité"),
    ("Vương cung thánh đường Sacré-Cœur, Montmartre, Paris", 48.88670, 2.34310, "Pháp", "Nhà thờ trắng trên đồi cao nhất Paris"),
    ("Cung điện Versailles, Pháp", 48.80486, 2.12036, "Pháp", "Hoàng cung lộng lẫy của Vua Mặt Trời Louis XIV"),
    ("Tu viện đảo Mont-Saint-Michel, Normandy, Pháp", 48.63606, -1.51146, "Pháp", "Lâu đài tu viện nổi giữa biển khi thủy triều lên"),
    ("Cầu máng nước La Mã Pont du Gard, Pháp", 43.94750, 4.53500, "Pháp", "Cầu dẫn nước 3 tầng cổ đại thời La Mã"),
    ("Đại lộ Promenade des Anglais, Nice, Pháp", 43.69470, 7.26550, "Pháp", "Đường dạo biển trứ danh vùng Riviera Pháp"),
    # Ý & Vatican
    ("Đấu trường La Mã Colosseum, Rome, Ý", 41.89021, 12.49223, "Ý", "Đấu trường cổ đại vĩ đại nhất đế chế La Mã"),
    ("Đài phun nước Trevi, Rome, Ý", 41.90093, 12.48331, "Ý", "Đài phun nước Baroque nổi tiếng ném đồng xu ước nguyện"),
    ("Đền Pantheon, Rome, Ý", 41.89861, 12.47687, "Ý", "Ngôi đền La Mã với mái vòm bê tông gần 2.000 năm"),
    ("Quảng trường Thánh Phêrô, Vatican", 41.90224, 12.45675, "Vatican", "Trung tâm Tòa Thánh và Vương cung thánh đường lớn nhất thế giới"),
    ("Tháp nghiêng Pisa, Ý", 43.72295, 10.39660, "Ý", "Tháp chuông đá cẩm thạch nghiêng nổi tiếng vùng Tuscany"),
    ("Nhà thờ chính tòa Florence (Duomo), Ý", 43.77314, 11.25596, "Ý", "Mái vòm gạch đỏ Phục hưng của Brunelleschi"),
    ("Cầu Ponte Vecchio, Florence, Ý", 43.76792, 11.25314, "Ý", "Cây cầu cổ đầy cửa hàng kim hoàn bắc qua sông Arno"),
    ("Quảng trường San Marco, Venice, Ý", 45.43417, 12.33889, "Ý", "Quảng trường trung tâm thành phố kênh đào Venice"),
    ("Cầu Rialto, Venice, Ý", 45.43798, 12.33590, "Ý", "Cây cầu đá cổ kính bắc qua Kênh Lớn Grand Canal"),
    ("Nhà thờ Duomo di Milano, Milan, Ý", 45.46421, 9.19138, "Ý", "Nhà thờ Gothic đá cẩm thạch trắng với hàng nghìn ngọn tháp"),
    ("Làng chài Positano, Bờ biển Amalfi, Ý", 40.62806, 14.48500, "Ý", "Ngôi làng rực rỡ bám trên vách đá Địa Trung Hải"),
    # Anh & Ireland
    ("Tháp đồng hồ Big Ben & Quốc hội Anh, London", 51.50085, -0.12195, "Anh", "Góc nhìn từ Cầu Westminster sang Tháp Elizabeth bên sông Thames"),
    ("Cầu Tháp London (Tower Bridge), Anh", 51.50546, -0.07536, "Anh", "Cây cầu cất đôi tháp xanh trắng biểu tượng London"),
    ("Cung điện Buckingham, London, Anh", 51.50136, -0.14189, "Anh", "Nơi ở chính thức của Hoàng gia Anh"),
    ("Vòng đu quay London Eye, Anh", 51.50332, -0.11954, "Anh", "Bánh xe quan sát khổng lồ bên sông Thames"),
    ("Tháp London (Tower of London), Anh", 51.50811, -0.07595, "Anh", "Pháo đài hoàng gia lưu giữ vương miện Anh"),
    ("Bãi đá cổ Stonehenge, Wiltshire, Anh", 51.17888, -1.82622, "Anh", "Vòng tròn đá tiền sử bí ẩn hơn 4.000 năm tuổi"),
    ("Lâu đài Edinburgh, Scotland, Anh", 55.94859, -3.19991, "Anh", "Pháo đài trên đỉnh núi đá lửa tắt giữa thủ đô Scotland"),
    ("Ghềnh đá Giant's Causeway, Bắc Ireland", 55.24081, -6.51156, "Anh", "Hàng chục nghìn cột đá bazan lục giác ven biển"),
    ("Vách đá Cliffs of Moher, Ireland", 52.97154, -9.43088, "Ireland", "Bức tường đá dựng đứng cao 214m hướng Đại Tây Dương"),
    ("Đại học Trinity College, Dublin, Ireland", 53.34379, -6.25457, "Ireland", "Ngôi trường cổ danh giá nhất Ireland"),
    # Tây Ban Nha & Bồ Đào Nha
    ("Nhà thờ Sagrada Família, Barcelona, Tây Ban Nha", 41.40363, 2.17436, "Tây Ban Nha", "Kiệt tác dang dở hơn 140 năm của Antoni Gaudí"),
    ("Công viên Park Güell, Barcelona, Tây Ban Nha", 41.41449, 2.15269, "Tây Ban Nha", "Công viên gạch gốm sắc màu nhìn ra Barcelona"),
    ("Cung điện Hoàng gia Madrid, Tây Ban Nha", 40.41796, -3.71431, "Tây Ban Nha", "Cung điện hoàng gia lớn nhất Tây Âu"),
    ("Quảng trường Plaza Mayor, Madrid", 40.41551, -3.70740, "Tây Ban Nha", "Quảng trường cổ lát đá bao quanh bởi kiến trúc đỏ"),
    ("Cung điện Alhambra, Granada, Tây Ban Nha", 37.17608, -3.58814, "Tây Ban Nha", "Pháo đài và cung điện nghệ thuật Moorish đỉnh cao"),
    ("Quảng trường Plaza de España, Seville", 37.37722, -5.98694, "Tây Ban Nha", "Quảng trường bán nguyệt tuyệt mỹ xứ Andalusia"),
    ("Bảo tàng Guggenheim Bilbao, Tây Ban Nha", 43.26867, -2.93400, "Tây Ban Nha", "Kiến trúc titan uốn lượn của Frank Gehry"),
    ("Tháp Belém, Lisbon, Bồ Đào Nha", 38.69158, -9.21598, "Bồ Đào Nha", "Ngọn tháp phòng thủ kỷ nguyên Thám hiểm hàng hải"),
    ("Cung điện Pena, Sintra, Bồ Đào Nha", 38.78759, -9.39061, "Bồ Đào Nha", "Lâu đài Lãng mạn rực rỡ sắc vàng đỏ trên đỉnh núi"),
    ("Cầu Dom Luís I, Porto, Bồ Đào Nha", 41.13997, -8.60942, "Bồ Đào Nha", "Cầu vòm sắt 2 tầng bắc qua sông Douro"),
    # Đức, Áo, Thụy Sĩ, Hà Lan, Bỉ
    ("Cổng Brandenburg, Berlin, Đức", 52.51627, 13.37770, "Đức", "Khải hoàn môn biểu tượng thống nhất nước Đức"),
    ("Nhà Quốc hội Reichstag, Berlin, Đức", 52.51862, 13.37619, "Đức", "Mái vòm kính biểu tượng nền dân chủ Đức"),
    ("Nhà thờ chính tòa Köln (Cologne Cathedral), Đức", 50.94128, 6.95828, "Đức", "Nhà thờ Gothic hai tháp nhọn bên sông Rhine"),
    ("Lâu đài Neuschwanstein, Bavaria, Đức", 47.55757, 10.74980, "Đức", "Lâu đài cổ tích trên dãy Alps nguồn cảm hứng cho Disney"),
    ("Quảng trường Marienplatz, Munich, Đức", 48.13715, 11.57549, "Đức", "Tòa thị chính mới kiểu Neo-Gothic trung tâm Bavaria"),
    ("Cung điện Schönbrunn, Vienna, Áo", 48.18581, 16.31277, "Áo", "Cung điện mùa hè hoàng gia Habsburg"),
    ("Ngôi làng cổ tích Hallstatt, Áo", 47.56223, 13.64926, "Áo", "Ngôi làng cổ bên hồ núi Alps"),
    ("Cầu gỗ Kapellbrücke, Lucerne, Thụy Sĩ", 47.05161, 8.30750, "Thụy Sĩ", "Cầu gỗ có mái che cổ nhất Châu Âu"),
    ("Đỉnh Matterhorn (Zermatt), Thụy Sĩ", 46.02071, 7.74912, "Thụy Sĩ", "Ngọn núi kim tự tháp biểu tượng dãy Alps"),
    ("Đài phun nước Jet d'Eau, Geneva, Thụy Sĩ", 46.20739, 6.15590, "Thụy Sĩ", "Cột nước cao 140m trên hồ Geneva"),
    ("Bảo tàng Rijksmuseum, Amsterdam, Hà Lan", 52.36000, 4.88522, "Hà Lan", "Bảo tàng quốc gia lưu giữ kiệt tác Rembrandt"),
    ("Cối xay gió Kinderdijk, Hà Lan", 51.88326, 4.64271, "Hà Lan", "Hệ thống 19 cối xay gió cổ Di sản UNESCO"),
    ("Quảng trường Grand-Place, Brussels, Bỉ", 50.84673, 4.35241, "Bỉ", "Quảng trường trung cổ dát vàng lộng lẫy"),
    ("Công trình Atomium, Brussels, Bỉ", 50.89494, 4.34155, "Bỉ", "Mô hình tinh thể sắt phóng đại 165 tỷ lần"),
    # Bắc Âu, Đông Âu & Địa Trung Hải
    ("Kênh đào Nyhavn, Copenhagen, Đan Mạch", 55.67978, 12.59066, "Đan Mạch", "Dãy nhà đầy màu sắc bên cảng lịch sử"),
    ("Tượng Nàng Tiên Cá, Copenhagen, Đan Mạch", 55.69286, 12.59928, "Đan Mạch", "Bức tượng đồng lấy cảm hứng từ truyện cổ Andersen"),
    ("Cung điện Hoàng gia Stockholm, Thụy Điển", 59.32682, 18.07172, "Thụy Điển", "Cung điện bên khu phố cổ Gamla Stan"),
    ("Công viên điêu khắc Vigeland, Oslo, Na Uy", 59.92703, 10.70085, "Na Uy", "Hơn 200 tác phẩm tượng đá và đồng ngoài trời"),
    ("Nhà thờ Trắng Helsinki, Phần Lan", 60.17039, 24.95220, "Phần Lan", "Nhà thờ chính tòa tân cổ điển bên Quảng trường Thượng viện"),
    ("Thánh đường Hallgrímskirkja, Reykjavik, Iceland", 64.14170, -21.92660, "Iceland", "Kiến trúc lấy cảm hứng từ cột đá bazan núi lửa"),
    ("Đền Parthenon (Acropolis), Athens, Hy Lạp", 37.97153, 23.72575, "Hy Lạp", "Kiệt tác đền đài Hy Lạp cổ đại trên đồi thiêng"),
    ("Ngôi làng trắng Oia, Đảo Santorini, Hy Lạp", 36.46180, 25.37530, "Hy Lạp", "Mái vòm xanh lam và nhà trắng bên miệng núi lửa biển Aegean"),
    ("Tu viện trên núi đá Meteora, Hy Lạp", 39.72170, 21.63060, "Hy Lạp", "Các tu viện treo lơ lửng trên cột đá cao vút"),
    ("Cầu Charles (Karlův most), Praha, Séc", 50.08648, 14.41144, "Séc", "Cây cầu đá trung cổ với 30 tượng thánh bắc qua sông Vltava"),
    ("Tòa nhà Quốc hội Hungary, Budapest", 47.50712, 19.04567, "Hungary", "Kiến trúc Neo-Gothic tráng lệ bên bờ sông Danube"),
    ("Pháo đài Fisherman's Bastion, Budapest", 47.50219, 19.03478, "Hungary", "Đài vọng cảnh 7 ngọn tháp trắng nhìn toàn cảnh Danube"),
    ("Lâu đài Wawel & Quảng trường Chính, Kraków, Ba Lan", 50.05405, 19.93542, "Ba Lan", "Cố đô hoàng gia nghìn năm của Ba Lan"),
    ("Lâu đài Bran (Lâu đài Dracula), Romania", 45.51490, 25.36716, "Romania", "Pháo đài trên đỉnh đồi vùng Transylvania"),
    ("Phố cổ Dubrovnik (Thành tường đá), Croatia", 42.64120, 18.10860, "Croatia", "Viên ngọc biển Adriatic tường thành đá cổ"),
    ("Hồ Bled & Đảo Nhà thờ, Slovenia", 46.36360, 14.09380, "Slovenia", "Hồ băng hà ngọc bích với nhà thờ nhỏ giữa hồ"),
    ("Quảng trường Đỏ & Nhà thờ Thánh Basil, Moscow", 55.75252, 37.62309, "Nga", "Mái vòm củ hành rực rỡ sắc màu trung tâm nước Nga"),
    ("Cung điện Mùa Đông (Hermitage), Saint Petersburg", 59.93983, 30.31456, "Nga", "Bảo tàng nghệ thuật hoàng gia Nga bên sông Neva"),
    # --- Mở rộng thêm Landmark Châu Âu ---
    ("Sân vận động Parc des Princes, Paris, Pháp", 48.84140, 2.25300, "Pháp", "Thánh địa bóng đá của CLB Paris Saint-Germain"),
    ("Nhà hát Palais Garnier (Opéra Paris), Pháp", 48.87190, 2.33160, "Pháp", "Nhà hát Opera lộng lẫy bậc nhất thế giới"),
    ("Khải Hoàn Môn La Défense (Grande Arche), Paris", 48.89260, 2.23610, "Pháp", "Khải Hoàn Môn hiện đại khu tài chính Paris"),
    ("Nhà thờ Sacré-Cœur & Basilica Notre-Dame de Fourvière, Lyon", 45.76220, 4.82250, "Pháp", "Thánh đường trên đồi nhìn toàn cảnh thành phố Lyon"),
    ("Sân vận động Wembley, London, Anh", 51.55602, -0.27952, "Anh", "Sân vận động mái vòm biểu tượng bóng đá Anh"),
    ("Sân vận động Old Trafford, Manchester, Anh", 53.46306, -2.29139, "Anh", "Nhà hát của những giấc mơ - Manchester United"),
    ("Sân vận động Anfield, Liverpool, Anh", 53.43083, -2.96083, "Anh", "Sân nhà huyền thoại của CLB Liverpool"),
    ("Quảng trường Trafalgar Square, London, Anh", 51.50804, -0.12807, "Anh", "Cột Nelson và Phòng trưng bày Quốc gia London"),
    ("Nhà thờ Thánh Paul (St Paul's Cathedral), London", 51.51385, -0.09835, "Anh", "Mái vòm biểu tượng bên bờ sông Thames"),
    ("Đại học Oxford (Radcliffe Camera), Anh", 51.75340, -1.25400, "Anh", "Thư viện hình tròn cổ kính giữa lòng Oxford"),
    ("Đại học Cambridge (King's College Chapel), Anh", 52.20480, 0.11650, "Anh", "Ngôi trường đại học danh giá bên dòng sông Cam"),
    ("Sân vận động Santiago Bernabéu, Madrid, Tây Ban Nha", 40.45305, -3.68834, "Tây Ban Nha", "Thánh địa của CLB Hoàng gia Real Madrid"),
    ("Sân vận động Camp Nou, Barcelona, Tây Ban Nha", 41.38090, 2.12282, "Tây Ban Nha", "Sân vận động lớn nhất Châu Âu của FC Barcelona"),
    ("Khải Hoàn Môn Arc de Triomf, Barcelona", 41.39100, 2.18060, "Tây Ban Nha", "Cổng vòm gạch đỏ dẫn vào công viên Ciutadella"),
    ("Sân vận động San Siro, Milan, Ý", 45.47810, 9.12400, "Ý", "Ngôi nhà chung của AC Milan và Inter Milan"),
    ("Sân vận động Allianz Stadium, Turin, Ý", 45.10960, 7.64130, "Ý", "Sân nhà của Juventus tại vùng Piedmont"),
    ("Đấu trường Verona Arena, Verona, Ý", 45.43900, 10.99440, "Ý", "Đấu trường La Mã cổ đại hơn 2.000 năm tuổi"),
    ("Sân vận động Allianz Arena, Munich, Đức", 48.21880, 11.62470, "Đức", "Sân vận động phát sáng biểu tượng Bayern Munich"),
    ("Sân vận động Signal Iduna Park, Dortmund, Đức", 51.49260, 7.45190, "Đức", "Khán đài Bức tường Vàng trứ danh nước Đức"),
    ("Tháp truyền hình Berliner Fernsehturm, Berlin", 52.52082, 13.40942, "Đức", "Ngọn tháp cao nhất nước Đức tại Alexanderplatz"),
    ("Nhà hát Elbphilharmonie, Hamburg, Đức", 53.54130, 9.98410, "Đức", "Nhà hát kính sóng nước trên cảng Hamburg"),
    ("Sân vận động Johan Cruyff Arena, Amsterdam, Hà Lan", 52.31437, 4.94196, "Hà Lan", "Sân vận động hiện đại của Ajax Amsterdam"),
    ("Cung điện Hòa bình (Peace Palace), The Hague, Hà Lan", 52.08660, 4.29560, "Hà Lan", "Trụ sở Tòa án Công lý Quốc tế Liên Hợp Quốc"),
    ("Tháp Belvedere & Quảng trường Venceslas, Praha, Séc", 50.08110, 14.42780, "Séc", "Đại lộ lịch sử trung tâm thủ đô Praha"),
    ("Cung điện Văn hoá và Khoa học, Warsaw, Ba Lan", 52.23184, 21.00672, "Ba Lan", "Toà nhà tháp đồng hồ biểu tượng thủ đô Ba Lan"),
    ("Đài tưởng niệm Chiến thắng (Siegessäule), Berlin", 52.51454, 13.35011, "Đức", "Cột thiên thần vàng giữa công viên Tiergarten"),
    ("Cầu 25 tháng 4 (Ponte 25 de Abril), Lisbon", 38.68960, -9.17720, "Bồ Đào Nha", "Cây cầu treo đỏ giống Cầu Cổng Vàng tại Bồ Đào Nha"),
    ("Sân vận động Estádio da Luz, Lisbon, Bồ Đào Nha", 38.75270, -9.18470, "Bồ Đào Nha", "Thánh địa Ánh sáng của CLB Benfica"),
    ("Đấu trường Pula Arena, Croatia", 44.87320, 13.85010, "Croatia", "Đấu trường La Mã bảo tồn nguyên vẹn bên biển Adriatic"),
    ("Nhà thờ Chính tòa Saint Sava, Belgrade, Serbia", 44.79806, 20.46861, "Serbia", "Một trong những nhà thờ Chính thống giáo lớn nhất thế giới"),
    # --- Đợt mở rộng lần 2: thêm Landmark Châu Âu ---
    ("Trung tâm Pompidou, Paris, Pháp", 48.86064, 2.35224, "Pháp", "Bảo tàng nghệ thuật với hệ thống đường ống sắc màu bên ngoài"),
    ("Quảng trường Place de la Concorde, Paris, Pháp", 48.86563, 2.32124, "Pháp", "Quảng trường rộng lớn nhất Paris với cột đá Ai Cập"),
    ("Quảng trường Piccadilly Circus, London, Anh", 51.50986, -0.13426, "Anh", "Ngã tư bảng quảng cáo LED trứ danh trung tâm West End"),
    ("Sân vận động Stamford Bridge (Chelsea), London", 51.48167, -0.19111, "Anh", "Sân nhà của CLB bóng đá Chelsea tại Tây London"),
    ("Sân vận động Emirates (Arsenal), London, Anh", 51.55489, -0.10844, "Anh", "Sân vận động hiện đại của CLB Arsenal"),
    ("Cầu Millennium Bridge, London, Anh", 51.50950, -0.09850, "Anh", "Cầu đi bộ thép nối nhà thờ St Paul và Tate Modern"),
    ("Bức tường Milan (Galleria Vittorio Emanuele II), Milan", 45.46583, 9.18972, "Ý", "Mái vòm kính trung tâm thương mại cổ kính nhất thế giới"),
    ("Quảng trường Piazza Navona, Rome, Ý", 41.89916, 12.47307, "Ý", "Quảng trường hình bầu dục với Đài phun nước Bốn Dòng Sông"),
    ("Sân vận động Stadio Olimpico, Rome, Ý", 41.93407, 12.45472, "Ý", "Sân vận động chính của thành phố Rome"),
    ("Bức tường Berlin (East Side Gallery), Berlin, Đức", 52.50500, 13.43970, "Đức", "Đoạn tường lịch sử dài nhất còn sót lại dọc sông Spree"),
    ("Cổng Isartor & Tháp Olympiaturm, Munich, Đức", 48.17450, 11.55360, "Đức", "Công viên Olympic Munich và tháp truyền hình"),
    ("Quảng trường Dam Square (Cung điện Hoàng gia Amsterdam)", 52.37306, 4.89250, "Hà Lan", "Quảng trường trung tâm lịch sử thủ đô Amsterdam"),
    ("Tòa nhà Euromast & Cảng Rotterdam, Hà Lan", 51.90540, 4.46660, "Hà Lan", "Tháp quan sát biểu tượng của thành phố cảng Rotterdam"),
    ("Quảng trường Puerta del Sol, Madrid, Tây Ban Nha", 40.41694, -3.70361, "Tây Ban Nha", "Điểm Km0 của toàn bộ mạng lưới đường bộ Tây Ban Nha"),
    ("Đài tưởng niệm Columbus (Mirador de Colom), Barcelona", 41.37583, 2.17778, "Tây Ban Nha", "Cột đài hướng ra bến cảng cuối đại lộ La Rambla"),
    ("Quảng trường Rossio (Praça Dom Pedro IV), Lisbon", 38.71389, -9.13944, "Bồ Đào Nha", "Quảng trường gạch lượn sóng đen trắng giữa lòng Lisbon"),
    ("Nhà hát Opera Quốc gia Oslo, Na Uy", 59.90750, 10.75310, "Na Uy", "Toà nhà đá cẩm thạch trắng nổi lên từ vịnh Oslo như tảng băng"),
    ("Bảo tàng Vasa & Đảo Djurgården, Stockholm, Thụy Điển", 59.32800, 18.09140, "Thụy Điển", "Bảo tàng lưu giữ chiến hạm thế kỷ 17 gần như nguyên vẹn"),
    ("Lâu đài Christiansborg (Quốc hội Đan Mạch), Copenhagen", 55.67611, 12.58000, "Đan Mạch", "Cung điện nằm trên đảo nhỏ Slotsholmen"),
    ("Quảng trường Syntagma (Quốc hội Hy Lạp), Athens", 37.97556, 23.73472, "Hy Lạp", "Quảng trường Hiến pháp trung tâm thủ đô Athens"),
    ("Quảng trường Chính (Rynek Główny), Kraków, Ba Lan", 50.06167, 19.93722, "Ba Lan", "Quảng trường trung cổ lớn bậc nhất Châu Âu"),
    ("Tòa nhà Nhảy múa (Dancing House), Praha, Séc", 50.07540, 14.41410, "Séc", "Kiến trúc uốn lượn nổi tiếng của Frank Gehry bên sông Vltava"),
    ("Cầu Xích Széchenyi (Chain Bridge), Budapest, Hungary", 47.49889, 19.04361, "Hungary", "Cây cầu đá treo đầu tiên nối Buda và Pest"),
]

NORTH_AMERICA_LANDMARKS: list[tuple[str, float, float, str, str]] = [
    # Hoa Kỳ
    ("Tượng Nữ thần Tự do, New York, Mỹ", 40.68925, -74.04450, "Mỹ", "Biểu tượng tự do tại cảng New York"),
    ("Quảng trường Thời đại (Times Square), New York", 40.75800, -73.98554, "Mỹ", "Giao lộ ánh sáng rực rỡ nhất hành tinh"),
    ("Tòa nhà Empire State, New York", 40.74844, -73.98566, "Mỹ", "Toà nhà Art Deco huyền thoại giữa Manhattan"),
    ("Cầu Brooklyn, New York", 40.70609, -73.99686, "Mỹ", "Cây cầu treo đá và cáp thép lâu đời nối Manhattan - Brooklyn"),
    ("Công viên Trung tâm Central Park, New York", 40.78286, -73.96536, "Mỹ", "Ốc đảo xanh khổng lồ giữa rừng cao ốc Manhattan"),
    ("Nhà Trắng (The White House), Washington D.C.", 38.89768, -77.03653, "Mỹ", "Nơi ở và làm việc của Tổng thống Hoa Kỳ"),
    ("Điện Capitol Hoa Kỳ, Washington D.C.", 38.88994, -77.00905, "Mỹ", "Trụ sở Quốc hội Mỹ với mái vòm trắng đặc trưng"),
    ("Đài tưởng niệm Lincoln, Washington D.C.", 38.88927, -77.05018, "Mỹ", "Đền đá cẩm thạch nhìn ra hồ phản chiếu"),
    ("Cầu Cổng Vàng (Golden Gate Bridge), San Francisco", 37.81993, -122.47826, "Mỹ", "Cây cầu treo màu đỏ cam vắt qua eo biển Golden Gate"),
    ("Đường dốc hoa Lombard Street, San Francisco", 37.80200, -122.41874, "Mỹ", "Con phố ngoằn ngoèo 8 khúc cua nổi tiếng nhất thế giới"),
    ("Bảng hiệu Hollywood, Los Angeles", 34.13412, -118.32155, "Mỹ", "Chữ trắng khổng lồ trên sườn núi Lee"),
    ("Bến tàu Santa Monica Pier, California", 34.00924, -118.49760, "Mỹ", "Điểm kết thúc tuyến đường huyền thoại Route 66"),
    ("Tháp Space Needle, Seattle, Mỹ", 47.62051, -122.34930, "Mỹ", "Tháp đĩa bay biểu tượng vùng Tây Bắc Thái Bình Dương"),
    ("Hạt Đậu Cloud Gate (The Bean), Chicago", 41.88266, -87.62330, "Mỹ", "Tác phẩm gương thép không gỉ tại Công viên Thiên niên kỷ"),
    ("Cổng vòm Gateway Arch, St. Louis", 38.62469, -90.18478, "Mỹ", "Vòm thép không gỉ cao 192m bên sông Mississippi"),
    ("Khu phố Pháp French Quarter, New Orleans", 29.95844, -90.06441, "Mỹ", "Ban công sắt rèn và quê hương nhạc Jazz"),
    ("Hẻm núi Grand Canyon, Arizona, Mỹ", 36.05444, -112.14011, "Mỹ", "Kỳ quan địa chất vĩ đại do sông Colorado bào mòn"),
    ("Thung lũng Monument Valley, Utah - Arizona", 36.99800, -110.09800, "Mỹ", "Những khối đá sa thạch đỏ bối cảnh phim Viễn Tây"),
    ("Vườn quốc gia Yellowstone (Old Faithful), Wyoming", 44.46048, -110.82814, "Mỹ", "Mạch nước phun và hồ khoáng đa sắc"),
    ("Vườn quốc gia Yosemite (Half Dome), California", 37.74590, -119.53320, "Mỹ", "Vách đá granite và thác nước kỳ vĩ"),
    ("Núi Rushmore, South Dakota, Mỹ", 43.87910, -103.45907, "Mỹ", "Tượng 4 vị Tổng thống Hoa Kỳ tạc trên vách núi"),
    ("Đập thủy điện Hoover Dam, Nevada - Arizona", 36.01606, -114.73773, "Mỹ", "Đập bê tông vòm khổng lồ trên hẻm núi Đen"),
    ("Đại lộ ánh sáng Las Vegas Strip, Nevada", 36.11465, -115.17281, "Mỹ", "Thủ phủ giải trí sáng rực giữa sa mạc Mojave"),
    ("Cầu Seven Mile Bridge, Florida Keys", 24.70000, -81.14800, "Mỹ", "Cây cầu vượt biển tuyệt đẹp nối chuỗi đảo Florida"),
    ("Bãi biển Waikiki & Núi Diamond Head, Hawaii", 21.27670, -157.82670, "Mỹ", "Thiên đường đảo nhiệt đới giữa Thái Bình Dương"),
    # Canada
    ("Tháp CN Tower, Toronto, Canada", 43.64257, -79.38706, "Canada", "Tháp truyền thông biểu tượng bên hồ Ontario"),
    ("Thác Niagara (Horseshoe Falls), Canada - Mỹ", 43.07990, -79.07470, "Canada", "Thác nước hùng vĩ bậc nhất Bắc Mỹ"),
    ("Lâu đài Château Frontenac, Québec, Canada", 46.81209, -71.20520, "Canada", "Khách sạn lâu đài biểu tượng khu phố cổ nói tiếng Pháp"),
    ("Đồi Quốc hội Parliament Hill, Ottawa, Canada", 45.42359, -75.70093, "Canada", "Quần thể kiến trúc Gothic bên sông Ottawa"),
    ("Hồ Louise, Vườn quốc gia Banff, Canada", 51.41670, -116.21670, "Canada", "Hồ băng hà màu ngọc lam giữa dãy núi Rockies"),
    ("Công viên Stanley Park, Vancouver, Canada", 49.30430, -123.14430, "Canada", "Công viên bán đảo rừng xanh bên bờ Thái Bình Dương"),
    # Mexico, Trung Mỹ & Caribe
    ("Kim tự tháp Chichén Itzá (El Castillo), Mexico", 20.68428, -88.56778, "Mexico", "Thành phố cổ đại văn minh Maya kỳ quan thế giới mới"),
    ("Quần thể kim tự tháp Teotihuacán, Mexico", 19.69227, -98.84350, "Mexico", "Kim tự tháp Mặt Trời và Mặt Trăng cổ đại"),
    ("Quảng trường Zócalo & Cung điện Mỹ thuật, Mexico City", 19.43261, -99.13321, "Mexico", "Trái tim lịch sử thủ đô Mexico"),
    ("Khu di tích cổ bên biển Tulum, Mexico", 20.21490, -87.42930, "Mexico", "Thành cổ Maya nhìn thẳng ra biển Caribe ngọc bích"),
    ("Quảng trường Nhà thờ Chính toà & Malecón, La Habana", 23.14140, -82.35190, "Cuba", "Phố cổ xe hơi cổ điển và bức tường biển La Habana"),
    ("Pháo đài El Morro, San Juan, Puerto Rico", 18.47100, -66.12350, "Puerto Rico", "Thành lũy đá thế kỷ 16 canh giữ cửa vịnh Caribe"),
    ("Kênh đào Panama (Âu tàu Miraflores)", 8.99720, -79.59140, "Panama", "Tuyến đường thủy kỳ vĩ nối Thái Bình Dương và Đại Tây Dương"),
    # --- Mở rộng thêm Landmark Bắc Mỹ ---
    ("Nhà ga Grand Central Terminal, New York, Mỹ", 40.75273, -73.97723, "Mỹ", "Nhà ga lịch sử trần sao hoàng đạo tại Midtown Manhattan"),
    ("Tòa nhà Flatiron Building, New York, Mỹ", 40.74106, -73.98970, "Mỹ", "Toà nhà hình bàn là tam giác nổi tiếng Đại lộ 5"),
    ("Tòa nhà Willis Tower (Sears Tower), Chicago, Mỹ", 41.87888, -87.63591, "Mỹ", "Toà nhà biểu tượng với ban công kính Skydeck"),
    ("Cầu Fenway Park, Boston, Mỹ", 42.34668, -71.09722, "Mỹ", "Sân bóng chày lâu đời nhất nước Mỹ"),
    ("Đại học Harvard (Harvard Yard), Cambridge, Mỹ", 42.37444, -71.11694, "Mỹ", "Khuôn viên trường đại học lâu đời nhất Hoa Kỳ"),
    ("Đại học Stanford (Hoover Tower), California, Mỹ", 37.42760, -122.16700, "Mỹ", "Ngọn tháp biểu tượng giữa thung lũng Silicon"),
    ("Trụ sở Apple Park Visitor Center, Cupertino, Mỹ", 37.33280, -122.00540, "Mỹ", "Vòng tròn kính phi thuyền Apple Park tại California"),
    ("Cầu Bixby Creek Bridge, Big Sur, California", 36.37140, -121.90170, "Mỹ", "Cây cầu vòm bê tông trên cung đường ven biển đẹp nhất Mỹ"),
    ("Đài quan sát Griffith Observatory, Los Angeles", 34.11843, -118.30039, "Mỹ", "Đài thiên văn nhìn ra biển hiệu Hollywood"),
    ("Sân vận động Rose Bowl, Pasadena, California", 34.16133, -118.16765, "Mỹ", "Sân vận động lịch sử tổ chức chung kết World Cup 1994"),
    ("Nhà hát Walt Disney Concert Hall, Los Angeles", 34.05530, -118.24980, "Mỹ", "Công trình thép không gỉ uốn lượn của Frank Gehry"),
    ("Tháp Reunion Tower, Dallas, Texas, Mỹ", 32.77550, -96.80890, "Mỹ", "Quả cầu ánh sáng biểu tượng thành phố Dallas"),
    ("Đài tưởng niệm Alamo, San Antonio, Texas, Mỹ", 29.42597, -98.48614, "Mỹ", "Pháo đài lịch sử biểu tượng bang Texas"),
    ("Tháp Thiên thần (Ángel de la Independencia), Mexico City", 19.42702, -99.16766, "Mexico", "Cột đài tưởng niệm Độc lập trên đại lộ Reforma"),
    ("Sân vận động Estadio Azteca, Mexico City", 19.30286, -99.15053, "Mexico", "Sân vận động huyền thoại chứng kiến Pelé và Maradona vô địch"),
    ("Sân vận động BC Place, Vancouver, Canada", 49.27675, -123.11199, "Canada", "Sân vận động mái vòm cáp treo bên vịnh False Creek"),
    ("Đài Olympic Montreal (Olympic Stadium), Canada", 45.55790, -73.55150, "Canada", "Ngọn tháp nghiêng cao nhất thế giới tại Montréal"),
]

SOUTH_AMERICA_LANDMARKS: list[tuple[str, float, float, str, str]] = [
    ("Tượng Chúa Cứu Thế (Christ the Redeemer), Rio de Janeiro", -22.95192, -43.21049, "Brazil", "Bức tượng Art Deco trên đỉnh núi Corcovado"),
    ("Núi Đường (Sugarloaf Mountain), Rio de Janeiro", -22.94930, -43.15460, "Brazil", "Đỉnh núi đá granite nhô ra vịnh Guanabara"),
    ("Bãi biển Copacabana, Rio de Janeiro, Brazil", -22.97196, -43.18254, "Brazil", "Lát gạch lượn sóng đen trắng trứ danh thế giới"),
    ("Nhà thờ Chính toà Brasília, Brazil", -15.79835, -47.87556, "Brazil", "Kiệt tác bê tông hình vương miện của Oscar Niemeyer"),
    ("Thác nước Iguazu, Brazil - Argentina", -25.69526, -54.43667, "Brazil", "Hệ thống 275 ngọn thác hùng vĩ giữa rừng nhiệt đới"),
    ("Nhà hát Amazon (Teatro Amazonas), Manaus, Brazil", -3.13028, -60.02333, "Brazil", "Nhà hát mái vòm xanh vàng giữa lòng rừng rậm Amazon"),
    ("Khu phố cổ Pelourinho, Salvador, Brazil", -12.97140, -38.51080, "Brazil", "Phố lát đá cuội và nhà thuộc địa Bồ Đào Nha rực rỡ"),
    ("Cột tháp Obelisco de Buenos Aires, Argentina", -34.60374, -58.38157, "Argentina", "Biểu tượng đại lộ 9 de Julio trung tâm thủ đô Argentina"),
    ("Khu phố sắc màu Caminito, La Boca, Buenos Aires", -34.63930, -58.36270, "Argentina", "Ngôi làng nhà tôn sơn màu rực rỡ quê hương điệu Tango"),
    ("Dinh Tổng thống Casa Rosada, Buenos Aires", -34.60806, -58.37028, "Argentina", "Phủ Tổng thống màu hồng bên Quảng trường Tháng Năm"),
    ("Sông băng Perito Moreno, Patagonia, Argentina", -50.49670, -73.13760, "Argentina", "Bức tường băng trắng khổng lồ cao 70m"),
    ("Thành phố cực Nam Ushuaia (Đất Lửa), Argentina", -54.80191, -68.30300, "Argentina", "Thành phố tận cùng thế giới cửa ngõ Nam Cực"),
    ("Thánh địa cổ Machu Picchu, Peru", -13.16314, -72.54496, "Peru", "Thành phố mất tích trên mây của Đế chế Inca"),
    ("Quảng trường Plaza de Armas, Cusco, Peru", -13.51673, -71.97877, "Peru", "Cố đô của Đế chế Inca trên dãy Andes"),
    ("Quảng trường Chính Plaza Mayor, Lima, Peru", -12.04597, -77.03057, "Peru", "Trung tâm lịch sử thủ đô Peru với ban công gỗ chạm khắc"),
    ("Cánh đồng muối Salar de Uyuni, Bolivia", -20.13378, -67.48913, "Bolivia", "Tấm gương khổng lồ phản chiếu bầu trời lớn nhất thế giới"),
    ("Hồ Titicaca (Đảo nổi Uros), Peru - Bolivia", -15.82250, -69.97220, "Peru", "Hồ nước có tàu thuyền qua lại cao nhất thế giới"),
    ("Đảo Phục Sinh (Tượng đá Moai Ahu Tongariki), Chile", -27.12583, -109.27694, "Chile", "Những pho tượng đầu đá bí ẩn hướng ra Thái Bình Dương"),
    ("Vườn quốc gia Torres del Paine, Patagonia, Chile", -50.94230, -73.40680, "Chile", "Ba ngọn tháp đá granite hùng vĩ tận cùng Nam Mỹ"),
    ("Khu phố dốc sắc màu Valparaíso, Chile", -33.04580, -71.61970, "Chile", "Thành phố cảng đầy tranh tường nghệ thuật và thang máy cổ"),
    ("Thành cổ Cartagena de Indias, Colombia", 10.42360, -75.54800, "Colombia", "Tường thành đá bao quanh phố cổ bên biển Caribe"),
    ("Tảng đá El Peñón de Guatapé, Colombia", 6.21970, -75.17890, "Colombia", "Khối đá nguyên khối 740 bậc thang giữa hồ đảo"),
    ("Đài tưởng niệm Xích đạo Mitad del Mundo, Quito", -0.00222, -78.45583, "Ecuador", "Vạch vĩ tuyến 0° chia đôi Bắc và Nam bán cầu"),
    ("Quảng trường Độc lập, Montevideo, Uruguay", -34.90650, -56.19970, "Uruguay", "Quảng trường Palacio Salvo trung tâm thủ đô Uruguay"),
    # --- Mở rộng thêm Landmark Nam Mỹ ---
    ("Sân vận động Maracanã, Rio de Janeiro, Brazil", -22.91211, -43.23016, "Brazil", "Thánh đường bóng đá huyền thoại của Brazil"),
    ("Đại lộ Avenida Paulista (Bảo tàng MASP), São Paulo", -23.56141, -46.65588, "Brazil", "Bảo tàng treo đỏ biểu tượng đại lộ tài chính São Paulo"),
    ("Sân vận động La Bombonera, Buenos Aires, Argentina", -34.63561, -58.36475, "Argentina", "Sân nhà rực lửa sắc vàng xanh của Boca Juniors"),
    ("Cây cầu Puente de la Mujer, Puerto Madero, Buenos Aires", -34.60790, -58.36490, "Argentina", "Cây cầu quay trắng hiện đại của Santiago Calatrava"),
    ("Tòa nhà Costanera Center (Gran Torre), Santiago, Chile", -33.41700, -70.60660, "Chile", "Toà nhà chọc trời cao nhất Nam Mỹ"),
    ("Cung điện Tổng thống La Moneda, Santiago, Chile", -33.44290, -70.65390, "Chile", "Phủ Tổng thống tân cổ điển trung tâm Santiago"),
    ("Quảng trường Plaza de Bolívar, Bogotá, Colombia", 4.59812, -74.07604, "Colombia", "Quảng trường lịch sử với Nhà thờ Chính tòa Bogotá"),
    ("Thánh đường Las Lajas Sanctuary, Ipiales, Colombia", 0.80550, -77.58610, "Colombia", "Nhà thờ Gothic xây bắc ngang hẻm núi đá tuyệt mỹ"),
]

AFRICA_LANDMARKS: list[tuple[str, float, float, str, str]] = [
    ("Kim tự tháp Giza & Tượng Nhân Sư, Ai Cập", 29.97923, 31.13420, "Ai Cập", "Kỳ quan duy nhất còn tồn tại của Thế giới Cổ đại"),
    ("Đền Karnak, Luxor, Ai Cập", 25.71883, 32.65727, "Ai Cập", "Quần thể cột đá chạm khắc lớn nhất Ai Cập cổ đại"),
    ("Đền Abu Simbel, Aswan, Ai Cập", 22.33723, 31.62580, "Ai Cập", "Bốn pho tượng Ramses II khổng lồ tạc vào vách núi"),
    ("Thư viện Alexandria (Bibliotheca Alexandrina), Ai Cập", 31.20887, 29.90920, "Ai Cập", "Công trình hình đĩa mặt trời bên bờ Địa Trung Hải"),
    ("Núi Bàn (Table Mountain), Cape Town, Nam Phi", -33.96282, 18.40984, "Nam Phi", "Ngọn núi đỉnh bằng phẳng nhìn xuống cảng Cape Town"),
    ("Mũi Hảo Vọng (Cape of Good Hope), Nam Phi", -34.35684, 18.47399, "Nam Phi", "Mũi đá cực Tây Nam châu Phi nơi giao thoa hai đại dương"),
    ("Khu phố Bo-Kaap, Cape Town, Nam Phi", -33.92140, 18.41440, "Nam Phi", "Những ngôi nhà rực rỡ sắc màu dưới chân núi Tín Hiệu"),
    ("Bến cảng V&A Waterfront, Cape Town, Nam Phi", -33.90360, 18.42060, "Nam Phi", "Khu bến cảng lịch sử nhộn nhịp nhìn ra Núi Bàn"),
    ("Tòa nhà Liên minh (Union Buildings), Pretoria, Nam Phi", -25.74020, 28.21200, "Nam Phi", "Trụ sở Chính phủ Nam Phi và tượng Nelson Mandela"),
    ("Thánh đường Hassan II, Casablanca, Morocco", 33.60845, -7.63265, "Morocco", "Ngọn tháp Hồi giáo cao nhất thế giới xây vươn ra Đại Tây Dương"),
    ("Thành phố Xanh Chefchaouen, Morocco", 35.16880, -5.26360, "Morocco", "Ngôi làng cổ trên núi sơn phủ sắc xanh lam"),
    ("Quảng trường Jemaa el-Fnaa, Marrakech, Morocco", 31.62583, -7.98916, "Morocco", "Quảng trường chợ đêm sôi động bậc nhất Bắc Phi"),
    ("Thành đất Ksar Aït Benhaddou, Morocco", 31.04700, -7.13190, "Morocco", "Pháo đài đất nung cổ ven sa mạc Sahara"),
    ("Đấu trường La Mã El Jem, Tunisia", 35.29639, 10.70694, "Tunisia", "Đấu trường cổ bảo tồn tốt bậc nhất châu Phi"),
    ("Thành cổ Carthage (Đồi Byrsa), Tunisia", 36.85290, 10.32330, "Tunisia", "Di tích đế chế Carthage bên vịnh Tunis"),
    ("Thác Victoria (Mosi-oa-Tunya), Zambia - Zimbabwe", -17.92430, 25.85720, "Zambia", "Bức màn nước khổng lồ sấm rền trên sông Zambezi"),
    ("Công viên Quốc gia Nairobi, Kenya", -1.37330, 36.85890, "Kenya", "Khu bảo tồn hoang dã ngay sát đường chân trời thủ đô"),
    ("Núi Kilimanjaro (Moshi), Tanzania", -3.06742, 37.35563, "Tanzania", "Nóc nhà Châu Phi đỉnh núi tuyết giữa xích đạo"),
    ("Đại lộ Cây Bao Báp, Morondava, Madagascar", -20.25083, 44.41833, "Madagascar", "Hàng cây Bao báp khổng lồ 800 năm tuổi"),
    ("Đài tưởng niệm Phục hưng Châu Phi, Dakar, Senegal", 14.72222, -17.49500, "Senegal", "Bức tượng đồng cao nhất châu Phi nhìn ra Đại Tây Dương"),
    # --- Mở rộng thêm Landmark Châu Phi ---
    ("Sân vận động FNB Stadium (Soccer City), Johannesburg", -26.23472, 27.98250, "Nam Phi", "Sân vận động hình quả bầu gốm tổ chức Chung kết World Cup 2010"),
    ("Quảng trường Nelson Mandela Square, Sandton, Johannesburg", -26.10722, 28.05444, "Nam Phi", "Tượng đài Nelson Mandela giữa khu thương mại hiện đại"),
    ("Tòa nhà Trung tâm KICC, Nairobi, Kenya", -1.28860, 36.82310, "Kenya", "Toà tháp hội nghị hình trụ biểu tượng thủ đô Kenya"),
    ("Quảng trường Độc lập (Black Star Square), Accra, Ghana", 5.54778, -0.19278, "Ghana", "Khải Hoàn Môn Ngôi sao Đen bên bờ vịnh Guinea"),
    ("Vương cung thánh đường Đức Bà Hòa Bình, Yamoussoukro", 6.81111, -5.29694, "Bờ Biển Ngà", "Nhà thờ Công giáo có diện tích lớn bậc nhất thế giới"),
    ("Tượng đài Chiến sĩ Độc lập (Uhuru Monument), Dar es Salaam", -6.81806, 39.27750, "Tanzania", "Ngọn đuốc Tự do trung tâm thành phố biển Tanzania"),
    ("Sân vận động Cape Town Stadium (Green Point), Nam Phi", -33.90350, 18.41120, "Nam Phi", "Sân vận động hướng biển bên chân núi Signal Hill"),
    ("Cầu Nelson Mandela Bridge, Johannesburg, Nam Phi", -26.19720, 28.03320, "Nam Phi", "Cầu dây văng biểu tượng nối Braamfontein và Newtown"),
    ("Tòa nhà Carlton Centre, Johannesburg, Nam Phi", -26.20550, 28.04680, "Nam Phi", "Toà nhà chọc trời lịch sử tại trung tâm Johannesburg"),
    ("Phố cổ Medina of Tunis (Cổng Bab Bhar), Tunisia", 36.79920, 10.17570, "Tunisia", "Cổng thành cổ dẫn vào khu chợ Medina Di sản UNESCO"),
    ("Cầu Lekki-Ikoyi Link Bridge, Lagos, Nigeria", 6.44080, 3.46530, "Nigeria", "Cây cầu dây văng hiện đại bên đầm phá Lagos"),
    ("Thánh đường Quốc gia Abuja, Nigeria", 9.05480, 7.49320, "Nigeria", "Thánh đường mái vòm vàng trung tâm thủ đô Nigeria"),
    ("Đài tưởng niệm Kwame Nkrumah, Accra, Ghana", 5.54444, -0.20306, "Ghana", "Công viên tưởng niệm vị Tổng thống đầu tiên của Ghana"),
    ("Sân vận động Moses Mabhida, Durban, Nam Phi", -29.82890, 31.03030, "Nam Phi", "Sân vận động mái vòm cung khổng lồ bên Ấn Độ Dương"),
    ("Thư viện Quốc gia & Quảng trường Nhà thờ (Church Square), Pretoria", -25.74630, 28.18790, "Nam Phi", "Quảng trường lịch sử trung tâm thành phố Pretoria"),
    ("Vườn quốc gia Kirstenbosch (Núi Bàn), Cape Town", -33.98750, 18.43270, "Nam Phi", "Vườn thực vật nằm dưới sườn Đông Núi Bàn"),
    ("Tháp đồng hồ (Clock Tower Avenue Habib Bourguiba), Tunis", 36.79990, 10.18620, "Tunisia", "Tháp đồng hồ trung tâm đại lộ lớn nhất thủ đô Tunis"),
    ("Nhà thờ Chính tòa Dakar & Quảng trường Độc lập, Senegal", 14.66830, -17.43470, "Senegal", "Trung tâm lịch sử khu Plateau thủ đô Senegal"),
    ("Tượng đài Three Dikgosi, Gaborone, Botswana", -24.65310, 25.90890, "Botswana", "Tượng đài 3 vị tù trưởng sáng lập quốc gia Botswana"),
    ("Bùng binh Ngọn Đuốc Độc lập (Independence Avenue), Windhoek, Namibia", -22.56750, 17.08360, "Namibia", "Tòa nhà Bảo tàng Độc lập và Nhà thờ Christuskirche"),
    ("Tháp Hòa bình (Christuskirche), Windhoek, Namibia", -22.56750, 17.08750, "Namibia", "Nhà thờ đá sa thạch đỏ biểu tượng thủ đô Namibia"),
]

OCEANIA_LANDMARKS: list[tuple[str, float, float, str, str]] = [
    ("Nhà hát Opera Sydney, Úc", -33.85678, 151.21530, "Úc", "Kiến trúc cánh buồm trắng Di sản Thế giới bên vịnh Sydney"),
    ("Cầu Cảng Sydney (Harbour Bridge), Úc", -33.85231, 151.21079, "Úc", "Cây cầu vòm thép khổng lồ cạnh Nhà hát Con Sò"),
    ("Bãi biển Bondi Beach, Sydney, Úc", -33.89148, 151.27668, "Úc", "Bãi biển lướt sóng nổi tiếng nhất nước Úc"),
    ("Núi đá đỏ Uluru (Ayers Rock), Úc", -25.34443, 131.03688, "Úc", "Khối đá sa thạch khổng lồ thiêng liêng giữa sa mạc Đỏ"),
    ("Mười Hai Vị Tông Đồ (Great Ocean Road), Victoria, Úc", -38.66590, 143.10450, "Úc", "Những cột đá vôi sừng sững giữa sóng biển Nam Dương"),
    ("Quảng trường Liên bang & Ga Flinders Street, Melbourne", -37.81808, 144.96707, "Úc", "Nhà ga vàng mái vòm trung tâm văn hoá Melbourne"),
    ("Đài tưởng niệm Chiến tranh Úc, Canberra", -35.28060, 149.14890, "Úc", "Công trình mái vòm đồng xanh nhìn thẳng tới Tòa nhà Quốc hội"),
    ("Cầu Story Bridge, Brisbane, Úc", -27.46360, 153.03580, "Úc", "Cây cầu thép biểu tượng bắc qua sông Brisbane"),
    ("Bãi biển Surfers Paradise, Gold Coast, Úc", -28.00230, 153.43100, "Úc", "Dải cao ốc chạy dọc bãi cát vàng Thái Bình Dương"),
    ("Công viên Kings Park & Đường chân trời Perth, Úc", -31.96140, 115.84250, "Úc", "Công viên đồi cây bản địa ngắm toàn cảnh sông Swan"),
    ("Quảng trường Salamanca Place, Hobart, Tasmania", -42.88720, 147.33220, "Úc", "Dãy nhà kho đá sa thạch cổ kính bên bến cảng Tasmania"),
    ("Tháp Sky Tower, Auckland, New Zealand", -36.84845, 174.76219, "New Zealand", "Ngọn tháp cao nhất Nam bán cầu tại Auckland"),
    ("Làng cổ tích Hobbiton, Matamata, New Zealand", -37.85767, 175.68055, "New Zealand", "Ngôi làng người lùn Hobbit giữa đồi cỏ xanh"),
    ("Vịnh hẹp Milford Sound, Fiordland, New Zealand", -44.67160, 167.92560, "New Zealand", "Vịnh băng hà vách đá dựng đứng và đỉnh Mitre Peak"),
    ("Thành phố Queenstown & Hồ Wakatipu, New Zealand", -45.03116, 168.66264, "New Zealand", "Thủ phủ thể thao mạo hiểm bên hồ núi Alps phương Nam"),
    ("Bảo tàng Quốc gia Te Papa, Wellington, New Zealand", -41.29047, 174.78210, "New Zealand", "Bảo tàng văn hoá Maori bên cảng gió Wellington"),
    ("Đảo Núi lửa Bora Bora (Mount Otemanu), Polynesia", -16.50041, -151.74149, "French Polynesia", "Đầm phá ngọc lam nổi tiếng bậc nhất Thái Bình Dương"),
    # --- Mở rộng thêm Landmark Châu Đại Dương ---
    ("Sân vận động Melbourne Cricket Ground (MCG), Úc", -37.81997, 144.98345, "Úc", "Sân vận động lớn nhất nước Úc và Thế vận hội 1956"),
    ("Đài tưởng niệm Shrine of Remembrance, Melbourne, Úc", -37.83050, 144.97350, "Úc", "Công trình tưởng niệm cổ điển nhìn thẳng đại lộ St Kilda"),
    ("Tháp Sydney Tower Eye, Sydney, Úc", -33.87045, 151.20892, "Úc", "Ngọn tháp vàng cao nhất thành phố Sydney"),
    ("Tòa nhà Quốc hội Úc (Parliament House), Canberra", -35.30820, 149.12440, "Úc", "Công trình có cột cờ khổng lồ trên đồi Capital Hill"),
    ("Tháp đồng hồ & Cầu Waitematā Harbour, Auckland", -36.84220, 174.76670, "New Zealand", "Bến phà lịch sử màu cam tại cảng Auckland"),
    ("Nhà thờ Giấy Cardboard Cathedral, Christchurch, New Zealand", -43.53260, 172.64260, "New Zealand", "Nhà thờ tam giác độc đáo xây dựng sau động đất 2011"),
]


def _bearing(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lng2 - lng1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return int(round((math.degrees(math.atan2(y, x)) + 360.0) % 360.0)) % 360


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 6371000.0 * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def _probe_rpc(lat: float, lng: float, radius: int) -> dict | None:
    """Chỉ nhận Panorama 360° CHÍNH THỨC ngoài trời (type == 2, © Google, loc_block[3] is None)."""
    opts = [None, ["vi", "VN"], None, None, None, None, None, None, [2], None, [[[2, True, 2]]]]
    payload = json.dumps([
        ["apiv3"],
        [[None, None, round(lat, 6), round(lng, 6)], int(radius)],
        opts,
        [[1, 2, 3, 4, 8, 6]],
    ]).encode("utf-8")
    req = urllib.request.Request(
        SV_RPC_URL,
        data=payload,
        headers={"Content-Type": "application/json+protobuf", "User-Agent": "Mozilla/5.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=2.5) as r:
            data = json.loads(r.read(32768).decode("utf-8", errors="ignore"))
        node = data[1]
        if not (isinstance(node[1], list) and len(node[1]) > 1 and node[1][0] == 2):
            return None
        pano_id = str(node[1][1])
        loc_block = node[5][0][1]
        if len(loc_block) > 3 and loc_block[3] is not None:
            return None
        coords = loc_block[0]
        snap_lat, snap_lng = float(coords[2]), float(coords[3])
        return {"lat": round(snap_lat, 5), "lng": round(snap_lng, 5), "pano": pano_id}
    except Exception:
        return None


def _thumb_bright_ok(pano_id: str, hdg: int) -> bool:
    """Tải thumbnail thực tế từ Google để chắc chắn 100% ảnh sáng rõ nét, không bị đen/xám/lỗi."""
    turl = f"https://streetviewpixels-pa.googleapis.com/v1/thumbnail?cb_client=maps_sv.tactile&w=160&h=90&panoid={pano_id}&yaw={hdg}"
    try:
        with urllib.request.urlopen(urllib.request.Request(turl, headers={"User-Agent": "Mozilla/5.0"}), timeout=3.0) as r:
            raw = r.read()
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        st = ImageStat.Stat(im)
        mean_b = sum(st.mean) / 3.0
        stddev = sum(st.stddev) / 3.0
        return mean_b >= 15.0 and stddev >= 9.0
    except Exception:
        return False


def _snap_item(item: dict) -> dict | None:
    """Tìm góc đứng ngoài trời chính thức (25m-320m), xoay camera nhìn thẳng & xác thực độ sáng ảnh."""
    lm_lat, lm_lng = item["lat"], item["lng"]
    candidates: list[tuple[float, dict]] = []

    probe_points: list[tuple[float, float]] = [(lm_lat, lm_lng)]
    for dist_m in (85, 175):
        for ang in (0, 60, 120, 180, 240, 300):
            rad = math.radians(ang)
            dlat = (dist_m * math.cos(rad)) / 111320.0
            dlng = (dist_m * math.sin(rad)) / (111320.0 * max(0.2, math.cos(math.radians(lm_lat))))
            probe_points.append((lm_lat + dlat, lm_lng + dlng))

    seen_panos: set[str] = set()
    for p_lat, p_lng in probe_points:
        hit = _probe_rpc(p_lat, p_lng, 220)
        if not hit or hit["pano"] in seen_panos:
            continue
        seen_panos.add(hit["pano"])
        d_m = _haversine_m(hit["lat"], hit["lng"], lm_lat, lm_lng)
        if d_m > 340.0:
            continue
        score = abs(d_m - 85.0)
        candidates.append((score, hit))
        if 30.0 <= d_m <= 140.0:
            break

    candidates.sort(key=lambda x: x[0])
    for _, hit in candidates:
        d_final = _haversine_m(hit["lat"], hit["lng"], lm_lat, lm_lng)
        hdg = _bearing(hit["lat"], hit["lng"], lm_lat, lm_lng) if d_final >= 10.0 else 0
        if _thumb_bright_ok(hit["pano"], hdg):
            return {**item, "lat": hit["lat"], "lng": hit["lng"], "heading": hdg, "pano": hit["pano"]}
    return None


def to_entries(
    raw: list[tuple[str, float, float, str, str]],
    region_code: str,
) -> list[dict]:
    draft: list[dict] = []
    seen: set[tuple[float, float]] = set()
    for name, lat, lng, country, hint in raw:
        key = (round(lat, 4), round(lng, 4))
        if key in seen:
            continue
        seen.add(key)
        draft.append(
            {
                "name": name,
                "lat": round(lat, 5),
                "lng": round(lng, 5),
                "heading": 0,
                "country": country,
                "region": region_code,
                "hint": hint,
                "difficulty": "landmark",
            }
        )
    with ThreadPoolExecutor(max_workers=20) as ex:
        snapped = list(ex.map(_snap_item, draft))
    return [x for x in snapped if x is not None]


def main() -> None:
    # Giữ lại tập fallback_streets từ geo_locations.json cũ (nếu có)
    fallback_streets: dict[str, list[dict]] = {"world": [], "asia": [], "vietnam": []}
    if GEO_DATA_PATH.exists():
        try:
            old = json.loads(GEO_DATA_PATH.read_text(encoding="utf-8"))
            if isinstance(old, dict):
                if "fallback_streets" in old and isinstance(old["fallback_streets"], dict):
                    fallback_streets = old["fallback_streets"]
                else:
                    for m in ("world", "asia", "vietnam"):
                        sec = old.get(m) or {}
                        combined = []
                        if isinstance(sec, dict):
                            for k in ("medium", "hard"):
                                combined.extend(sec.get(k) or [])
                        fallback_streets[m] = combined
        except Exception:
            pass

    landmarks: dict[str, list[dict]] = {
        "vietnam": to_entries(VIETNAM_LANDMARKS, "vietnam"),
        "asia": to_entries(ASIA_LANDMARKS, "asia"),
        "europe": to_entries(EUROPE_LANDMARKS, "europe"),
        "north_america": to_entries(NORTH_AMERICA_LANDMARKS, "north_america"),
        "south_america": to_entries(SOUTH_AMERICA_LANDMARKS, "south_america"),
        "africa": to_entries(AFRICA_LANDMARKS, "africa"),
        "oceania": to_entries(OCEANIA_LANDMARKS, "oceania"),
    }

    # `world` tổng hợp toàn bộ landmark các châu lục + 30 landmark tiêu biểu nhất của Việt Nam
    # để tránh Việt Nam chiếm tỷ trọng quá lớn trong vòng chơi Thế giới.
    world_items: list[dict] = []
    seen_world: set[tuple[float, float]] = set()
    for reg in ("asia", "europe", "north_america", "south_america", "africa", "oceania"):
        for item in landmarks[reg]:
            k = (round(item["lat"], 3), round(item["lng"], 3))
            if k not in seen_world:
                seen_world.add(k)
                world_items.append(item)
    for item in landmarks["vietnam"][:30]:
        k = (round(item["lat"], 3), round(item["lng"], 3))
        if k not in seen_world:
            seen_world.add(k)
            world_items.append(item)

    landmarks["world"] = world_items

    out = {
        "landmarks": landmarks,
        "fallback_streets": fallback_streets,
    }
    GEO_DATA_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Landmark counts by region:")
    for k, v in landmarks.items():
        print(f"  {k}: {len(v)}")
    print("Fallback street counts:")
    for k, v in fallback_streets.items():
        print(f"  {k}: {len(v)}")


if __name__ == "__main__":
    main()
