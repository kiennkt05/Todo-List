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

Để lưu báo cáo cùng dữ liệu từng request (thư mục cha được tạo tự động):

```bash
python kaggle/benchmark.py --concurrency 2 --iterations 3 --output-json results/run.json
```

Mỗi bản ghi có `worker_id`, `iteration` (đều bắt đầu từ 0), `method`, `status`, `latency_ms`, `success`, `error_type` và `error_message`. `status` là `null` nếu chưa nhận được HTTP response. Request chỉ thành công khi status đúng, response hợp lệ và (với GET) thấy task vừa tạo. Không lưu body, mật khẩu hoặc token vào các bản ghi. Báo cáo JSON và terminal dùng chung dữ liệu tổng hợp:

- `expected_requests`: `3 × concurrency × iterations`, không gồm đăng ký/login.
- `attempted_requests`, `successful_requests`, `failed_requests`: số request task có bản ghi, thành công và thất bại, bao gồm cả timeout/lỗi mạng/response không hợp lệ.
- `skipped_requests`: POST lỗi làm bỏ qua GET/DELETE, cộng 2 cho mỗi vòng đó.
- `completed_cycles`: chỉ tăng khi tạo thành công, GET thành công và thấy task vừa tạo, DELETE thành công. GET lỗi hoặc không thấy task vẫn thử DELETE.
- `expected_cycles`, `incomplete_cycles`: số vòng mục tiêu và số vòng không hoàn tất thành công.
- `unrecorded_requests`: phần công việc chưa có bản ghi và không thuộc số request bị bỏ qua. Khi dừng sớm, không được coi số này là request thành công hoặc khẳng định chưa tới server.
- `throughput_rps`: mọi request có bản ghi / thời gian đo; `success_throughput`: request thành công / thời gian đo, cùng đơn vị req/s. `error_rate`: request thất bại / request có bản ghi (từ 0 đến 1).
- `methods`: `n` là mọi mẫu của method; `successful_requests`/`failed_requests` là số thành công/lỗi. Mean/p50/p95 **chỉ tính trên mẫu thành công**; không có mẫu thành công thì ghi `null` (terminal hiển thị `n/a`). `measurements` giữ dữ liệu từng request, kể cả lỗi.
- `failures_by_status`, `failures_by_error_type`: số lỗi theo HTTP status và loại lỗi, có ở cấp toàn báo cáo và từng method. `no_response` nghĩa là chưa nhận status; status `200` vẫn có thể nằm trong nhóm lỗi nếu JSON sai hoặc thiếu task.

Ví dụ trên khi thành công có 6 vòng hoàn thành, 18 request dự kiến/thực hiện/thành công, 0 request lỗi hoặc bị bỏ qua. Khi chưa đo được thời gian (setup thất bại), throughput là `null`; khi chưa có request task, `error_rate` là `null`.

Các loại lỗi request:

| `error_type` | Ý nghĩa |
|---|---|
| `http_error` | Status khác kỳ vọng; ưu tiên phân loại theo status ngay cả khi body lỗi không phải JSON |
| `timeout` | Hết thời gian chờ kết nối hoặc đọc response (`--timeout`, mặc định 30 giây) |
| `network_error` | Không kết nối được, kết nối bị đóng hoặc response bị ngắt khi đọc |
| `invalid_response` | JSON lỗi, sai cấu trúc/thiếu ID hoặc token cần thiết, DELETE 204 có body |
| `consistency_error` | GET trả 200 với danh sách hợp lệ nhưng không có task vừa tạo |

Script không tự retry. POST thất bại bỏ qua hai bước còn lại; GET lỗi vẫn thử DELETE. Một task có thể còn lại nếu POST đã tới server nhưng client không nhận được ID, DELETE thất bại hoặc worker bị gián đoạn.

`run_status` có ba giá trị:

- `completed`: toàn bộ vòng thành công; exit code 0.
- `completed_with_errors`: các worker kết thúc nhưng có request/vòng lỗi; exit code 1.
- `aborted`: setup thất bại, worker gặp lỗi bất ngờ hoặc người chạy nhấn Ctrl+C; exit code 1. `run_errors` ghi giai đoạn (`setup`, `measurement`, `worker`), worker liên quan và nguyên nhân. Lỗi lập trình bất ngờ vẫn in traceback ra stderr.

Khi một worker lỗi bất ngờ, báo cáo giữ các request đã ghi của worker đó và kết quả các worker khác. Khi nhận Ctrl+C, script hủy worker chưa chạy, chờ worker đang chạy kết thúc vòng hiện tại để thu dữ liệu rồi ghi báo cáo. Đăng ký/login không tính vào thống kê task; nếu setup lỗi, báo cáo `aborted` có 0 request task và chi tiết lỗi setup. Nếu có `--output-json`, báo cáo được ghi trước khi script trả exit code; bỏ tùy chọn này thì chỉ in terminal. Cần cho phép script kết thúc xử lý lỗi và ghi file: việc cưỡng bức kill tiến trình hoặc nơi lưu file không ghi được không bảo đảm có báo cáo.

Chạy các test cho công cụ đo (mock timeout/lỗi mạng/response, báo cáo setup lỗi và worker gián đoạn):

```bash
python -m pytest -q tests/test_benchmark.py
```

### Metadata, warm-up và timeout

```bash
python kaggle/benchmark.py \
  --concurrency 2 \
  --iterations 3 \
  --warmup-iterations 2 \
  --timeout 10 \
  --output-json results/local-with-warmup.json
```

Thứ tự chạy: chuẩn bị tài khoản → warm-up trên các tài khoản đó → đợi tất cả worker warm-up hoàn tất → bắt đầu đo chính thức. Warm-up dùng cùng workload POST → GET → DELETE và được lưu riêng trong trường `warmup` (gồm bộ đếm, thời gian, request và lỗi). Với ví dụ trên, warm-up có **12 request / 4 vòng**, còn báo cáo cấp ngoài chỉ tính **18 request / 6 vòng**. `duration_seconds` và throughput ở cấp ngoài không bao gồm setup, thu thập metadata hoặc warm-up. Task warm-up được xóa sau mỗi vòng thành công.

`--warmup-iterations` mặc định `0` (không warm-up, trường `warmup` là `null`), phải là số nguyên không âm. Nếu warm-up có lỗi HTTP, dữ liệu không nhất quán, lỗi bất ngờ hoặc bị ngắt, script lưu dữ liệu warm-up và dừng với `run_status=aborted`, `run_errors` có `stage=warmup`, exit code 1. Phần đo chính thức có 0 request và thời gian 0; không gộp số liệu warm-up vào đó. Nếu setup lỗi trước warm-up, `warmup` cũng là `null`.

`--timeout` chấp nhận số giây dương, hữu hạn (ví dụ `0.5`, `10`, `30`); áp dụng cho đăng ký, đăng nhập, warm-up và phần đo. Đây là timeout socket của thư viện HTTP cho kết nối/đọc dữ liệu, không phải giới hạn thời gian cho toàn bộ đợt benchmark.

Báo cáo có thêm metadata tại cấp ngoài:

| Trường | Ý nghĩa |
|---|---|
| `run_id`, `started_at_utc` | UUID riêng cho mỗi lần chạy và thời điểm UTC trước setup, định dạng ISO 8601 kết thúc bằng `Z` |
| `git_commit`, `git_dirty` | Commit và trạng thái thay đổi của repository chứa script; tính cả file chưa track, bỏ qua file bị Git ignore. Không lấy được giá trị thì ghi `null` |
| `python_version`, `dependency_versions` | Python và tên/phiên bản các distribution đã cài trong môi trường **client benchmark**; không chứa URL cài đặt |
| `platform`, `cpu_count` | Nền tảng và số CPU do `os.cpu_count()` báo cáo; không đồng nghĩa với quota CPU thực tế được cấp |
| `concurrency`, `iterations`, `warmup_iterations`, `timeout_seconds` | Các tham số thực tế của lần chạy |

Script đọc Git theo thư mục mã nguồn, không theo thư mục đang gọi lệnh, và vẫn chạy được khi Git không có hoặc mã được tải về dưới dạng ZIP. Metadata không thu thập biến môi trường, token, mật khẩu hoặc URL API; CLI từ chối base URL chứa thông tin đăng nhập, query hoặc fragment. Số worker Uvicorn, chính sách reset/dùng lại database và môi trường server cần được ghi riêng trong notebook; client không tự suy ra các thông tin này. Giữ cùng cấu hình warm-up, timeout và database khi so sánh các lần đo.

### Notebook chạy tải trên Kaggle

Notebook [kaggle/load_test.ipynb](kaggle/load_test.ipynb) quản lý server, chạy tải và xuất biểu đồ:

1. Import notebook lên Kaggle, dùng CPU và bật Internet nếu cần clone repository/cài dependencies.
2. Ở cell cấu hình, kiểm tra `REPO_URL` và điền `SOURCE_COMMIT` của phiên bản đã push có benchmark đợt 3. Nếu dùng source từ Dataset, đặt `SOURCE_DIR` trỏ đến thư mục chứa `app/` và `requirements.txt`.
3. Chạy các cell theo thứ tự. Notebook ghi phiên bản Python thực tế; nếu cần Python 3.12, đặt `BASE_PYTHON` trỏ tới interpreter 3.12 đã cài.
4. Kiểm tra smoke test trước baseline. Mặc định smoke là 1 user × 25 vòng; baseline là concurrency 1/4/8, mỗi mức 100 vòng/user và lặp 3 lần. Mỗi lần chạy có 5 vòng warm-up/user riêng.
5. Tải ZIP ở cell cuối, hoặc lấy thư mục `/kaggle/working/benchmark-results/<batch_id>/`.

Mỗi lần đo dùng database SQLite mới và secret ngẫu nhiên, khởi động Uvicorn, chờ `/health`, rồi chạy benchmark. Server được dừng trong `finally` trước khi xóa database. Log nằm trong `runs/<run_label>/`; từng báo cáo có tên `smoke.json`, `c1-r1.json`, v.v. `environment.json` ghi cấu hình server/database và dấu vết mã nguồn. Không ghi secret vào báo cáo.

`runs.csv` giữ từng lần baseline, kể cả lần lỗi hoặc chưa chạy. Ba biểu đồ trong `charts/` thể hiện throughput thành công, p95 từng method và tỷ lệ lỗi. Warm-up và smoke không gộp vào baseline; không lấy trung bình các p95 làm p95 gộp. Biểu đồ throughput/p95 chỉ dùng các lần hoàn tất có cấu hình khớp; CSV và biểu đồ lỗi vẫn giữ thông tin các lần còn lại.

Nếu ngắt ma trận giữa chừng, có thể chạy tiếp cell tổng hợp/biểu đồ để xem kết quả đã có. Để chạy một batch mới, chạy lại từ cell cấu hình; notebook không ghi đè kết quả cũ. Khi kernel bị cưỡng bức tắt, `finally` không được bảo đảm chạy. Server và client cùng máy nên kết quả phản ánh cấu hình notebook đó.

---

## 8. Định hướng Kế hoạch Pha 2

| Thuộc tính | Thách thức ở Pha 1 | Đề xuất cải tiến Pha 2 | Cách kiểm chứng |
|---|---|---|---|
| **Hiệu năng** | SQLite một writer giới hạn tốc độ ghi đồng thời | Chuyển sang PostgreSQL, đánh chỉ mục kép `(user_id, id)`, hỗ trợ phân trang cho danh sách task | Đo p95 latency và throughput khi tăng tải |
| **Tin cậy** | Chưa có migration khi cập nhật schema | Tích hợp Alembic Migration, bổ sung health check sâu cho DB | Thử nghiệm migration dữ liệu tự động |
| **Bảo mật** | Chưa có cơ chế thu hồi token trước hạn | Bổ sung Refresh Token / Token Blacklist, giới hạn tần suất gọi API (Rate Limiting) | Thử nghiệm token hết hạn/thu hồi và brute-force |
| **Bảo trì** | Chưa tự động hóa quy trình kiểm thử | Xây dựng pipeline CI/CD (GitHub Actions) tự động chạy `pytest` khi mở Pull Request | Tỷ lệ pass test và thời gian phản hồi CI |
