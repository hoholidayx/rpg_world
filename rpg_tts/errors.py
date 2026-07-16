class TTSError(Exception):
    error_code = "TTS_ERROR"


class TTSInvalidAudioError(TTSError):
    error_code = "TTS_INVALID_AUDIO"


class TTSSourceChangedError(TTSError):
    error_code = "TTS_SOURCE_CHANGED"
