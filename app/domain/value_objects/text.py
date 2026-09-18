from app.domain.exceptions.errors import InvalidValue


def clean_optional(raw: str | None, field: str, max_length: int) -> str | None:
    """Recorta espacios; vacío -> None. Valida la longitud (debe coincidir con la columna)."""
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if len(value) > max_length:
        raise InvalidValue(f"{field} excede {max_length} caracteres", field=field)
    return value


def clean_required(raw: str | None, field: str, max_length: int) -> str:
    value = clean_optional(raw, field, max_length)
    if value is None:
        raise InvalidValue(f"{field} es obligatorio", field=field)
    return value
