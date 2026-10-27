# Todo List API — Pha 1

Dịch vụ quản lý công việc cá nhân. Mỗi tài khoản chỉ xem và sửa công việc của mình. API giao tiếp bằng JSON; Swagger UI có tại `/docs`, tài liệu OpenAPI JSON tại `/openapi.json` và bản đặc tả tĩnh trong [`openapi.json`](openapi.json).

Bài toán đặt ra là xây dựng một hệ thống để mỗi người dùng có thể tạo công việc, theo dõi danh sách, cập nhật trạng thái hoàn thành và xóa những công việc không còn cần thiết.

Yêu cầu quan trọng nhất là tách biệt dữ liệu giữa các tài khoản. Người dùng chỉ được xem và thao tác trên công việc của mình. Ví dụ, tài khoản A tạo một công việc thì tài khoản B không được xem, cập nhật hay xóa công việc đó, kể cả khi biết ID.


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

## Kế hoạch Pha 2

| Thuộc tính | Vấn đề cần kiểm chứng | Cải tiến dự kiến | Cách đo |
|---|---|---|---|
| Hiệu năng | GET danh sách lớn và ghi đồng thời có thể chậm | Phân trang; chỉ mục theo `(user_id, id)`; cân nhắc PostgreSQL | p95 GET/POST, throughput và tỷ lệ lỗi ở cùng mức tải |
| Tin cậy | SQLite không phù hợp nhiều writer; chưa có migration | PostgreSQL, Alembic migration, health check DB | Thử ghi đồng thời, khởi động lại, kiểm tra toàn vẹn dữ liệu |
| Bảo mật | Token chưa thu hồi; chưa giới hạn đăng nhập | Refresh/revocation, rate limit, kiểm tra cấu hình secret | Thử token hết hạn/thu hồi, brute-force, truy cập chéo tài khoản |
| Bảo trì | Khi tăng chức năng cần hợp đồng rõ hơn | Unit test nghiệp vụ, integration test DB, CI | Tỷ lệ pass và thời gian test trên mỗi commit |

Đây là danh sách giả thuyết cho Pha 2; chọn ưu tiên sau khi có số liệu Kaggle CPU.
