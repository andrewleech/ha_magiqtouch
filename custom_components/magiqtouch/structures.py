import json
import dataclasses
from dataclasses import dataclass, field


def dataclass_from_dict(klass, d, show_errors=False):
    # https://stackoverflow.com/a/54769644
    try:
        fieldtypes = {f.name: f.type for f in dataclasses.fields(klass)}
        return klass(**{f: dataclass_from_dict(fieldtypes[f], d[f]) for f in d})
    except KeyError:
        raise
    except:
        # if type(klass) == Optional:
        # print(klass, type(klass), klass.__dict__)
        if show_errors or (isinstance(d, dict) and "MacAddressId" in d):
            print(klass, d)
            raise
        return d  # Not a dataclass fieldtypes


def flatten_dict(data, sep="_", parent_key="", result=None):
    """
    Flattens a nested dictionary into a single level dictionary.

    Args:
        data: The nested dictionary to flatten.
        sep: The separator to use when concatenating keys (default: "_").
        parent_key: The parent key for the current level (default: "").
        result: An optional dictionary to store the flattened data (default: None).

    Returns:
        A dictionary with flattened key-value pairs.
    """
    if result is None:
        result = {}
    for key, value in data.items():
        combined_key = parent_key + sep + key if parent_key else key
        if isinstance(value, dict):
            flatten_dict(value, sep, combined_key, result)
        else:
            result[combined_key] = value
    return result


# @dataclass
# class RemoteStatusOld:
#     SystemOn: int = 0
#     MacAddressId: str = ""
#     DateKey: int = 0  # 20201028
#     TimeKey: int = 0  # 1155
#     TimeRunning: str = ""  # '2020-10-28 19:15:43.186'
#     CoolerType: int = 0
#     TouchCount: int = 0  # 39
#     ExternalTemp: int = 0
#     InternalTemp: int = 0  # 16
#     EvapCRunning: int = 0  # 1
#     FanOrTempControl: int = 0
#     PumpStatus: int = 0
#     CFanOnlyOrCool: int = 0  # 1
#     NightQuietMode: int = 0  # 1
#     PumpOffExternalAirSensor: int = 0  # 1
#     DrainExternalSensor: int = 0
#     ManualDrain: int = 0
#     PadFlush: int = 0
#     AutoClean: int = 0
#     DrainDry: int = 0
#     FaultCodePresent: int = 0
#     CFanSpeed: int = 0
#     CTemp: int = 0  # 27
#     HumiditySetPoint = 0  # 60
#     HumidityActualValue: int = 0
#     Fault: int = 0
#     HRunning: int = 0
#     HFanOnly: int = 0
#     BasicFault: int = 0
#     Spanner: int = 0
#     HFanSpeed: int = 0
#     HActualFanSpeed: int = 0
#     HActualGasRate: int = 0
#     HSetGasRate: int = 0
#     HTemp: int = 0  # 27
#     HActualGasRateVariable: int = 0
#     ThermistorTemperature: int = 0
#     HNewFault: int = 0
#     FlameSenseVoltage: int = 0
#     FAOCRunning: int = 0
#     FAOCActualCompressorON: int = 0
#     FAOCTemp: int = 0  # 27
#     IAOCRunning: int = 0
#     IAOCCompressorON: int = 0
#     IAOCSetTemp: int = 0  # 27
#     IAOCActualTemp: int = 0
#     ProgramMode: int = 0
#     ProgramModeOverridden: int = 0
#     UpdateMicroProcessor: int = 0
#     UpdateWiFiModule: int = 0
#     ClearSoftwareUpdate: int = 0
#     LoggingFrequency: int = 0
#     EnableLiveStreaming: int = 0
#     UpdateInPogress: int = 0
#     UpdateCompleted: int = 0
#     UpdateFailed: int = 0
#     SignalStrength: int = 0  # 26
#     OnOffZone1: int = 0
#     DamperOnOffZone1: int = 0
#     ProgramModeZone1: int = 0
#     ProgramModeOverriddenZone1: int = 0
#     SetTempZone1: int = 0  # 27
#     ActualTempZone1: int = 0  # -99
#     OnOffZone2: int = 0
#     DamperOnOffZone2: int = 0
#     ProgramModeZone2: int = 0
#     ProgramModeOverriddenZone2: int = 0
#     SetTempZone2: int = 0
#     ActualTempZone2: int = 0
#     OnOffZone3: int = 0
#     DamperOnOffZone3: int = 0
#     ProgramModeZone3: int = 0
#     ProgramModeOverriddenZone3: int = 0
#     SetTempZone3: int = 0
#     ActualTempZone3: int = 0
#     OnOffZone4: int = 0
#     DamperOnOffZone4: int = 0
#     ProgramModeZone4: int = 0
#     ProgramModeOverriddenZone4: int = 0
#     SetTempZone4: int = 0
#     ActualTempZone4: int = 0
#     OnOffZone5: int = 0
#     DamperOnOffZone5: int = 0
#     ProgramModeZone5: int = 0
#     ProgramModeOverriddenZone5: int = 0
#     SetTempZone5: int = 0
#     ActualTempZone5: int = 0
#     OnOffZone6: int = 0
#     DamperOnOffZone6: int = 0
#     ProgramModeZone6: int = 0
#     ProgramModeOverriddenZone6: int = 0
#     SetTempZone6: int = 0
#     ActualTempZone6: int = 0
#     OnOffZone7: int = 0
#     DamperOnOffZone7: int = 0
#     ProgramModeZone7: int = 0
#     ProgramModeOverriddenZone7: int = 0
#     SetTempZone7: int = 0
#     ActualTempZone7: int = 0
#     OnOffZone8: int = 0
#     DamperOnOffZone8: int = 0
#     ProgramModeZone8: int = 0
#     ProgramModeOverriddenZone8: int = 0
#     SetTempZone8: int = 0
#     ActualTempZone8: int = 0
#     OnOffZone9: int = 0
#     DamperOnOffZone9: int = 0
#     ProgramModeZone9: int = 0
#     ProgramModeOverriddenZone9: int = 0
#     SetTempZone9: int = 0
#     ActualTempZone9: int = 0
#     OnOffZone10: int = 0
#     DamperOnOffZone10: int = 0
#     ProgramModeZone10: int = 0
#     ProgramModeOverriddenZone10: int = 0
#     SetTempZone10: int = 0
#     ActualTempZone10: int = 0

#     def __eq__(self, other):
#         if not isinstance(other, RemoteStatus):
#             return False
#         s = dict(**self.__dict__)
#         o = dict(**other.__dict__)

#         for key in list(s.keys()):
#             if "Actual" in key:
#                 s.pop(key)
#                 o.pop(key)
#             elif key in (
#                 "DateKey",
#                 "TimeKey",
#                 "TimeRunning",
#                 "SignalStrength",
#             ):
#                 s.pop(key)
#                 o.pop(key)
#         return s == o

#     def __str__(self):
#         return json.dumps(self.__dict__)

#     @classmethod
#     def from_dict(cls, env):
#         """Converts a dict to a dataclass instance, ignoring extra vars.
#         Taken from https://stackoverflow.com/a/55096964"""
#         return cls(
#             **{k: v for k, v in env.items() if k in inspect.signature(cls).parameters}
#         )


# @dataclass
# class SystemDetailsOld:
#     NoOfZones: int = 0
#     NoOfZonesControl: int = (
#         0  # Best guess - these are the number of zones with temp control.
#     )
#     HeaterInSystem: int = 0
#     AOCInverterInSystem: int = 0
#     AOCFixedInSystem: int = 0
#     NoOfEVAPInSystem: int = 0
#     Heater: Dict[str, Any] = field(default_factory=dict)
#     AOCFixed: Dict[str, Any] = field(default_factory=dict)
#     AOCInverter: Dict[str, Any] = field(default_factory=dict)
#     EVAPCooler: Dict[str, Any] = field(default_factory=dict)
#     ZoneName1: str = ""
#     ZoneName2: str = ""
#     ZoneName3: str = ""
#     ZoneName4: str = ""
#     ZoneName5: str = ""
#     ZoneName6: str = ""
#     ZoneName7: str = ""
#     ZoneName8: str = ""
#     ZoneName9: str = ""
#     ZoneName10: str = ""

#     @classmethod
#     def from_dict(cls, env):
#         """Converts a dict to a dataclass instance, ignoring extra vars.
#         Taken from https://stackoverflow.com/a/55096964"""
#         return cls(
#             **{k: v for k, v in env.items() if k in inspect.signature(cls).parameters}
#         )


################
# System Details
################


@dataclass
class Zone:
    Name: str
    Type: str
    CoolerCompatible: bool
    HeaterCompatible: bool


@dataclass
class AOC:
    InSystem: bool
    MaximumTemperature: int
    MinimumTemperature: int


@dataclass
class Cabinet:
    CabinetSerialNo: int
    CoolerCabinetSoftRev: str
    ElectronicsSerialNo: str
    ModelNumber: str


@dataclass
class EVAPCoolerDef:
    Brands: int
    HumidityControl: bool
    MaximumTemperature: int
    MinimumTemperature: int
    TemperatureUnits: int


@dataclass
class WallControllerDef:
    Firmware: str
    Type: int


@dataclass
class HeaterDef:
    InSystem: bool
    FixedFan: bool
    Brands: int
    DataTableVersion: str
    ICSSoftwareRev: str
    MaxSetFanSpeed: int
    MaximumTemperature: int
    MinimumTemperature: int
    ModelNo: str
    SerialNo: int


@dataclass
class SystemDevice:
    available: bool
    fanFixed: bool


@dataclass
class SystemDef:
    configuration: int
    cooler: SystemDevice
    heater: SystemDevice
    fan: SystemDevice
    Address: str
    Name: str


@dataclass
class WifiModuleDef:
    MacAddressId: str = ""
    version: str = ""
    type: str = ""


@dataclass
class ACZonesDef:
    Manual: bool
    SlaveWallControls: bool
    Zones: list[Zone]


@dataclass
class SystemDetails:
    ACZones: ACZonesDef = None
    AOCFixed: AOC = None
    AOCInverter: AOC = None
    Cabinets: list[Cabinet] = field(default_factory=list)
    EVAPCooler: EVAPCoolerDef = None
    WallController: WallControllerDef = None
    Heater: HeaterDef = None
    MasterAirSensorPresent: bool = False
    SlaveWallControls: int = 0
    NoOfZoneControls: int = 0
    System: SystemDef = None
    Wifi_Module: WifiModuleDef = None  # field(default_factory=WifiModuleDef)
    ExternalAirSensorPresent: bool = False
    DamperDelayModulePresent: bool = False
    BMSS1: bool = False
    BMSMS1: bool = False
    ZoneAirSensors: int = 0

    def __str__(self):
        # report as valid json in logs
        return json.dumps(self.to_dict())

    def to_dict(self):
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data):
        dc = dataclass_from_dict(cls, data, True)
        dc.ACZones.Zones = [Zone(**d) for d in dc.ACZones.Zones]
        dc.Cabinets = [Cabinet(**d) for d in dc.Cabinets]
        return dc


################
# Remote Status
################
@dataclass
class UnitDetails:
    brand: int = 0
    name: str = ""
    runningState: str = ""
    zoneRunningState: str = ""
    zoneOn: bool = False
    zoneType: str = ""
    set_temp: float = 0.0
    temperature_units: str = ""
    actual_temp: float = 0.0
    max_temp: float = 0.0
    min_temp: float = 0.0
    fan_speed: int = 0
    max_fan_speed: int = 0
    min_fan_speed: int = 0
    control_mode: str = ""
    control_mode_type: str = ""
    internal_temp: float = 0.0
    external_temp: float = None
    programMode: str = ""
    ProgramModeOverridden: bool = False
    ProgramPeriodActive: bool = False
    programOverrideDisabled: bool = False


@dataclass
class Fan:
    cooler_available: bool
    cooler_brand: int
    heater_available: bool
    heater_brand: int
    heater_Fan_Speed: int
    cooler_Fan_Speed: int


@dataclass
class Installed:
    evap: bool
    faoc: bool
    heater: bool
    iaoc: bool
    coolerType: int


@dataclass
class RemoteStatus:
    device: str = ""
    timestamp: int = 0
    online: bool = False
    systemOn: bool = False
    runningMode: str = ""
    heaterFault: bool = False
    coolerFault: bool = False
    cooler: list[UnitDetails] = field(default_factory=list)
    heater: list[UnitDetails] = field(default_factory=list)
    fan: Fan = None
    touchCount: int = 0
    installed: Installed = None

    def __str__(self):
        # report as valid json in logs
        return json.dumps(self.to_dict())

    def to_dict(self):
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data):
        dc = dataclass_from_dict(cls, data)
        dc.cooler = [UnitDetails(**c) for c in dc.cooler]
        dc.heater = [UnitDetails(**h) for h in dc.heater]
        return dc

    def __eq__(self, other):
        if not isinstance(other, RemoteStatus):
            return False
        s = flatten_dict(dataclasses.asdict(self))
        o = flatten_dict(dataclasses.asdict(other))

        for key in list(s.keys()):
            if "actual" in key.lower() or key in ("timestamp",):
                s.pop(key)
                o.pop(key)
        return s == o
