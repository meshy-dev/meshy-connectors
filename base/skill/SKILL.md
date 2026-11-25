---
name: {{ skill.name }}
description: Meshy 3D 生成技能 - 文字或图片生成 3D 模型、给模型上贴图、生成图片、查看进度和积分、下载模型
version: 0.1.0
author: Meshy
---

# Meshy Skill

Meshy 的生成都是异步任务：创建类工具立即返回任务 ID，用 `get_task` 查进度，成功后再展示或下载。每个工具的参数以工具自带的 schema 为准，这里只说用途和用法。

## 可用工具

### 生成

| 工具 | 用途 |
| --- | --- |
| `text_to_3d_preview` | 文字生成 3D 模型的第一步：先出没有贴图的模型 |
| `text_to_3d_refine` | 第二步：给成功的 `text_to_3d_preview` 模型上贴图 |
| `image_to_3d` | 用一张图片生成 3D 模型 |
| `texture_model` | 给用户已有的、没有贴图的模型上贴图 |
| `text_to_image` | 文字生成图片，常用来先出一张参考图，再交给 `image_to_3d` |
| `image_to_image` | 用一张图片加一句描述生成新图片，比如修改原图 |
| `create_upload` | 宿主没法直接附带文件时，把用户电脑上的文件传给 Meshy，供上面的生成使用 |

### 查询与下载

| 工具 | 用途 |
| --- | --- |
| `get_balance` | 用户的积分余额，以及每种生成要花多少积分 |
| `get_task` | 任务的状态和进度；成功后返回缩略图或图片，以及 `download_model` 能导出的格式 |
| `list_tasks` | 用户的模型（或图片）列表，最新的在前，分页返回 |
| `download_model` | 已成功模型的下载链接，格式取自 `get_task` 列出的那些 |
| `show_model` | 在对话里用卡片展示模型或图片：生成中显示进度，完成后显示缩略图、3D 预览和下载 |
| `open_meshy_studio` | 打开 Meshy：显示积分余额和最新模型，可以查看、下载、贴图或生成 |

## 常用流程

- **文字生成 3D**：`text_to_3d_preview` → 用 `get_task` 等它成功 → 用户要贴图时再调 `text_to_3d_refine` → 再用 `get_task` 等它成功。
- **图片生成 3D**：用户给了图片链接，直接调 `image_to_3d`；图片在用户电脑上而宿主附带不了，先 `create_upload`。
- **先出图再出模型**：`text_to_image` → 成功后取其中一张图片链接 → `image_to_3d`。
- **展示结果**：任务创建后用 `show_model` 展示一次，卡片会自己刷新进度，不要对同一个任务反复调用。

## 注意事项

- 需要用户先完成 Meshy 授权。授权失效时工具会返回未授权错误，提示用户在连接器里重新连接。
- 生成会消耗积分。生成前可以用 `get_balance` 看余额和价格；余额不足时告诉用户，不要反复重试。
- `get_task` 和 `download_model` 返回的链接会过期，要用时重新获取。
- `download_model` 会计入用户套餐的每月下载次数（有上限的套餐）。
- 生成通常要几十秒到几分钟。等待时间隔查询 `get_task`，不要连续密集调用。
