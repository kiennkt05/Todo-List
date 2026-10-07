from contextlib import asynccontextmanager
from collections.abc import Iterator

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.schemas import (
    LoginIn,
    RegisterIn,
    TaskIn,
    TaskOut,
    TaskStatusIn,
    TokenOut,
    UserOut,
)
from app.domain.errors import (
    DomainError,
    EmailAlreadyExists,
    InvalidCredentials,
    TaskNotFound,
)
from app.domain.services import AuthService, TaskService
from app.infrastructure.database import Base, build_database
from app.infrastructure.repositories import SqlTaskRepository, SqlUserRepository
from app.infrastructure.security import JwtTokenCodec, Pbkdf2PasswordHasher
from app.infrastructure import tables  # noqa: F401 - register ORM tables


def create_app(database_url: str, token_secret: str) -> FastAPI:
    engine, session_factory = build_database(database_url)
    tokens = JwtTokenCodec(token_secret)
    passwords = Pbkdf2PasswordHasher()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Base.metadata.create_all(engine)
        yield
        engine.dispose()

    app = FastAPI(title="Todo List API", version="1.0.0", lifespan=lifespan)
    app.state.session_factory = session_factory

    @app.middleware("http")
    async def authenticate_tasks(request: Request, call_next):
        path = request.url.path
        if path == "/api/tasks" or path.startswith("/api/tasks/"):
            header = request.headers.get("Authorization", "")
            scheme, _, token = header.partition(" ")
            user_id = tokens.read_user_id(token) if scheme.lower() == "bearer" else None
            if user_id is None:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Valid Bearer token required"},
                    headers={"WWW-Authenticate": "Bearer"},
                )
            request.state.user_id = user_id
        return await call_next(request)

    @app.exception_handler(DomainError)
    async def handle_domain_error(_request: Request, exc: DomainError):
        code = 400
        if isinstance(exc, InvalidCredentials):
            code = 401
        elif isinstance(exc, EmailAlreadyExists):
            code = 409
        elif isinstance(exc, TaskNotFound):
            code = 404
        return JSONResponse(status_code=code, content={"detail": str(exc)})

    def get_session(request: Request) -> Iterator[Session]:
        with request.app.state.session_factory() as session:
            yield session

    def auth_service(session: Session = Depends(get_session)) -> AuthService:
        return AuthService(SqlUserRepository(session), passwords, tokens)

    def task_service(session: Session = Depends(get_session)) -> TaskService:
        return TaskService(SqlTaskRepository(session))

    @app.get("/health", tags=["System"])
    def health():
        return {"status": "ok"}

    @app.post(
        "/api/auth/register",
        response_model=UserOut,
        status_code=201,
        tags=["Authentication"],
        responses={400: {"description": "Invalid input"}, 409: {"description": "Email exists"}},
    )
    def register(body: RegisterIn, service: AuthService = Depends(auth_service)):
        return service.register(body.email, body.password)

    @app.post(
        "/api/auth/login",
        response_model=TokenOut,
        tags=["Authentication"],
        responses={401: {"description": "Invalid credentials"}},
    )
    def login(body: LoginIn, service: AuthService = Depends(auth_service)):
        return TokenOut(access_token=service.login(body.email, body.password))

    @app.get(
        "/api/tasks",
        response_model=list[TaskOut],
        tags=["Tasks"],
        responses={401: {"description": "Bearer token required"}},
    )
    def list_tasks(request: Request, service: TaskService = Depends(task_service)):
        return service.list_tasks(request.state.user_id)

    @app.post(
        "/api/tasks",
        response_model=TaskOut,
        status_code=201,
        tags=["Tasks"],
        responses={400: {"description": "Blank title"}, 401: {"description": "Bearer token required"}},
    )
    def create_task(body: TaskIn, request: Request, service: TaskService = Depends(task_service)):
        return service.create_task(request.state.user_id, body.title, body.description)

    @app.get(
        "/api/tasks/{task_id}",
        response_model=TaskOut,
        tags=["Tasks"],
        responses={401: {"description": "Bearer token required"}, 404: {"description": "Task not found"}},
    )
    def get_task(task_id: int, request: Request, service: TaskService = Depends(task_service)):
        return service.get_task(request.state.user_id, task_id)

    @app.patch(
        "/api/tasks/{task_id}",
        response_model=TaskOut,
        tags=["Tasks"],
        responses={401: {"description": "Bearer token required"}, 404: {"description": "Task not found"}},
    )
    def set_done(
        task_id: int,
        body: TaskStatusIn,
        request: Request,
        service: TaskService = Depends(task_service),
    ):
        return service.set_done(request.state.user_id, task_id, body.is_done)

    @app.delete(
        "/api/tasks/{task_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["Tasks"],
        responses={401: {"description": "Bearer token required"}, 404: {"description": "Task not found"}},
    )
    def delete_task(task_id: int, request: Request, service: TaskService = Depends(task_service)):
        service.delete_task(request.state.user_id, task_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
        schema.setdefault("components", {}).setdefault("securitySchemes", {})["BearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
        for path, methods in schema["paths"].items():
            if path == "/api/tasks" or path.startswith("/api/tasks/"):
                for operation in methods.values():
                    operation["security"] = [{"BearerAuth": []}]
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi
    return app
