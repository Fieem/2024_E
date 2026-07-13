//
// Created by Administrator on 2026/6/4.
// 视觉模块通信 - 接收与解析
//

#include "communicate.h"

VisionData_t vision_data = {0};

/* 解析状态机 */
typedef enum {
    STATE_HEADER1 = 0,      // 等待帧头 0x55
    STATE_HEADER2,          // 等待帧头 0xAA
    STATE_DATA,             // 接收 16 字节浮点数据
    STATE_CHECKSUM,         // 接收 4 字节校验和
    STATE_TAIL,             // 等待帧尾 0x0D
} ParseState_t;

static ParseState_t parse_state = STATE_HEADER1;

/* 接收缓存 */
static uint8_t  data_buf[8];            // 2个float的原始字节
static uint8_t  data_idx;               // 数据字节计数
static uint32_t received_checksum;      // 收到的校验和
static uint8_t  checksum_byte_idx;      // 校验和字节计数

//-------------------------------------------------------------------------------------------------------------------
// 函数简介     计算校验和（对 data 区 16 字节做累加）
//-------------------------------------------------------------------------------------------------------------------
static uint32_t calc_checksum(const uint8_t *data, uint8_t len)
{
    uint32_t sum = 0;
    for (uint8_t i = 0; i < len; i++) {
        sum += data[i];
    }
    return sum;
}

//-------------------------------------------------------------------------------------------------------------------
// 函数简介     喂一个字节给解析状态机，在 UART RX 回调里调用
//-------------------------------------------------------------------------------------------------------------------
void comm_parse_byte(uint8_t byte)
{
    switch (parse_state) {

        //--- 等待帧头 0x55 ---
        case STATE_HEADER1:
            if (byte == COMM_HEADER1) {
                parse_state = STATE_HEADER2;
            }
            // 不是 0x55 就留在当前状态，丢弃该字节
            break;

        //--- 等待帧头 0xAA ---
        case STATE_HEADER2:
            if (byte == COMM_HEADER2) {
                parse_state = STATE_DATA;
                data_idx = 0;
            } else {
                // 不是 0xAA，退回找下一个 0x55
                parse_state = STATE_HEADER1;
                if (byte == COMM_HEADER1) {
                    parse_state = STATE_HEADER2;
                }
            }
            break;

        //--- 接收 16 字节数据 ---
        case STATE_DATA:
            data_buf[data_idx++] = byte;
            if (data_idx >= 8) {
                parse_state = STATE_CHECKSUM;
                checksum_byte_idx = 0;
                received_checksum = 0;
            }
            break;

        //--- 接收 4 字节校验和（小端序） ---
        case STATE_CHECKSUM:
            received_checksum |= ((uint32_t)byte << (checksum_byte_idx * 8));
            checksum_byte_idx++;
            if (checksum_byte_idx >= 4) {
                parse_state = STATE_TAIL;
            }
            break;

        //--- 等待帧尾 0x0D ---
        case STATE_TAIL:
            if (byte == COMM_TAIL) {
                // 校验和验证
                uint32_t computed = calc_checksum(data_buf, 8);
                if (computed == received_checksum) {
                    // 校验通过，解析 float
                    float *floats = (float *)data_buf;
                    vision_data.yaw_error   = floats[0];
                    vision_data.pitch_error = floats[1];
                    vision_data.new_data    = true;
                }
                // 校验失败则丢弃这一帧
            }
            // 无论校验成功与否，都回到找帧头状态
            parse_state = STATE_HEADER1;
            break;

        default:
            parse_state = STATE_HEADER1;
            break;
    }
}

/* 单字节接收缓冲区（地址需稳定，HAL 保存其指针） */
uint8_t comm_rx_byte;

//-------------------------------------------------------------------------------------------------------------------
// 函数简介     初始化通信，启动 USART1 单字节中断接收
//-------------------------------------------------------------------------------------------------------------------
void comm_init(void)
{
    // USART1 已在 MX_USART1_UART_Init() 中初始化
    // 启动单字节中断接收（回调在 test.c 的 HAL_UART_RxCpltCallback 中统一处理）
    HAL_UART_Receive_IT(&huart1, &comm_rx_byte, 1);
}

//-------------------------------------------------------------------------------------------------------------------
// 函数简介     获取视觉数据（用户读取后自动清除 new_data 标志）
//-------------------------------------------------------------------------------------------------------------------
bool comm_get_vision_data(VisionData_t *out)
{
    if (!vision_data.new_data) return false;
    memcpy(out, &vision_data, sizeof(VisionData_t));
    vision_data.new_data = false;
    return true;
}

// 发送应答包给 K230: 0x55 0xAA | uint8 status | uint32 checksum | 0x0D
void comm_send_ack(uint8_t status)
{
    uint8_t buf[8];

    buf[0] = COMM_HEADER1;   // 0x55
    buf[1] = COMM_HEADER2;   // 0xAA
    buf[2] = status;         // 数据: 1=完成, 0=失败 2=收到 3=K230开始 4=K230停止发送数据

    // 校验和对 data 区累加
    uint32_t sum = calc_checksum(&buf[2], 1);
    buf[3] = (uint8_t)(sum >> 0);
    buf[4] = (uint8_t)(sum >> 8);
    buf[5] = (uint8_t)(sum >> 16);
    buf[6] = (uint8_t)(sum >> 24);

    buf[7] = COMM_TAIL;      // 0x0D

    HAL_UART_Transmit(&huart1, buf, 8, 100);
}

  void comm_flush_rx(void)
  {
      parse_state        = STATE_HEADER1;
      data_idx           = 0;
      checksum_byte_idx  = 0;
      received_checksum  = 0;
      memset(data_buf, 0, sizeof(data_buf));

      // 重新启动 UART 中断接收（这也会把 HAL 内部锁定的状态清掉）
      HAL_UART_AbortReceive_IT(&huart1);   // 先中止当前接收
      HAL_UART_Receive_IT(&huart1, &comm_rx_byte, 1);  // 重新启动
  }
