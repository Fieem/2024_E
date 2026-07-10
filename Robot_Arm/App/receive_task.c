#include "main.h"
#include "usart.h"
#include <stm32f4xx_hal_uart.h>
#include "Communicate/communicate.h"
#include "Test/test.h"
//
// Created by Administrator on 2026/7/8.
//
void StartReceiveTask(void *argument) {
    comm_init();                //启动 USART1 单字节中断接收
    VisionData_t data;
    for (;;) {
        if (comm_get_vision_data(&data)) {

        }
    }
}

/* ================================================================
 *  HAL UART 接收回调（覆盖 __weak 默认实现）
 *  每收到一个字节就推入环形缓冲区，然后重新启动单字节接收
 * ================================================================ */

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART1)
    {
        /* 视觉模块 → 喂给 communicate 解析器 */
        comm_parse_byte(comm_rx_byte);
        HAL_UART_Receive_IT(&huart1, &comm_rx_byte, 1);
    }
    else if (huart == TEST_VOFA_HUART)
    {
        /* VOFA+ → 推入环形缓冲区 */
        rx_ring_push(s_rx_byte);
        HAL_UART_Receive_IT(TEST_VOFA_HUART, &s_rx_byte, 1);
    }
}