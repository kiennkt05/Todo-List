# BUGS — Kết quả kiểm tra P0

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
