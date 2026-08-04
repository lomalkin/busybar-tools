from busybar_tools.device.storage import (
    DeviceStorage,
    StorageErrorCode,
    StorageProtocolError,
)


def test_send_file_reconnects_and_retries_already_open(monkeypatch):
    storage = DeviceStorage(("device", 23))
    attempts = []
    reconnects = []

    def send_once(source, destination):
        attempts.append((source, destination))
        if len(attempts) == 1:
            raise StorageProtocolError.from_error_code(
                destination,
                StorageErrorCode.ALREADY_OPEN,
            )

    monkeypatch.setattr(storage, "_send_file_once", send_once)
    monkeypatch.setattr(
        storage,
        "_reconnect_after_interrupted_transfer",
        lambda: reconnects.append(True),
    )

    storage.send_file("local.bin", "/bkp/recovery/file.bin")

    assert len(attempts) == 2
    assert reconnects == [True]


def test_send_file_does_not_retry_other_storage_errors(monkeypatch):
    storage = DeviceStorage(("device", 23))
    attempts = []

    def send_once(source, destination):
        attempts.append((source, destination))
        raise StorageProtocolError.from_error_code(
            destination,
            StorageErrorCode.DENIED,
        )

    monkeypatch.setattr(storage, "_send_file_once", send_once)

    try:
        storage.send_file("local.bin", "/bkp/recovery/file.bin")
    except StorageProtocolError as exc:
        assert exc.error_code == StorageErrorCode.DENIED
    else:
        raise AssertionError("StorageProtocolError was not raised")

    assert len(attempts) == 1


def test_power_on_animation_timeout_has_actionable_message():
    storage = DeviceStorage(("device", 23))
    path = "/bkp/recovery/resources/power_on/animations/back_power_on_148x80.anim"

    error = storage._open_file_timeout_error(path)

    assert error.error_code == StorageErrorCode.ALREADY_OPEN
    assert "first-start animation" in str(error)
    assert "Press any button" in str(error)
