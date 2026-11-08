from sms.core.security import derive_successor_token, generate_refresh_token


def test_successor_is_deterministic() -> None:
    # The point of it (ADR 0031): every replay of a refresh token — a
    # reload's aborted request still running on the server, the new page's
    # request — computes the *same* next token, so the order they finish in
    # can't retire the cookie the browser kept.
    token = generate_refresh_token()

    assert derive_successor_token(token) == derive_successor_token(token)


def test_successor_differs_per_token_and_from_its_input() -> None:
    a, b = generate_refresh_token(), generate_refresh_token()

    assert derive_successor_token(a) != a
    assert derive_successor_token(a) != derive_successor_token(b)


def test_successor_is_cookie_safe_and_full_strength() -> None:
    # Same shape as generate_refresh_token's output: 256 bits, base64url,
    # no padding — safe in a cookie value without quoting.
    successor = derive_successor_token(generate_refresh_token())

    assert len(successor) == 43
    assert set(successor) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
