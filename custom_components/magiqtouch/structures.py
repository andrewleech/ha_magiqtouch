import json
from dataclasses import dataclass, field
import inspect
from typing import Any, Dict


@dataclass
class RemoteAccessRequest:
    SerialNo: str = ""
    TimeRequest: str = ""
    StandBy: int = 0
    EvapCRunning: int = 0
    CTemp: int = 0
    CFanSpeed: int = 0
    CFanOnly: int = 0
    CThermosOrFan: int = 0
    HRunning: int = 0
    HTemp: int = 0
    HFanSpeed: int = 0
    HFanOnly: int = 0
    FAOCRunning: int = 0
    FAOCTemp: int = 0
    IAOCRunning: int = 0
    IAOCTemp: int = 0

    OnOffZone1: int = 0
    TempZone1: int = 0
    Override1: int = 0

    OnOffZone2: int = 0
    TempZone2: int = 0
    Override2: int = 0

    OnOffZone3: int = 0
    TempZone3: int = 0
    Override3: int = 0

    OnOffZone4: int = 0
    TempZone4: int = 0
    Override4: int = 0

    OnOffZone5: int = 0
    TempZone5: int = 0
    Override5: int = 0

    OnOffZone6: int = 0
    TempZone6: int = 0
    Override6: int = 0

    OnOffZone7: int = 0
    TempZone7: int = 0
    Override7: int = 0

    OnOffZone8: int = 0
    TempZone8: int = 0
    Override8: int = 0

    OnOffZone9: int = 0
    TempZone9: int = 0
    Override9: int = 0

    OnOffZone10: int = 0
    TempZone10: int = 0
    Override10: int = 0

    CC3200FW_Major: int = 0
    CC3200FW_Minor: int = 0
    STM32FW_Major: int = 0
    STM32FW_Minor: int = 0

    TouchCount: int = 0
    CCL = None
    STL = None

    @classmethod
    def from_dict(cls, env):
        """Converts a dict to a dataclass instance, ignoring extra vars.
        Taken from https://stackoverflow.com/a/55096964"""
        return cls(
            **{k: v for k, v in env.items() if k in inspect.signature(cls).parameters}
        )


@dataclass
class RemoteStatus:
    SystemOn: int = 0
    MacAddressId: str = ""
    DateKey: int = 0  # 20201028
    TimeKey: int = 0  # 1155
    TimeRunning: str = ""  # '2020-10-28 19:15:43.186'
    CoolerType: int = 0
    TouchCount: int = 0  # 39
    ExternalTemp: int = 0
    InternalTemp: int = 0  # 16
    EvapCRunning: int = 0  # 1
    FanOrTempControl: int = 0
    PumpStatus: int = 0
    CFanOnlyOrCool: int = 0  # 1
    NightQuietMode: int = 0  # 1
    PumpOffExternalAirSensor: int = 0  # 1
    DrainExternalSensor: int = 0
    ManualDrain: int = 0
    PadFlush: int = 0
    AutoClean: int = 0
    DrainDry: int = 0
    FaultCodePresent: int = 0
    CFanSpeed: int = 0
    CTemp: int = 0  # 27
    HumiditySetPoint = 0  # 60
    HumidityActualValue: int = 0
    Fault: int = 0
    HRunning: int = 0
    HFanOnly: int = 0
    BasicFault: int = 0
    Spanner: int = 0
    HFanSpeed: int = 0
    HActualFanSpeed: int = 0
    HActualGasRate: int = 0
    HSetGasRate: int = 0
    HTemp: int = 0  # 27
    HActualGasRateVariable: int = 0
    ThermistorTemperature: int = 0
    HNewFault: int = 0
    FlameSenseVoltage: int = 0
    FAOCRunning: int = 0
    FAOCActualCompressorON: int = 0
    FAOCTemp: int = 0  # 27
    IAOCRunning: int = 0
    IAOCCompressorON: int = 0
    IAOCSetTemp: int = 0  # 27
    IAOCActualTemp: int = 0
    ProgramMode: int = 0
    ProgramModeOverridden: int = 0
    UpdateMicroProcessor: int = 0
    UpdateWiFiModule: int = 0
    ClearSoftwareUpdate: int = 0
    LoggingFrequency: int = 0
    EnableLiveStreaming: int = 0
    UpdateInPogress: int = 0
    UpdateCompleted: int = 0
    UpdateFailed: int = 0
    SignalStrength: int = 0  # 26
    OnOffZone1: int = 0
    DamperOnOffZone1: int = 0
    ProgramModeZone1: int = 0
    ProgramModeOverriddenZone1: int = 0
    SetTempZone1: int = 0  # 27
    ActualTempZone1: int = 0  # -99
    OnOffZone2: int = 0
    DamperOnOffZone2: int = 0
    ProgramModeZone2: int = 0
    ProgramModeOverriddenZone2: int = 0
    SetTempZone2: int = 0
    ActualTempZone2: int = 0
    OnOffZone3: int = 0
    DamperOnOffZone3: int = 0
    ProgramModeZone3: int = 0
    ProgramModeOverriddenZone3: int = 0
    SetTempZone3: int = 0
    ActualTempZone3: int = 0
    OnOffZone4: int = 0
    DamperOnOffZone4: int = 0
    ProgramModeZone4: int = 0
    ProgramModeOverriddenZone4: int = 0
    SetTempZone4: int = 0
    ActualTempZone4: int = 0
    OnOffZone5: int = 0
    DamperOnOffZone5: int = 0
    ProgramModeZone5: int = 0
    ProgramModeOverriddenZone5: int = 0
    SetTempZone5: int = 0
    ActualTempZone5: int = 0
    OnOffZone6: int = 0
    DamperOnOffZone6: int = 0
    ProgramModeZone6: int = 0
    ProgramModeOverriddenZone6: int = 0
    SetTempZone6: int = 0
    ActualTempZone6: int = 0
    OnOffZone7: int = 0
    DamperOnOffZone7: int = 0
    ProgramModeZone7: int = 0
    ProgramModeOverriddenZone7: int = 0
    SetTempZone7: int = 0
    ActualTempZone7: int = 0
    OnOffZone8: int = 0
    DamperOnOffZone8: int = 0
    ProgramModeZone8: int = 0
    ProgramModeOverriddenZone8: int = 0
    SetTempZone8: int = 0
    ActualTempZone8: int = 0
    OnOffZone9: int = 0
    DamperOnOffZone9: int = 0
    ProgramModeZone9: int = 0
    ProgramModeOverriddenZone9: int = 0
    SetTempZone9: int = 0
    ActualTempZone9: int = 0
    OnOffZone10: int = 0
    DamperOnOffZone10: int = 0
    ProgramModeZone10: int = 0
    ProgramModeOverriddenZone10: int = 0
    SetTempZone10: int = 0
    ActualTempZone10: int = 0

    def __eq__(self, other):
        if not isinstance(other, RemoteStatus):
            return False
        s = dict(**self.__dict__)
        o = dict(**other.__dict__)

        for key in list(s.keys()):
            if "Actual" in key:
                s.pop(key)
                o.pop(key)
            elif key in (
                "DateKey",
                "TimeKey",
                "TimeRunning",
                "SignalStrength",
            ):
                s.pop(key)
                o.pop(key)
        return s == o

    def __str__(self):
        return json.dumps(self.__dict__)

    @classmethod
    def from_dict(cls, env):
        """Converts a dict to a dataclass instance, ignoring extra vars.
        Taken from https://stackoverflow.com/a/55096964"""
        return cls(
            **{k: v for k, v in env.items() if k in inspect.signature(cls).parameters}
        )


@dataclass
class SystemDetails:
    NoOfZones: int = 0
    NoOfZonesControl: int = (
        0  # Best guess - these are the number of zones with temp control.
    )
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
        """Converts a dict to a dataclass instance, ignoring extra vars.
        Taken from https://stackoverflow.com/a/55096964"""
        return cls(
            **{k: v for k, v in env.items() if k in inspect.signature(cls).parameters}
        )
