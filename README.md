# Todo List API — Pha 1

Dịch vụ RESTful API quản lý danh sách công việc cá nhân (Todo List) xây dựng trên nền tảng **FastAPI**, **SQLAlchemy** và **SQLite**, hỗ trợ đóng gói và triển khai an toàn bằng **Docker**.

Mục tiêu cốt lõi của Pha 1 là phân tách dữ liệu tuyệt đối giữa các tài khoản: người dùng chỉ có thể thao tác trên công việc do chính mình tạo ra, không thể xem, sửa hoặc xóa dữ liệu của người khác ngay cả khi biết chính xác ID.

---

## 1. Nghiệp vụ & Phạm vi (Pha 1)

- **Xác thực:** Đăng ký tài khoản bằng email (không phân biệt chữ hoa/thường) và mật khẩu; đăng nhập nhận token JWT (Bearer token, hạn 60 phút).
- **Quản lý công việc (CRUD):**
  - Tạo công việc mới (tiêu đề bắt buộc, mô tả tùy chọn).
  - Lấy danh sách công việc của tài khoản (sắp xếp theo ID giảm dần).
  - Xem chi tiết công việc.
  - Cập nhật trạng thái hoàn thành (`is_done: true/false`).
  - Xóa công việc.
- **Bảo mật dữ liệu:** Truy cập công việc thuộc tài khoản khác hoặc không tồn tại đều trả về mã `404 Not Found`.

---

## 2. Kiến trúc 3 tầng (Layered Architecture)

Ứng dụng được thiết kế phân tầng rõ ràng nhằm đảm bảo tính độc lập và khả năng kiểm thử:

```text
[ Tầng API / Application ]
  ├── FastAPI Routing, Dependency Injection (app/factory.py, app/main.py)
  └── Pydantic Schemas & Validation (app/api/schemas.py)
              ↓
[ Tầng Nghiệp vụ (Domain) ]
  ├── Entity Models (app/domain/models.py)
  ├── Business Logic (app/domain/services.py)
  └── Repository Ports / Protocol (app/domain/ports.py)
              ↓
[ Tầng Hạ tầng (Infrastructure) ]
  ├── Repository Implementations (app/infrastructure/repositories.py)
  ├── Database Engine & SQLAlchemy Tables (app/infrastructure/database.py, tables.py)
  └── Security: PBKDF2 Password Hasher & PyJWT Codec (app/infrastructure/security.py)
              ↓
         SQLite Database (data/todo.db)
```

- **Domain:** Thuần Python chuẩn (standard library), hoàn toàn không phụ thuộc vào FastAPI, SQLAlchemy hay framework ngoài.
- **Application:** Khởi tạo qua `factory.py`, kiểm soát xác thực token qua middleware tập trung trước khi chuyển tiếp `user_id` đã xác thực vào service.
- **Infrastructure:** Quản lý ánh xạ ORM tới cơ sở dữ liệu SQLite và thuật toán mã hóa mật khẩu PBKDF2 với salt ngẫu nhiên.

---

## 3. Công nghệ & Yêu cầu môi trường

- **Ngôn ngữ:** Python 3.12+
- **Framework & Thư viện chính:**
  - `fastapi` & `uvicorn`: Web framework và ASGI server
  - `SQLAlchemy`: ORM quản lý dữ liệu
  - `PyJWT`: Ký và xác thực token JWT (thuật toán HS256)
  - `pytest` & `httpx`: Kiểm thử tự động
- **Cơ sở dữ liệu:** SQLite
- **Triển khai:** Docker (chạy non-root user `appuser`, volume SQLite bền vững)

---

## 4. Đặc tả API (8 Endpoints)

API giao tiếp bằng định dạng JSON. Tất cả endpoint công việc yêu cầu header: `Authorization: Bearer <access_token>`.

- **Swagger UI:** `http://localhost:8000/docs`
- **OpenAPI JSON:** [`openapi.json`](openapi.json) hoặc `http://localhost:8000/openapi.json`

| STT | Method | Endpoint | Xác thực | Mô tả | Mã thành công | Mã lỗi chính |
|:---:|:---:|:---|:---:|:---|:---:|:---|
| 1 | `GET` | `/health` | Không | Kiểm tra trạng thái hệ thống | `200` | — |
| 2 | `POST` | `/api/auth/register` | Không | Đăng ký tài khoản mới | `201` | `400`, `409`, `422` |
| 3 | `POST` | `/api/auth/login` | Không | Đăng nhập lấy access token | `200` | `401`, `422` |
| 4 | `GET` | `/api/tasks` | `BearerAuth` | Lấy danh sách công việc của user | `200` | `401` |
| 5 | `POST` | `/api/tasks` | `BearerAuth` | Tạo công việc mới | `201` | `400`, `401`, `422` |
| 6 | `GET` | `/api/tasks/{task_id}` | `BearerAuth` | Xem chi tiết 1 công việc | `200` | `401`, `404` |
| 7 | `PATCH` | `/api/tasks/{task_id}` | `BearerAuth` | Đổi trạng thái hoàn thành (`is_done`) | `200` | `401`, `404`, `422` |
| 8 | `DELETE`| `/api/tasks/{task_id}` | `BearerAuth` | Xóa một công việc | `204` | `401`, `404` |

---

## 5. Hướng dẫn chạy và Triển khai

### Cách 1: Chạy bằng Docker (Khuyên dùng)

Container được thiết lập chạy bằng **non-root user** (`appuser`), dữ liệu SQLite được lưu bền vững qua Docker Volume:

```bash
# 1. Build Docker image
docker build -t todo-list-api .

# 2. Khởi chạy container với volume lưu trữ dữ liệu
docker run -d \
  --name todo-api \
  -p 8000:8000 \
  -e TOKEN_SECRET="thay-bang-chuoi-ngau-nhien-it-nhat-32-ky-tu" \
  -v todo-data:/app/data \
  todo-list-api
```

> **Lưu ý về tính bền vững:** File dữ liệu `todo.db` nằm tại `/app/data/todo.db`. Khi dừng hoặc xóa container (`docker rm -f todo-api`), toàn bộ dữ liệu người dùng và công việc vẫn được bảo toàn nguyên vẹn trong volume `todo-data`.

### Cách 2: Chạy trực tiếp cục bộ (Local)

**Trên Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

$env:TOKEN_SECRET = "chuoi-bi-mat-ngau-nhien-it-nhat-32-ky-tu"
uvicorn app.main:app --reload --port 8000
```

**Trên Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

export TOKEN_SECRET="chuoi-bi-mat-ngau-nhien-it-nhat-32-ky-tu"
uvicorn app.main:app --reload --port 8000
```

---

## 6. Chạy Kiểm thử (Testing)

Chạy kiểm thử tự động bao phủ xác thực JWT, bảo vệ endpoint và phân lập dữ liệu giữa các tài khoản:

```bash
python -m pytest -q
```

---

## 7. Kiểm thử tải trên Kaggle CPU (Benchmark)

Kịch bản đo lường hiệu năng tải được định nghĩa tại [`kaggle/benchmark.py`](kaggle/benchmark.py). Kịch bản tạo tài khoản và thực hiện lặp liên tục chu trình (POST $\rightarrow$ GET $\rightarrow$ DELETE).

### Cách thực hiện trên Kaggle Notebook:
1. Tạo Kaggle Notebook (Accelerator: None / CPU).
2. Cài đặt phụ thuộc: `pip install -r requirements.txt`.
3. Chạy backend Uvicorn dưới nền.
4. Chạy script đo lường với các mức concurrency:
   ```bash
   python kaggle/benchmark.py --concurrency 1 --iterations 25
   python kaggle/benchmark.py --concurrency 4 --iterations 25
   python kaggle/benchmark.py --concurrency 8 --iterations 25
   ```

### Bảng kết quả đo lường (Chờ số liệu từ Người 3):

| Mức tải (Concurrency) | Số vòng (Iterations) | Throughput (req/s) | p50 Latency (ms) | p95 Latency (ms) | Tỷ lệ lỗi (Error %) |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | 25 | *(Đang cập nhật)* | *(Đang cập nhật)* | *(Đang cập nhật)* | 0% |
| 4 | 25 | *(Đang cập nhật)* | *(Đang cập nhật)* | *(Đang cập nhật)* | 0% |
| 8 | 25 | *(Đang cập nhật)* | *(Đang cập nhật)* | *(Đang cập nhật)* | 0% |

*(Bảng số liệu sẽ được Người 3 cập nhật sau khi hoàn tất phiên đo tải thực tế trên Kaggle).*

---

## 8. Định hướng Kế hoạch Pha 2

| Thuộc tính | Thách thức ở Pha 1 | Đề xuất cải tiến Pha 2 | Cách kiểm chứng |
|---|---|---|---|
| **Hiệu năng** | SQLite một writer giới hạn tốc độ ghi đồng thời | Chuyển sang PostgreSQL, đánh chỉ mục kép `(user_id, id)`, hỗ trợ phân trang cho danh sách task | Đo p95 latency và throughput khi tăng tải |
| **Tin cậy** | Chưa có migration khi cập nhật schema | Tích hợp Alembic Migration, bổ sung health check sâu cho DB | Thử nghiệm migration dữ liệu tự động |
| **Bảo mật** | Chưa có cơ chế thu hồi token trước hạn | Bổ sung Refresh Token / Token Blacklist, giới hạn tần suất gọi API (Rate Limiting) | Thử nghiệm token hết hạn/thu hồi và brute-force |
| **Bảo trì** | Chưa tự động hóa quy trình kiểm thử | Xây dựng pipeline CI/CD (GitHub Actions) tự động chạy `pytest` khi mở Pull Request | Tỷ lệ pass test và thời gian phản hồi CI |
