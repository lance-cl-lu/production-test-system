# Non-Soldering Circuit Architecture Guide

This document provides a hardware setup, logic control matrix, and code implementation for controlling impedance switching (**0Ω / Open / 1.5MΩ / 3.5MΩ**) using an **MS51FB9AE MCU** and a **2-Channel Relay Module**.

---

## 1. System Architecture Diagram

All connections on the high-voltage/test side use **screw terminal blocks** and **DIP through-hole resistors**, requiring **no soldering iron**.

```
                              [ 2-Channel 5V Relay Module ]
                               ┌───────────────────────────────────────┐
  [ MS51FB9AE MCU ]            │         [ Screw Terminal Block ]      │
  ┌───────────────┐            │                                       │
  │            5V ├─[Dupont]──►│ VCC                                   │
  │           GND ├─[Dupont]──►│ GND                                   │
  │               │            │                                       │
  │      P1.5(IN1)├─[Dupont]──►│ IN1 ───► Relay 1                      │
  │      P1.4(IN2)├─[Dupont]──►│ IN2 ───► Relay 2                      │
  └───────────────┘            │                                       │
                               │   [Relay 1 Terminal]   [Relay 2 Terminal]
                               │     NO1   COM1           NO2   COM2   │
                               └──────┬─────┬──────────────┬─────┬─────┘
                                      │     │              │     │
                                      │     └───┬──────────┘     │
                                      │         │                │
                                      │    [Contact Point A]     │
                                      │    (Test Point 1)        │
                                      │                          │
                                 [1.5MΩ Resistor]          [3.5MΩ Resistor]
                                      │                          │
                                      └─────────┬────────────────┘
                                                │
                                           [Contact Point B] ───► System GND (0Ω Ref)
                                          (Test Point 2)
```

---

## 2. Hardware Connection Details (No Soldering Required)

1. **MCU Control Side (Dupont Wires):**
   * `5V` (MCU) $\rightarrow$ `VCC` (Relay Module)
   * `GND` (MCU) $\rightarrow$ `GND` (Relay Module)
   * `P1.5` (MCU) $\rightarrow$ `IN1` (Relay Module - Controls 1.5MΩ Channel)
   * `P1.4` (MCU) $\rightarrow$ `IN2` (Relay Module - Controls 3.5MΩ Channel)

2. **Test Load Side (Screw Terminals & DIP Resistors):**
   * **Contact Point A (Test Node 1):** Connect a wire bridging **COM1** and **COM2** together.
   * **1.5MΩ Resistor (DIP Package):** Insert one lead into **NO1** terminal and tighten the screw. Connect the other lead to **Contact Point B (GND)**.
   * **3.5MΩ Resistor (DIP Package):** Insert one lead into **NO2** terminal and tighten the screw. Connect the other lead to **Contact Point B (GND)**.
   * **Contact Point B (Test Node 2):** Connect to System Ground (`GND`).
   * **NC1 & NC2 Terminals:** Leave **Floating** (Unconnected) for Open mode, or connect **NC1** to GND if a default **0Ω (Short)** mode is required.

---

## 3. Control Logic & Impedance Truth Table

Assuming Low-Level Trigger Relay Module (Standard Type):

| IN1 (P1.5) | IN2 (P1.4) | Relay 1 (NO1) | Relay 2 (NO2) | Connected Path (Point A to B) | Measured Impedance |
| :---: | :---: | :---: | :---: | :--- | :--- |
| **HIGH (1)** | **HIGH (1)** | Open (Off) | Open (Off) | Disconnected (Floating) | **Open (High-Z)** |
| **LOW (0)**  | **HIGH (1)** | Closed (On) | Open (Off) | Through 1.5MΩ to GND | **1.5 MΩ** |
| **HIGH (1)** | **LOW (0)**  | Open (Off) | Closed (On) | Through 3.5MΩ to GND | **3.5 MΩ** |
| **LOW (0)**  | **LOW (0)**  | Closed (On) | Closed (On) | 1.5MΩ // 3.5MΩ Parallel | **~1.05 MΩ** |

> **Note for 0Ω Configuration:** If NC1 is connected to GND instead of floating, setting `IN1 = HIGH, IN2 = HIGH` will route Point A directly to GND via NC1, giving a **0Ω (Short Circuit)** output.

---

## 4. Bill of Materials (BOM)

| Component | Description / Specification | Quantity | Mounting Type |
| :--- | :--- | :---: | :--- |
| **MCU Board** | MS51FB9AE Development Board | 1 | Header Pins |
| **Relay Module** | 2-Channel 5V Relay Module with Optocoupler | 1 | Screw Terminals & Pins |
| **Resistor 1** | 1.5 MΩ ±1% 1/4W (or 1/2W) DIP Color-code Resistor | 1 | Plug-in (Screw Fixed) |
| **Resistor 2** | 3.5 MΩ ±1% 1/4W (or 1/2W) DIP Color-code Resistor | 1 | Plug-in (Screw Fixed) |
| **Wiring** | Female-to-Female Dupont Wires (20cm) | 4+ | Plug-in |

---

## 5. C51 Sample Firmware Code

```c
#include "MS51_16K.h"

// Define GPIO Control Pins
#define RELAY_1.5M   P15   // Controls IN1
#define RELAY_3.5M   P14   // Controls IN2

void GPIO_Init(void) {
    // Configure P1.4 and P1.5 as Push-Pull Outputs
    P1M1 &= ~(SET_BIT5 | SET_BIT4);
    P1M2 |=  (SET_BIT5 | SET_BIT4);
    
    // Default: Both Relays OFF (Open Circuit)
    RELAY_1.5M = 1;
    RELAY_3.5M = 1;
}

void Set_Impedance(uint8_t mode) {
    switch(mode) {
        case 0: // Mode 0: Open / High-Z (or 0Ω if NC connected)
            RELAY_1.5M = 1;
            RELAY_3.5M = 1;
            break;
            
        case 1: // Mode 1: 1.5 MΩ
            RELAY_1.5M = 0;
            RELAY_3.5M = 1;
            break;
            
        case 2: // Mode 2: 3.5 MΩ
            RELAY_1.5M = 1;
            RELAY_3.5M = 0;
            break;
            
        default:
            RELAY_1.5M = 1;
            RELAY_3.5M = 1;
            break;
    }
}

void main(void) {
    uint8_t cmd = 0;
    
    // Clock & UART Initialization
    MODIFY_HIRC(HIRC_16);
    UART_Open(16000000, 9600);
    GPIO_Init();
    
    while(1) {
        cmd = Receive_Data(UART0);
        
        if (cmd == '0') {
            Set_Impedance(0); // Open
            Send_Data(UART0, '0');
        } 
        else if (cmd == '1') {
            Set_Impedance(1); // 1.5M
            Send_Data(UART0, '1');
        } 
        else if (cmd == '2') {
            Set_Impedance(2); // 3.5M
            Send_Data(UART0, '2');
        }
    }
}
```