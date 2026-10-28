# BUGS — Kết quả kiểm tra P0 và P1

## P1 — Kiểm thử nghiệp vụ, xác thực và ranh giới Domain

Ngày thực hiện: **2026-10-27** (Asia/Bangkok).

### Môi trường và phạm vi thay đổi

- Baseline commit: `4bf04640509df50ea3acb3c405f18a61bf4db6bd`, branch `minhnq44-dev`.
- Kết quả dưới đây áp dụng cho baseline cộng các thay đổi kiểm thử P1 trong working tree, chưa tạo commit mới.
- Python **3.12.16**, pytest **8.3.5**, SQLite file tạm riêng cho từng test API qua `tmp_path`.
- FastAPI **0.115.12**, SQLAlchemy **2.0.40**, PyJWT **2.10.1**, httpx **0.28.1**, Pydantic **2.14.1**, Starlette **0.46.2**, AnyIO **4.15.1**. Dependencies không đổi so với snapshot P0 bên dưới.
- Đã đọc 3 test API và 2 test Domain có sẵn. Mở rộng các test CRUD/ownership hiện có; giữ test OpenAPI và 2 test Domain; chuyển các assertion thiếu/hỏng token sang ma trận xác thực để không viết trùng kịch bản.
- Bổ sung các trường hợp API còn thiếu trong `tests/test_api.py` và 2 test kiến trúc trong `tests/test_architecture.py`. Tổng số trường hợp pytest thu thập tăng từ **5 lên 37** (bao gồm các biến thể parametrized).
- Không thay đổi mã ứng dụng, schema API hoặc dependencies trong P1.

### Lệnh chạy và kết quả tổng hợp

Chạy tại thư mục gốc repository:

```bash
source .venv/bin/activate
pytest -q -rA
```

`-rA` yêu cầu pytest liệt kê kết quả từng trường hợp, không thay đổi điều kiện pass/fail.

Output tổng hợp thực tế:

```text
.....................................                                    [100%]
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/starlette/testclient.py:37
  DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = typing.Callable[[], typing.ContextManager[anyio.abc.BlockingPortal]]

37 passed, 1 warning in 6.64s
```

**Exit code 0; 37 passed; 0 failed; 0 errors; không có test skip/xfail.**

| File | Số trường hợp pytest | Kết quả |
|---|---:|---|
| `tests/test_api.py` | 33 | 33 PASS |
| `tests/test_domain.py` | 2 | 2 PASS |
| `tests/test_architecture.py` | 2 | 2 PASS |
| **Tổng** | **37** | **37 PASS** |

Test kiến trúc còn chạy lại 2 unittest Domain trong subprocess cô lập. Hai lượt chạy nội bộ này không được cộng thêm vào con số 37 trường hợp pytest.

### Đối chiếu yêu cầu P1 với kết quả từng nhóm test

Tên test API trong bảng thuộc `tests/test_api.py`, trừ khi ghi đường dẫn khác.

| Test / nhóm test | Số trường hợp | Nội dung và HTTP status đã xác nhận | Kết quả |
|---|---:|---|---|
| `test_authentication_and_task_lifecycle` | 1 | Đăng ký `201`, login `200`; tạo task `201`, đúng owner, trim title/description, mặc định chưa hoàn thành; GET chi tiết/danh sách `200`; PATCH `true` rồi `false` đều `200`, đọc lại xác nhận dữ liệu; danh sách mới nhất trước; DELETE `204` body rỗng; GET sau xóa `404`, task khác vẫn còn | PASS |
| `test_owner_isolation_and_bad_credentials` | 1 | B list được `200 []`; B GET/PATCH/DELETE task của A đều `404`; sau từng thao tác A vẫn GET được `200` với toàn bộ task không đổi; sai mật khẩu `401`; email trùng nguyên bản/khác hoa thường/thừa khoảng trắng đều `409`; đăng ký trùng không ghi đè mật khẩu cũ | PASS |
| `test_openapi_marks_protected_operations` | 1 | GET/POST tasks có `BearerAuth` trong OpenAPI; login không bị đánh dấu yêu cầu token; tái sử dụng test cũ | PASS |
| `test_registration_normalizes_email_and_login_accepts_normalized_email` | 1 | Đăng ký email có chữ hoa và khoảng trắng trả email chuẩn hóa, chỉ có `id/email`; login bằng email ban đầu và email chuẩn hóa đều `200`, token type `bearer`; email chưa đăng ký trả `401` | PASS |
| `test_registration_rejects_invalid_input` | 3 | `invalid-email`: `400`; `short-password` (7 ký tự): `422`; `missing-password`: `422`; kiểm tra kiểu chi tiết lỗi hoặc vị trí trường bị lỗi | PASS 3/3 |
| `test_tasks_reject_invalid_authentication` | 14 | 7 dạng xác thực lỗi × GET/POST `/api/tasks`, chi tiết ở bảng bên dưới; đều `401`, có `WWW-Authenticate: Bearer` và thông báo lỗi; dùng token hợp lệ đọc lại xác nhận không tạo task ngoài ý muốn | PASS 14/14 |
| `test_task_rejects_invalid_title` | 5 | `missing-title`, `null-title`, `empty-title`: `422`; `whitespace-title`: `400`; `too-long-title` (201 ký tự): `422`; kiểm tra chi tiết lỗi và không lưu task không hợp lệ | PASS 5/5 |
| `test_task_accepts_maximum_title_length_and_null_description` | 1 | Title đúng 200 ký tự, description `null`: `201`; đọc lại task đúng nội dung | PASS |
| `test_nonexistent_task_returns_not_found` | 3 | GET/PATCH/DELETE ID 999 trong DB mới đều `404`, body `{"detail":"Task not found"}` | PASS 3/3 |
| `test_invalid_status_update_does_not_change_task` | 3 | Body `{}`, `{"is_done":null}`, `{"is_done":"not-a-boolean"}` đều `422`, lỗi chỉ đúng trường `is_done`; GET lại xác nhận toàn bộ task không đổi | PASS 3/3 |
| `tests/test_domain.py::DomainTests::test_registration_and_login` | 1 | Giữ test cũ: chuẩn hóa email, login thành công; email trùng, sai mật khẩu và email sai gây đúng exception nghiệp vụ | PASS |
| `tests/test_domain.py::DomainTests::test_task_ownership_and_validation` | 1 | Giữ test cũ: trim dữ liệu, đổi trạng thái, chặn truy cập/xóa chéo owner, từ chối title trắng, xóa thành công | PASS |
| `tests/test_architecture.py::test_domain_imports_only_standard_library_and_domain_modules` | 1 | Quét AST các file Python trong `app/domain`; chỉ cho phép import thư viện chuẩn hoặc module Domain; không phụ thuộc API, infrastructure, FastAPI, SQLAlchemy hay Pydantic | PASS |
| `tests/test_architecture.py::test_domain_tests_run_without_site_packages` | 1 | Chạy 2 unittest Domain bằng Python `-I -S`, không nạp site-packages và bỏ qua cấu hình/PYTHONPATH bên ngoài; dùng repository giả trong bộ nhớ; subprocess exit code 0 | PASS |

### Ma trận JWT và GET/POST chưa xác thực

Mỗi biến thể bên dưới được pytest thu thập riêng cho GET và POST. Token lỗi có cấu trúc JWT được tạo từ claim của token tài khoản thực vừa đăng ký. Token hết hạn được ký bằng đúng secret, có `iat` cách hiện tại 2 giờ và `exp` cách hiện tại 1 giờ; không dùng sleep hoặc chờ hết hạn thật.

| Biến thể parametrized | Đầu vào | GET `/api/tasks` | POST `/api/tasks` |
|---|---|---|---|
| `missing` | Không có header Authorization | 401 — PASS | 401 — PASS |
| `empty` | `Authorization: Bearer ` không có token | 401 — PASS | 401 — PASS |
| `wrong-scheme` | Scheme `Basic` với token vốn hợp lệ | 401 — PASS | 401 — PASS |
| `malformed` | `Bearer not-a-jwt` | 401 — PASS | 401 — PASS |
| `wrong-signature` | JWT ký bằng secret khác | 401 — PASS | 401 — PASS |
| `expired` | JWT đúng chữ ký nhưng đã hết hạn | 401 — PASS | 401 — PASS |
| `missing-exp` | JWT đúng chữ ký nhưng thiếu claim `exp` | 401 — PASS | 401 — PASS |

### Bugs và cảnh báo sau lần chạy P1

- **Không có test P1 thất bại; không phát hiện bug mới trong các điều kiện được kiểm tra ở trên.** Các status `400/401/404/409/422` trong các kịch bản âm là kết quả mong đợi, không phải lỗi test.
- **BUG-001: Fixed.** Pytest thu thập và chạy được toàn bộ 37 trường hợp với cấu hình `pytest.ini` hiện có; không tái xuất hiện `ModuleNotFoundError: No module named 'app'`.
- **WARN-001: Open.** Vẫn có đúng 1 `DeprecationWarning` tại `starlette/testclient.py:37` khi import `TestClient`: Starlette 0.46.2 tham chiếu alias `anyio.abc.BlockingPortal` đã deprecated trong AnyIO 4.15.1. Đây là cảnh báo collection từ dependency, không phải lỗi của một test nghiệp vụ; không gây exit code khác 0. Tái hiện bằng lệnh chạy toàn bộ test ở trên. Hướng xử lý và bằng chứng gốc nằm ở phần WARN-001 của P0 bên dưới.

Kết quả P1 chỉ xác nhận các kịch bản trong ma trận này. Những nhận xét ngoài phạm vi các assertion này từ lần rà soát mã nguồn trước đó không được coi là đã khắc phục chỉ vì bộ test pass.

## Lịch sử kiểm tra P0

Ngày kiểm tra: **2026-10-27** (Asia/Bangkok).

Phạm vi: cài dependencies trên Python 3.12, chạy bộ kiểm thử hiện có, khởi động FastAPI bằng Uvicorn và kiểm tra HTTP thực tế. BUG-001 đã được sửa bằng cấu hình pytest và kiểm chứng lại ngày 2026-10-27; WARN-001 còn tồn tại. Bằng chứng trước khi sửa được giữ lại bên dưới.

## Baseline và môi trường

- Commit mã nguồn: `150c7cd3f04734832496dacdb8305a713003f48e`.
- Branch khi kiểm tra: `minhnq44-dev`.
- Hệ điều hành/kiến trúc: Linux x86_64.
- Python: **3.12.16**; pip: **26.2.2**.
- Virtual environment: `.venv/` trong thư mục dự án, đã được `.gitignore` loại trừ.
- Máy ban đầu chỉ có Python 3.13.3. Đã tải Python 3.12.16 bằng uv 0.13.6; runtime nằm trong `.venv/python-runtime/cpython-3.12.16-linux-x86_64-gnu/`.
- Dependencies được cài bằng `.venv/bin/python -m pip install --no-cache-dir --disable-pip-version-check -r requirements-dev.txt`.
- `python -m pip check`: **`No broken requirements found.`**

Các lệnh kiểm tra được chạy tại thư mục gốc repository sau khi kích hoạt môi trường:

```bash
source .venv/bin/activate
python --version
```

## Kết quả thực thi

| Hạng mục | Kết quả thực tế | Trạng thái |
|---|---|---|
| Cài `requirements-dev.txt` trên Python 3.12.16 | Cài thành công; không có dependency bị thiếu/xung đột theo `pip check` | PASS |
| `pytest -q` — trước khi sửa | Exit code 2; hai lỗi import trong giai đoạn collection | FAIL — BUG-001 |
| `pytest -q` — sau khi thêm `pytest.ini` | `5 passed, 1 warning in 1.00s`; exit code 0 | PASS, còn WARN-001 |
| `python -m pytest -q` — chạy đối chiếu | `5 passed, 1 warning in 1.01s`; exit code 0 | PASS, còn WARN-001 |
| Khởi động `uvicorn app.main:app` | `Application startup complete.` | PASS |
| `GET /health` qua HTTP localhost | `200`, body `{"status":"ok"}` | PASS |
| `GET /docs` qua HTTP localhost | `200`, `text/html; charset=utf-8`, có Swagger UI trong HTML | PASS |
| Khởi tạo SQLite | File database được tạo trong thư mục tạm | PASS |

**Đã đạt điều kiện chạy đúng `pytest -q` với cả 5 bài kiểm thử thành công trên Python 3.12.16.** Kết quả sau sửa sử dụng baseline commit nêu trên cộng với file `pytest.ini` mới trong working tree, chưa tạo commit mới. Điều này xác nhận mục kiểm thử, không thay thế việc tạo branch hoặc hoàn thiện traceability matrix của P0.

## BUG-001 — `pytest -q` không import được package `app`

- Trạng thái: **Fixed — đã kiểm chứng trong working tree ngày 2026-10-27**.
- Mức độ: Trung bình — chặn lệnh kiểm thử được hướng dẫn trong README.
- Vị trí xuất hiện: `tests/test_api.py:3`, `tests/test_domain.py:4`.

### Tái hiện

Trên baseline trước khi thêm `pytest.ini`, tại thư mục gốc dự án, dùng môi trường Python 3.12 đã cài dependencies:

```bash
source .venv/bin/activate
pytest -q
```

### Kỳ vọng

Thu thập và chạy đủ 5 bài kiểm thử, thoát với exit code 0.

### Thực tế

```text
ERROR collecting tests/test_api.py
tests/test_api.py:3: in <module>
    from app.factory import create_app
E   ModuleNotFoundError: No module named 'app'

ERROR collecting tests/test_domain.py
tests/test_domain.py:4: in <module>
    from app.domain.errors import EmailAlreadyExists, InvalidCredentials, InvalidInput, TaskNotFound
E   ModuleNotFoundError: No module named 'app'

ERROR tests/test_api.py
ERROR tests/test_domain.py
Interrupted: 2 errors during collection
1 warning, 2 errors in 0.25s
```

Exit code: **2**. Chưa bài kiểm thử nào được thực thi bởi lần gọi này.

### Chẩn đoán và cách chạy tạm thời

Baseline chưa có cấu hình pytest bổ sung thư mục gốc vào Python import path hoặc cấu hình cài package dự án. Khi gọi console script `pytest`, package `app` không được tìm thấy trong môi trường này. Gọi `python -m pytest` từ thư mục gốc đưa thư mục hiện tại vào Python import path, cho phép import `app` và chạy đủ bộ kiểm thử:

```bash
python -m pytest -q
```

```text
.....                                                                    [100%]
5 passed, 1 warning in 1.01s
```

### Khắc phục đã áp dụng

Thêm `pytest.ini` tại thư mục gốc repository:

```ini
[pytest]
pythonpath = .
```

Pytest thêm đường dẫn này vào `sys.path` trong phiên kiểm thử. Dấu `.` được tính theo thư mục gốc chứa cấu hình, giúp các test import được package `app` khi gọi console script. Không cần đặt `PYTHONPATH` thủ công mỗi lần chạy.

Đã kiểm chứng bằng đúng lệnh:

```bash
source .venv/bin/activate
pytest -q
```

```text
.....                                                                    [100%]
5 passed, 1 warning in 1.00s
```

Exit code: **0**. Cảnh báo còn lại là WARN-001 bên dưới.

## WARN-001 — DeprecationWarning từ Starlette/AnyIO

- Trạng thái: **Open**, không làm thất bại các bài kiểm thử.
- Môi trường tái hiện: Starlette 0.46.2, AnyIO 4.15.1.
- Vị trí: `.venv/lib/python3.12/site-packages/starlette/testclient.py:37`.

```text
DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated,
use anyio.from_thread.BlockingPortal instead.
```

Cảnh báo xuất hiện trong cả hai cách gọi pytest. Đây là cảnh báo từ dependency, không phải assertion thất bại của dự án. Cần kiểm tra tổ hợp phiên bản dependency khi xử lý; lần P0 này giữ nguyên requirements.

## Bằng chứng khởi động FastAPI và kiểm tra HTTP

Đã chạy tiến trình Uvicorn thật, không dùng TestClient cho bước này:

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 51233
```

Tiến trình nhận `TOKEN_SECRET` ngẫu nhiên sinh bằng `secrets.token_urlsafe(48)` và `DATABASE_URL` trỏ tới SQLite trong thư mục tạm. Secret không được ghi vào tài liệu. Cổng 51233 là cổng trống được chọn cho lần chạy này.

Trích log thực tế:

```text
INFO:     Started server process [8502]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:51233 (Press CTRL+C to quit)
INFO:     127.0.0.1:50658 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.1:50664 - "GET /docs HTTP/1.1" 200 OK
INFO:     Shutting down
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [8502]
```

Response `/health` đã được đọc và đối chiếu bằng JSON với `{"status":"ok"}`. Không phát hiện lỗi khởi động hoặc lỗi HTTP ở hai endpoint trên. Server được chủ động dừng bằng SIGTERM sau kiểm tra; subprocess trả `-15`, log xác nhận hoàn tất shutdown. Database tạm đã được dọn dẹp.

Để chạy lại thủ công tại thư mục gốc repository:

```bash
source .venv/bin/activate
export TOKEN_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export DATABASE_URL=sqlite:///./data/todo.db
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Ở terminal khác:

```bash
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/docs
```

## Snapshot dependencies đã cài

Kết quả `python -m pip freeze` để đối chiếu môi trường của lần kiểm tra này:

```text
annotated-types==0.8.0
anyio==4.15.1
certifi==2026.10.23
click==8.5.0
fastapi==0.115.12
greenlet==3.5.6
h11==0.16.0
httpcore==1.0.9
httpx==0.28.1
idna==3.20
iniconfig==2.3.1
packaging==26.3
pluggy==1.7.0
pydantic==2.14.1
pydantic_core==2.50.1
PyJWT==2.10.1
pytest==8.3.5
SQLAlchemy==2.0.40
starlette==0.46.2
typing-inspection==0.4.4
typing_extensions==4.16.0
uvicorn==0.34.2
```
