# 机械臂控制系统

基于 STM32F4 的机械臂控制系统，通过串口屏幕（Nextion）交互，与树莓派协作完成棋子取放。

## 硬件架构

| 外设 | 接口 | 引脚 | 波特率/频率 |
|------|------|------|------------|
| 树莓派 | USART1 | PA9 (TX) / PA10 (RX) | 921600 |
| Nextion 串口屏 | USART3 | PB10 (TX) / PB11 (RX) | 115200 |
| 步进电机 ×2 (Emm_V5) | CAN1 | PA11 (RX) / PA12 (TX) | 1Mbps |
| SG90 舵机 | TIM2_CH4 | PA3 (PWM) | 50Hz |
| 电磁铁 | GPIO | PA5 | — |
| LED 指示灯 | GPIO | PF9 | — |

## 舵机与电磁铁

| 宏/函数 | 值/引脚 | 说明 |
|---------|---------|------|
| `High_Angle` | 10° | 舵机抬起位（运输姿态） |
| `Low_Angle` | 180° | 舵机下压位（取子/放子） |
| `Magnet_ON` | PA5 高电平 | 电磁铁吸合 |
| `Magnet_OFF` | PA5 低电平 | 电磁铁释放 |

## 树莓派通信协议（USART1, 921600, 文本协议）

**帧格式**：逗号分隔，`\n` 结尾，大小写不敏感

### MCU → 树莓派

| 命令 | 格式                                 | 说明 |
|------|------------------------------------|------|
| `PLACE` | `PLACE,<B\|W>,<row>,<num>,<col>\n` | 请求放子位置 |
| `BATTLE_START` | `BATTLE_START,<B\|W>\n`            | 比赛开始，指定颜色 |
| `READY` | `READY\n`                          | MCU 就绪通知 |

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
| `ZERO` | 电机使能并触发回零 |
| `ON` / `OFF` | 电磁铁吸合 / 释放 |
| `LOW` / `HIGH` | 舵机低位 / 高位 |
| `DISABLE` | 关闭电机使能 |
| `TEST` | 读取两轴当前脉冲值并打印 |
| `COLOR=<0\|1>` | 设定颜色（0=B, 1=W） |
| `POSR=<n>` | 设定行号 |
| `POSC=<n>` | 设定列号 |
| `PLACE` | 发送 PLACE 给树莓派 |
| `BATTLE` | 发送 BATTLE_START 给树莓派 |
| `READY` | 发送 READY 给树莓派 |

## FreeRTOS 任务

| 任务 | 周期 | 优先级 | 栈大小 | 职责 |
|------|------|--------|--------|------|
| ReceiveTask | 5ms | Normal | 1KB (256 words) | 解析树莓派协议，触发机械臂命令 |
| MotorTask | 5ms | Normal | 1KB (256 words) | 机械臂状态机，CAN 控制电机，LED 标志 |
| ScreenTask | 10ms | Normal | 1KB (256 words) | VOFA 命令解析，屏幕消息输出 |
| Sg90Task | 1s | AboveNormal | 512B (128 words) | 舵机初始化 |
| defaultTask | 1ms | Normal | 512B (128 words) | 空闲（保留） |

## 机械臂状态机

每一步棋的完整流程（`MotorTask` 固定延时状态机，时长可根据实际运动调整）：

```
ARM_IDLE                     ← 空闲，等待命令
  ↓ CMD_EXEC
ARM_MOVING_TO_PICK           ← 移动到取子位置（6500ms）
  ↓
ARM_PICK_ARRIVED → 舵机下压 Low_Angle
  ↓
ARM_SERVO_LOWERING           ← 舵机下降等待（500ms）
  ↓
ARM_MAGNET_SETTLING → 电磁铁吸合 Magnet_ON
  ↓                        ← 吸合稳定等待（500ms）
ARM_SERVO_RAISING_TO_PLACE → 舵机抬起 High_Angle
  ↓                        ← 舵机上升等待（500ms）
ARM_MOVING_TO_PLACE          ← 移动到落子位置（4500ms）
  ↓
ARM_PLACE_ARRIVED → 舵机下压 Low_Angle
  ↓
ARM_SERVO_LOWERING_TO_PLACE  ← 舵机下降等待（500ms）
  ↓
ARM_MAGNET_RELEASING → 电磁铁释放 Magnet_OFF
  ↓                        ← 释放等待（300ms）
ARM_SERVO_RAISING → 舵机抬起 High_Angle
  ↓                        ← 舵机上升等待（500ms）
ARM_MOVING_TO_ZERO → 触发两轴回零，LED (PF9) 亮 0.5s
  ↓                        ← 回零等待（500ms）
ARM_IDLE                     ← 回到空闲，LED (PF9) 灭
```

### 延时配置宏（`motor_task.c`）

| 宏 | 值 | 说明 |
|---|----|------|
| `ARM_STARTUP_ZERO_DELAY_MS` | 2000 | 上电回零等待 |
| `ARM_PICK_MOVE_DELAY_MS` | 6500 | 取子移动 |
| `ARM_SERVO_MOVE_DELAY_MS` | 500 | 舵机升降 |
| `ARM_MAGNET_SETTLE_DELAY_MS` | 500 | 电磁铁吸合稳定 |
| `ARM_MAGNET_RELEASE_DELAY_MS` | 300 | 电磁铁释放 |
| `ARM_PLACE_MOVE_DELAY_MS` | 4500 | 落子移动 |
| `ARM_RETURN_ZERO_DELAY_MS` | 500 | 回零等待 + LED 亮灯时长 |

## LED 指示灯

| 引脚 | 用途 |
|------|------|
| PF9 | 每步棋回零触发时亮 0.5s；CAN 发送超时时翻转；系统错误时 500ms 周期闪烁 |

## 开发日志

- USART1 与树莓派通信：`ReceiveTask`
- USART3 与串口屏通信：`ScreenTask`
- **问题**：树莓派返回 ERROR/BUSY 后单片机卡死 → 增大任务栈到 **256 words (1KB)**
- **变更**：丝杆结构变更，舵机角度宏修改（`High_Angle` 0→10）
- **新增**：每步棋回零完成后 LED PF9 闪亮 0.5s 作为标志
- 串口调试技巧：启用 `fflush(stdout)` 实时输出

## 构建

STM32CubeMX 项目，CMake 构建，FreeRTOS + CMSIS-OS2。
