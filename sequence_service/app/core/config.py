from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Load env vars from sequence_service/.env and web-api/.env when present.
    model_config = SettingsConfigDict(
        extra='ignore',
        env_file=('.env', '../web-api/.env'),
        env_file_encoding='utf-8',
    )

    MYSQL_DSN: str = Field(
        default='mysql+pymysql://root:root@127.0.0.1:3306/automation',
        validation_alias=AliasChoices('MYSQL_DSN', 'SEQUENCE_MYSQL_DSN'),
    )
    SERVICE_ID: str = 'sequence-main'
    START_WEB: bool = True
    SIMUL_MODE: bool = False

    TICK_SECONDS: float = 0.1
    PRINT_SIM_SECONDS: int = 15
    CURE_SIM_SECONDS: int = 120
    ROBOT_SIM_SECONDS: int = 3
    DEFAULT_CURING_TIME: int = 120
    DEFAULT_WASHING_TIME: int = 360

    ENABLE_CELL_STATE: bool = True
    ENABLE_TCP_IO: bool = True
    ROBOT_TCP_HOST: str = '127.0.0.1'
    ROBOT_TCP_PORT: int = 9100
    ROBOT_TCP_TIMEOUT_SECONDS: float = 5.0
    ROBOT_MODBUS_SLAVE_ID: int = 1
    ROBOT_MODBUS_COMMAND_REG: int = 130
    ROBOT_MODBUS_PARAM_START_REG: int = 131
    ROBOT_MODBUS_PARAM_COUNT: int = 5
    ROBOT_MODBUS_SEND_REG: int = 150
    ROBOT_MODBUS_PC_READY_REG: int = 151
    ROBOT_MODBUS_ROBOT_READY_REG: int = 200
    ROBOT_MODBUS_ROBOT_MOVED_REG: int = 206
    ROBOT_MODBUS_CMD_PRINTING_VALUE: int = 0
    ROBOT_MODBUS_CMD_FW_VALUE: int = 1
    ROBOT_MODBUS_CMD_FC_VALUE: int = 2
    ROBOT_MODBUS_PC_READY_OFF_DELAY_SECONDS: float = 4.0
    ROBOT_MODBUS_RETRY_SECONDS: float = 3.0
    VISION_TCP_HOST: str = '127.0.0.1'
    VISION_TCP_PORT: int = 9200
    VISION_TCP_TIMEOUT_SECONDS: float = 3.0
    ENABLE_VISION_TCP: bool = False

    # Ajin IO (AXL.dll) integration
    AJIN_SIMULATION: bool = True
    AJIN_IRQ_NO: int = 7
    AJIN_AUTO_OPEN: bool = False
    AJIN_DLL_PATH: str = 'app/io/bin/AXL.dll'

    # web-api integration for real print dispatch/status polling
    WEB_API_BASE_URL: str = 'http://127.0.0.1:8085'
    WEB_API_TIMEOUT_SECONDS: int = 15
    PRINTER_SERVER_SIMUL: bool = True
    PRINT_MACHINE_TYPE: str = 'FORM-4-0'
    PRINT_MATERIAL_CODE: str = 'FLGPGR05'
    PRINT_LAYER_THICKNESS_MM: float = 0.05
    PRINT_SUPPORT_DENSITY: str = 'normal'
    PRINT_SUPPORT_TOUCHPOINT_SIZE: float = 0.5
    PRINT_SUPPORT_INTERNALS: bool = False
    PRINTER_STEP_DELAY_SECONDS: float = 5.0
    PRINT_PRECHECK_RETRIES: int = 3
    PRINTER_STATUS_POLL_SECONDS: float = 3.0
    PRINT_UPLOAD_RETRIES: int = 3
    PRINT_START_RETRIES: int = 3
    PRINT_DISPATCH_RETRY_SECONDS: float = 5.0
    PRINT_DISPATCH_MAX_RETRIES: int = 5
    PRINTER_SERIAL_MAP: dict[int, str] = {
        4: 'Form4-CapableGecko',
        3: 'Form4-HeavenlyTuna',
        2: 'Form4-CorrectPelican',
        1: 'Form4-ShrewdStork',
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()
