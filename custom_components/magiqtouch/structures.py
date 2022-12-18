import json
from dataclasses import dataclass, field
import inspect
from structured_config import Structure, IntField, StrField
from typing import Any, Dict


class RemoteAccessRequest(Structure):
    SerialNo = StrField("")
    TimeRequest = StrField("")
    StandBy = IntField(0)
    EvapCRunning = IntField(0)
    CTemp = IntField(0)
    CFanSpeed = IntField(0)
    CFanOnly = IntField(0)
    CThermosOrFan = IntField(0)
    HRunning = IntField(0)
    HTemp = IntField(0)
    HFanSpeed = IntField(0)
    HFanOnly = IntField(0)
    FAOCRunning = IntField(0)
    FAOCTemp = IntField(0)
    IAOCRunning = IntField(0)
    IAOCTemp = IntField(0)

    OnOffZone1 = IntField(0)
    TempZone1 = IntField(0)
    Override1 = IntField(0)

    OnOffZone2 = IntField(0)
    TempZone2 = IntField(0)
    Override2 = IntField(0)

    OnOffZone3 = IntField(0)
    TempZone3 = IntField(0)
    Override3 = IntField(0)

    OnOffZone4 = IntField(0)
    TempZone4 = IntField(0)
    Override4 = IntField(0)

    OnOffZone5 = IntField(0)
    TempZone5 = IntField(0)
    Override5 = IntField(0)

    OnOffZone6 = IntField(0)
    TempZone6 = IntField(0)
    Override6 = IntField(0)

    OnOffZone7 = IntField(0)
    TempZone7 = IntField(0)
    Override7 = IntField(0)

    OnOffZone8 = IntField(0)
    TempZone8 = IntField(0)
    Override8 = IntField(0)

    OnOffZone9 = IntField(0)
    TempZone9 = IntField(0)
    Override9 = IntField(0)

    OnOffZone10 = IntField(0)
    TempZone10 = IntField(0)
    Override10 = IntField(0)

    CC3200FW_Major = IntField(0)
    CC3200FW_Minor = IntField(0)
    STM32FW_Major = IntField(0)
    STM32FW_Minor = IntField(0)

    TouchCount = IntField(0)
    CCL = None
    STL = None


class RemoteStatus(Structure):
    SystemOn = 0
    MacAddressId = ''
    DateKey = 0  # 20201028
    TimeKey = 0  # 1155
    TimeRunning = ''  # '2020-10-28 19:15:43.186'
    CoolerType = 0
    TouchCount = 0  # 39
    ExternalTemp = 0
    InternalTemp = 0  # 16
    EvapCRunning = 0  # 1
    FanOrTempControl = 0
    PumpStatus = 0
    CFanOnlyOrCool = 0  # 1
    NightQuietMode = 0  # 1
    PumpOffExternalAirSensor = 0  # 1
    DrainExternalSensor = 0
    ManualDrain = 0
    PadFlush = 0
    AutoClean = 0
    DrainDry = 0
    FaultCodePresent = 0
    CFanSpeed = 0
    CTemp = 0  # 27
    HumiditySetPoint = 0  # 60
    HumidityActualValue = 0
    Fault = 0
    HRunning = 0
    HFanOnly = 0
    BasicFault = 0
    Spanner = 0
    HFanSpeed = 0
    HActualFanSpeed = 0
    HActualGasRate = 0
    HSetGasRate = 0
    HTemp = 0  # 27
    HActualGasRateVariable = 0
    ThermistorTemperature = 0
    HNewFault = 0
    FlameSenseVoltage = 0
    FAOCRunning = 0
    FAOCActualCompressorON = 0
    FAOCTemp = 0  # 27
    IAOCRunning = 0
    IAOCCompressorON = 0
    IAOCSetTemp = 0  # 27
    IAOCActualTemp = 0
    ProgramMode = 0
    ProgramModeOverridden = 0
    UpdateMicroProcessor = 0
    UpdateWiFiModule = 0
    ClearSoftwareUpdate = 0
    LoggingFrequency = 0
    EnableLiveStreaming = 0
    UpdateInPogress = 0
    UpdateCompleted = 0
    UpdateFailed = 0
    SignalStrength = 0  # 26
    OnOffZone1 = 0
    DamperOnOffZone1 = 0
    ProgramModeZone1 = 0
    ProgramModeOverriddenZone1 = 0
    SetTempZone1 = 0  # 27
    ActualTempZone1 = 0  # -99
    OnOffZone2 = 0
    DamperOnOffZone2 = 0
    ProgramModeZone2 = 0
    ProgramModeOverriddenZone2 = 0
    SetTempZone2 = 0
    ActualTempZone2 = 0
    OnOffZone3 = 0
    DamperOnOffZone3 = 0
    ProgramModeZone3 = 0
    ProgramModeOverriddenZone3 = 0
    SetTempZone3 = 0
    ActualTempZone3 = 0
    OnOffZone4 = 0
    DamperOnOffZone4 = 0
    ProgramModeZone4 = 0
    ProgramModeOverriddenZone4 = 0
    SetTempZone4 = 0
    ActualTempZone4 = 0
    OnOffZone5 = 0
    DamperOnOffZone5 = 0
    ProgramModeZone5 = 0
    ProgramModeOverriddenZone5 = 0
    SetTempZone5 = 0
    ActualTempZone5 = 0
    OnOffZone6 = 0
    DamperOnOffZone6 = 0
    ProgramModeZone6 = 0
    ProgramModeOverriddenZone6 = 0
    SetTempZone6 = 0
    ActualTempZone6 = 0
    OnOffZone7 = 0
    DamperOnOffZone7 = 0
    ProgramModeZone7 = 0
    ProgramModeOverriddenZone7 = 0
    SetTempZone7 = 0
    ActualTempZone7 = 0
    OnOffZone8 = 0
    DamperOnOffZone8 = 0
    ProgramModeZone8 = 0
    ProgramModeOverriddenZone8 = 0
    SetTempZone8 = 0
    ActualTempZone8 = 0
    OnOffZone9 = 0
    DamperOnOffZone9 = 0
    ProgramModeZone9 = 0
    ProgramModeOverriddenZone9 = 0
    SetTempZone9 = 0
    ActualTempZone9 = 0
    OnOffZone10 = 0
    DamperOnOffZone10 = 0
    ProgramModeZone10 = 0
    ProgramModeOverriddenZone10 = 0
    SetTempZone10 = 0
    ActualTempZone10 = 0
    
    def __str__(self):
        return json.dumps(self.__as_dict__())


@dataclass
class SystemDetails:
    NoOfZones: int = 0
    NoOfZonesControl: int = 0 # Best guess - these are the number of zones with temp control.
    HeaterInSystem: int = 0
    AOCInverterInSystem: int = 0
    AOCFixedInSystem: int = 0
    NoOfEVAPInSystem: int = 0
    Heater: Dict[str, Any] = field(default_factory=dict)
    AOCFixed: Dict[str, Any] = field(default_factory=dict)
    AOCInverter: Dict[str, Any] = field(default_factory=dict)
    EVAPCooler: Dict[str, Any] = field(default_factory=dict)
    ZoneName1: str = ""
    ZoneName2: str = ""
    ZoneName3: str = ""
    ZoneName4: str = ""
    ZoneName5: str = ""
    ZoneName6: str = ""
    ZoneName7: str = ""
    ZoneName8: str = ""
    ZoneName9: str = ""
    ZoneName10: str = ""

    @classmethod
    def from_dict(cls, env):      
        """ Converts a dict to a dataclass instance, ignoring extra vars.
        Taken from https://stackoverflow.com/a/55096964 """
        return cls(**{
            k: v for k, v in env.items() 
            if k in inspect.signature(cls).parameters
        })

