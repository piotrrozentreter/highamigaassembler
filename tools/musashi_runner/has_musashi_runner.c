#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "m68k.h"

#define MEM_SIZE (2u * 1024u * 1024u)
#define DEFAULT_LOAD_ADDR 0x00010000u
#define DEFAULT_ENTRY_ADDR 0x00010000u
#define DEFAULT_STACK_ADDR 0x00003ff0u
#define DEFAULT_CYCLE_BUDGET 4000000u
#define DEFAULT_SLICE 20000u

#define MMIO_FAIL_ADDR 0x00100000u
#define MMIO_PASS_ADDR 0x00100004u
#define MMIO_STDOUT_ADDR 0x00100014u

static uint8_t g_mem[MEM_SIZE];
static uint32_t g_pass_count = 0;
static uint32_t g_fail_count = 0;

static uint32_t read_be16(const uint8_t* mem, uint32_t addr) {
    return ((uint32_t)mem[addr] << 8) | (uint32_t)mem[addr + 1];
}

static uint32_t read_be32(const uint8_t* mem, uint32_t addr) {
    return ((uint32_t)mem[addr] << 24) |
           ((uint32_t)mem[addr + 1] << 16) |
           ((uint32_t)mem[addr + 2] << 8) |
           (uint32_t)mem[addr + 3];
}

static void write_be16(uint8_t* mem, uint32_t addr, uint32_t value) {
    mem[addr] = (uint8_t)((value >> 8) & 0xffu);
    mem[addr + 1] = (uint8_t)(value & 0xffu);
}

static void write_be32(uint8_t* mem, uint32_t addr, uint32_t value) {
    mem[addr] = (uint8_t)((value >> 24) & 0xffu);
    mem[addr + 1] = (uint8_t)((value >> 16) & 0xffu);
    mem[addr + 2] = (uint8_t)((value >> 8) & 0xffu);
    mem[addr + 3] = (uint8_t)(value & 0xffu);
}

unsigned int m68k_read_disassembler_16(unsigned int address) {
    if (address + 1u >= MEM_SIZE) {
        return 0;
    }
    return read_be16(g_mem, address);
}

unsigned int m68k_read_disassembler_32(unsigned int address) {
    if (address + 3u >= MEM_SIZE) {
        return 0;
    }
    return read_be32(g_mem, address);
}

unsigned int m68k_read_memory_8(unsigned int address) {
    if (address >= MEM_SIZE) {
        m68k_pulse_bus_error();
        return 0;
    }
    return g_mem[address];
}

unsigned int m68k_read_memory_16(unsigned int address) {
    if (address + 1u >= MEM_SIZE) {
        m68k_pulse_bus_error();
        return 0;
    }
    return read_be16(g_mem, address);
}

unsigned int m68k_read_memory_32(unsigned int address) {
    if (address + 3u >= MEM_SIZE) {
        m68k_pulse_bus_error();
        return 0;
    }
    return read_be32(g_mem, address);
}

static void handle_mmio_write(unsigned int address, unsigned int value, unsigned int size_bits) {
    if (address == MMIO_FAIL_ADDR) {
        (void)value;
        (void)size_bits;
        g_fail_count++;
        m68k_end_timeslice();
        return;
    }
    if (address == MMIO_PASS_ADDR) {
        (void)value;
        (void)size_bits;
        g_pass_count++;
        m68k_end_timeslice();
        return;
    }
    if (address == MMIO_STDOUT_ADDR) {
        putchar((int)(value & 0xffu));
        fflush(stdout);
        return;
    }
}

void m68k_write_memory_8(unsigned int address, unsigned int value) {
    if (address == MMIO_FAIL_ADDR || address == MMIO_PASS_ADDR || address == MMIO_STDOUT_ADDR) {
        handle_mmio_write(address, value, 8u);
        return;
    }
    if (address >= MEM_SIZE) {
        m68k_pulse_bus_error();
        return;
    }
    g_mem[address] = (uint8_t)(value & 0xffu);
}

void m68k_write_memory_16(unsigned int address, unsigned int value) {
    if (address == MMIO_FAIL_ADDR || address == MMIO_PASS_ADDR || address == MMIO_STDOUT_ADDR) {
        handle_mmio_write(address, value, 16u);
        return;
    }
    if (address + 1u >= MEM_SIZE) {
        m68k_pulse_bus_error();
        return;
    }
    write_be16(g_mem, address, value);
}

void m68k_write_memory_32(unsigned int address, unsigned int value) {
    if (address == MMIO_FAIL_ADDR || address == MMIO_PASS_ADDR || address == MMIO_STDOUT_ADDR) {
        handle_mmio_write(address, value, 32u);
        return;
    }
    if (address + 3u >= MEM_SIZE) {
        m68k_pulse_bus_error();
        return;
    }
    write_be32(g_mem, address, value);
}

static unsigned parse_u32(const char* text, unsigned fallback) {
    char* end = NULL;
    unsigned long val = strtoul(text, &end, 0);
    if (end == text || *end != '\0') {
        return fallback;
    }
    if (val > 0xffffffffUL) {
        return fallback;
    }
    return (unsigned)val;
}

static int parse_cpu_type(const char* text) {
    if (strcmp(text, "68000") == 0) return M68K_CPU_TYPE_68000;
    if (strcmp(text, "68010") == 0) return M68K_CPU_TYPE_68010;
    if (strcmp(text, "68EC020") == 0) return M68K_CPU_TYPE_68EC020;
    if (strcmp(text, "68020") == 0) return M68K_CPU_TYPE_68020;
    return M68K_CPU_TYPE_68000;
}

static void usage(const char* argv0) {
    fprintf(stderr,
        "Usage: %s <program.bin> [--entry <addr>] [--stack <addr>] [--load <addr>]\\n"
        "       [--cycles <budget>] [--slice <cycles>] [--cpu <68000|68010|68EC020|68020>]\\n",
        argv0);
}

int main(int argc, char** argv) {
    const char* path = NULL;
    unsigned entry_addr = DEFAULT_ENTRY_ADDR;
    unsigned stack_addr = DEFAULT_STACK_ADDR;
    unsigned load_addr = DEFAULT_LOAD_ADDR;
    unsigned cycle_budget = DEFAULT_CYCLE_BUDGET;
    unsigned slice_cycles = DEFAULT_SLICE;
    int cpu_type = M68K_CPU_TYPE_68000;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--entry") == 0 && i + 1 < argc) {
            entry_addr = parse_u32(argv[++i], entry_addr);
        } else if (strcmp(argv[i], "--stack") == 0 && i + 1 < argc) {
            stack_addr = parse_u32(argv[++i], stack_addr);
        } else if (strcmp(argv[i], "--load") == 0 && i + 1 < argc) {
            load_addr = parse_u32(argv[++i], load_addr);
        } else if (strcmp(argv[i], "--cycles") == 0 && i + 1 < argc) {
            cycle_budget = parse_u32(argv[++i], cycle_budget);
        } else if (strcmp(argv[i], "--slice") == 0 && i + 1 < argc) {
            slice_cycles = parse_u32(argv[++i], slice_cycles);
        } else if (strcmp(argv[i], "--cpu") == 0 && i + 1 < argc) {
            cpu_type = parse_cpu_type(argv[++i]);
        } else if (argv[i][0] == '-') {
            usage(argv[0]);
            return 2;
        } else if (!path) {
            path = argv[i];
        } else {
            usage(argv[0]);
            return 2;
        }
    }

    if (!path) {
        usage(argv[0]);
        return 2;
    }

    FILE* f = fopen(path, "rb");
    if (!f) {
        perror("open");
        return 2;
    }

    memset(g_mem, 0, sizeof(g_mem));
    g_pass_count = 0;
    g_fail_count = 0;

    if (load_addr >= MEM_SIZE) {
        fprintf(stderr, "Load address out of range: 0x%08x\\n", load_addr);
        fclose(f);
        return 2;
    }

    size_t max_bytes = MEM_SIZE - load_addr;
    size_t nread = fread(&g_mem[load_addr], 1, max_bytes, f);
    int truncated = 0;
    if (nread == max_bytes) {
        int probe = fgetc(f);
        if (probe != EOF) {
            truncated = 1;
        }
    }
    fclose(f);

    if (nread == 0) {
        fprintf(stderr, "No program bytes loaded from %s\\n", path);
        return 2;
    }
    if (truncated) {
        fprintf(stderr, "Program too large for memory map: %s\\n", path);
        return 2;
    }

    write_be32(g_mem, 0u, stack_addr);
    write_be32(g_mem, 4u, entry_addr);

    m68k_init();
    m68k_set_cpu_type(cpu_type);
    m68k_pulse_reset();

    m68k_set_reg(M68K_REG_SP, stack_addr);
    m68k_set_reg(M68K_REG_PC, entry_addr);

    unsigned executed = 0;
    while (executed < cycle_budget && g_pass_count == 0 && g_fail_count == 0) {
        unsigned remaining = cycle_budget - executed;
        unsigned chunk = remaining < slice_cycles ? remaining : slice_cycles;
        int ran = m68k_execute((int)chunk);
        if (ran <= 0) {
            break;
        }
        executed += (unsigned)ran;
    }

    fprintf(stderr, "musashi-runner: pass=%u fail=%u cycles=%u\\n", g_pass_count, g_fail_count, executed);

    if (g_fail_count > 0) {
        return 1;
    }
    if (g_pass_count > 0) {
        return 0;
    }

    fprintf(stderr, "musashi-runner: no PASS/FAIL MMIO signal before cycle budget\\n");
    return 3;
}
