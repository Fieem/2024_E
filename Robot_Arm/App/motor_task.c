//
// Created by Administrator on 2026/7/8.
//

#include "main.h"
#include "can.h"
#include "cmsis_os2.h"
#include "Emm_V5/Emm_V5.h"
#include "SG90/sg90.h"
#include "Public/public.h"

void StartMotorTask(void *argument)
{
    /* ---- 初始化 CAN 滤波器并启动接收 ---- */
    USER_CAN1_Filter_Init();

    arm_state = ARM_IDLE;
    arm_cmd.type = CMD_NONE;

    for (;;) {

        switch (arm_state) {

        /* ============================================================
         *  IDLE：等待新命令
         * ============================================================ */
        case ARM_IDLE:
            if (arm_cmd.type != CMD_NONE) {
                /* 有新命令 → 发送移动指令 */
                Move_Pos(arm_cmd.x, arm_cmd.y);
                arm_state = ARM_MOVING;
            }
            break;

        /* ============================================================
         *  MOVING：轮询等待两个电机到位
         * ============================================================ */
        case ARM_MOVING:
            Is_Arrived();               /* 非阻塞，单次 < 10ms */
            if (arrive_flag) {
                arm_state = ARM_ARRIVED;
            }
            break;

        /* ============================================================
         *  ARRIVED：执行末端动作（电磁铁），然后回到 IDLE
         * ============================================================ */
        case ARM_ARRIVED:
            switch (arm_cmd.type) {
            case CMD_GET_CHESS:
                Magnet_ON();            /* 吸合电磁铁取子 */
                break;
            case CMD_PUT_CHESS:
                Magnet_OFF();           /* 释放电磁铁放子 */
                break;
            default:
                break;
            }
            /* 清理标志，准备接收下一条命令 */
            arrive_flag   = false;
            arm_cmd.type  = CMD_NONE;
            arm_state     = ARM_IDLE;
            break;

        default:
            arm_state = ARM_IDLE;
            break;
        }

        osDelay(10);   /* 10ms 一个状态机周期 */
    }
}
