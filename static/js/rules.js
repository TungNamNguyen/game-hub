/* Cẩm nang luật chơi & hướng dẫn cho toàn bộ trò chơi trên VPHub.
 *
 * Dùng #modalRoot giống openSettings() trong ui.js nên có thể mở bất cứ lúc nào
 * (Trang chủ, Sảnh chờ, hoặc ngay giữa ván đấu từ Topbar) mà không làm rời phòng.
 */

import { clear, h, icon, mount } from './dom.js';
import { getLang, t } from './i18n.js';

export const GAME_RULES = [
  {
    id: 'caro',
    name: 'Cờ caro',
    icon: 'caro',
    players: '2 người (hoặc với máy)',
    goal: 'Tạo thành một hàng liên tiếp đủ số quân quy định (ngang, dọc hoặc chéo) trước đối thủ.',
    basics: [
      'Hai người lần lượt đánh dấu X và O vào các ô trống trên bàn cờ.',
      'Bàn 3×3 (XO cổ điển): Ai nối được 3 quân liên tiếp trước sẽ thắng.',
      'Bàn 15×15, 30×30 hoặc 50×50: Ai nối được 5 quân liên tiếp trước sẽ thắng.',
      'Nếu bàn cờ kín hết ô mà chưa có ai thắng thì ván đấu xử Hòa.',
    ],
    specials: [
      'Sau mỗi ván, người đi trước (X) sẽ tự động đổi luân phiên giữa hai ghế để đảm bảo công bằng.',
      'Hỗ trợ 3 mức độ Bot: Dễ, Thường, Khó.',
    ],
    tips: [
      'Ưu tiên tạo các thế "nước đôi" (cùng lúc mở hai đầu 3 hoặc tạo hai hàng 4) để đối thủ không thể chặn hết.',
      'Chặn ngay khi thấy đối thủ có 3 quân liên tiếp thoáng hai đầu.',
    ],
  },
  {
    id: 'chess',
    name: 'Cờ vua',
    icon: 'chess',
    players: '2 người (hoặc với máy)',
    goal: 'Chiếu hết (Checkmate) Vua của đối phương — khiến Vua bị chiếu và không có nước nào thoát được.',
    basics: [
      'Quân Trắng luôn đi trước; mỗi ván mới trên Game Hub tự động đổi màu Trắng/Đen giữa hai ghế.',
      'Bấm vào quân của mình để xem các ô xanh hợp lệ có thể đi.',
      'Nhập thành (Castling): Chọn Vua và bấm vào ô cách 2 bước về phía Xe khi giữa Vua-Xe trống và Vua không bị chiếu hay đi qua ô bị khống chế.',
      'Bắt tốt qua đường (En Passant): Tốt đối phương vừa tiến 2 ô đứng cạnh tốt mình, có thể ăn chéo ngay ở lượt kế tiếp.',
      'Phong cấp: Tốt đi tới hàng cuối cùng sẽ hiện hộp thoại chọn phong thành Hậu, Xe, Tượng hoặc Mã.',
    ],
    specials: [
      'Xử Hòa tự động khi: Bí nước (Stalemate — không bị chiếu nhưng hết nước đi), lặp lại cùng một thế cờ 3 lần, 50 nước liên tiếp không ăn quân/không đi tốt, hoặc hai bên thiếu quân không thể chiếu hết.',
    ],
    tips: [
      'Khai cuộc nên kiểm soát trung tâm (e4, d4), phát triển Mã/Tượng sớm và nhập thành bảo vệ Vua.',
      'Không đưa Hậu ra quá sớm để tránh bị quân nhẹ đối phương đuổi mất nhịp.',
    ],
  },
  {
    id: 'xiangqi',
    name: 'Cờ tướng',
    icon: 'xiangqi',
    players: '2 người (hoặc với máy)',
    goal: 'Chiếu hết Tướng đối phương, hoặc làm đối phương rơi vào thế bí không còn nước đi hợp lệ.',
    basics: [
      'Quân Đỏ đi trước; mỗi ván mới tự động đổi bên Đỏ/Đen giữa hai người chơi.',
      'Tướng và Sĩ chỉ được đi trong Cửu Cung 3×3. Tượng đi chéo 2 ô nhưng không được qua sông và bị chặn nếu có quân ở "mắt tượng".',
      'Mã đi chữ L (ngang 2 dọc 1 hoặc dọc 2 ngang 1), bị cản nếu có quân đứng ngay sát bên theo hướng xuất phát ("cản chân mã").',
      'Pháo đi giống Xe khi di chuyển bình thường, nhưng muốn ăn quân phải nhảy qua đúng 1 quân làm ngòi.',
      'Binh/Tốt chỉ đi thẳng 1 ô; sau khi qua sông được phép đi ngang hoặc đi thẳng (không đi lùi).',
    ],
    specials: [
      'Luật Lộ Mặt Tướng: Hai Tướng không được đứng đối diện trực tiếp trên cùng một cột dọc mà giữa không có quân nào.',
      'Khác cờ vua: Trong Cờ tướng KHÔNG có hòa vì bí nước — bên nào tới lượt mà hết nước đi hợp lệ là THUA ngay!',
      'Hòa khi lặp thế 3 lần hoặc 60 nước liên tiếp không ăn quân.',
    ],
    tips: [
      'Khai cuộc phổ biến là Pháo đầu (Pháo 2/8 bình 5), Bình Phong Mã, hoặc Tiên Nhân Chỉ Lộ.',
      'Luôn giữ liên kết Sĩ - Tượng và để ý chân Mã khi đối phương áp sát.',
    ],
  },
  {
    id: 'ship',
    name: 'Bắn tàu',
    icon: 'ship',
    players: '2 người (hoặc với máy)',
    goal: 'Tìm và đánh chìm toàn bộ hạm đội 5 tàu của đối thủ trên lưới 10×10 trước khi hạm đội mình bị tiêu diệt.',
    basics: [
      'Pha Đặt tàu: Mỗi bên xếp 5 con tàu (dài 5, 4, 3, 3 và 2 ô) lên bảng 10×10. Bấm nút Xoay (hoặc phím R) để đổi hướng ngang/dọc, hoặc bấm "Xếp ngẫu nhiên" rồi bấm "Sẵn sàng".',
      'Pha Bắn nhau: Lần lượt chọn một ô trên bản đồ đối phương để khai hỏa.',
      'Nếu bắn TRÚNG tàu địch, bạn được GIỮ LƯỢT BẮN TIẾP cho đến khi bắn trượt!',
      'Khi toàn bộ các ô của một con tàu bị bắn trúng, tàu đó chìm và hệ thống sẽ thông báo tên tàu.',
    ],
    specials: [
      'Tàu không được phép đặt đè lên nhau hoặc thò ra ngoài lưới.',
      'Người xem hoặc đối thủ hoàn toàn không thấy vị trí tàu chưa bị bắn của bạn.',
    ],
    tips: [
      'Áp dụng chiến thuật bắn kiểu bàn cờ caro (cách ô theo đường chéo) vì con tàu nhỏ nhất dài 2 ô — chắc chắn không thể lọt qua lưới ô xen kẽ.',
      'Khi đã bắn trúng 1 ô, hãy thử bắn 4 ô xung quanh để xác định hướng nằm ngang hay dọc của tàu.',
    ],
  },
  {
    id: 'bluff',
    name: 'Sòng Bịp',
    icon: 'cards',
    players: '2–4 người (hoặc chơi cùng các Bot)',
    goal: 'Là người cuối cùng còn sống sót trên bàn bằng cách tống hết bài trên tay hoặc bắt bài đối thủ nói dối.',
    basics: [
      'Mỗi vòng sẽ có một Quân Chủ (Át, K hoặc Q). Mỗi người được chia 5 lá bài.',
      'Đến lượt (tối đa 30 giây): Chọn 1 đến 3 lá bài bất kỳ để ĐẶT ÚP xuống bàn và mặc định khai báo chúng là Quân Chủ.',
      'Bạn có thể đặt bài thật, hoặc trà trộn bài khác để BỊP!',
      'Người kế tiếp có 2 lựa chọn: (1) Đánh tiếp bài úp lên bàn, hoặc (2) Hô "BỊP!" để lật bài của người vừa đánh.',
    ],
    specials: [
      'Nếu người bị tố cáo nói DỐI (có ít nhất 1 lá không phải Quân Chủ và không phải Joker): Người đó phải kề súng vào đầu và bóp cò (ổ đạn 6 viên, 1 viên thật).',
      'Nếu người bị tố cáo nói THẬT: Chính người hô "Bịp!" phải tự bắn mình!',
      'Chế độ Ma Vương (DEVIL): Nếu lá bị lật có lá Ma Vương, TẤT CẢ những người khác trên bàn đều phải bóp cò thay cho người đặt bài!',
      'Ai sống sót qua phát súng sẽ tiếp tục vòng mới với ổ đạn xoay tiếp (xác suất nổ tăng dần từ 1/6 đến 6/6).',
    ],
    tips: [
      'Đừng bịp quá lộ liễu khi số bài trên tay bạn còn ít.',
      'Quan sát số lượng lá đối thủ đặt xuống: đặt 3 lá liên tiếp rất dễ là cú bịp hoặc lá Ma Vương!',
    ],
  },
  {
    id: 'poker',
    name: 'Xì Tố',
    icon: 'cards',
    players: '2–6 người (Chỉ chơi với người thật)',
    goal: 'Tạo thành bộ 5 lá bài mạnh nhất (kết hợp 2 lá tẩy trên tay + 5 lá chung) hoặc tố khiến cả bàn bỏ bài.',
    basics: [
      'Blinds cố định 500 / 1.000 chip. Mỗi người vào bàn tiền lẻ được cấp 100.000 chip ảo (hết chip bấm Rebuy).',
      '4 vòng cược: Pre-flop (2 lá tẩy) → Flop (3 lá chung) → Turn (lá thứ 4) → River (lá thứ 5).',
      'Thứ tự tay bài từ thấp đến cao: Mậu thầu → 1 Đôi → 2 Đôi → Sám cô → Sảnh → Thùng → Cù lũ → Tứ quý → Thùng phá sảnh.',
      'Hành động: Fold (Bỏ), Check (Qua), Call (Theo), Bet/Raise (Cược/Tố), All-in (Tất tay). Có nút đặt hành động trước khi chưa tới lượt.',
    ],
    specials: [
      'Chế độ Tiền lẻ vs Giải đấu: Bàn Giải đấu chia chip bằng nhau, hết chip bị loại trực tiếp, người trụ lại cuối cùng vô địch giải.',
      'Chia 2 lần (Run It Twice): Khi All-in trước Showdown và hai bên đồng ý, phần bài chung còn lại được chia làm 2 dãy độc lập chia đôi pot.',
      'Bảng xếp hạng "Vô địch ngày" ghi nhận tổng chip lời/lỗ trong ngày.',
    ],
    tips: [
      'Ở vị trí cuối (Dealer / Button) bạn có lợi thế lớn vì được hành động sau cùng ở mọi vòng sau Flop.',
      'Quản lý kích thước cược (1/2 pot, 3/4 pot) để ép đối thủ trả giá đắt khi chờ sảnh/thùng.',
    ],
  },
  {
    id: 'geo',
    name: 'Địa Đồ (GeoGuessr)',
    icon: 'globe',
    players: '1–6 người (Solo, FFA & Đấu Sinh Tử Team/Boss 1vN)',
    goal: 'Quan sát khung cảnh thực tế và ghim tọa độ gần vị trí thật nhất trên bản đồ để ghi tối đa 5.000 điểm mỗi vòng.',
    basics: [
      'Chọn 1 trong 8 khu vực bản đồ (Thế giới, Việt Nam, Châu Á, Châu Âu, Bắc Mỹ, Nam Mỹ, Châu Phi, Châu Đại Dương) và 2 chế độ: Toàn Cầu (100% ảnh Google Street View toàn cầu) hoặc Landmark (Địa danh & kỳ quan nổi tiếng).',
      'Tùy chỉnh góc nhìn: MOVING (di chuyển tự do, phím R về gốc), NM (chỉ xoay 360° & zoom), hoặc NMPZ (khóa cứng khung hình).',
      'Bấm lên bản đồ để cắm Cờ Nháp (nhấn M để ghim bản đồ), rồi bấm "📍 Chốt tọa độ" hoặc nhấn phím Space để đoán nhanh và qua vòng tiếp theo.',
      'Quy tắc vàng: nếu hết giờ mà bạn mới cắm Cờ Nháp chưa kịp bấm Chốt, hệ thống tự động lấy Cờ Nháp tính điểm để không bị 0 điểm oan!',
    ],
    specials: [
      'Đấu Sinh Tử (6.000 HP — có thể chỉnh 12.000 HP cho kèo Boss 1vN): Điểm mỗi đội là điểm cao nhất trong đội (Best Guess). Từ vòng 5, sát thương tăng ×1.5, ×2.0, ×2.5...',
      'Đồng hồ Panic 15s: Chế độ Đội mặc định chỉ rút 15s khi toàn bộ thành viên đang online của 1 phe đã chốt (chống 1 người chốt bừa để ép giờ đối thủ).',
      'Công thức điểm chuẩn: 5.000 × e^(-10 × d / D), đạt tuyệt đối 5.000 điểm trong ngưỡng 25m (bản đồ Thế giới).',
    ],
    tips: [
      'Chú ý ngôn ngữ trên biển hiệu, kiểu vạch kẻ đường, bên tay lái (trái/phải) và thảm thực vật.',
      'Dùng phím Space để chốt nhanh ngay khi chắc chắn, hoặc rê chuột vào bản đồ để phóng rộng khi soi tọa độ chi tiết.',
    ],
  },
  {
    id: 'flags',
    name: 'Đố Cờ & Thủ Đô',
    icon: 'flag',
    players: '1–6 người (Solo, vs Bot & Nhiều người)',
    goal: 'Nhận diện nhanh tên quốc gia qua lá cờ hoặc đoán đúng tên thủ đô của quốc gia được hỏi để ghi nhiều điểm nhất.',
    basics: [
      'Chọn khu vực: Toàn thế giới (197 nước) hoặc lọc theo từng châu lục (Châu Á, Châu Âu, Châu Mỹ, Châu Phi, Châu Đại Dương).',
      'Chọn 1 trong 3 thể loại: Đoán Nước từ Lá Cờ, Đoán Thủ Đô từ Tên Nước, hoặc Hỗn hợp cả hai.',
      'Chọn 1 trong 2 cách trả lời: Trắc nghiệm 4 đáp án A/B/C/D (bấm phím 1–4 cực nhanh) hoặc Tự gõ kết quả (chấp nhận cả tiếng Việt không dấu lẫn tiếng Anh).',
    ],
    specials: [
      'Điểm tốc độ: Trả lời đúng càng nhanh điểm càng cao (500–1.000 điểm mỗi câu) + thưởng chuỗi đúng liên tiếp tối đa +300 điểm.',
      'Ở chế độ Tự gõ: Gõ sai có thể sửa và gửi lại miễn là chưa hết giờ; có gợi ý gõ nhanh hoặc bấm Bỏ qua nếu chưa nhớ ra.',
    ],
    tips: [
      'Chế độ Tự gõ chấp nhận tên không dấu ("viet nam", "ha noi") hoặc tên quốc tế ("hanoi", "tokyo", "usa").',
      'Dùng phím số 1, 2, 3, 4 ở chế độ Trắc nghiệm để phản xạ trước đối thủ!',
    ],
  },
];

export const GAME_RULES_EN = [
  {
    id: 'caro',
    name: 'Caro / XO',
    icon: 'caro',
    players: '2 players (or vs Bot)',
    goal: 'Connect the required number of your marks in a row (horizontally, vertically, or diagonally) before your opponent.',
    basics: [
      'Players take turns placing X and O on empty squares.',
      '3×3 board (Classic XO): First to connect 3 in a row wins.',
      '15×15, 30×30 or 50×50 boards: First to connect 5 in a row wins.',
      'If the board fills up completely with no winner, the game is a Draw.',
    ],
    specials: [
      'After every game, the starting mark (X) alternates fairly between the two seats.',
      'Supports 3 AI Bot difficulty levels: Easy, Normal, and Hard.',
    ],
    tips: [
      'Try to build double threats (open threes or simultaneous fours) so your opponent cannot block both.',
      'Block immediately when you spot an opponent with an open three-in-a-row.',
    ],
  },
  {
    id: 'chess',
    name: 'Chess',
    icon: 'chess',
    players: '2 players (or vs Bot)',
    goal: 'Checkmate the opponent\'s King so it is under attack with no legal escape.',
    basics: [
      'White always moves first; colors swap automatically after each rematch.',
      'Click one of your pieces to highlight all legal moves.',
      'Castling: Select the King and move two squares toward a Rook when both are unmoved, clear, and safe.',
      'En Passant: Capture an enemy pawn immediately after it advances two squares beside yours.',
      'Promotion: Reaching the last rank opens a choice to promote into Queen, Rook, Bishop, or Knight.',
    ],
    specials: [
      'Automatic draw on Stalemate, Threefold Repetition, 50-move rule, or Insufficient Material.',
    ],
    tips: [
      'Control the center (e4, d4), develop Knights and Bishops early, and castle to keep your King safe.',
      'Avoid bringing the Queen out too early where minor pieces can chase it for tempo.',
    ],
  },
  {
    id: 'xiangqi',
    name: 'Xiangqi',
    icon: 'xiangqi',
    players: '2 players (or vs Bot)',
    goal: 'Checkmate the opponent\'s General, or leave them with no legal moves.',
    basics: [
      'Red moves first; sides alternate automatically between games.',
      'General and Advisors stay inside the 3×3 Palace. Elephants move 2 points diagonally without crossing the river and can be blocked at the eye.',
      'Horses move in an L shape and can be blocked by an adjacent orthogonal piece.',
      'Cannons slide like Chariots but must jump over exactly one screen piece to capture.',
      'Soldiers move 1 step forward, and gain sideways movement after crossing the river.',
    ],
    specials: [
      'Flying General rule: The two Generals cannot face each other directly on an unobstructed file.',
      'Unlike Western Chess, stalemate is NOT a draw in Xiangqi — the player with no legal moves LOSES.',
      'Draws occur on threefold repetition or 60 moves without a capture.',
    ],
    tips: [
      'Popular openings include Central Cannon, Screen Horses, and Pawn Opening.',
      'Keep Advisors and Elephants coordinated around the palace for solid defense.',
    ],
  },
  {
    id: 'ship',
    name: 'Battleship',
    icon: 'ship',
    players: '2 players (or vs Bot)',
    goal: 'Locate and sink all 5 enemy ships on a 10×10 grid before your fleet is sunk.',
    basics: [
      'Placement Phase: Place 5 ships (lengths 5, 4, 3, 3, and 2). Press R (or Rotate) to toggle orientation, or click Auto-place, then click Ready.',
      'Battle Phase: Take turns firing at coordinates on the enemy grid.',
      'Landing a HIT lets you KEEP FIRING until you miss!',
      'Once all cells of a ship are hit, it sinks and is announced.',
    ],
    specials: [
      'Ships cannot overlap, go out of bounds, or touch orthogonally/diagonally.',
      'Neither opponents nor spectators can see your unhit ship positions.',
    ],
    tips: [
      'Fire in a checkerboard parity pattern — the smallest ship is 2 cells long and cannot hide between diagonal gaps.',
      'After a hit, probe the 4 orthogonal neighbors to determine the ship\'s orientation.',
    ],
  },
  {
    id: 'bluff',
    name: 'Liar\'s Bar',
    icon: 'cards',
    players: '2–4 players (with optional AI Bots)',
    goal: 'Be the last player standing by emptying your hand or calling out liars.',
    basics: [
      'Each round picks one Table Rank (Dragon, Phoenix, or Tiger). Everyone receives 5 cards.',
      'On your turn (30s): Place 1–3 cards face-down and claim they match the Table Rank.',
      'Play truthfully (with matching cards or wild Demons) or sneak in other cards to BLUFF!',
      'The next player may either play more cards on top, or click CALL LIAR! to reveal the last play.',
    ],
    specials: [
      'If the accused player lied: they pull the trigger on a 6-chamber revolver (1 live bullet).',
      'If the accused told the truth: the challenger pulls the trigger instead!',
      'Devil Mode: If a Devil card is flipped on a challenge, ALL OTHER active players pull the trigger instead!',
      'Spent chambers are not re-spun until a death, raising the lethal odds from 1/6 up to 6/6.',
    ],
    tips: [
      'Avoid risky bluffs when holding only 1–2 cards left.',
      'Watch 3-card plays carefully — they are often bold bluffs or a hidden Devil card.',
    ],
  },
  {
    id: 'poker',
    name: 'Poker (Texas Hold\'em)',
    icon: 'cards',
    players: '2–6 players (Humans & AI Bots)',
    goal: 'Make the best 5-card hand from your 2 hole cards + 5 community cards, or force everyone else to fold.',
    basics: [
      'Fixed 500 / 1,000 blinds. Cash tables start you with 100,000 virtual chips (free Rebuy anytime).',
      'Four betting streets: Pre-flop → Flop (3 cards) → Turn (4th card) → River (5th card).',
      'Hand rankings: High Card → One Pair → Two Pair → Three of a Kind → Straight → Flush → Full House → Four of a Kind → Straight Flush.',
      'Supports Fold, Check, Call, Bet/Raise slider & presets, All-in, and Pre-actions.',
    ],
    specials: [
      'Cash vs Knockout Tournament tables: Equal stacks, rising blind levels, elimination on bust.',
      'Run It Twice: When all-in before showdown and all players agree, deal the remaining board twice for split pots.',
      'Daily Leaderboard tracks net chip profit across all Poker tables.',
    ],
    tips: [
      'Acting last on the Button gives a huge informational edge after the Flop.',
      'Use 1/2 pot and 3/4 pot bets to charge drawing hands.',
    ],
  },
  {
    id: 'geo',
    name: 'GeoGuessr',
    icon: 'globe',
    players: '1–6 players (Solo, Classic, Streak & Team Duels)',
    goal: 'Inspect real-world Street View imagery and pin the exact location on the map for up to 5,000 points per round.',
    basics: [
      'Choose from 8 map regions (World, Vietnam, Asia, Europe, North America, South America, Africa, Oceania) and 2 modes: Global (100% real-time worldwide Street View) or Landmarks (iconic sites & monuments).',
      'Movement rules: MOVING (full 360° navigation, R to reset), NM (pan & zoom only), or NMPZ (locked frame).',
      'Click the mini-map to place a Draft Pin (press M to pin map), then press Guess or Spacebar to lock in and advance rounds.',
      'Auto-lock safety: If time expires while you have a Draft Pin placed, it automatically submits instead of scoring 0!',
    ],
    specials: [
      'Duels (6,000 HP or 12,000 HP Boss 1vN): Uses each team\'s Best Guess, with escalating multipliers from Round 5.',
      'Country / Province Streak: See how many consecutive regions you can identify without missing.',
      'Scoring formula: 5,000 × e^(-10 × d / D), awarding full 5,000 pts within 25m on World.',
    ],
    tips: [
      'Look for road lines, script on signs, driving side (left/right), utility poles, and sun position.',
      'Use R to snap back to spawn, hover the map to expand it, or click Pin to keep it open.',
    ],
  },
  {
    id: 'flags',
    name: 'Flags & Capitals',
    icon: 'flag',
    players: '1–6 players (Solo, vs Bot & Multiplayer)',
    goal: 'Identify countries by their flag or name their capital city as fast as possible.',
    basics: [
      'Choose a region: All 197 countries worldwide or filter by Asia, Europe, Americas, Africa, or Oceania.',
      'Pick a quiz mode: Flag → Country, Country → Capital, or Mixed.',
      'Pick an answer mode: Multiple Choice (4 options, press 1–4 hotkeys) or Type Answer (accepts both English & Vietnamese names).',
    ],
    specials: [
      'Speed + Streak scoring: Correct answers score 500–1,000 pts by speed plus up to +300 streak bonus.',
      'In Typing mode, wrong guesses can be retried until time runs out, with optional quick autocomplete suggestions.',
    ],
    tips: [
      'In Typing mode, diacritics are optional and common aliases like USA, UK, or Hanoi/Beijing work smoothly.',
    ],
  },
];

export function openRulesModal(initialGameId = 'caro') {
  const root = document.getElementById('modalRoot');
  if (!root) return;

  const list = getLang() === 'en' ? GAME_RULES_EN : GAME_RULES;
  let activeId = list.some((g) => g.id === initialGameId) ? initialGameId : 'caro';
  const done = () => clear(root);

  const tabsBox = h('div', { class: 'rules-tabs' });
  const bodyBox = h('div', { class: 'rules-body' });

  function renderContent() {
    const rule = list.find((g) => g.id === activeId) || list[0];

    mount(tabsBox,
      list.map((g) => h('button', {
        type: 'button',
        class: 'sm' + (g.id === activeId ? ' active' : ' ghost'),
        onclick: () => { activeId = g.id; renderContent(); },
      }, icon(g.icon, 14), ' ', g.name)));

    mount(bodyBox,
      h('div', { class: 'rules-hero' },
        h('div', { class: 'rules-title-row' },
          icon(rule.icon, 22),
          h('h3', { style: { margin: '0' } }, rule.name),
          h('span', { class: 'chip accent' }, rule.players)),
        h('p', { class: 'rules-goal' },
          h('strong', {}, t('rules.goalLabel')), rule.goal)),

      h('div', { class: 'rules-section' },
        h('h4', {}, t('rules.basicsTitle')),
        h('ul', { class: 'rules-list' },
          rule.basics.map((item) => h('li', {}, item)))),

      rule.specials?.length
        ? h('div', { class: 'rules-section' },
            h('h4', {}, t('rules.specialsTitle')),
            h('ul', { class: 'rules-list' },
              rule.specials.map((item) => h('li', {}, item))))
        : null,

      rule.tips?.length
        ? h('div', { class: 'rules-section rules-tips' },
            h('h4', {}, t('rules.tipsTitle')),
            h('ul', { class: 'rules-list' },
              rule.tips.map((item) => h('li', {}, item))))
        : null);
  }

  const box = h('div', { class: 'modal rules-modal' },
    h('div', { class: 'spread', style: { marginBottom: '10px' } },
      h('div', { class: 'row', style: { gap: '8px' } },
        icon('book', 20),
        h('h2', { style: { margin: '0' } }, t('rules.title'))),
      h('button', { class: 'icon ghost xs', type: 'button', onclick: done, 'aria-label': t('ui.close') },
        icon('close', 16))),
    tabsBox,
    bodyBox);

  const back = h('div', {
    class: 'modal-back',
    onclick: (event) => { if (event.target === back) done(); },
  }, box);
  back.addEventListener('keydown', (event) => { if (event.key === 'Escape') done(); });

  renderContent();
  clear(root).appendChild(back);
}
