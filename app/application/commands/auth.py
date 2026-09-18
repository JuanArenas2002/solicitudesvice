from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class LoginCommand:
    email: str
    password: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class RefreshCommand:
    refresh_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ChangePasswordCommand:
    current_password: str = field(repr=False)
    new_password: str = field(repr=False)
