# 落潮镇 · 第十三次钟声

适用于 Dify 的中文 AI 跑团工作流。原创雾港悬疑短团，支持 1–3 人轮流行动。

失踪的守灯人、突然复亮的灯塔、每夜多响一次的钟。你们需要在异常潮水吞没镇子前找出秘密，并决定如何处理灯塔。

AI 识别行动、演绎场景与 NPC；程序负责真实随机骰、角色资源、线索、移动限制和结局。采用 Fate Accelerated 的轻量改编，规则来源与署名见 [Sources.txt](materials/trpg/Sources.txt)。

## 导入 Dify

1. 使用已有 Dify 服务，在应用列表选择“导入 DSL 文件”。
2. 导入 [fog-harbor.yaml](examples/trpg/fog-harbor.yaml)。
3. 在两个 LLM 节点选择你已配置的模型。默认使用通义 `qwen3.7-flash`；模型凭据由 Dify 管理。
4. 试运行：`action` 填“开团”，`session` 留空；也可使用 [开场输入示例](examples/trpg/opening-inputs.json)。

导入现成 DSL 不需要安装本仓库的 Python 依赖。已经在 Dify 1.17.1 / DSL 0.7.0 环境中完成草稿实跑；本仓库不包含 Dify 服务或部署文件。

## 输入与输出

| 输入 | 含义 |
| --- | --- |
| `action` | 本回合尝试的行动；首次填“开团” |
| `session` | 上一回合的 JSON 存档；新团留空 |
| `party` | 初始队伍，如 `沈砚:调查员;林汐:技师`；默认单人调查员 |
| `actor` | 当前行动角色姓名；默认队伍第一位 |
| `invoke` | `否` / `是`；调用特质时须在行动正文解释理由 |

| 输出 | 含义 |
| --- | --- |
| `answer` | 本回合叙事、检定、状态和下一步选项 |
| `session` | 下一回合需要传回的存档 |
| `choices` | 建议行动，也可自由描述 |
| `roll` | 程序产生的骰点与算式 JSON |
| `status` | `playing` / `ended` |
| `turn` | 累计有效行动回合数 |

Workflow 每次调用执行一个回合。在 Dify 中手动游玩时，复制 `session` 到下一次输入；下面的可选本地入口会自动保存并传回存档。

```mermaid
flowchart LR
  A[玩家输入] --> B[读取存档与角色]
  B --> C[AI 识别行动]
  C --> D[程序掷骰与规则结算]
  D --> E[AI 主持叙述]
  E --> F[生成战报与存档]
  F --> G[本回合结果]
```

## 可选：自动存档入口

需要 Python 3.11+、已有 Dify 服务，以及第三方 `dify-workflow` CLI 的本地登录会话。此入口使用 Dify Console 草稿接口，应用无需发布。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/dify-workflow remote login --server http://localhost --email YOUR_EMAIL
cp examples/trpg/app.example.json examples/trpg/app.json
```

登录密码通过隐藏提示输入。在本地 `app.json` 中填写导入后生成的应用 ID，再运行：

```bash
bash ./trpg
bash ./trpg --new --party '沈砚:调查员;林汐:技师;陆舟:水手'
```

Windows 用户可在默认 WSL 环境完成以上配置后双击 `Run-TRPG.cmd`。也可通过 `DIFY_WORKFLOW_PYTHON` 指定已有的 Python 环境。

- 直接描述行动，或输入选项编号。
- `/actor 姓名`：切换队伍成员。
- `/invoke`：下次检定请求花费命运点，随后行动需说明调用特质的理由。
- `/rules`、`/recap`：查看规则或回顾，不推进时间。
- `/new`、`/exit`：开新团或退出。

存档与运行报告保存在 `debug/trpg/`，只有成功运行才更新存档，并保留上一版 `.bak`。使用 `--save debug/trpg/another-table.json` 可建立另一桌独立存档。登录配置、个人存档和本地 `app.json` 均不提交到 Git。

## 玩法概要

职业为调查员、水手、技师。行动方式包括谨慎、机智、华丽、强势、迅捷、隐秘，分值由职业卡确定。

掷四枚各取 `-1/0/+1` 的骰子，加上行动方式和特质/优势加值，再与难度比较：低于难度失败，相等为付出代价的成功，高 1–2 为成功，高 3 或以上为大成功。

必要线索在失败时仍可取得，但潮水加速；重复调查同一核心线索不产生额外收益。每三个有效行动潮水推进一格，失败或平手再推进一格，到八格触发撤离。角色压力到三格退出冒险，所有人退出则结束本次行动。

初始命运点三点；明确调用特质并说明理由，可花一点得 `+2`。创造优势可积累最多两次后续检定的 `+2`。普通移动无需掷骰，涨潮后需要检定。终局必须到达灯塔，并拥有对应证据。

这是固定模组的轻量调查玩法：省略完整战术战斗、装备系统和原规则的部分机制。修改点和许可说明见 [Sources.txt](materials/trpg/Sources.txt)。

## 修改与验证

[fog-harbor.json](materials/trpg/fog-harbor.json) 包含主持人真相、地点、NPC、线索和结局；保持悬念的玩家可从 Dify 应用开始。

```bash
.venv/bin/python scripts/trpg/build.py
.venv/bin/dify-workflow validate examples/trpg/fog-harbor.yaml -j
.venv/bin/dify-workflow checklist examples/trpg/fog-harbor.yaml -j
.venv/bin/python -m pytest tests -q
```

生成器将剧本与规则代码内嵌到 DSL，修改后可再次导入已有应用。更新应用前先导出备份，明确指定目标应用；发布是单独操作。

本项目已实际验证开场、连续调查、多人轮换、真实骰点、终局、回顾、非法移动和损坏存档处理。本仓库保留规则测试，不上传真实运行报告。

## 仓库内容

仅保留工作流 DSL、原创素材、来源与署名、生成器、规则测试，以及可选本地游玩入口和其必要的草稿接口适配器。Dify 本体、Compose 配置、模型凭据、Console 会话和个人存档由使用者自己的环境提供。
