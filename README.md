# Todo List API — Pha 1

Dịch vụ RESTful API quản lý danh sách công việc cá nhân (Todo List) xây dựng trên nền tảng **FastAPI**, **SQLAlchemy** và **SQLite**, hỗ trợ đóng gói và triển khai an toàn bằng **Docker**.

Mục tiêu cốt lõi của Pha 1 là phân tách dữ liệu tuyệt đối giữa các tài khoản: người dùng chỉ có thể thao tác trên công việc do chính mình tạo ra, không thể xem, sửa hoặc xóa dữ liệu của người khác ngay cả khi biết chính xác ID.

## Tài liệu liên quan

- [Đặc tả OpenAPI tĩnh](openapi.json) — hợp đồng của 8 endpoint.
- [Báo cáo kiểm thử chức năng và lịch sử lỗi](BUGS.md) — bằng chứng P0/P1 và các cảnh báo dependency còn mở.
- [Phân tích kiểm thử tải Kaggle](kaggle/KaggleTest.md) — phương pháp, dữ liệu từng lần chạy, biểu đồ và diễn giải.
- [Notebook Kaggle](kaggle/load_test.ipynb) — tự động khởi động API, chạy smoke/baseline và xuất kết quả.

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

Bộ kiểm thử hiện tại thu thập **96 trường hợp**, bao phủ nghiệp vụ Domain, API/JWT, phân lập dữ liệu, ranh giới kiến trúc, công cụ benchmark và notebook Kaggle:

```bash
python -m pytest -q
```

Có thể chạy riêng các nhóm chính:

```bash
python -m pytest -q tests/test_api.py tests/test_domain.py tests/test_architecture.py
python -m pytest -q tests/test_benchmark.py tests/test_load_test_notebook.py
```

Kết quả kiểm thử chức năng đã kiểm chứng và cảnh báo dependency được lưu trong [BUGS.md](BUGS.md).

---

## 7. Kiểm thử tải trên Kaggle CPU (Benchmark)

Kịch bản đo lường hiệu năng tải được định nghĩa tại [`kaggle/benchmark.py`](kaggle/benchmark.py). Kịch bản tạo tài khoản và thực hiện lặp liên tục chu trình (POST $\rightarrow$ GET $\rightarrow$ DELETE).

### Chạy nhanh bằng script

Sau khi API đang chạy tại `http://127.0.0.1:8000`, có thể chạy một lần đo thủ công:

```bash
python kaggle/benchmark.py \
  --concurrency 4 \
  --iterations 100 \
  --warmup-iterations 5 \
  --output-json results/run.json
```

Để tái lập đầy đủ ma trận chính thức, dùng [notebook Kaggle](kaggle/load_test.ipynb): concurrency 1/4/8, 100 vòng/user, 3 lần/mức và 5 vòng warm-up/user.

### Kết quả batch `20261027T154217Z-a5e499c1`

| Concurrency | Vòng/user × số lần | Throughput TB (req/s) | p50 gộp (ms) | p95 gộp (ms) | Tỷ lệ lỗi |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | 100 × 3 | 71.23 | 15.03 | 22.43 | 0.00% |
| 4 | 100 × 3 | 77.05 | 28.20 | 136.66 | 0.00% |
| 8 | 100 × 3 | 81.92 | 35.95 | 350.79 | 0.00% |

Cả smoke test và **9/9 baseline** đều hoàn tất: 3.900 chu trình chính thức, 11.700 request task thành công và 0 request thất bại. Throughput chỉ tăng khoảng 15% từ concurrency 1 lên 8, trong khi p95 tăng mạnh; kết quả cho thấy độ trễ đuôi suy giảm khi tăng tải nhưng chưa xác định riêng SQLite là nút thắt.

Số liệu trên lấy từ request gốc của ba lần chạy tại mỗi mức tải; smoke, warm-up, đăng ký và đăng nhập không được gộp vào baseline. Xem [báo cáo phân tích đầy đủ](kaggle/KaggleTest.md), [CSV tổng hợp](kaggle/20261027T154217Z-a5e499c1/runs.csv) và [thư mục bằng chứng](kaggle/20261027T154217Z-a5e499c1/).


### Hướng dẫn chạy kiểm thử tải trên Kaggle

Notebook [kaggle/load_test.ipynb](kaggle/load_test.ipynb) quản lý server, chạy tải và xuất biểu đồ:

1. Import notebook lên Kaggle, dùng CPU và bật Internet nếu cần clone repository/cài dependencies.
2. Ở cell cấu hình, kiểm tra `REPO_URL` và điền `SOURCE_COMMIT` của phiên bản đã push có benchmark đợt 3. Nếu dùng source từ Dataset, đặt `SOURCE_DIR` trỏ đến thư mục chứa `app/` và `requirements.txt`.
3. Chạy các cell theo thứ tự. Notebook ghi phiên bản Python thực tế; nếu cần Python 3.12, đặt `BASE_PYTHON` trỏ tới interpreter 3.12 đã cài.
4. Kiểm tra smoke test trước baseline. Mặc định smoke là 1 user × 25 vòng; baseline là concurrency 1/4/8, mỗi mức 100 vòng/user và lặp 3 lần. Mỗi lần chạy có 5 vòng warm-up/user riêng.
5. Tải ZIP ở cell cuối, hoặc lấy thư mục `/kaggle/working/benchmark-results/<batch_id>/`.

Mỗi lần đo dùng database SQLite mới và secret ngẫu nhiên, khởi động Uvicorn, chờ `/health`, rồi chạy benchmark. Server được dừng trong `finally` trước khi xóa database. Log nằm trong `runs/<run_label>/`; từng báo cáo có tên `smoke.json`, `c1-r1.json`, v.v. `environment.json` ghi cấu hình server/database và dấu vết mã nguồn. Không ghi secret vào báo cáo.

`runs.csv` giữ từng lần baseline, kể cả lần lỗi hoặc chưa chạy. Ba biểu đồ trong `charts/` thể hiện throughput thành công, p95 từng method và tỷ lệ lỗi. Warm-up và smoke không gộp vào baseline; không lấy trung bình các p95 làm p95 gộp. Biểu đồ throughput/p95 chỉ dùng các lần hoàn tất có cấu hình khớp; CSV và biểu đồ lỗi vẫn giữ thông tin các lần còn lại.

