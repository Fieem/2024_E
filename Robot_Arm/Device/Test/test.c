/*******************************************************
 * 串口命令说明（VOFA/串口助手）
 *
 * 通用格式:
 *   KEY=VALUE!
 *   也支持一帧多命令: KEY1=V1,KEY2=V2,KEY3=V3!
 *
 * 帧结束符:
 *   !  或  \r  或  \n   （任意一个即可触发解析）
 *   注意: 必须是英文半角 ! ，不是中文全角 ！
 *
 * 命令列表:
 *
 * 示例:
 *   P1=0.80!
 *   TY=90!
 *   SL=120,SR=120!
 *   CAL=1!
 *******************************************************/

#include "test.h"

#include <ctype.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "usart.h"
#include "main.h"
#include "Emm_V5/Emm_V5.h"

static void prints_u(uint8_t index, unsigned int val);



/* ================================================================
 *  静态变量
 * ================================================================ */

/* VOFA 帧组装缓冲 */
static char     s_vofa_frame_buf[TEST_VOFA_FRAME_MAX_LEN];
static uint8_t  s_vofa_frame_len = 0U;

/* UART 环形缓冲区：ISR 写 head，main loop 读 tail */
static uint8_t           s_rx_ring[TEST_VOFA_RX_RING_SIZE];
static volatile uint16_t s_rx_head = 0U;
static uint16_t          s_rx_tail = 0U;

/* HAL_UART_Receive_IT 单字节接收缓冲 */
uint8_t s_rx_byte = 0U;

/* printsf 多行环形缓存 */
static char    s_log_lines[PRINTSF_MAX_LINES][PRINTSF_MAX_LINE_LEN];
static uint8_t s_log_head  = 0U;
static uint8_t s_log_count = 0U;

/* ================================================================
 *  环形缓冲区操作
 * ================================================================ */

static int rx_ring_is_empty(void)
{
    return (s_rx_tail == s_rx_head);
}

/* 从环形缓冲区取一个字节，返回 0 表示空 */
static int rx_ring_pop(uint8_t *out)
{
    if (rx_ring_is_empty())
    {
        return 0;
    }
    *out = s_rx_ring[s_rx_tail];
    s_rx_tail = (s_rx_tail + 1U) % TEST_VOFA_RX_RING_SIZE;
    return 1;
}

/* 向环形缓冲区写入一个字节（仅 ISR / 回调上下文中调用） */
void rx_ring_push(uint8_t byte)
{
    uint16_t next = (s_rx_head + 1U) % TEST_VOFA_RX_RING_SIZE;
    if (next != s_rx_tail)   /* 未满则写入 */
    {
        s_rx_ring[s_rx_head] = byte;
        s_rx_head = next;
    }
    /* 满了则丢弃该字节 */
}



/* ================================================================
 *  VOFA 命令解析
 * ================================================================ */

static int test_key_equal(const char *a, const char *b)
{
    while ((*a != '\0') && (*b != '\0'))
    {
        if (toupper((unsigned char)*a) != toupper((unsigned char)*b))
        {
            return 0;
        }
        a++;
        b++;
    }
    return ((*a == '\0') && (*b == '\0'));
}

static int test_vofa_apply_kv(const char *key, float value) {
    if (test_key_equal(key, "START")) {

        return 1;


    }
    /*
     * 在此处添加你的 PID 参数赋值逻辑，例如:
     *
     *   if (test_key_equal(key, "P1")) { pid_angle.Kp = value;
     *       printsf(0, "[VOFA] P1=%.4f", value);
     *       return 1;
     *   }
     *   if (test_key_equal(key, "I1")) { pid_angle.Ki = value; return 1; }
     *   if (test_key_equal(key, "D1")) { pid_angle.Kd = value; return 1; }
     */

    (void)key;
    (void)value;
    return 0;
}

static void test_vofa_parse_segment(char *segment)
{
    char *eq        = NULL;
    char *key       = NULL;
    char *value_str = NULL;
    char *endptr    = NULL;
    float value     = 0.0f;

    /* 跳过前导空格 */
    while (isspace((unsigned char)*segment)) { segment++; }
    if (*segment == '\0')
    {
        return;
    }

    eq = strchr(segment, '=');
    if (eq == NULL)
    {
        return;
    }

    *eq = '\0';
    key       = segment;
    value_str = eq + 1;

    /* 跳过值前导空格 */
    while (isspace((unsigned char)*value_str)) { value_str++; }
    if (*value_str == '\0')
    {
        return;
    }

    value = strtof(value_str, &endptr);
    if (endptr == value_str)
    {
        return;
    }

    /* 值后只允许空白字符 */
    while ((endptr != NULL) && isspace((unsigned char)*endptr)) { endptr++; }
    if ((endptr != NULL) && (*endptr != '\0'))
    {
        return;
    }

    if (test_vofa_apply_kv(key, value))
    {
        // printsf(0, "[VOFA] %s=%.4f", key, value);
    }
}

void test_vofa_parse_frame(const char *frame)
{
    char   work_buf[TEST_VOFA_FRAME_MAX_LEN];
    char  *token  = NULL;
    size_t len    = 0U;

    if (frame == NULL)
    {
        return;
    }

    len = strlen(frame);
    if (len >= TEST_VOFA_FRAME_MAX_LEN)
    {
        len = TEST_VOFA_FRAME_MAX_LEN - 1U;
    }

    memcpy(work_buf, frame, len);
    work_buf[len] = '\0';

    token = strtok(work_buf, ",;");
    while (token != NULL)
    {
        test_vofa_parse_segment(token);
        token = strtok(NULL, ",;");
    }
}

void test_vofa_feed_byte(uint8_t byte)
{
    /* 碰到帧结束符则触发解析 */
    if ((byte == '!') || (byte == '\r') || (byte == '\n'))
    {
        if (s_vofa_frame_len > 0U)
        {
            s_vofa_frame_buf[s_vofa_frame_len] = '\0';
            test_vofa_parse_frame(s_vofa_frame_buf);
            s_vofa_frame_len = 0U;
        }
        return;
    }

    /* 累积字节 */
    if (s_vofa_frame_len < (TEST_VOFA_FRAME_MAX_LEN - 1U))
    {
        s_vofa_frame_buf[s_vofa_frame_len++] = (char)byte;
    }
    else
    {
        /* 缓冲区溢出，丢弃当前帧等待下一个分隔符 */
        s_vofa_frame_len = 0U;
    }
}

/* ================================================================
 *  公开 API
 * ================================================================ */

/**
  * @brief  初始化 VOFA+ 接收
  * @note   配置 USART2 NVIC 中断，并启动 HAL_UART_Receive_IT 单字节循环接收
  */
void test_vofa_init(void)
{
    s_vofa_frame_len = 0U;
    memset(s_vofa_frame_buf, 0, sizeof(s_vofa_frame_buf));

    s_rx_head = 0U;
    s_rx_tail = 0U;


    /* ---- 启动单字节中断接收（每收到一个字节触发 HAL_UART_RxCpltCallback） ---- */
    HAL_UART_Receive_IT(TEST_VOFA_HUART, &s_rx_byte, 1);
}

/**
  * @brief  轮询环形缓冲区并解析收到的字节
  * @note   建议在 main 的 while(1) 中高频调用
  */
void test_vofa_poll(void)
{
    uint8_t ch;
    while (rx_ring_pop(&ch))
    {
        test_vofa_feed_byte(ch);
    }
}

/* ================================================================
 *  Nextion 显示函数
 * ================================================================ */

/**
  * @brief  Nextion 文本控件打印
  * @param  index   控件索引（t0.txt, t1.txt ...）
  * @param  content 文本内容
  */
void prints(uint8_t index, const char *content)
{
    if (content == NULL)
    {
        content = "";
    }

    printf("page0.t%u.txt=\"%s\"", (unsigned int)index, content);
    printf("%c%c%c", (char)0xFF, (char)0xFF, (char)0xFF);
    fflush(stdout);
}

static void prints_u(uint8_t index, unsigned int val)
{
    char buf[16];
    snprintf(buf, sizeof(buf), "%u", val);
    prints(index, buf);
}

/**
  * @brief  将一行文本存入环形日志缓存
  */
static void printsf_store_line(const char *line)
{
    uint8_t pos;

    if (s_log_count < PRINTSF_MAX_LINES)
    {
        pos = (uint8_t)((s_log_head + s_log_count) % PRINTSF_MAX_LINES);
        s_log_count++;
    }
    else
    {
        /* 覆盖最旧行 */
        pos        = s_log_head;
        s_log_head = (uint8_t)((s_log_head + 1U) % PRINTSF_MAX_LINES);
    }

    strncpy(s_log_lines[pos], line, PRINTSF_MAX_LINE_LEN - 1U);
    s_log_lines[pos][PRINTSF_MAX_LINE_LEN - 1U] = '\0';
}

/**
  * @brief  格式化 Nextion 文本控件打印（支持多行滚动）
  * @param  index 控件索引
  * @param  fmt   格式化字符串
  * @param  ...   可变参数
  */
void printsf(uint8_t index, const char *fmt, ...)
{
    char    line[PRINTSF_MAX_LINE_LEN];
    char    merged[PRINTSF_TEXT_BUF_LEN];
    va_list args;
    size_t  off = 0U;
    uint8_t i;

    if (fmt == NULL)
    {
        return;
    }

    va_start(args, fmt);
    (void)vsnprintf(line, sizeof(line), fmt, args);
    va_end(args);

    /* 将双引号替换为单引号，避免破坏 Nextion 命令字符串 */
    for (i = 0U; line[i] != '\0'; i++)
    {
        if (line[i] == '"') { line[i] = '\''; }
    }

    printsf_store_line(line);

    merged[0] = '\0';
    for (i = 0U; i < s_log_count; i++)
    {
        uint8_t pos = (uint8_t)((s_log_head + i) % PRINTSF_MAX_LINES);
        int n = snprintf(merged + off, sizeof(merged) - off, "%s%s",
                         s_log_lines[pos],
                         (i + 1U < s_log_count) ? "\r\n" : "");
        if (n < 0) { break; }
        if ((size_t)n >= (sizeof(merged) - off))
        {
            off = sizeof(merged) - 1U;
            merged[off] = '\0';
            break;
        }
        off += (size_t)n;
    }

    prints(index, merged);
}

/**
  * @brief  清空指定 Nextion 文本控件
  */
void printsf_clear(uint8_t index)
{
    uint8_t i;

    s_log_head  = 0U;
    s_log_count = 0U;

    for (i = 0U; i < PRINTSF_MAX_LINES; i++)
    {
        s_log_lines[i][0] = '\0';
    }

    prints(index, "");
}
