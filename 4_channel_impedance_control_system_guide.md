# 4-Channel Impedance Control System Architecture Guide

This document details the hardware design, wire-to-terminal architecture, logic mapping, and GPIO table for controlling 4 independent Test Points (**TP1 ~ TP4**). Each test point can be set to **Open**, **1.5MΩ**, or **3.5MΩ** using an **STM32F103C8T6 MCU** and an **8-Channel 5V Relay Module**.

## 1. System Architecture Diagram

```
                                      [ 8-Channel 5V Relay Module ]
                                    ┌────────────────────────────────────────────────────────┐
  [ STM32F103C8T6 ]                 │                  [ Screw Terminals ]                   │
  ┌─────────────────┐               │                                                        │
  │              5V ├──[Dupont]────►│ VCC                                                    │
  │             GND ├──[Dupont]────►│ GND                                                    │
  │                 │               │                                                        │
  │        PA0(IN1) ├──[Dupont]────►│ IN1 ──► Relay 1 ─┬── NO1 ───[ 1.5MΩ ]───┐              │
  │        PA1(IN2) ├──[Dupont]────►│ IN2 ──► Relay 2 ─┼── NO2 ───[ 3.5MΩ ]───┼──► GND       │
  │                 │               │                  └── COM1/2 (Bridge)────┼────────────► [ Test Point 1 (TP1) ]
  │                 │               │                                         │
  │        PA2(IN3) ├──[Dupont]────►│ IN3 ──► Relay 3 ─┬── NO3 ───[ 1.5MΩ ]───┤              │
  │        PA3(IN4) ├──[Dupont]────►│ IN4 ──► Relay 4 ─┼── NO4 ───[ 3.5MΩ ]───┼──► GND       │
  │                 │               │                  └── COM3/4 (Bridge)────┼────────────► [ Test Point 2 (TP2) ]
  │                 │               │                                         │
  │        PA4(IN5) ├──[Dupont]────►│ IN5 ──► Relay 5 ─┬── NO5 ───[ 1.5MΩ ]───┤              │
  │        PA5(IN6) ├──[Dupont]────►│ IN6 ──► Relay 6 ─┼── NO6 ───[ 3.5MΩ ]───┼──► GND       │
  │                 │               │                  └── COM5/6 (Bridge)────┼────────────► [ Test Point 3 (TP3) ]
  │                 │               │                                         │
  │        PA6(IN7) ├──[Dupont]────►│ IN7 ──► Relay 7 ─┬── NO7 ───[ 1.5MΩ ]───┤              │
  │        PA7(IN8) ├──[Dupont]────►│ IN8 ──► Relay 8 ─┼── NO8 ───[ 3.5MΩ ]───┼──► GND       │
  └─────────────────┘               │                  └── COM7/8 (Bridge)────┴────────────► [ Test Point 4 (TP4) ]
                                    └────────────────────────────────────────────────────────┘
```

## 2. Wiring & Screw Terminal Setup (No Soldering Required)

### Control Signals (Dupont Wires)

* **Power Supply:** Connect STM32 `5V` (or `VIN`) $\rightarrow$ Relay `VCC`, and STM32 `GND` $\rightarrow$ Relay `GND`.
* **Control Input Mapping:**
  * **Test Point 1 (TP1):** `PA0` $\rightarrow$ `IN1` | `PA1` $\rightarrow$ `IN2`
  * **Test Point 2 (TP2):** `PA2` $\rightarrow$ `IN3` | `PA3` $\rightarrow$ `IN4`
  * **Test Point 3 (TP3):** `PA4` $\rightarrow$ `IN5` | `PA5` $\rightarrow$ `IN6`
  * **Test Point 4 (TP4):** `PA6` $\rightarrow$ `IN7` | `PA7` $\rightarrow$ `IN8`

### Test Point Wiring (Screw Terminals & DIP Resistors)

Repeat the following configuration for each channel pair ($N = 1, 2, 3, 4$):

1. **Test Node (TP** $N$**):** Bridge **COM$(2N-1)$** and **COM$(2N)$** with a jumper wire. This joined terminal serves as **Test Point** $N$ **(TP** $N$**)**.
2. **1.5MΩ Resistor (DIP Package):** Insert one pin into **NO$(2N-1)$** and tighten the screw. Connect the other pin to System **GND**.
3. **3.5MΩ Resistor (DIP Package):** Insert one pin into **NO$(2N)$** and tighten the screw. Connect the other pin to System **GND**.
4. **NC Terminals:** Leave all **NC** (Normally Closed) terminals **unconnected (Floating)**.

## 3. Channel Control Logic & UART Commands

Most 8-Channel Relay Modules use **Low-Level Triggering** (`RESET` / `0` = Relay ON, `SET` / `1` = Relay OFF).

### State Truth Table (Example for TP1)

| MCU PA0 (IN1) | MCU PA1 (IN2) | Relay 1 (NO1) | Relay 2 (NO2) | TP1 Route to GND | Measured State |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **HIGH (1)** | **HIGH (1)** | OFF (Open) | OFF (Open) | Disconnected | **Open (High-Z)** |
| **LOW (0)** | **HIGH (1)** | ON (Closed) | OFF (Open) | Through 1.5MΩ | **1.5 MΩ** |
| **HIGH (1)** | **LOW (0)** | OFF (Open) | ON (Closed) | Through 3.5MΩ | **3.5 MΩ** |
| **LOW (0)** | **LOW (0)** | ON (Closed) | ON (Closed) | Parallel (1.5M // 3.5M) | **~1.05 MΩ** |

### Default UART Command Mapping (115200 Baud, 8N1)

| Test Point | Command Character | Configured State | Active Relay Pin |
| :---: | :---: | :---: | :---: |
| **TP1** | `'A'` / `'B'` / `'C'` | Open / 1.5MΩ / 3.5MΩ | PA0 / PA1 |
| **TP2** | `'D'` / `'E'` / `'F'` | Open / 1.5MΩ / 3.5MΩ | PA2 / PA3 |
| **TP3** | `'G'` / `'H'` / `'I'` | Open / 1.5MΩ / 3.5MΩ | PA4 / PA5 |
| **TP4** | `'J'` / `'K'` / `'L'` | Open / 1.5MΩ / 3.5MΩ | PA6 / PA7 |

## 4. Hardware Bill of Materials (BOM)

| Item | Model / Specification | Quantity | Attachment Method |
| :--- | :--- | :---: | :--- |
| **MCU Board** | STM32F103C8T6 (Blue Pill Core Board) | 1 | Header Pins |
| **Relay Module** | 8-Channel 5V Relay Module with Optocoupler | 1 | Screw Terminals & Header Pins |
| **Resistors** | 1.5MΩ 1/4W (or 1/2W) DIP Metal Film 1% | 4 | Screw Terminals |
| **Resistors** | 3.5MΩ 1/4W (or 1/2W) DIP Metal Film 1% | 4 | Screw Terminals |
| **Jumper Wires** | Female-to-Female Dupont Wires (20cm) | 10+ | Plug-in |
| **Debugger** | ST-Link V2 (for STM32CubeIDE flashing) | 1 | Plug-in |