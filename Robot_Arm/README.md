# 机械臂控制系统

基于 STM32F4 的机械臂控制系统，通过串口屏幕（Nextion）交互，与树莓派协作完成棋子取放。

## 硬件架构

| 外设 | 接口 | 引脚 | 波特率 |
|------|------|------|--------|
| 树莓派 | USART1 | PA9 (TX) / PA10 (RX) | 921600 |
| Nextion 串口屏 | USART3 | PB10 (TX, DMA) / PB11 (RX) | 115200 |
| 步进电机 ×2 (Emm_V5) | CAN1 | — | — |
| SG90 舵机 | TIM2_CH4 | PA3 (PWM) | 50Hz |
| 电磁铁 | GPIO | PA5 | — |

## 树莓派通信协议（USART1, 921600, 文本协议）

**帧格式**：逗号分隔，`\n` 结尾，大小写不敏感

### MCU → 树莓派

| 命令 | 格式 | 说明 |
|------|------|------|
| `PLACE` | `PLACE,<B\|W>,<row>,<col>\n` | 请求放子位置 |
| `BATTLE_START` | `BATTLE_START,<B\|W>\n` | 比赛开始，指定颜色 |
| `READY` | `READY\n` | MCU 就绪通知 |

### 树莓派 → MCU

| 命令 | 格式 | 说明 |
|------|------|------|
| `PULSES` | `PULSES,<pick_p1>,<pick_p2>,<place_p1>,<place_p2>` | 返回取/放子脉冲坐标 |
| `ERROR` | `ERROR,<code>,<msg>` | 错误信息 |
| `BUSY` | `BUSY,<msg>` | 忙碌信息 |

## 串口屏调试命令（USART3, VOFA+ 格式）

**帧格式**：`KEY=VALUE!`，支持多命令 `K1=V1,K2=V2!`

| 命令 | 说明 |
|------|------|
| `ZERO` | 电机归零 |
| `ON` / `OFF` | 电磁铁吸合 / 释放 |
| `LOW` / `HIGH` | 舵机低/高位 |
| `DISABLE` | 禁用电机关闭 |
| `TEST` | 测试移动 (800, 800) |
| `COLOR=<0\|1>` | 设定颜色（0=B, 1=W） |
| `POSR=<n>` | 设定行号 |
| `POSC=<n>` | 设定列号 |
| `PLACE` | 发送 PLACE 给树莓派 |
| `BATTLE` | 发送 BATTLE_START 给树莓派 |
| `READY` | 发送 READY 给树莓派 |

## FreeRTOS 任务

| 任务 | 周期 | 优先级 | 栈大小 | 职责 |
|------|------|--------|--------|------|
| ReceiveTask | 5ms | Normal | 512B | 解析树莓派协议，触发机械臂动作 |
| MotorTask | 10ms | Normal | 512B | 机械臂状态机，CAN 控制电机 |
| ScreenTask | 10ms | Normal | 512B | VOFA 命令解析，屏幕消息输出 |
| Sg90Task | 1s | AboveNormal | 512B | 舵机控制 |

## 机械臂状态机

```
IDLE → MOVING_TO_PICK → PICK_ARRIVED → MOVING_TO_PLACE → PLACE_ARRIVED → IDLE
```

## 开发日志

- USART1 与树莓派通信：`ReceiveTask`
- USART3 与串口屏通信：`ScreenTask`
- **问题**：树莓派返回 ERROR/BUSY 后单片机卡死 → 增大任务栈到 **256 words (1KB)**
- 串口调试技巧：启用 `fflush(stdout)` 实时输出

## 构建

STM32CubeIDE 项目，CMake 构建，FreeRTOS + CMSIS-OS2。
