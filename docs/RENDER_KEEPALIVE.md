# Hướng dẫn giữ Web trên Render (Free Tier) không bị ngủ đông

Trên gói **Render Free Web Service**, Render sẽ tự động cho container ngủ đông (**Spin Down**) nếu **không có HTTP request từ bên ngoài đi qua proxy của Render trong 15 phút liên tiếp**. Khi ngủ đông, người dùng kế tiếp vào web phải chờ **30–60 giây** để server khởi động lại.

> **Lưu ý kỹ thuật quan trọng**: Việc tự ping `127.0.0.1` bên trong code Python **không** tính là lưu lượng ngoài và không ngăn Render sleep. Hơn nữa, khi container đã bị đóng băng, tiến trình Python bên trong cũng dừng chạy. Vì vậy cần kết hợp **ping từ bên ngoài** gọi vào endpoint `/healthz` (đã hỗ trợ cả `GET` và `HEAD`).

---

## Cách 1: Dùng UptimeRobot hoặc Cron-job.org (Khuyên dùng — Ổn định 24/7, Miễn phí)

Đây là cách **chắc chắn nhất** (không bị delay như GitHub Actions):

1. Truy cập **[https://uptimerobot.com](https://uptimerobot.com)** (hoặc **[https://cron-job.org](https://cron-job.org)**) và tạo tài khoản miễn phí.
2. Tạo Monitor mới:
   - **Monitor Type**: `HTTP(s)`
   - **URL**: `https://<ten-service-cua-ban>.onrender.com/healthz`
   - **Monitoring Interval**: `5 minutes` (hoặc `10 minutes`)
   - **HTTP Method**: `HEAD` hoặc `GET` (server `/healthz` hỗ trợ cả hai).
3. Lưu lại — Render sẽ luôn nhận request đều đặn mỗi 5–10 phút và **không bao giờ tự ngắt** (lưu ý gói Render Free có giới hạn 750 giờ miễn phí/tháng cho toàn bộ service, đủ cho 1 web chạy liên tục 24/7 cả tháng).

---

## Cách 2: Bật sẵn GitHub Actions Keep-Alive có trong repo này

Repo đã tạo sẵn workflow tại [`.github/workflows/keepalive.yml`](../.github/workflows/keepalive.yml):

1. Vào repo GitHub của bạn -> **Settings** -> **Secrets and variables** -> **Actions** -> tab **Variables** (hoặc Secrets).
2. Bấm **New repository variable**:
   - Name: `RENDER_URL`
   - Value: `https://<ten-service-cua-ban>.onrender.com` (không có dấu `/` cuối cũng được).
3. Vào tab **Actions** -> chọn workflow **Render Keep-Alive Ping** -> bật lên nếu repo chưa kích hoạt cron.

*(Lưu ý: GitHub Actions có thể delay vài phút vào giờ cao điểm nên kết hợp thêm Cách 1 để đạt 100% uptime).*

---

## Cách 3: Cơ chế tự ping tích hợp trong `server.py`

Trong `server.py` đã tích hợp sẵn background task `keepalive_loop()` gửi request `GET <RENDER_EXTERNAL_URL>/healthz` mỗi 10 phút khi biến môi trường `RENDER_EXTERNAL_URL` (Render tự gắn sẵn) hoặc `KEEPALIVE_URL` tồn tại. Điều này giúp duy trì kết nối đều đặn khi server đang thức, kết hợp với **Cách 1** để chống ngủ đông tuyệt đối.
