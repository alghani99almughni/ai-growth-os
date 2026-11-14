from app.telephony_twilio import E164, _stream_token, _valid_stream_token, TOOL_SCHEMAS


def test_stream_token_binds_call_and_both_phone_numbers():
    token = _stream_token("CA123", "+919876543210", "+919900001111")
    assert _valid_stream_token("CA123", "+919876543210", "+919900001111", token)
    assert not _valid_stream_token("CA124", "+919876543210", "+919900001111", token)
    assert not _valid_stream_token("CA123", "+919876543211", "+919900001111", token)
    assert not _valid_stream_token("CA123", "+919876543210", "+919900001112", token)


def test_did_numbers_must_be_e164():
    assert E164.fullmatch("+919876543210")
    assert not E164.fullmatch("9876543210")
    assert not E164.fullmatch("+0123456789")
    assert not E164.fullmatch("+123")


def test_voice_tools_are_explicit_and_have_required_fields():
    names = {item["function"]["name"]: item["function"] for item in TOOL_SCHEMAS}
    assert set(names) == {"save_customer_identity", "log_callback_message", "send_whatsapp_info"}
    assert names["log_callback_message"]["parameters"]["required"] == [
        "caller_name", "phone_number", "inquiry_summary"
    ]
    assert names["send_whatsapp_info"]["parameters"]["required"] == [
        "phone_number", "info_type"
    ]
