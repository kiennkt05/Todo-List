# Todo List API — Pha 1

Dịch vụ quản lý công việc cá nhân. Mỗi tài khoản chỉ xem và sửa công việc của mình. API giao tiếp bằng JSON; Swagger UI có tại `/docs`, tài liệu OpenAPI JSON tại `/openapi.json` và bản đặc tả tĩnh trong [`openapi.json`](openapi.json).

## Phạm vi nghiệp vụ

- Đăng ký bằng email và mật khẩu; email không phân biệt hoa thường, không được trùng.
- Đăng nhập nhận Bearer token có hạn 60 phút.
- Tạo, xem danh sách, xem chi tiết, đánh dấu hoàn thành/chưa hoàn thành và xóa công việc.
- Danh sách sắp xếp theo ID giảm dần (mới trước). Truy cập ID của người khác trả `404`.
- Pha 1 chưa có hạn chót, nhãn, chia sẻ, phân trang hay làm mới token.

## Kiến trúc

```text
HTTP/JSON (app/factory.py, app/api/schemas.py)
    ↓
Nghiệp vụ (app/domain/services.py, models.py, ports.py)
    ↓ qua các Protocol repository
Truy cập dữ liệu (app/infrastructure/repositories.py)
    ↓
SQLAlchemy ORM → SQLite
```

Tầng `domain` chỉ dùng thư viện chuẩn Python; không import FastAPI, Pydantic hoặc SQLAlchemy. `factory.py` nối các tầng qua dependency injection. Middleware kiểm tra Bearer token tập trung cho mọi đường dẫn `/api/tasks`; endpoint chỉ nhận `user_id` đã được middleware xác minh. Mật khẩu được băm PBKDF2-SHA256 với salt ngẫu nhiên; token JWT được ký HS256. Mỗi truy vấn công việc luôn lọc theo `user_id`.

## Chạy cục bộ

Yêu cầu Python 3.12. Từ thư mục dự án:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
$env:TOKEN_SECRET = "thay-bang-chuoi-ngau-nhien-it-nhat-32-ky-tu"
uvicorn app.main:app --reload
```

Linux/macOS: kích hoạt bằng `source .venv/bin/activate`, đặt biến bằng `export TOKEN_SECRET='...'`. Mặc định dữ liệu nằm tại `data/todo.db`; có thể đổi bằng `DATABASE_URL`. Schema SQLite được tạo khi server khởi động. `TOKEN_SECRET` bắt buộc và phải có ít nhất 32 ký tự; giữ cùng giá trị giữa các lần khởi động nếu muốn token cũ còn hiệu lực.

## Docker

```powershell
docker build -t todo-list-api .
docker run --rm -p 8000:8000 -e TOKEN_SECRET="thay-bang-chuoi-ngau-nhien-it-nhat-32-ky-tu" -v todo-data:/app/data todo-list-api
```

Mở `http://localhost:8000/docs`. Volume `todo-data` lưu SQLite qua các lần chạy container. Không commit secret hay file DB.

## Đặc tả endpoint

Tất cả request body dùng `Content-Type: application/json`. Các endpoint công việc yêu cầu `Authorization: Bearer <access_token>`.

| Method | Đường dẫn | Body | Thành công | Lỗi chính |
|---|---|---|---|---|
| GET | `/health` | — | `200 {"status":"ok"}` | — |
| POST | `/api/auth/register` | `{"email":"a@example.com","password":"secret123"}` | `201` tài khoản `{id,email}` | `400/422` dữ liệu sai; `409` email trùng |
| POST | `/api/auth/login` | `{"email":"a@example.com","password":"secret123"}` | `200 {access_token,token_type}` | `401` sai thông tin |
| GET | `/api/tasks` | — | `200` mảng công việc của chủ token | `401` thiếu/sai token |
| POST | `/api/tasks` | `{"title":"Mua sữa","description":"Tùy chọn"}` | `201` công việc vừa tạo | `400/422` tiêu đề sai; `401` |
| GET | `/api/tasks/{task_id}` | — | `200` một công việc | `401`; `404` không có/không sở hữu |
| PATCH | `/api/tasks/{task_id}` | `{"is_done":true}` | `200` công việc sau cập nhật | `401`; `404`; `422` |
| DELETE | `/api/tasks/{task_id}` | — | `204` không có body | `401`; `404` |

Một công việc có dạng:

```json
{
  "id": 1,
  "user_id": 1,
  "title": "Mua sữa",
  "description": "Tùy chọn",
  "is_done": false,
  "created_at": "2026-10-07T10:00:00Z"
}
```

Thời gian `created_at` là UTC. `description` có thể là `null`. Lỗi nghiệp vụ trả `{"detail":"..."}`; lỗi kiểm tra schema của FastAPI trả `422` theo định dạng mặc định của framework.

### Ví dụ luồng gọi

```bash
curl -X POST http://localhost:8000/api/auth/register -H "Content-Type: application/json" -d '{"email":"a@example.com","password":"secret123"}'
curl -X POST http://localhost:8000/api/auth/login -H "Content-Type: application/json" -d '{"email":"a@example.com","password":"secret123"}'
curl -X POST http://localhost:8000/api/tasks -H "Authorization: Bearer <access_token>" -H "Content-Type: application/json" -d '{"title":"Mua sữa"}'
curl http://localhost:8000/api/tasks -H "Authorization: Bearer <access_token>"
```

## Kiểm thử

```bash
pytest -q
```

Các kiểm thử bao phủ đăng nhập, từ chối GET/POST không có token, CRUD, phân tách dữ liệu giữa hai tài khoản và khai báo bảo mật trong OpenAPI.

### Kiểm thử tải trên Kaggle CPU

1. Tạo notebook với Accelerator `None` (CPU). Đưa thư mục dự án vào notebook; nếu cài từ PyPI, bật Internet cho notebook hoặc đính kèm các wheel phụ thuộc.
2. Trong notebook, chuyển đến thư mục dự án và chạy `pip install -r requirements.txt`.
3. Khởi động API bằng `subprocess.Popen(["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"], env={**os.environ, "TOKEN_SECRET": "<secret-dai-it-nhat-32-ky-tu>"})`; chờ `/health` trả `200`.
4. Chạy `python kaggle/benchmark.py --concurrency 1 --iterations 25`, sau đó lặp với `--concurrency 4` và `8`. Ghi lại loại CPU, phiên bản Python, số worker Uvicorn, thông số lệnh, throughput, p50/p95 từng method và số lỗi HTTP. Script tạo tài khoản ngoài phần đo, rồi mỗi vòng POST → GET → DELETE.

Giữ nguyên môi trường và số vòng khi so sánh. SQLite một file và một process Uvicorn là cấu hình cơ sở của Pha 1; kết quả đo là cơ sở để chọn cải tiến, không phải cam kết hiệu năng.

## Kế hoạch Pha 2

| Thuộc tính | Vấn đề cần kiểm chứng | Cải tiến dự kiến | Cách đo |
|---|---|---|---|
| Hiệu năng | GET danh sách lớn và ghi đồng thời có thể chậm | Phân trang; chỉ mục theo `(user_id, id)`; cân nhắc PostgreSQL | p95 GET/POST, throughput và tỷ lệ lỗi ở cùng mức tải |
| Tin cậy | SQLite không phù hợp nhiều writer; chưa có migration | PostgreSQL, Alembic migration, health check DB | Thử ghi đồng thời, khởi động lại, kiểm tra toàn vẹn dữ liệu |
| Bảo mật | Token chưa thu hồi; chưa giới hạn đăng nhập | Refresh/revocation, rate limit, kiểm tra cấu hình secret | Thử token hết hạn/thu hồi, brute-force, truy cập chéo tài khoản |
| Bảo trì | Khi tăng chức năng cần hợp đồng rõ hơn | Unit test nghiệp vụ, integration test DB, CI | Tỷ lệ pass và thời gian test trên mỗi commit |

Đây là danh sách giả thuyết cho Pha 2; chọn ưu tiên sau khi có số liệu Kaggle CPU.

## GitHub

Mã nguồn sẵn để đưa lên repository công khai. Nên commit theo từng bước có nghĩa: `chore: scaffold`, `feat: auth and tasks`, `test: API contracts`, `docs: architecture and benchmark`. Không commit `.env`, `data/` hoặc token. Đường dẫn GitHub công khai do nhóm tạo và thêm vào README khi xuất bản.
