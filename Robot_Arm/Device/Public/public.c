#include <stdbool.h>
#include <stdint.h>
#include "main.h"
#include "public.h"
//
// Created by Administrator on 2026/7/11.
//
int32_t last_pos_yaw   = 0;
int32_t last_pos_pitch = 0;

bool arrive_flag = false;

ArmCmd_t   arm_cmd   = { .type = CMD_NONE, .x = 0, .y = 0 };
ArmState_t arm_state = ARM_IDLE;
