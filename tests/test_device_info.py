"""Unit tests for device_info parsing helpers (no device required)."""
import pytest

import busybar_tools as bt

# A representative device_info dict (subset of real fields, as strings).
BASE_INFO = {
    "u5_firmware_commit": "74c397e6",
    "u5_firmware_branch": "0.8.1",
    "u5_firmware_builddate": "2026-04-17",
    "u5_firmware_target": "22",
    "sl_firmware_commit": "74c397e6",
    "sl_firmware_branch": "0.8.1",
    "sl_firmware_builddate": "2026-04-17",
    "sl_nwp_secureboot": "true",
    "sl_m4_secureboot": "true",
}


def test_target_parsed_as_int():
    assert bt.device_info_target(BASE_INFO) == 22


def test_target_accepts_nonstandard_value():
    # No closed list: a target outside {20,21,22} is returned as-is.
    assert bt.device_info_target(dict(BASE_INFO, u5_firmware_target="23")) == 23


def test_target_missing_raises():
    with pytest.raises(RuntimeError):
        bt.device_info_target({})


def test_target_non_numeric_raises():
    with pytest.raises(RuntimeError):
        bt.device_info_target({"u5_firmware_target": "nope"})


def test_signed_when_both_secureboot_true():
    assert bt.device_info_signed(BASE_INFO) is True


def test_unsigned_when_both_secureboot_false():
    info = dict(BASE_INFO, sl_nwp_secureboot="false", sl_m4_secureboot="false")
    assert bt.device_info_signed(info) is False


@pytest.mark.parametrize("nwp,m4", [("true", "false"), ("false", "true")])
def test_signed_inconsistent_secureboot_raises(nwp, m4):
    info = dict(BASE_INFO, sl_nwp_secureboot=nwp, sl_m4_secureboot=m4)
    with pytest.raises(RuntimeError):
        bt.device_info_signed(info)


def test_signed_missing_field_raises():
    info = dict(BASE_INFO)
    del info["sl_m4_secureboot"]
    with pytest.raises(RuntimeError):
        bt.device_info_signed(info)


def test_secureboot_value_is_case_insensitive():
    info = dict(BASE_INFO, sl_nwp_secureboot="True", sl_m4_secureboot="TRUE")
    assert bt.device_info_signed(info) is True


def test_fingerprint_changes_on_commit():
    after = dict(BASE_INFO, u5_firmware_commit="aaaa1111")
    assert bt.device_version_fingerprint(BASE_INFO) != bt.device_version_fingerprint(after)


def test_fingerprint_changes_on_builddate():
    after = dict(BASE_INFO, sl_firmware_builddate="2026-06-01")
    assert bt.device_version_fingerprint(BASE_INFO) != bt.device_version_fingerprint(after)


def test_fingerprint_stable_for_equal_info():
    assert bt.device_version_fingerprint(BASE_INFO) == bt.device_version_fingerprint(dict(BASE_INFO))


def test_format_version_contains_key_fields():
    s = bt.format_version(BASE_INFO)
    assert "0.8.1" in s and "74c397e6" in s and "2026-04-17" in s
