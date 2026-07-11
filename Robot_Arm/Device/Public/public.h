//
// Created by Administrator on 2026/7/11.
//

#ifndef INC_2024E_PUBLIC_H
#define INC_2024E_PUBLIC_H
#include <stdint.h>
#include <stdbool.h>

/* ---- 全局变量 ---- */
extern int32_t last_pos_yaw;
extern int32_t last_pos_pitch;
extern bool    arrive_flag;

/* ---- 机械臂命令类型 ---- */
typedef enum {
    CMD_NONE = 0,
    CMD_GET_CHESS,      /* 移动到 (x,y)，到位后吸合电磁铁取子 */
    CMD_PUT_CHESS,      /* 移动到 (x,y)，到位后释放电磁铁放子 */
} ArmCmdType_t;

/* ---- 机械臂状态机 ---- */
typedef enum {
    ARM_IDLE = 0,       /* 空闲，等待新命令               */
    ARM_MOVING,         /* 已发送移动指令，轮询等待到位    */
    ARM_ARRIVED,        /* 已到位，执行末端动作（吸合/释放）*/
} ArmState_t;

/* ---- 命令结构体 ---- */
typedef struct {
    ArmCmdType_t type;
    int32_t      x;
    int32_t      y;
} ArmCmd_t;

extern ArmCmd_t   arm_cmd;
extern ArmState_t arm_state;

#endif //INC_2024E_PUBLIC_H
