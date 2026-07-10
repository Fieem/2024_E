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
6. 在每个格子中用“颜色 + 连通域面积”识别空格、黑棋、白棋
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

常用参数：

```bash
python main.py --camera-index 0 --width 1280 --height 720 --board-size 700
```

可选参数：

- `--history-size`：历史帧数量，默认 `5`
- `--consensus-frames`：判稳最少票数，默认 `3`
- `--exposure`：手动曝光值
- `--white-balance`：手动白平衡值
- `--headless`：不显示窗口，仅在终端输出稳定结果
- `--debug-dir`：按 `s` 保存调试图片时的目录

## 调试方式

默认会显示这些窗口：

- `raw`：原始画面
- `board_detection`：棋盘定位结果
- `red_mask`：红色区域分割结果
- `warped_board`：透视矫正后的标准棋盘与识别覆盖层

快捷键：

- `q`：退出
- `s`：保存当前原图、定位图、透视图到调试目录

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
- `bbox`
- `state`
- `confidence`

## 后续建议

下一阶段可以继续接：

- 图像坐标到机械臂坐标的标定映射
- 棋盘/棋子阈值参数外置到配置文件
- 用采样图片做离线回放与参数调优
- 为“交点落子”版本替换 `grid_model.py` 的坐标定义
