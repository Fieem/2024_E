# Vision

`Vision` 目录现在提供了一个面向树莓派 + USB 摄像头的实时五子棋视觉原型，目标棋盘是红底黑线、`7x7` 格子、黑白圆棋子、按格子中心落子。

## 当前结构

- `main.py`：实时入口，负责采集、检测、显示调试窗口、输出稳定棋盘状态
- `camera.py`：USB 摄像头初始化与参数设置
- `board_detector.py`：红色棋盘分割、四角提取、透视矫正
- `grid_model.py`：固定 `7x7` 网格建模，生成 49 个格心与 ROI
- `piece_detector.py`：按格子判断 `empty / black / white`
- `vision_types.py`：视觉输出对象与公共数据结构

## 识别流程

1. 读取 USB 摄像头画面
2. 在 HSV 空间提取红色棋盘区域
3. 找最大候选轮廓并通过最小外接矩形得到四角
4. 透视矫正到固定尺寸棋盘图，默认 `700x700`
5. 将标准棋盘均分为 `7x7`，得到 49 个格子的中心点和检测区域
6. 在每个格子中先看红底占比判断“是否有棋子”，再用颜色 + 连通域面积判断是黑棋还是白棋
   这样白棋不会因为亮度瞬间掉下去，就直接回到 `empty`
7. 对最近几帧结果做多数投票，只在结果稳定后输出

## 依赖

推荐 Python 3.10+，需要：

- `numpy`
- `opencv-python`

可以在树莓派环境里自行安装，或参考：

```bash
pip install -r requirements.txt
```

如果树莓派已经通过系统包安装了 OpenCV，也可以直接复用系统环境。

## 运行

在 `Vision` 目录下执行：

```bash
python main.py
```

如果你想打开可交互调参上位机：

```bash
python tuner.py
```

如果你要运行串口联动控制层：

```bash
python control_main.py --headless
```

常用参数：

默认采集参数已经调整为：

- 分辨率：`1600x1200`
- 帧率：`60 FPS`
- 输出格式：`MJPG / MJPEG`
- 曝光：默认手动曝光 `180.0`，用于把偏暗画面提亮

控制层额外需要：

- `vision_control_settings.json`
- `pyserial`

常用启动方式：

```bash
python main.py --camera-index 0 --width 1600 --height 1200 --fps 60 --pixel-format MJPG --exposure 180
```

可选参数：

- `--history-size`：历史帧数量，默认 `5`
- `--consensus-frames`：判稳最少票数，默认 `3`
- `--pixel-format`：相机输出格式，默认 `MJPG`
- `--exposure`：手动曝光值，默认 `180.0`
- `--white-balance`：手动白平衡值
- `--sample-radius-ratio`：格心采样圆半径比例，默认 `0.42`
- `--center-sample-radius-ratio`：中心判定圆半径比例，默认 `0.24`
- `--min-piece-area-ratio`：判定棋子的最小面积比例，默认 `0.10`
- `--white-min-piece-area-ratio`：白棋判定最小面积比例，默认 `0.05`
- `--white-relaxed-piece-area-ratio`：白棋宽松面积比例，默认 `0.03`
- `--white-norm-min-piece-area-ratio`：白棋归一化补救面积比例，默认 `0.025`
- `--white-center-ratio-min`：中心区域白色占比下限，默认 `0.12`
- `--black-value-max`：黑棋灰度上限，默认 `70`
- `--black-saturation-min`：黑棋饱和度下限，默认 `0`
- `--black-saturation-max`：黑棋饱和度上限，默认 `255`
- `--white-value-min`：白棋亮度下限，默认 `170`
- `--white-saturation-max`：白棋饱和度上限，默认 `80`
- `--white-norm-value-min`：白棋归一化亮度下限，默认 `150`
- `--white-norm-saturation-max`：白棋归一化饱和度上限，默认 `140`
- `--empty-red-ratio-threshold`：空格红底占比阈值，默认 `0.45`
  这是现在“有无棋子”判断的核心参数
- `--headless`：不显示窗口，仅在终端输出稳定结果
- `--debug-dir`：按 `s` 保存调试图片时的目录

说明：

- 不同 USB 摄像头对曝光数值的定义可能不同，`180.0` 是当前项目的默认亮一点配置
- 如果树莓派上画面仍偏暗，可以继续把 `--exposure` 往上调
- 如果摄像头驱动不接受 `MJPG`，OpenCV 可能会回退到设备支持的其他格式
- 如果空格大面积被误判成黑棋，先优先降低 `--black-value-max`
- 如果黑棋经常被认成空格，可以先试着提高 `--black-value-max` 或降低 `--min-piece-area-ratio`
- 如果白棋能靠平滑保持、但当前帧经常检测不到，可以先试着降低 `--white-min-piece-area-ratio`
- 如果白棋边缘不明显、但中心很亮，可以先试着降低 `--white-relaxed-piece-area-ratio` 或降低 `--white-center-ratio-min`
- 如果白棋经常被漏检，可以先试着降低 `--white-value-min` 或提高 `--white-saturation-max`
- 如果白棋在阴影里容易掉成空格，可以先试着降低 `--white-norm-value-min`、降低 `--white-norm-min-piece-area-ratio`，或提高 `--white-norm-saturation-max`
- 如果空格经常被误判成棋子，先优先提高 `--empty-red-ratio-threshold`
- 如果已经确认“有棋子”但黑白容易分错，再分别调黑棋和白棋参数
- 如果黑棋表面有反光而被识别成白棋，当前判定会优先保留足够明显的黑色主体；仍有误判时可适当提高 `--black-value-max`

## 调参上位机

`tuner.py` 会打开一个滑块控制窗口，让你实时调整：

- 相机曝光
- 红色棋盘 HSV 阈值
- 棋盘最小面积和形态学核大小
- 黑棋、白棋、空格相关阈值

现在会分成 3 个控制窗口：

- `tuner_camera_board`：相机曝光、红色棋盘阈值、棋盘面积、平滑、形态学核
- `tuner_white_piece`：白棋相关和采样半径
- `tuner_black_misc`：黑棋相关、通用面积阈值、空格红底阈值

红板定位现在默认带一层“亮度归一化”：

- 只在 `board_detector` 找红板前生效
- 目的是减小阴影、局部过亮对 `red_mask` 的影响
- 不会直接修改 `piece_detector.py` 用来判黑白棋的透视图
- 如果你已经调好的黑白棋阈值比较稳定，通常不用因为这个功能重调一整轮

推荐调参顺序：

1. 先在 `tuner_camera_board` 把曝光调到棋盘不发黑、白棋不过曝
2. 如果红底受阴影影响大，先保持 `board_norm_enable=1`，再看 `clahe_clip_x10 / clahe_tile` 能不能把红板补均匀
3. 再调红色 HSV，让 `red_mask` 里基本只剩棋盘主体
4. 确认 `board_detection` 能稳定框住四角，再细调 `board_min_area_x1000 / board_kernel / board_smooth_x100 / theta_smooth_x100`
5. 空棋盘下调 `piece_min_x100 / empty_red_ratio_x100`，让 49 格尽量都保持 `empty`
6. 最后分别放黑棋、白棋，再调黑白两组参数

关键滑块作用：

- `camera_exposure`
  - 往右：整体更亮
  - 往左：整体更暗
- `board_norm_enable`
  - `1`：开启红板亮度归一化，光照不均时更稳
  - `0`：关闭归一化，直接用原图分红色
- `clahe_clip_x10`
  - 往右：局部亮度补偿更强，更适合阴影明显时
  - 往左：补偿更弱，更接近原图
- `clahe_tile`
  - 往右：按更大的局部块做归一化，效果更平缓
  - 往左：按更小的局部块做归一化，对局部阴影更敏感
- `board_min_area_x1000`
  - 往右：只接受更大的红色区域，能减少误锁背景
  - 往左：更容易锁到较小棋盘，但误检风险更高
- `board_smooth_x100`
  - 往右：四角更稳，但跟随真实移动更慢
  - 往左：响应更快，但角点抖动会更明显
- `theta_smooth_x100`
  - 往右：角度更稳，适合后续做旋转补偿
  - 往左：角度变化响应更快
- `board_kernel`
  - 往右：红板区域更容易连成整体
  - 往左：保留更多细节，但噪声也更容易进来
- `piece_min_x100`
  - 往右：更不容易把噪声认成棋子
  - 往左：更容易检出小棋子，但误报也会增加
- `white_min_area_x100`
  - 往右：白棋需要更完整的白色连通域
  - 往左：白棋更容易被检出
- `white_relaxed_x100`
  - 往右：放宽白棋补救判定，需要更大白色区域
  - 往左：补救判定更容易触发
- `white_center_min_x100`
  - 往右：要求中心亮区更明显才算白棋
  - 往左：对白棋中心亮斑要求更低
- `white_value_min`
  - 往右：只有更亮的区域才会被看成白棋
  - 往左：偏灰的白棋也更容易过线
- `white_sat_max`
  - 往右：允许颜色更杂的亮区域被看作白棋
  - 往左：只保留更接近白色的区域
- `white_norm_area_x100`
  - 往右：白棋归一化补救需要更大亮区
  - 往左：阴影里的白棋更容易被捞回来
- `white_norm_value_min`
  - 往右：归一化后也要更亮才算白棋
  - 往左：暗一些的白棋也能进入补救通道
- `white_norm_sat_max`
  - 往右：归一化补救允许更高饱和度，适合偏色白棋
  - 往左：只保留更接近中性白的区域
- `black_v_max`
  - 往右：更亮的深色区域也可能被算成黑棋
  - 往左：只有更黑的区域才会算黑棋
- `empty_red_ratio_x100`
  - 往右：更强调“红底占比高就是空格”
  - 往左：空格更不容易被红底规则直接判空

常用按键：

- `q`：退出上位机
- `p`：保存当前参数到 `vision_settings.json`
- `s`：保存当前调试图片和识别结果

保存后的 `vision_settings.json` 会被 `main.py` 自动读取，所以你调好一次以后，直接运行：

```bash
python main.py
```

就会自动带上你保存的参数。

## 串口控制层

`control_main.py` 会把视觉识别、串口协议、`gomoku_ai` 和脉冲查表拼起来，但仍然不依赖 `Robot_Arm` 目录。

它使用两个配置文件：

- `vision_settings.json`
  - 相机、红板检测、棋子识别参数
- `vision_control_settings.json`
  - 串口端口、AI 难度、棋盘倾斜补偿、14 个取子位脉冲、49 个棋盘格脉冲
  - 默认串口示例：`/dev/ttyAMA0`，`921600`

启动方式：

```bash
python control_main.py --vision-config vision_settings.json --control-config vision_control_settings.json --headless
```

如果你希望保留调试窗口，可以去掉 `--headless`。

串口请求报文：

- `PLACE,<color>,<piece_no>,<row>,<col>`
- `BATTLE_START,<color>`
- `READY`

其中 `<color>` 使用单字符：`B` 表示黑棋，`W` 表示白棋；`<piece_no>` 使用 `1~7`，第 `1` 个棋子对应配置中的数组下标 `0`。例如：

```text
PLACE,B,3,3,4
BATTLE_START,W
```

PLACE 中，下位机明确指定颜色、取第几个棋子以及落子行列，因此取子不要求按顺序进行。Vision 会将 `piece_no` 转换为 `piece_no - 1` 后选择取子槽位。

串口响应报文：

- `PULSES,<pick_p1>,<pick_p2>,<place_p1>,<place_p2>`
- `ERROR,<code>,<message>`
- `BUSY,<message>`

下棋模式和对弈模式成功时都统一返回 `PULSES`，对弈模式不再通过串口返回行列坐标。
`ERROR` 和 `BUSY` 后面的消息最多包含两个英文单词，例如 `ERROR,NO_BOARD,NO BOARD`、`BUSY,BATTLE ON`。

颜色固定为：

- `B`：黑棋
- `W`：白棋

错误码固定为：

- `NO_BOARD`
- `BAD_CMD`
- `BAD_COLOR`
- `BAD_POS`
- `NO_SLOT`
- `AI_TURN_MISMATCH`
- `ILLEGAL_BOARD`
- `AI_FAIL`

控制逻辑固定为：

- `PLACE`：检查当前稳定棋盘、目标格和槽位，然后返回 4 个脉冲
  - 使用请求中的 `piece_no` 选择对应颜色的取子槽位，不要求按顺序取子
  - 同一局中同一颜色的取子槽位不能重复使用，否则返回 `ERROR,NO_SLOT,NO SLOT`
  - 会读取视觉当前的 `theta_deg`
  - 只对“落子位”这 2 个脉冲做倾斜补偿
  - 旋转补偿角度限制为 `-55° ~ +55°`，超出范围时按对应边界值处理
  - `|theta_deg| <= 3°` 时按 `0°` 处理
- `BATTLE_START`：记录机械臂执棋颜色，进入对弈模式
- `READY`：读取当前稳定整盘状态，若轮到机械臂，则调用 `gomoku_ai` 的 `hard` 难度求下一步，再返回 4 个脉冲

脉冲配置规则：

- `black_slots[7]` / `white_slots[7]`
  - 每项是一个 `[pulse1, pulse2]`
- `board_cells[7][7]`
  - 每格是一个 `[pulse1, pulse2]`
- PLACE 模式使用请求中的 `piece_no` 选择 `black_slots[piece_no - 1]` 或 `white_slots[piece_no - 1]`
- PLACE 模式会记录已使用的取子槽位；棋盘从有棋子重新变为空棋盘时清空记录
- READY 对弈模式未指定取子序号，仍按当前棋盘中该颜色棋子数量选择下一个槽位

倾斜补偿配置：

- `tilt_compensation.enabled`
  - `true`：开启 PLACE 模式下的落子倾斜补偿
  - `false`：PLACE 模式直接使用基准格脉冲
- `tilt_compensation.dead_zone_deg`
  - 死区角度，默认 `3.0`
  - 当视觉输出角度在 `-3° ~ +3°` 内时，按 `0°` 处理
- `tilt_compensation.max_tilt_deg`
  - 旋转补偿最大角度，默认 `55.0`
  - 视觉输出超过 `±55°` 时，按 `-55°` 或 `+55°` 进行补偿

当前补偿方式：

- 仍然只使用 `board_cells[7][7]` 这张脉冲表
- 不引入 `Robot_Arm` 目录和逆运动学
- 会把目标格按当前 `theta_deg` 在棋盘索引平面内做旋转，再对脉冲表做双线性插值
- 取子槽位 `black_slots / white_slots` 不参与旋转补偿

## 调试方式

默认会显示这些窗口：

- `raw`：原始画面
- `board_detection`：棋盘定位结果
- `red_mask`：红色区域分割结果
- `warped_board`：透视矫正后的标准棋盘与识别覆盖层
  - 每格会显示 `P0/P1` 与 `Rxx`
  - `P1` 表示当前按红底占比判断“有棋子”
  - `Rxx` 是当前格的红底占比 `red_ratio`

快捷键：

- `q`：退出
- `s`：保存当前原图、定位图、透视图，以及当前识别结果 JSON 到调试目录

## 输出格式

当棋盘结果稳定后，终端会输出 JSON，包含：

- `board_found`
- `board_image_size`
- `cells`
- `board_state`
- `timestamp`
- `stable`
- `stable_frames`

每个 `cell` 包含：

- `id`
- `row`
- `col`
- `center_px`
- `center_px_raw`
- `bbox`
- `state`
- `confidence`
- `diagnostics`：当前格子的判定细节，例如 `red_ratio / black_ratio / white_ratio / reason`

实时稳定输出现在分两类：

- `event_type = board_state`
  - 稳定整盘状态
  - 包含 `theta_deg`
- `event_type = move`
  - 仅当稳定棋盘相比上一稳定棋盘只新增 1 个棋子时输出
  - 包含 `row / col / piece / theta_deg`
  - 如果中途丢失棋盘，再重新识别时会先重新发布整盘状态，不跨“盲区”推断落子事件

## 后续建议

下一阶段可以继续接：

- 图像坐标到机械臂坐标的标定映射
- 棋盘/棋子阈值参数外置到配置文件
- 用采样图片做离线回放与参数调优
- 为“交点落子”版本替换 `grid_model.py` 的坐标定义
