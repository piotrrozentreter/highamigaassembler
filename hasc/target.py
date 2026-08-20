from dataclasses import dataclass
from enum import Enum
from typing import Union


class CpuTarget(str, Enum):
    M68000 = "68000"
    M68020 = "68020"


@dataclass(frozen=True)
class TargetSpec:
    cpu: CpuTarget
    supports_scaled_index: bool
    supports_full_index_extension: bool
    supports_memory_indirect: bool
    supports_32bit_muldiv: bool
    supports_extb_l: bool

    @classmethod
    def for_cpu(cls, cpu: Union[CpuTarget, str]) -> "TargetSpec":
        cpu_target = cpu if isinstance(cpu, CpuTarget) else CpuTarget(cpu)
        if cpu_target is CpuTarget.M68000:
            return cls(cpu_target, False, False, False, False, False)
        if cpu_target is CpuTarget.M68020:
            return cls(cpu_target, True, True, False, True, True)
        raise ValueError(f"Unsupported CPU target: {cpu}")


DEFAULT_TARGET = TargetSpec.for_cpu(CpuTarget.M68000)