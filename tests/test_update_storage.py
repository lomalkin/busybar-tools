import logging

import busybar_tools.device.update_storage as update_storage
from busybar_tools.errors import StorageError
from busybar_tools.options import DeviceEndpoint


def test_upload_bundle_verifies_after_upload_error(monkeypatch, caplog):
    endpoint = DeviceEndpoint("device", 23)
    verified = []

    monkeypatch.setattr(update_storage, "ensure_device_reachable", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        update_storage,
        "upload_directory",
        lambda *args, **kwargs: (_ for _ in ()).throw(StorageError("file is already open")),
    )
    monkeypatch.setattr(
        update_storage,
        "verify_directory",
        lambda *args: verified.append(args),
    )

    with caplog.at_level(logging.WARNING):
        destination = update_storage.upload_bundle(endpoint, "bundle")

    assert destination == update_storage.DIR_BSB_TMP_UPDATE
    assert verified == [(endpoint, "bundle", update_storage.DIR_BSB_TMP_UPDATE)]
    assert "Continuing with device content verification" in caplog.text
