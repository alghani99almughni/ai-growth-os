"""Make numpy optional in voice_bot.py so local dev without numpy still works."""

import pathlib

path = pathlib.Path("voice_bot.py")
text = path.read_text(encoding="utf-8")

if "_NUMPY_AVAILABLE" in text:
    print("SKIP: already patched")
    raise SystemExit(0)

old = "import numpy as np\n"

new = (
    "try:\n"
    "    import numpy as np\n"
    "    _NUMPY_AVAILABLE = True\n"
    "except ImportError:\n"
    "    np = None\n"
    "    _NUMPY_AVAILABLE = False\n"
)

if old not in text:
    print("ERROR: numpy import line not found")
    raise SystemExit(1)

text = text.replace(old, new, 1)

# Also guard the TTSAudioTrack class definition
old_class = "if _AIORTC_AVAILABLE:\n    class TTSAudioTrack(MediaStreamTrack):"
new_class = "if _AIORTC_AVAILABLE and _NUMPY_AVAILABLE:\n    class TTSAudioTrack(MediaStreamTrack):"

if old_class in text:
    text = text.replace(old_class, new_class, 1)
    print("Guarded TTSAudioTrack")

path.write_text(text, encoding="utf-8")
print("Patched voice_bot.py")
print("numpy optional:", "_NUMPY_AVAILABLE" in text)