//
// Created by Administrator on 2026/6/4.
// 视觉模块通信 - USART1, 115200, PA9/PA10
// 数据包: 0x55 0xAA | float[2] | uint32 checksum | 0x0D
//

#ifndef INC_2023E_COMMUNICATE_H
#define INC_2023E_COMMUNICATE_H

#include <stdbool.h>

#include "main.h"
#include "usart.h"
#include <string.h>

/* 数据包结构 */
#define COMM_PACKET_SIZE    15U     // 完整数据包大小: 2 + 8 + 4 + 1
#define COMM_DATA_SIZE      2U      // 2 个 float
#define COMM_HEADER1        0x55U   // 帧头1
#define COMM_HEADER2        0xAAU   // 帧头2
#define COMM_TAIL           0x0DU   // 帧尾

/* 视觉模块发来的解析结果 */
typedef struct {
    float yaw_error;        // yaw 误差
    float pitch_error;      // pitch 误差
    bool  new_data;         // 新数据标志（收到完整包后置 true，用户读取后清 false）
} VisionData_t;

extern VisionData_t vision_data;
extern uint8_t comm_rx_byte;   /* HAL_UART_Receive_IT 用的单字节接收缓冲 */

/* 函数声明 */
void comm_init(void);
void comm_parse_byte(uint8_t byte);
bool comm_get_vision_data(VisionData_t *out);
void comm_send_ack(uint8_t status);
void comm_flush_rx(void);

#endif //INC_2023E_COMMUNICATE_H
