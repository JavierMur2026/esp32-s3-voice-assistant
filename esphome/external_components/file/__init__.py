# Vendored from https://github.com/jesserockz/esphome-components (components/file/__init__.py, main @ 7aaa7fde 2026-03-03)
# PATCH 2026-11-20 (esp32-s3-voice-assistant project): compatibility with ESPHome 2026.11+
#   Upstream cg.progmem_array() now emits the PROGMEM array as a statement inside
#   setup() (CORE.add -> main_statements). Since 2026.11, lambdas used in automation
#   actions are hoisted into named static functions at global scope, emitted in the
#   include block BEFORE setup(), so they can no longer see the array:
#   error: 'timer_finished_wave_file' was not declared in this scope.
#   Fix: emit the declaration in the global statements bucket (cg.add_global), which
#   is rendered inside the AUTO GENERATED INCLUDE BLOCK (after #include "esphome.h",
#   so PROGMEM is available) and always before the generated action function bodies.
import hashlib
import logging
from pathlib import Path

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome import external_files
from esphome.const import (
    CONF_FILE,
    CONF_ID,
    CONF_PATH,
    CONF_TYPE,
    CONF_URL,
)
from esphome.core import CORE, HexInt
from esphome.cpp_generator import (
    MockObj,
    ProgmemAssignmentExpression,
    safe_exp,
)

_LOGGER = logging.getLogger(__name__)

try:
    from esphome.external_files import download_content
except ImportError:
    from esphome.components.font import download_content

CODEOWNERS = ["@jesserockz"]
DOMAIN = "file"
MULTI_CONF = True

TYPE_LOCAL = "local"
TYPE_WEB = "web"


def _compute_local_file_path(value: dict) -> Path:
    url = value[CONF_URL]
    h = hashlib.new("sha256")
    h.update(url.encode())
    key = h.hexdigest()[:8]
    base_dir = external_files.compute_local_file_dir(DOMAIN)
    _LOGGER.debug("_compute_local_file_path: base_dir=%s", base_dir / key)
    return base_dir / key


def _download_web_file(value):
    url = value[CONF_URL]
    path = _compute_local_file_path(value)
    download_content(url, path)
    _LOGGER.debug("download_web_file: path=%s", path)
    return value


LOCAL_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_PATH): cv.file_,
    }
)

WEB_SCHEMA = cv.All(
    {
        cv.Required(CONF_URL): cv.url,
    },
    _download_web_file,
)


def _validate_file_shorthand(value):
    value = cv.string_strict(value)
    if value.startswith("http://") or value.startswith("https://"):
        return _file_schema(
            {
                CONF_TYPE: TYPE_WEB,
                CONF_URL: value,
            }
        )
    return _file_schema(
        {
            CONF_TYPE: TYPE_LOCAL,
            CONF_PATH: value,
        }
    )


TYPED_FILE_SCHEMA = cv.typed_schema(
    {
        TYPE_LOCAL: LOCAL_SCHEMA,
        TYPE_WEB: WEB_SCHEMA,
    },
)


def _file_schema(value):
    if isinstance(value, str):
        return _validate_file_shorthand(value)
    return TYPED_FILE_SCHEMA(value)


CONFIG_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_ID): cv.declare_id(cg.uint8),
        cv.Required(CONF_FILE): _file_schema,
    }
)


def _trim_wav_file(data: bytes) -> bytes:
    header = []
    index = 0
    length = len(data)
    while index < length:
        byte = data[index : index + 1]
        if byte == b"":
            raise ValueError("Could not find data in wav file")
        header.append(byte)
        index += 1
        if header[-4:] == [b"d", b"a", b"t", b"a"] or index > 100:
            break
    index += 2
    return data[index:]


async def to_code(config):
    conf_file = config[CONF_FILE]
    file_source = conf_file[CONF_TYPE]
    if file_source == TYPE_LOCAL:
        path = CORE.relative_config_path(conf_file[CONF_PATH])
    elif file_source == TYPE_WEB:
        path = _compute_local_file_path(conf_file)

    with open(path, "rb") as f:
        data = f.read()

    try:
        import puremagic

        file_type = puremagic.from_string(data, mime=True)
    except ImportError:
        try:  # magic removed from ESPHome in 2024.10.0 and replaced with puremagic
            from magic import Magic

            magic = Magic(mime=True)
            file_type = magic.from_buffer(data)
        except ImportError:
            raise ImportError("Please install puremagic")

    if "wav" in file_type:
        data = _trim_wav_file(data)

    # --- PATCH: global-scope declaration instead of cg.progmem_array() ---
    id_ = config[CONF_ID]
    rhs = safe_exp([HexInt(x) for x in data])
    expr = ProgmemAssignmentExpression(id_.type, id_, rhs)
    cg.add_global(expr)
    CORE.register_variable(id_, MockObj(id_, "."))
