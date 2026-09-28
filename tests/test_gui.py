from __future__ import annotations

from pathlib import Path
import os
import time
import tkinter as tk

import pytest

from vault.core import create_keyfile, encrypt
from vault.gui.app import VaultApp


@pytest.fixture(scope="module")
def application(tmp_path_factory: pytest.TempPathFactory):
    # One Tcl interpreter, like the real desktop app. Repeated destruction and
    # creation of Tk interpreters is unreliable on some Windows Tcl builds.
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("VAULT_REQUIRE_GUI_TESTS") == "1":
            pytest.fail(f"CI requires working Tk and a display: {exc}")
        pytest.skip(f"Tk/display unavailable: {exc}")
    root.withdraw()
    application = VaultApp(root, config_dir=tmp_path_factory.mktemp("gui-config"), tutorial=False)
    root.update()
    yield application
    application.shutdown()


@pytest.fixture
def app(application: VaultApp):
    application.notebook.select(application.lock)
    application.root.update()
    application.lock.clear_secrets()
    application.unlock.clear_secrets()
    for variable in (application.lock.source, application.lock.output, application.lock.key,
                     application.unlock.source, application.unlock.output, application.unlock.key):
        variable.set("")
    application.lock.use_key.set(False)
    application.lock.erase.set(False)
    application.unlock.header = None
    application.lock.validate()
    application.unlock.validate()
    return application


def test_button_validation(app: VaultApp, tmp_path: Path) -> None:
    source = tmp_path / "test.txt"
    source.write_text("example")
    lock = app.lock
    assert lock.submit.instate(["disabled"])
    lock.source.set(str(source))
    lock.output.set(str(tmp_path / "example.vault"))
    lock.password.set("a long random passphrase")
    lock.confirm.set("different")
    assert lock.submit.instate(["disabled"])
    lock.confirm.set(lock.password.get())
    assert lock.submit.instate(["!disabled"])
    lock.use_key.set(True)
    lock.validate()
    assert lock.submit.instate(["disabled"])
    key = create_keyfile(tmp_path / "example.key")
    lock.key.set(str(key))
    assert lock.submit.instate(["!disabled"])
    lock.output.set(str(source))
    assert lock.submit.instate(["disabled"])
    app.notebook.select(app.unlock)
    app.root.update()
    assert lock.password.get() == lock.confirm.get() == ""


def test_unlock_header_and_validation(app: VaultApp, tmp_path: Path) -> None:
    source = tmp_path / "test.txt"
    source.write_text("example")
    key = create_keyfile(tmp_path / "example.key")
    vault = tmp_path / "example.vault"
    encrypt(source, vault, "testing passphrase", keyfile=key)
    app.notebook.select(app.unlock)
    app.root.update()
    unlock = app.unlock
    unlock.set_source(str(vault))
    assert unlock.header.keyfile
    assert "Yes" in unlock.preview.cget("text")
    assert unlock.submit.instate(["disabled"])
    unlock.password.set("testing passphrase")
    assert unlock.submit.instate(["disabled"])
    unlock.key.set(str(key))
    assert unlock.submit.instate(["!disabled"])
    app.notebook.select(app.help)
    app.root.update()
    assert unlock.password.get() == ""


def test_worker_clears_fields(app: VaultApp, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(app, "success", lambda *args: None)
    app.lock.password.set("do not log this")
    app.lock.confirm.set("do not log this")
    app.run_operation("lock", lambda cancel, progress: tmp_path / "result")
    assert app.busy
    assert app.lock.password_entry.instate(["disabled"])
    deadline = time.monotonic() + 3
    while app.busy and time.monotonic() < deadline:
        app.root.update()
        time.sleep(0.01)
    assert not app.busy
    assert not app.lock.password.get()
    assert not app.lock.confirm.get()
    assert app.cancel_button.instate(["disabled"])
