//
// Created by Administrator on 2026/7/8.
//

#include "main.h"
#include "can.h"
#include "cmsis_os2.h"
#include "Emm_V5/Emm_V5.h"
#include "SG90/sg90.h"
#include "Public/public.h"

/* 固定等待时间，按实际机械臂运动时间调整。 */
#define ARM_STARTUP_ZERO_DELAY_MS    2000U
#define ARM_PICK_MOVE_DELAY_MS       6500U
#define ARM_SERVO_MOVE_DELAY_MS       1000U
#define ARM_MAGNET_SETTLE_DELAY_MS   1000U
#define ARM_MAGNET_RELEASE_DELAY_MS   300U
#define ARM_PLACE_MOVE_DELAY_MS      5000U
#define ARM_RETURN_ZERO_DELAY_MS     1000U

static uint32_t arm_state_start_tick;

static bool arm_delay_elapsed(uint32_t delay_ms)
{
    return (uint32_t)(HAL_GetTick() - arm_state_start_tick) >= delay_ms;
}

void StartMotorTask(void *argument)
{
    /* ---- 初始化 CAN 滤波器并启动回零 ---- */
    USER_CAN1_Filter_Init();
    Emm_V5_Origin_Trigger_Return(1, 0, false);
    Emm_V5_Origin_Trigger_Return(2, 0, false);

    HAL_GPIO_TogglePin(GPIOF, GPIO_PIN_9);

    arm_state = ARM_STARTUP_ZERO;
    arm_state_start_tick = HAL_GetTick();
    arm_cmd.type = CMD_NONE;

    for (;;) {
        switch (arm_state) {
        case ARM_STARTUP_ZERO:
            /* 上电回零不再查询到位标志，固定等待后允许接收命令。 */
            if (arm_delay_elapsed(ARM_STARTUP_ZERO_DELAY_MS)) {
                arm_state = ARM_IDLE;
            }
            break;

        case ARM_IDLE:
            if (arm_cmd.type == CMD_EXEC) {
                Move_Pos(arm_cmd.pick_x, arm_cmd.pick_y);
                arm_state_start_tick = HAL_GetTick();
                arm_state = ARM_MOVING_TO_PICK;
            }
            break;

        case ARM_MOVING_TO_PICK:
            if (arm_delay_elapsed(ARM_PICK_MOVE_DELAY_MS)) {
                arm_state = ARM_PICK_ARRIVED;
            }
            break;

        case ARM_PICK_ARRIVED:
            /* 取子位置到位后先降下舵机。 */
            SG90_SetAngle(Low_Angle);
            arm_state_start_tick = HAL_GetTick();
            arm_state = ARM_SERVO_LOWERING;
            break;

        case ARM_SERVO_LOWERING:
            if (arm_delay_elapsed(ARM_SERVO_MOVE_DELAY_MS)) {
                /* 舵机下降到位后再吸合电磁铁。 */
                Magnet_ON();
                arm_state_start_tick = HAL_GetTick();
                arm_state = ARM_MAGNET_SETTLING;
            }
            break;

        case ARM_MAGNET_SETTLING:
            if (arm_delay_elapsed(ARM_MAGNET_SETTLE_DELAY_MS)) {
                /* 吸棋稳定后先升起舵机，再移动到落子位置。 */
                SG90_SetAngle(High_Angle);
                arm_state_start_tick = HAL_GetTick();
                arm_state = ARM_SERVO_RAISING_TO_PLACE;
            }
            break;

        case ARM_SERVO_RAISING_TO_PLACE:
            if (arm_delay_elapsed(ARM_SERVO_MOVE_DELAY_MS)) {
                Move_Pos(arm_cmd.place_x, arm_cmd.place_y);
                arm_state_start_tick = HAL_GetTick();
                arm_state = ARM_MOVING_TO_PLACE;
            }
            break;

        case ARM_MOVING_TO_PLACE:
            if (arm_delay_elapsed(ARM_PLACE_MOVE_DELAY_MS)) {
                arm_state = ARM_PLACE_ARRIVED;
            }
            break;

        case ARM_PLACE_ARRIVED:
            /* 到达落子位置后先降下舵机。 */
            SG90_SetAngle(Low_Angle);
            arm_state_start_tick = HAL_GetTick();
            arm_state = ARM_SERVO_LOWERING_TO_PLACE;
            break;

        case ARM_SERVO_LOWERING_TO_PLACE:
            if (arm_delay_elapsed(ARM_SERVO_MOVE_DELAY_MS)) {
                /* 舵机下降到位后再断开电磁铁。 */
                Magnet_OFF();
                arm_state_start_tick = HAL_GetTick();
                arm_state = ARM_MAGNET_RELEASING;
            }
            break;

        case ARM_MAGNET_RELEASING:
            if (arm_delay_elapsed(ARM_MAGNET_RELEASE_DELAY_MS)) {
                /* 确认棋子释放后再升高舵机。 */
                SG90_SetAngle(High_Angle);
                arm_state_start_tick = HAL_GetTick();
                arm_state = ARM_SERVO_RAISING;
            }
            break;

        case ARM_SERVO_RAISING:
            if (arm_delay_elapsed(ARM_SERVO_MOVE_DELAY_MS)) {
                /* 舵机升起后再触发两轴回零。 */
                /* 释放棋子后回到原点。 */
                Emm_V5_MMCL_Origin_Trigger_Return(1, 0, false);
                Emm_V5_MMCL_Origin_Trigger_Return(2, 0, false);
                Emm_V5_Multi_Motor_Cmd(0);
                arm_state_start_tick = HAL_GetTick();
                arm_state = ARM_MOVING_TO_ZERO;
            }
            break;

        case ARM_MOVING_TO_ZERO:
            if (arm_delay_elapsed(ARM_RETURN_ZERO_DELAY_MS)) {
                arm_cmd.type = CMD_NONE;
                arm_state = ARM_IDLE;
            }
            break;

        default:
            arm_state = ARM_IDLE;
            break;
        }

        osDelay(5);
    }
}
