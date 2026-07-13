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
    Emm_V5_Origin_Trigger_Return(1, 0, false);
    Emm_V5_Origin_Trigger_Return(2, 0, false);

    HAL_GPIO_TogglePin(GPIOF, GPIO_PIN_9);

    arm_state = ARM_IDLE;
    arm_cmd.type = CMD_NONE;

    for (;;) {

        switch (arm_state) {

        /* ============================================================
         *  IDLE：等待 CMD_EXEC 命令
         * ============================================================ */
        case ARM_IDLE:
            if (arm_cmd.type == CMD_EXEC) {
                /* 第一步：移动到取子位置 */
                Move_Pos(arm_cmd.pick_x, arm_cmd.pick_y);
                arm_state = ARM_MOVING_TO_PICK;
            }
            break;

        /* ============================================================
         *  MOVING_TO_PICK：轮询等待两电机到位（取子位置）
         * ============================================================ */
        case ARM_MOVING_TO_PICK:
            Is_Arrived();
            if (arrive_flag) {
                arm_state = ARM_PICK_ARRIVED;
            }
            break;

        /* ============================================================
         *  PICK_ARRIVED：吸合电磁铁取子，发起第二步移动
         * ============================================================ */
        case ARM_PICK_ARRIVED:
            Magnet_ON();                    /* 吸合电磁铁取子 */
            arrive_flag = false;
            /* 第二步：移动到放子位置 */
            Move_Pos(arm_cmd.place_x, arm_cmd.place_y);
            arm_state = ARM_MOVING_TO_PLACE;
            break;

        /* ============================================================
         *  MOVING_TO_PLACE：轮询等待两电机到位（放子位置）
         * ============================================================ */
        case ARM_MOVING_TO_PLACE:
            Is_Arrived();
            if (arrive_flag) {
                arm_state = ARM_PLACE_ARRIVED;
            }
            break;

        /* ============================================================
         *  PLACE_ARRIVED：释放电磁铁放子，回到 IDLE
         * ============================================================ */
        case ARM_PLACE_ARRIVED:
            Magnet_OFF();                   /* 释放电磁铁放子 */
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
