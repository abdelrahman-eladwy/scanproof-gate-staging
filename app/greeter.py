"""Benign staging-only application. Nothing here is ever deployed anywhere real."""


def greet(name: str) -> str:
    cleaned = "".join(ch for ch in name if ch.isalnum() or ch in " -_")[:64]
    return f"Hello, {cleaned or 'world'}!"


if __name__ == "__main__":
    print(greet("staging"))
