# H4-7A TIFF 派生浏览器预览与页面生命周期缓存

## 完成范围

H4-7A 为 TIFF 附件补齐默认 bundle 与 direct classic 的真实浏览器预览闭环。原始 TIFF 始终是唯一持久化附件：磁盘附件、消息 `_images`、消息 content、Session JSONL 与模型输入来源均不保存派生预览字段，Session MIME 继续是 `image/tiff`。模型请求仍复用既有 TIFF → PNG 投影，不改变模型图片协议、AgentRun/Runtime、事件或会话格式。

用户已在真实浏览器中人工确认发送前预览、发送后用户消息预览、点击放大和完整刷新恢复均正常。本阶段的自动证据进一步冻结转换安全、失败降级、页面生命周期缓存和请求次数。

## 派生预览与安全边界

同源 `/api/attachments/preview` 提供两种展示入口：

- composer 使用 `POST` 提交当前页面内的 TIFF base64，成功后仅在前端临时状态保存 Blob URL；
- 已保存消息使用 `GET` 读取 `ATTACHMENTS_DIR` 内经现有安全解析确认的 attachment path。

两种入口都复用服务端既有图片嗅探、10 MB 大小、像素数量、最大尺寸和 TIFF → PNG 转换能力。成功响应固定为可解码 `image/png`，并设置 `X-Content-Type-Options: nosniff`；错误 base64、错误签名、损坏 TIFF、超限、超像素、任意绝对路径、目录穿越和非附件路径均返回有界错误。派生 PNG 只存在于响应内存与页面 Blob URL，不写预览文件、磁盘缓存、Session JSONL、AgentRun 事件或模型上下文，也不覆盖原 TIFF。

GIF 继续使用浏览器原生动画预览；PNG、JPEG、WebP、BMP 与 ICO 的既有显示路径不被统一改成首帧 PNG。本阶段只为 TIFF 启用派生浏览器预览。

## 页面生命周期缓存

已保存 TIFF 的缓存 key 为“规范化 TIFF MIME + 原持久化 attachment path”。`image/x-tiff` 与 `image/tiff` 归一为同一 MIME，path 不被替换为预览标识。页面级缓存只有三种状态：

| 状态 | 行为 |
|---|---|
| `pending` | 首次请求登记唯一 Promise；相同 key 的并发读取和消息子树重复投影复用该 Promise。 |
| `ready(blob URL)` | 所有后续重绘复用同一 Blob URL，不再发 GET 或重复转换。 |
| `failed` | 本页面生命周期内固定显示附件卡片，不再发 GET；发送与模型识别继续进行。 |

异步完成只在当前会话仍包含相同 TIFF path 时触发一次安全重绘；切换会话后不会用旧回调覆盖当前页面，也不会形成重绘循环。页面卸载时显式清理缓存，每个 ready Blob URL 只撤销一次；清理后才完成的 pending 请求也会立即撤销其 Blob URL，且失败 Promise 已收敛，不产生未处理 rejection。

完整刷新会自然重建页面缓存，因此允许对持久化 TIFF 发起一次新的 GET。缓存对象、Blob URL 与失败状态不写入消息、`_images`、content、Session JSONL、AgentRun、模型请求或保存 payload。

### dispose 终结态收尾

累计稳定性实现为页面缓存增加了与普通清理分离的 `dispose` 终结语义：

- `dispose` 后立即清空 entries，所有已经 ready 的 Blob URL 各撤销一次；重复调用 `dispose` 不会重复撤销。
- `dispose` 前已经 pending 的请求即使稍后成功，也只撤销刚生成的 Blob URL，不再写入 cache、不调用 `onSettled`、不触发消息重绘。
- `dispose` 后 `ensure` 对任意 key 都稳定返回空结果，不再调用 `requestPreview`；`source` 与 `status` 也不暴露已终结 entry。
- 页面卸载先把 `persistedTiffPreviewCache` 置为 disposed，再继续既有保存与计时收尾。旧 document 随后的 `renderSessionMessages` 或预览查询不能重建 GET；新 document 每次自然创建全新的页面缓存。

H4 继续严格区分 document generation：旧页进入 dispose 后 GET 增量为 0，新页面恢复后对同一持久化 TIFF 发起且只发起 1 次 GET。该收尾不跨页面复用 cache，不新增 localStorage、全局耐久缓存、磁盘缩略图或预览持久化字段。

## 精确浏览器请求证据

bundle 与 direct classic 使用同一预览逻辑和 H4 场景，按 method、path 与 phase 得到完全相同的计数：

| 阶段 | POST | GET |
|---|---:|---:|
| composer 成功预览 | 1 | 0 |
| composer 故障预览 | 1 | 0 |
| 发送后首次失败预览 | 0 | 1 |
| 模型流式重绘新增 | 0 | 0 |
| 完整刷新 | 0 | 1 |
| 刷新后真实会话重绘新增 | 0 | 0 |
| 点击放大新增 | 0 | 0 |
| 合计 | 2 | 2 |

每个入口总请求固定为 4。正常与故障两种转换均不会随模型增量或 `renderSessionMessages` 次数持续增长；完整刷新只重新尝试一次。故障场景显示稳定附件卡片，没有坏图标，不阻止发送或模型识别，失败状态也没有进入持久化。

浏览器同时冻结原 TIFF SHA-256 `42e6678c560a178b49da1cbc67c4f75a7f545975edbb96f23500ff98066f0b73`、单一磁盘附件、Session `image/tiff`、零派生字段、模型 PNG 识别，以及刷新后的 AgentRun POST、Runtime POST、chat、工具执行四项零增量。

## 原阶段实现哈希

原 H4-7A 收口时冻结的 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `app.js` | `271d076986202489f21d16331fe77bfdd16d5d4454c92a93b075b2d87f3980a2` |
| `server.py` | `9a51cb7000ac97bf4f0bcf76e945512f225bb03656c35ac6a01d7f6a211a1e2e` |
| `src/features/image-attachments.js` | `56e48dc26191b790f650893b027f35f56d09bc21278dc6f248e158aedc7ac1ce` |
| `src/ui/messages.js` | `f9c1ee5fe50b4828c8702ff3969957adce68a08b0d84624f855d4cb685c70853` |
| `styles.css` | `8831b3b470ee5608aff5bce60ee9e042d9968394661058e9dd3a4b37901f98c5` |
| `tests/e2e/h4/isolated_host.py` | `b34af9abb3931519946827197fd493305e08d4aea50a071cb85f92ee97e9835e` |
| `tests/e2e/h4/smoke.spec.cjs` | `b0a279b4937ec3e9ef4dd537fe9a0681cb6b0b02eddb021633f4589a970fac33` |
| `tests/test_frontend_modules.py` | `e75092a586798e86295cecbae1d7b58b03991912534933e2cf34c624b0ac68ae` |
| `tests/test_image_vision_and_browser_refresh.py` | `c25b71b20ff8a55fa7b7e932df1debee608467ea6a99f72d803dcbe7e23ac93b` |
| `tests/test_routes.py` | `250989454a4c5c54086078d34d667f24898eaeff93bab31faf21f3bc8df39600` |

## 原阶段验证与累计复验

实现完成时的有效结果：

- 缓存定向：`1 passed`；
- TIFF 路由/安全定向：`7 passed, 12 subtests passed`；
- 前端模块：`172 passed`；
- H3-2D1：`6 passed, 32 subtests passed`；
- H4 bundle/direct classic TIFF：各 `1 passed`；
- H4 infrastructure：通过；
- 标准 H4 连续两轮：各 `37 passed`、单 worker、`retries=0`；
- 图片、路由、Session 与 H3 组合：`98 passed, 58 subtests passed`；
- 完整 Python：`1121 passed, 751 subtests passed`；
- `npm run check:frontend`、Node/Python 语法、`git diff --check` 与资源清理：通过。

原专题文档收口只重跑缓存定向、TIFF 路由/安全定向、两条 TIFF H4、前端构建/新鲜度、语法和 diff；在上述十个文件哈希不变的前提下，沿用同一实现文件形态的两轮标准 H4 与完整 pytest 结果，不把未重跑项描述为文档收口后重跑。

原 H4-7A 收口时，先前失败诊断产生的五个受忽略文件已清理，H4 子进程、临时根和 `output/h4-playwright` 文件均为 0。

页面缓存 dispose 收尾包含在累计实现提交 `8178be99e8ede82d739902d6c8f37afc76846abb` 中。该最终树下，缓存定向、bundle/direct classic TIFF、前端定向与 H4 infrastructure 通过；连续两轮标准 H4 均为 `51 passed`、单 worker、`retries=0`；完整 pytest 为 `1131 passed, 751 subtests passed`；`npm run check:frontend`、Node/Python 语法与 `git diff --check` 通过。当前专题更新只执行 Markdown、链接、哈希引用、diff 与三文件白名单检查，不重跑长矩阵。

## 证明边界与回退

H4-7A 只证明固定有效 TIFF 在 bundle/direct classic 中的发送前、发送后、放大、刷新、失败卡片、页面生命周期请求去重与旧页 dispose 终结；不证明异常或孤儿历史附件记录、多标签页共享缓存、跨进程缓存恢复、持久化缩略图、TIFF 多页浏览、完整图片格式矩阵、SVG/AVIF/HEIC、动画/多尺寸选择、真实外部模型或发布门禁。queue/steer、多并行失败、工具型 follow-up 与后台工具副作用不属于图片预览场景，本阶段也不作推论；主观视觉质量仍只沿用原人工确认，不由新增 dispose 自动证据替代。

独立回退只需撤销本阶段十个实现/测试文件及收口文档；没有预览数据迁移、Session JSONL 迁移或磁盘缩略图清理动作。原 TIFF 数据和既有会话格式无需回写。
