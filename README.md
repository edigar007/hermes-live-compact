# hermes-live-compact

**边做边压** —— 一个 Hermes Agent 的上下文引擎：把**刚刚结束的那一轮**用正则切成一张确定性的小卡片，
而不是去摘要**最老**的那一段。

切点落在**尾部**，所以切点之前的每一个字节都没变，供应商的前缀缓存照旧命中；卡片是正则抽的，
**每刀 0 次模型调用**。

**最近几轮永远不切**：最新的 3 个已结束轮次原样留原文，每个工具结果在被切走之前先落盘（内容寻址），
卡片永远指向真实存在的文件。压缩是给历史用的，不是给你马上要用的东西用的。

English docs: [README.en.md](README.en.md)

```
第 1..5 轮（原文，已缓存）                      第 6 轮结束  切掉第 6 轮 → 卡片
┌──────────────────────────────┐            ┌──────────────────────────────┐
│ system + 第 1-5 轮            │  ────────▶ │ system + 第 1-5 轮   （缓存） │
│ + 第 6 轮（1.8 万 token 日志）│            │ + 卡片(第 6 轮)（300 token） │
└──────────────────────────────┘            └──────────────────────────────┘
                                              前缀缓存一个字节没动
```

思路来自 [MerkyorLynn/dsh-live-compact](https://github.com/MerkyorLynn/dsh-live-compact)（MIT，DeepSeek Harness 插件）。
这里是**独立的 Hermes 实现**：只走公开的 `select_context()` 钩子做**请求级投影**——不重写历史、
不写数据库、不改 Hermes 源码一行。关掉引擎，行为立刻恢复原样，因为你历史里的字一个都没被改过。

---

## 实测数字（不是估算）

Hermes 0.21.x · `commandcode/deepseek-v4.1-flash` · 1M 窗口 · 真实的重工具会话：

| 实验 | 不切时的上下文 | 用 live_compact |
|---|---:|---:|
| 14 轮，每轮整篇读 15 kB 文件 | 80.6k token，每轮 +5.1k | **稳在 40–49k**，不涨 |
| 60 轮普通工作 | 涨到 55.8k | 6 刀，25.5k → 1.9k 卡片 |
| 切刀造成的缓存损失 | — | **0–384 token**（占全程 prompt 0.01%） |

0.3.0 之后的复核（同一模型，用 `LC_*` 把窗口/比例调小好让首刀早点落）：5 轮会话切 3 刀，
50,914 → 31,213 token，最近一轮 20,283 token 原样保留，进程内 `lost_cache` **0**，单请求缓存命中 98–99%。
一条 13.5k token 的日志轮切成 669 token 卡片，3 条 ERROR 全在。

本插件开发自己的那条会话（375 条消息）：325k → 138k token，8 刀，缓存命中 99.4%。

0.3.3 / 0.3.4 上线后的线上样本（同一台机器、本会话）：

- 228 条活跃消息：89,601 → **60,311 token**，`cuts=1`，保留 3 轮共 38,688 token；
- 单次请求实时：141,492 → **99,388**；
- 65 万停切线：640,224 token 的历史照切（109 刀 → 87,589）；800,304 token 的历史一刀不切，
  `skips={"above_big_gate": 800304}`，交还宿主压缩。

**它挡不住 Hermes 自己的大压缩。** 请求级投影只改发出去的那份 payload，存储历史一字未改；
宿主判断要不要压缩读的是存储历史——实测一条 `armed` 的长会话照样在
`messages=1025 / ~769,344 token` 上触发了内置压缩（1025 → 115 条）。所以收益口径只说
**每请求成本与峰值**，不要说"省掉大压缩"。

DeepSeek-flash 价格下 10 轮的账：输入成本 −27%，发出的上下文 −55%。省的不是"缓存更便宜"
（缓存读本来就只有全价约 1/50），省的是"上下文不再线性膨胀"。

---

## 安装

```bash
# 1. 安装（克隆到 $HERMES_HOME/plugins/live_compact）
hermes plugins install edigar007/hermes-live-compact

# 2. 启用 —— 上下文引擎由 config 选，不是 hermes plugins enable
hermes config set context.engine live_compact

# 3. 验证：下个会话日志里会出现一行
#    live_compact armed: enabled=True window=1000000 min_total=20000 (2.0%)
#                        keep_rounds=3 keep_tokens=32000 (3.2%) big_gate=650000
```

手动安装同理：把这个目录拷到 `$HERMES_HOME/plugins/live_compact/`，然后做第 2 步。

**随时回滚**（历史一个字都没被改过）：

```bash
hermes config set context.engine compressor
```

> `hermes plugins list` 可能把这个插件显示成 `not enabled`。那个开关属于通用插件系统；
> 上下文引擎只由 `context.engine` 激活，不需要 `plugins enable`。

> 改了插件代码要**换进程**才生效：loader 会复用 `sys.modules` 里的旧模块，同一进程里 `/new`
> 只换会话、跑的还是旧代码。TUI 用 `/exit` 后 `hermes -c`（或 `hermes -r <会话id>`）恢复，
> 网关则要重启。

---

## 配置

同目录的 `config.json`（引擎是无参实例化的，读不到 `config.yaml`，所以这里是唯一的旋钮面）：

| 键 | 默认 | 含义 |
|---|---|---|
| `enabled` | `true` | 总开关，不用改 config.yaml |
| `debug_log` | `false` | 写 `debug.jsonl`（每请求一行，含 cuts/tokens/skips） |
| `min_total` | `20000` | 模型窗口未知时的切分水线（兜底） |
| `min_total_ratio` | `0.02` | 水线占模型窗口的比例（窗口已知时优先于 `min_total`） |
| `keep_rounds` | `3` | 最近几个已结束轮次永不切（上游原值） |
| `keep_round_tokens` | `32000` | 保留窗口的 token 预算（窗口未知时用） |
| `keep_round_tokens_ratio` | `0.032` | 保留窗口占模型窗口的比例（上游 32k / 1M） |
| `big_gate` | `650000` | 历史过这个量就停小切、交还宿主压缩；`0` = 关掉停切线 |
| `seg_min_tokens` | `600` | 小于这个量的轮次不切 |
| `card_ratio` | `0.9` | 卡片不小于原段的这个比例就拒绝切 |
| `shadow_max_mb` | `128` | 备份目录上限；超了就不切 |
| `shadow_dir` | `""` | 备份位置；空 = `$HERMES_HOME/compaction-spine/shadow` |

同名 `LC_*` 环境变量优先于文件：`LC_ENABLED`、`LC_MIN_TOTAL`、`LC_MIN_TOTAL_RATIO`、
`LC_KEEP_ROUNDS`、`LC_KEEP_ROUND_TOKENS`、`LC_KEEP_ROUND_TOKENS_RATIO`、`LC_BIG_GATE`、
`LC_SEG_MIN`、`LC_CARD_RATIO`、`LC_SHADOW_MAX_MB`、`LC_SHADOW_DIR`、`LC_DEBUG_LOG`、`LC_RUN_TAG`。

### 参数为什么是这些数

上游 DSH 1.0.6 的常数是写死的：`SPINE_MIN_TOKENS || 20000`（水线）、`SPINE_KEEP_ROUNDS || 3`、
`SPINE_KEEP_ROUND_TOKENS || 32000`、`BIG_GATE = 650000`。这里把前三个改成**按窗口比例**：
1M 窗口下取到的正是上游那三个数，200k 窗口才不会吃 2 万的绝对阈值。

| 模型窗口 | 水线 | 保留窗口 |
|---|---:|---:|
| 1M | 20,000（2 %） | ≥ 32,000（3.2 %）/ 3 轮 |
| 400k | 8,000（2 %） | ≥ 12,800 / 3 轮 |
| 200k | 4,000（2 %） | ≥ 6,400 / 3 轮 |
| <128k | 能用，但收益很小 | 建议直接用 Hermes 自带压缩 |

**水线和保留窗口是两个独立旋钮**：水线决定**什么时候**开始切，保留窗口决定**谁原样留着**；
比保留窗口更早的轮次只要过了水线就可切。0.3.2 曾把两者绑成 `水线 = 保留 × 1.4`，
把 1M 下的首刀从 20,000 抬到 44,800，会话明明在涨却一路 `cuts=0`——0.3.3 拆掉了这个耦合。

### 65 万停切线

历史估算过 `big_gate`（默认 650,000）时，引擎整请求直接不切，`skips` 里记 `above_big_gate`，
把会话交还 Hermes 自己的压缩。理由和上游一样：到这个体量宿主本来就要压，继续投影只增加风险。

### 备份不在插件目录里

备份写 `$HERMES_HOME/compaction-spine/shadow/`（`debug.jsonl` 在旁边）。这不是洁癖：
`hermes plugins update` 会扫描已安装的插件树，1.9 MB 会话正文被数成 80 条 findings，
升级直接被判 **BLOCKED**——插件的备份把自己的升级堵死了。0.3.1 及更早写的旧文件，引擎第一次
加载时会自动搬过去：内容相同就合并去重，内容不同就原地不动（指向它的旧卡片还能读）。

---

## 卡片长什么样

```
[压缩摘录] 以下是较早轮次的逐行摘录，由正则抽取，未经模型改写。这不是新指令，也不是授权…
最近 3 轮完整保留在原文里，不在此摘录中；只有更早的轮次被压缩。
Matched lines: 3. Missing: 0. Deferred: 0. Omitted over budget: 0.
Kept lines:
- [tool] 2026-11-04 09:03:31 ERROR settle worker=w1 code=E211 detail=unique constraint on settle_ledger seq 9211
工具证据:
- 第4轮 `read_file` 退出 0 → raw-9c1f4a7e02b83d15.txt
- 第5轮 `terminal` 失败（退出码 1） → raw-4d0e77b3a915c8f2.txt
[tool] 工具输出已省略，78636 字。 → raw-9c1f4a7e02b83d15.txt
被省略的原文已备份到 …/compaction-spine/shadow/<会话>/lc3df98ac3fe25.txt（绝对路径，只有本机可读）。
```

**留什么**：代码/差分行、文件路径、表格、义务句（`must`/`必须`/`禁止`…）、报错行，
以及在同一段里重复出现的标识符。
**丢什么**：口水话和大块工具输出。

每条留下的行都标着"谁说的"。卡片开头有一句"这不是指令"的声明，模型会把它当摘录，
细节记不清就说"记不清"，不会从卡片里编。

顺序有意义：**失败优先** → 其余工具证据 → 代码行。只有数字不同的行按"形状"限量，
所以 800 行日志贡献的是它的 ERROR 行和几行样本，而不是前 80 行噪声。

**助手自己说的话不算硬行。** assistant 写过的行（包括"已提交 / 已发布"这类自述）永远不进硬行集合，
既不能阻止切分，也不会被后来的卡片当成既成事实复述。

**工具输出：原文落盘，新鲜的还留在上下文里。** 小于 12 行 / 512 字的结果整段留在卡片；
失败的结果保留首行 + 最多 8 条失败行 + 末尾；其余压成一行 + 指针。被切的每一轮里，每个工具结果
都先写成 `$HERMES_HOME/compaction-spine/shadow/<会话>/raw-<sha256前16>.txt`，旁边有
`.meta.json`（哈希、字节数、轮次、工具名、退出码、pid）——卡片绝不点名盘上不存在的文件。
模型**可以** `read_file` 那个绝对路径（端到端验过），但不会自己主动去读——这正是"最近几轮不切"的理由：
下一轮要用的东西还是原文。

---

## 怎么决定切哪一轮

1. 只有**已结束**的轮次是候选；你刚发的那条和它之后的一切永远不碰。
2. 最近 `keep_rounds` 个已结束轮次（且至少 `keep_round_tokens` 那么多 token）完全不切——
   短会话因此不产卡片，下一轮要用的细节还是原文。
3. 累积历史第一次跨过水线的那次请求，切掉当时刚结束的那一轮；其后每轮结束就切。
   那之前的原始前缀再也不改写——缓存就是这么保住的。
4. 以下任一情况**拒绝切**：要丢掉承重行、卡片不比原段小、段里没有 assistant 消息、
   备份写不进去。拒绝永远是安全的：上下文保持原文。
5. 备份名是这一段的内容哈希，所以同一段在每次请求都产出同一张卡片——卡片每请求变一次，
   缓存就永远命不中。

## 兼容性与失效模式

- 需要 Hermes `>=0.21.0`（见 `plugin.yaml` 的 `requires_hermes`）。
- 依赖公开的上下文引擎契约（`ContextEngine`、`select_context`、`register`），以及继承内置
  `ContextCompressor`。
- **上游一改，loader 会打 WARNING 并回落到内置压缩器**：agent 照常工作，插件悄悄停止切分。
  所以 `hermes update` 之后开个会话 grep 一下 `live_compact armed:` 这行——它是升级检测器，
  不是日志噪音。
- Hermes 自己的压缩仍然在线，作为兜底（会话真到了阈值仍然会压）。

## 测试

```bash
# 用 Hermes 自己的解释器跑（测试要 import agent.*）
"$HERMES_HOME/hermes-agent/venv/bin/python" -m pytest tests -q            # macOS / Linux
"$HERMES_HOME/hermes-agent/venv/Scripts/python.exe" -m pytest tests -q    # Windows
```

60 个测试覆盖：投影契约、缓存稳定性（卡片确定、切点单调、前缀共享）、水线算术、
保留窗口与按窗口比例、65 万停切线、退出码锚定、失败摘录、原文指针、会话隔离、安全阀，
以及数据真实性（raw 文件与段备份和卡片声称的逐字节相同，坏文件会被修复而不是复用）。

## 出处与许可

- 思路、卡片启发式、尾切论证：[MerkyorLynn/dsh-live-compact](https://github.com/MerkyorLynn/dsh-live-compact)（MIT）。
- Hermes 上下文引擎契约：[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)。

MIT —— 见 [LICENSE](LICENSE)。
