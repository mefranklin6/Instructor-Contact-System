import logging as log


def raise_error_window(message: str, title: str = "Error") -> None:
    print(f"{title}: {message}")
    log.error(f"{title}: {message}")
    # TODO: Raise pop-up window in Flet
