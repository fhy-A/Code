# Harness H3-2D1：七格式图片 MIME 保留与模型投影契约

## 阶段定位

H3-2D1 为 Harness 总体方案第 6.3 节“图片历史含不支持 MIME，模型请求降级但 UI 保留原图”建立独立、严格版本化的生产调用链证据。本阶段只新增 schema、合成 fixture 和一份定向测试，没有修改生产代码、依赖、既有图片/持久化/前端测试、会话 JSONL、Run replay runner/schema、`package.json` 或发布脚本。

evidence profile 固定为 `h3-2d1-image-mime-preservation` v1，scope 为 `seven-format-production-chain`。七个案例使用固定、小尺寸、有效且脱敏的合成图片，顺序严格固定为 PNG、JPEG、WebP、BMP、GIF、ICO、TIFF；该证据不是单 Run或 multi-run replay，不并入任何轨迹、事件、检查点或恢复计数。

## 七格式固定矩阵

| ID | 源 MIME | 分类 | 源帧/页面 | 选择范围 | 源字节 SHA-256 | 规范 RGBA SHA-256 |
|---|---|---|---:|---|---|---|
| `png` | `image/png` | 原样送模 | 1 | 单图，4×4 | `9262204cf402f25d538b5bad046fab58672e011150fc4991ccc7020b15d7d358` | `a1b62c3d91c89576111f6620bf298a49c7ec05f08682adc58076e4107f8212d3` |
| `jpeg` | `image/jpeg` | 原样送模 | 1 | 单图，4×4 | `e67855ca30452e19e69a1d45c510d444e088529ef158ed821a0f072faa73d3ad` | `6456193579b58f7d80837f87710c60262d5be9ae623ee673b964b1b5b9317982` |
| `webp` | `image/webp` | 原样送模 | 1 | 单图，4×4 | `48ff9e02de480877b29ce6123c08eeb41ff9c21f91d59f9b537540fabe8b9d96` | `a1b62c3d91c89576111f6620bf298a49c7ec05f08682adc58076e4107f8212d3` |
| `bmp` | `image/bmp` | 转 PNG 送模 | 1 | 单图，4×4 | `03e9e4fe8c3a59fcbbf5845db6180545eb9e7ad4d8ad58785f3272787ae3a485` | `4f596d1149d7ab4f0a0c0e0efbb7ea1aa46a7b258667ca764edf82b840fdd9ed` |
| `gif` | `image/gif` | 转 PNG 送模 | 2 | 仅第 0 帧，4×4 | `af3d02c8e9faebe5e07c6435ef6fa2920b0f612ad699e03ebb71e3f8fb31d98e` | `4f596d1149d7ab4f0a0c0e0efbb7ea1aa46a7b258667ca764edf82b840fdd9ed` |
| `ico` | `image/x-icon` | 转 PNG 送模 | 1 | 仅单尺寸，16×16 | `7382b2ab160035853eb3981a14b932941ebe41e175811a6b1c4c270a09283370` | `c58a10581113a39bf8f21f016b1d7d1f8c1395182b4045e44be76da50db1b7f5` |
| `tiff` | `image/tiff` | 转 PNG 送模 | 2 | 仅首页，4×4 | `6165cf2ae17b6a07ea8a20496b7d7b12681ad1aefd59776ff8bbacef7146167c` | `4f596d1149d7ab4f0a0c0e0efbb7ea1aa46a7b258667ca764edf82b840fdd9ed` |

固定计数为 7 个案例、7 条消息、7 个 `content` 图片、7 个 `_images` 源图片和 7 条 JSONL 往返消息；其中 3 个原样送模案例、4 个转 PNG 案例，全部实际执行且没有 skip。

## 同一消息的生产调用链

七条规范用户消息同时包含 `content` 中的原始格式 data URL 和 `_images` 中的原始 MIME/base64。测试对同一批消息依次执行：

1. Node 调用生产 `serializeSessionMessages()`，使用 `includeModel/includeTime` 持久化选项并重复序列化；同时与 `buildSessionSavePayload(persistMessages=true)` 的消息结果核对。
2. 把这份真实序列化输出一次写入同一个临时 JSONL，再由生产 `write_jsonl()/read_jsonl()` 读取七条消息。
3. 将每条读取消息原有的 `content` 直接放入生产 `_project_model_payload_images()`；测试不会从 `_images` 重建模型 payload。
4. 将同一批读取消息交给生产 `renderUserProjection()/projectMessages()`，核对 HTML 字符串继续引用原始格式 data URL。

序列化与 JSONL 往返后，case 身份、原 MIME、base64、图片数量、源字节哈希和原 data URL 均保持不变。重复序列化、模型投影和 UI 投影稳定；模型投影前后源消息深度相等，`_images` 不增加第二项。所有磁盘写入只发生在测试临时目录，并显式确认 Session API、worker、模型、工具、外部网络和浏览器调用均为 0。

## 原样与转换语义

PNG、JPEG、WebP 的生产模型投影保持源 MIME、完整 data URL 和解码字节不变，因此其模型输出字节 SHA-256 与上表源字节 SHA-256 完全相同；JSONL 和 UI 投影继续使用各自原始格式。

BMP、GIF、ICO、TIFF 的生产模型投影输出 `image/png`，且具有有效 PNG 签名。测试分别直接解码源选择帧/首页和模型 PNG 为规范 RGBA，先核对尺寸相同，再直接核对 RGBA 字节相等，最后从这份相等的 RGBA 计算并匹配上表语义像素哈希。这不是让源像素与模型像素分别匹配两个独立期望值。

当前环境生成 PNG 的诊断哈希为：BMP/GIF/TIFF `2cba17dde14f2a1ab03f7870198fb2ff40eda347273f7ddb0d22c8529daa3f7b`，ICO `ff3c092218f02d7df9836cb76eb900c263dac63bc1acd237cb291b4a38acba2e`。这些转换后 PNG 编码哈希只用于诊断，不是跨 Pillow/压缩器版本的语义通过门禁；正式契约是输出 MIME、PNG 可解码性、尺寸及直接 RGBA 相等。PNG/JPEG/WebP 仍冻结精确输出字节。

GIF 与 TIFF 的两帧/两页 fixture 只证明当前模型投影选择第 0 帧/首页，不证明动画或多页内容进入模型；ICO 使用既有单尺寸样本，不证明多尺寸选择策略。

## 确定性基线

| 对象 | SHA-256 |
|---|---|
| H3-2D1 fixture | `8f3cdd6354987a977df545f5db1209e5f869924b01d8884c9e1b33784c5afad3` |
| H3-2D1 schema | `ac367f82b9df44a858186c02e2f6b90cd8150bcfb128ce544ced77defc94c39c` |

2026-08-14 发布门禁复核确认，CODE-004 的用户长文本收起结构只改变了七个案例各自的 `renderUserHtmlSha256` 与 `projectMessagesHtmlSha256`。同一证据连续生成两次完全一致；原 MIME、原始/派生字节、data URL、JSONL 往返、模型投影、RGBA 语义、稳定性与零副作用字段全部保持不变，因此只受控刷新上述 14 个 UI HTML 哈希和 fixture 文件哈希，没有放宽图片契约。

H3-2D1 是独立图片证据。默认单 Run `17/124/25/25/4`、H3-2C1、H3-2B1 与 H3-2B2 的计数和全部 fixture/replay/状态哈希均保持不变。

## 定向失败诊断

| 故意变异 | 首差异路径 |
|---|---|
| evidence profile 版本漂移 | `$.evidenceProfile.version` |
| case 缺失、重复或乱序 | `$.cases[6]`、`$.cases[6].id`、`$.cases[0].id` |
| 原 data URL 被改写 | `$.cases[0].sourceMessage.content[1].image_url.url` |
| `_images` MIME 与 case 错连 | `$.cases[3].sourceMessage._images[0].mime` |
| 源哈希错写 | `$.cases[6].source.sha256` |
| GIF 错连 BMP 数据 | `$.cases[4].sourceMessage._images[0].base64` |
| 原样类输出字节漂移 | `$.cases[0].expected.model.outputByteSha256` |
| 转换类未输出 PNG | `$.cases[3].expected.model.outputMime` |
| 转换类 RGBA 语义漂移 | `$.cases[4].expected.model.semanticPixelSha256` |
| UI 错用非原始图 | `$.cases[3].expected.ui.renderUserImageSrcSha256`、`$.cases[3].expected.ui.modelOutputUrlAbsentWhenConverted` |
| JSONL 往返消息漂移 | `$.cases[6].expected.persistence.roundTripMessageSha256` |

## 验证与完成边界

- H3-2D1 定向：`6 passed, 32 subtests passed`；
- 相关图片测试：`12 passed, 7 subtests passed`；
- 完整 Python 回归：`1095 passed, 699 subtests passed`；
- 持久化、前端模块、既有 Harness、各 CLI replay、Python/Node 语法、空白和差异检查均通过。

本阶段只证明七份脱敏合成小图在当前生产序列化、临时 JSONL、模型图片投影和 UI HTML 投影链路上的契约。它不覆盖 SVG、AVIF、HEIC 等其他格式、MIME 能力矩阵穷举、恶意或损坏输入、GIF 动画、TIFF 多页内容、ICO 多尺寸选择、真实模型请求、外部网络、真实浏览器/DOM 显示、页面刷新或发布门禁。

## 回退

回退时可独立删除 H3-2D1 schema、fixture、定向测试和本专题文档。生产图片投影、会话 JSONL、既有图片测试、Run replay runner/schema 及其他 Harness 基线均无需迁移或回写。
