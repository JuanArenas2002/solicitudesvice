import pytest

from app.domain.exceptions.errors import InvalidValue, PasswordPolicyViolation
from app.domain.value_objects.email import Email
from app.domain.value_objects.identifiers import Doi, Issn
from app.domain.value_objects.password import PlainPassword
from app.domain.value_objects.request_number import MAX_SEQUENCE, RequestNumber


def test_email_is_normalized() -> None:
    assert str(Email.parse("  Ana.Perez@Example.ORG ")) == "ana.perez@example.org"


@pytest.mark.parametrize(
    "raw", ["", "sin-arroba", "a@b", "a b@c.com", "@x.com", "a@" + "b" * 260 + ".co"]
)
def test_invalid_emails(raw: str) -> None:
    with pytest.raises(InvalidValue):
        Email.parse(raw)


def test_email_constructor_requires_normalized_value() -> None:
    with pytest.raises(InvalidValue):
        Email("Ana@Example.org")


@pytest.mark.parametrize("raw", ["10.1234/abc", "10.12345678/a-b_c(1)", " 10.1000/xyz "])
def test_valid_dois(raw: str) -> None:
    assert str(Doi.parse(raw)) == raw.strip()


@pytest.mark.parametrize(
    "raw", ["", "11.1234/abc", "10.12/abc", "10.1234/", "10.1234/a b", "doi:10.1234/x"]
)
def test_invalid_dois(raw: str) -> None:
    with pytest.raises(InvalidValue):
        Doi.parse(raw)


@pytest.mark.parametrize("raw", ["00280836", "0028-0836", " 0028 0836 ", "0378595x"])
def test_the_issn_hyphen_is_optional_and_always_stored_with_it(raw: str) -> None:
    expected = "0378-595X" if raw.strip().lower().startswith("0378") else "0028-0836"
    assert str(Issn.parse(raw)) == expected


def test_issn_is_uppercased_and_validated() -> None:
    assert str(Issn.parse("0378-595x")) == "0378-595X"
    for bad in ("1234-567", "ABCD-EFGH", "1234--5678", "12345-678", "1234567", "123456789"):
        with pytest.raises(InvalidValue):
            Issn.parse(bad)
    with pytest.raises(InvalidValue) as error:
        Issn.parse("bad", field="eissn")
    assert error.value.field == "eissn"


def test_request_number_format_and_roundtrip() -> None:
    number = RequestNumber(2026, 1)
    assert str(number) == "SOL-2026-000001"
    assert RequestNumber.parse("sol-2026-000042") == RequestNumber(2026, 42)
    assert str(RequestNumber(2026, MAX_SEQUENCE)) == "SOL-2026-999999"


@pytest.mark.parametrize(
    "year, sequence", [(2026, 0), (2026, MAX_SEQUENCE + 1), (99, 1), (10000, 1)]
)
def test_request_number_bounds(year: int, sequence: int) -> None:
    with pytest.raises(InvalidValue):
        RequestNumber(year, sequence)


@pytest.mark.parametrize("raw", ["", "SOL-2026-1", "SOL-26-000001", "REQ-2026-000001"])
def test_request_number_parse_rejects_garbage(raw: str) -> None:
    with pytest.raises(InvalidValue):
        RequestNumber.parse(raw)


def test_password_policy_and_no_leak_in_repr() -> None:
    password = PlainPassword("una-clave-segura-1")
    assert "una-clave" not in repr(password)
    for bad in ("corta", "x" * 129):
        with pytest.raises(PasswordPolicyViolation):
            PlainPassword(bad)
    PlainPassword("x" * 12)
    PlainPassword("x" * 128)
