//
// Created by Administrator on 2026/7/8.
//

#include "main.h"
#include "can.h"
#include "cmsis_os2.h"
#include "Emm_V5/Emm_V5.h"

void StartMotorTask(void *argument) {
    //USER_CAN1_Filter_Init();
    for (;;) {
        osDelay(10);
        Is_Arrived();
    }
}
