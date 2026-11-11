"""Test setup."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/which_car in tests."""
    yield


@pytest.fixture(scope="session", autouse=True)
def start_dns_cleanup_thread():
    """pycares starts one background thread on first use; start it before the
    per-test thread check so it is not reported as left behind."""
    try:
        import pycares

        pycares.Channel().close()
    except Exception:  # noqa: BLE001
        pass
    yield
