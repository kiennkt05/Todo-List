class DomainError(Exception):
    pass


class InvalidInput(DomainError):
    pass


class InvalidCredentials(DomainError):
    pass


class EmailAlreadyExists(DomainError):
    pass


class TaskNotFound(DomainError):
    pass
