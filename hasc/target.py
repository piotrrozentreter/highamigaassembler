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
    supports_long_branches: bool
    prefers_long_alignment: bool

    @classmethod
    def for_cpu(cls, cpu: Union[CpuTarget, str]) -> "TargetSpec":
        cpu_target = cpu if isinstance(cpu, CpuTarget) else CpuTarget(cpu)
        if cpu_target is CpuTarget.M68000:
            return cls(
                cpu_target,
                False,  # supports_scaled_index
                False,  # supports_full_index_extension
                False,  # supports_memory_indirect
                False,  # supports_32bit_muldiv
                False,  # supports_extb_l
                False,  # supports_long_branches
                False,  # prefers_long_alignment
            )
        if cpu_target is CpuTarget.M68020:
            return cls(
                cpu_target,
                True,   # supports_scaled_index
                True,   # supports_full_index_extension
                False,  # supports_memory_indirect
                True,   # supports_32bit_muldiv
                True,   # supports_extb_l
                True,   # supports_long_branches
                True,   # prefers_long_alignment
            )
        raise ValueError(f"Unsupported CPU target: {cpu}")


DEFAULT_TARGET = TargetSpec.for_cpu(CpuTarget.M68000)
