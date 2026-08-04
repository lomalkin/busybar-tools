import logging

import busybar_tools.commands.storage as storage_cmd
from busybar_tools.errors import StorageError
from busybar_tools.options import DeviceEndpoint


def test_upload_bundle_verifies_after_upload_error(monkeypatch, caplog):
    endpoint = DeviceEndpoint("device", 23)
    verified = []

    monkeypatch.setattr(storage_cmd, "ensure_device_reachable", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        storage_cmd,
        "upload_directory",
        lambda *args, **kwargs: (_ for _ in ()).throw(StorageError("file is already open")),
    )
    monkeypatch.setattr(
        storage_cmd,
        "verify_directory",
        lambda *args: verified.append(args),
    )

    with caplog.at_level(logging.WARNING):
        destination = storage_cmd.upload_bundle(endpoint, "bundle")

    assert destination == storage_cmd.DIR_BSB_TMP_UPDATE
    assert verified == [(endpoint, "bundle", storage_cmd.DIR_BSB_TMP_UPDATE)]
    assert "Continuing with device content verification" in caplog.text
