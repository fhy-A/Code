(function initializeCodeAgentTools(global) {
  "use strict";

  const agent = global.Code && global.Code.agent;
  if (!agent) throw new Error("Code agent namespace must load before tools");
  if (!agent.modelRequest) throw new Error("Code model request must load before tools");

  const { buildNativeToolCallMessage } = agent.modelRequest;

const nativeTools = [

  {

    type: "function",

    function: {

      name: "generate_image",

      description: "Generate one or more images using the AgentRun's separately selected image connection. Optionally edit one current-Session attachment or generated asset. Put visual quality and composition intent in the prompt; runtime owns provider execution parameters and Session-scoped caching. Never pass provider URLs, credentials, headers, or local paths.",

      parameters: {

        type: "object",

        properties: {

          prompt: { type: "string", minLength: 1, maxLength: 8000 },

          reference: {

            type: "object",

            properties: {

              type: { type: "string", enum: ["attachment", "generated_asset", "workspace_image"] },

              id: { type: "string", minLength: 1, maxLength: 512 },

            },

            required: ["type", "id"],

            additionalProperties: false,

          },

          count: { type: "integer", minimum: 1, maximum: 4 },

        },

        required: ["prompt"],

        additionalProperties: false,

      },

    },

  },

  {

    type: "function",

    function: {

      name: "manage_generated_image",

      description: "On explicit user request, export one current-Session generated asset to output/generated-images or rename one verified image already in that directory. Never invent a path or move the internal generated-asset cache.",

      parameters: {

        type: "object",

        properties: {

          operation: { type: "string", enum: ["export", "rename"] },

          assetId: { type: "string", minLength: 1, maxLength: 128 },

          path: { type: "string", minLength: 1, maxLength: 512 },

          name: { type: "string", minLength: 1, maxLength: 120 },

        },

        required: ["operation"],

        additionalProperties: false,

      },

    },

  },

  {

    type: "function",

    function: {

      name: "request_user_input",

      description: "Ask the user for a critical decision that cannot be safely inferred from context or discovered with available tools. Use this sparingly: do not ask about ordinary implementation choices, and search or inspect first when the answer is discoverable. Before asking, scan the conversation for previous answers or decisions on this topic — do not re-ask questions that have already been answered. Ask one question by default and normally use no more than three; use four or five only when the same stage has that many independent, necessary decisions. After receiving the answers, continue the original task immediately.",

      parameters: {

        type: "object",

        properties: {

          title: { type: "string", description: "Short questionnaire title." },

          reason: { type: "string", description: "One concise sentence explaining why this decision is needed." },

          questions: {

            type: "array",

            minItems: 1,

            maxItems: 5,

            items: {

              type: "object",

              properties: {

                id: { type: "string", description: "Stable identifier unique within this questionnaire." },

                prompt: { type: "string", description: "The decision the user needs to make." },

                type: { type: "string", enum: ["single", "multiple"] },

                required: { type: "boolean" },

                allowOther: { type: "boolean", description: "Allow a custom free-text answer in addition to the listed options." },

                options: {

                  type: "array",

                  minItems: 2,

                  maxItems: 3,

                  items: {

                    type: "object",

                    properties: {

                      value: { type: "string" },

                      label: { type: "string" },

                      description: { type: "string", minLength: 1 },

                      recommended: { type: "boolean" },

                    },

                    required: ["value", "label", "recommended"],

                    additionalProperties: false,

                  },

                },

              },

              required: ["id", "prompt", "type", "allowOther", "options"],

              additionalProperties: false,

            },

          },

        },

        required: ["questions"],

        additionalProperties: false,

      },

    },

  },

  {

    type: "function",

    function: {

      name: "list_files",

      description: "列出文件与目录：默认1层，深度限制1–3层，最多200项，跳过常见依赖/构建目录。目录不存在会失败；空结果不保证每个目录都可读。例：{\"path\":\"src\",\"maxDepth\":2}。",

      parameters: {

        type: "object",

        properties: {

          path: {

            type: "string",

            description: "可选起始目录，空值表示项目根。优先使用项目相对路径。当前公共解析器也可能接受用户主目录内路径，或将其他路径转到项目 output/同名文件；不要假定强项目沙箱或依赖重定向猜目标。",

          },

          maxDepth: {

            type: "integer",

            description: "整数深度，建议1–3，默认1；当前会将超范围值限制到1–3。",

          },

        },

        required: [],

        additionalProperties: false,

      },

    },

  },

  {

    type: "function",

    function: {

      name: "read_file",

      description: "读取项目或attachments/文件的文本，或图片/二进制信息。UTF-8文本最多返回512KiB且保留完整字符；无行范围时返回保留原换行的前缀。行范围从1开始且两端包含，可扫描初始文件大小内的后段行，结果以LF连接。truncated表示请求文本被省略，不代表文件本身较大；lineRange为实际返回行，末行可不完整。检测到读取期间文件变化会失败并提示重新读取；图片/二进制另有视觉上限。例：{\"path\":\"src/main.py\",\"startLine\":1,\"endLine\":40}。",

      parameters: {

        type: "object",

        properties: {

          path: {

            type: "string",

            description: "必填文件路径，也支持attachments/引用。优先用path；Server Agent仅在无冲突时兼容file_path别名。优先使用项目相对路径。当前公共解析器也可能接受用户主目录内路径，或将其他路径转到项目 output/同名文件；不要假定强项目沙箱或依赖重定向猜目标。",

          },

          startLine: {

            type: "integer",

            description: "可选、从1开始且包含该行；指定范围时默认1。开始超过EOF会失败并报告实际末行；空文件仅首行窗口成功，返回空content和null lineRange。",

          },

          endLine: {

            type: "integer",

            description: "可选且包含该行，省略则读取到EOF或输出上限；超过EOF截到实际末行，早于开始行则失败。请求窗口完整返回时truncated=false，即使文件较大。",

          },

        },

        required: ["path"],

        additionalProperties: false,

      },

    },

  },

  {

    type: "function",

    function: {

      name: "search_files",

      description: "搜索文件名与正文。query默认是字面文本，regex=true才解释正则；glob只过滤路径。正文跳过超过1MiB的文件，最多100个匹配文件、每文件通常10处匹配，不可读文件可能跳过。无匹配不等于执行失败。例：{\"query\":\"TODO|FIXME\",\"regex\":true,\"glob\":\"**/*.py\",\"contextAround\":1}。",

      parameters: {

        type: "object",

        properties: {

          query: {

            type: "string",

            description: "必填非空query，不使用pattern替代；只有regex=true时才解释 |、^、$、.*。",

          },

          path: {

            type: "string",

            description: "可选搜索目录。优先使用项目相对路径。当前公共解析器也可能接受用户主目录内路径，或将其他路径转到项目 output/同名文件；不要假定强项目沙箱或依赖重定向猜目标。",

          },

          regex: {

            type: "boolean",

            description: "布尔值，默认false；仅合法正则使用true，错误正则会被拒绝。",

          },

          type: {

            type: "string",

            description: "可选扩展名列表，逗号或空格分隔，例如js,ts,py；不是正则。",

          },

          glob: {

            type: "string",

            description: "可选路径glob，如 **/*.py；**包含根目录文件，不会让query自动变成正则。",

          },

          contextAround: {

            type: "integer",

            description: "匹配行前后的非负整数行数，默认0，通常用1–3。",

          },

        },

        required: ["query"],

        additionalProperties: false,

      },

    },

  },

  {

    type: "function",

    function: {

      name: "glob_files",

      description: "用glob查找文件名/相对路径，不搜索正文，也不使用正则语法。**匹配零层或多层目录；跳过常见目录，最多200项。起始目录无匹配时，当前会回到项目根重查，请检查返回路径。例：{\"pattern\":\"**/*.py\",\"path\":\"src\"}。",

      parameters: {

        type: "object",

        properties: {

          pattern: {

            type: "string",

            description: "必填非空glob，例如 **/*.py、*.js、src/**/*.tsx；搜索正文请用search_files。",

          },

          path: {

            type: "string",

            description: "可选起始目录，空值表示项目根。优先使用项目相对路径。当前公共解析器也可能接受用户主目录内路径，或将其他路径转到项目 output/同名文件；不要假定强项目沙箱或依赖重定向猜目标。",

          },

        },

        required: ["pattern"],

        additionalProperties: false,

      },

    },

  },

  {

    type: "function",

    function: {

      name: "propose_edit",

      description: "生成diff，再按当前权限/审批应用。二选一：newContent整文件内容（可为空），或oldText+newText片段替换；混用时完整片段参数对优先。先读取当前文件，提供有唯一上下文的精确原文。现有匹配会容忍空白/相似度并替换首个命中，不要依赖模糊选择。同内容/无diff或应用时文件变化可失败。例：{\"path\":\"src/main.py\",\"oldText\":\"return 1\",\"newText\":\"return 2\"}。",

      parameters: {

        type: "object",

        properties: {

          path: {

            type: "string",

            description: "必填目标文件路径。优先使用项目相对路径。当前公共解析器也可能接受用户主目录内路径，或将其他路径转到项目 output/同名文件；不要假定强项目沙箱或依赖重定向猜目标。",

          },

          oldText: {

            type: "string",

            description: "从最近读取结果复制的原文，与newText配对，包含足够唯一上下文，不猜测过时内容。",

          },

          newText: {

            type: "string",

            description: "与oldText配对的新片段，空字符串删除命中片段；与原文相同会拒绝。",

          },

          newContent: {

            type: "string",

            description: "完整新内容，可为空；用newContent而非content。整文件模式省略片段字段；混用时完整oldText/newText参数对优先。",

          },

        },

        required: ["path"],

        additionalProperties: false,

      },

    },

  },

  {

    type: "function",

    function: {

      name: "run_command",

      description: "运行低风险命令，用于查看、测试、构建、git 查询或 docker compose 查询。Python/Node 托管依赖安装需要用户授权；系统包管理器安装、持久化 PATH 修改和全局命令包装器会被拦截，必须由用户在 Code 外完成。",

      parameters: {

        type: "object",

        properties: {

          command: {

            type: "string",

            description: "要运行的命令，例如 dir、git status、npm test。",

          },

        },

        required: ["command"],

        additionalProperties: false,

      },

    },

  },

  {

    type: "function",

    function: {

      name: "task",

      description: "启动一个子 Agent 来并行处理独立的子任务。子 Agent 拥有和主 Agent 相同的完整工具集（读文件、写文件、运行命令、搜索、抓取网页等），可以独立完成复杂的多步骤任务。用于将大任务拆分成并行的独立步骤，提升效率。",

      parameters: {

        type: "object",

        properties: {

          prompt: {

            type: "string",

            description: "子任务的详细描述，包括要搜索什么、分析什么、返回什么格式的结果。",

          },

        },

        required: ["prompt"],

        additionalProperties: false,

      },

    },

  },

  {

    type: "function",

    function: {

      name: "use_skill",

      description: "按当前运行的 Skill 协议读取或加载 Skill。model-driven-v1 模式下从名称与描述目录自行选择；首次加载必须显式传 role=owner，仅可再追加一个 role=modifier。必须单独调用并等待返回后再调用其他工具。已加载 Skill 获取 runtimeResources 时可只传 name；只使用其精确路径和所选依赖运行时，不得搜索或复制资源。旧协议只允许访问已激活 Skill。",

      parameters: {

        type: "object",

        properties: {

          name: { type: "string", description: "Skill 名称，如 python-testing。" },

          role: { type: "string", enum: ["owner", "modifier"], description: "仅用于 model-driven-v1 的追加加载，必须由模型明确选择角色；不能替换已有 owner。" },

        },

        required: ["name"],

        additionalProperties: false,

      },

    },

  },

  {

    type: "function",

    function: {

      name: "check_skill_dependencies",

      description: "按当前任务所需能力检查 Skill 依赖。多能力 Skill 省略 capability 时只查看状态，随后只能选择一个相关能力，不能安装全部能力。Python/Node 包可按隔离环境方案授权安装；系统命令必须由用户在 Code 外安装，只能展示 installHints，禁止执行、修改 PATH 或创建全局包装器。安装后再次调用确认。",

      parameters: {

        type: "object",

        properties: {

          name: { type: "string", description: "已安装的 Skill 名称。" },

          capability: { type: "string", description: "本次任务实际需要的能力；仅查看多能力状态时可省略。" },

        },

        required: ["name"],

        additionalProperties: false,

      },

    },

  },

  {

    type: "function",

    function: {

      name: "read_skill_resource",

      description: "读取已安装 Skill 目录内的非隐藏打包资源。当 Skill 正文指引你查阅某个资源时按需加载，支持根目录文件和自定义资源目录。",

      parameters: {

        type: "object",

        properties: {

          skill: { type: "string", description: "Skill 名称，如 hyperframes。" },

          file: { type: "string", description: "Skill 目录内的相对路径，如 references/transitions/catalog.md 或 scripts/validate.py。" },

        },

        required: ["skill", "file"],

        additionalProperties: false,

      },

    },

  },

  {

    type: "function",

    function: {

      name: "write_file",

      description: "创建UTF-8文本文件或整文件覆盖；自动创建父目录，覆盖前备份，空content合法。必须提供完整JSON，并正确转义字符串中的引号、反斜线与换行；实际内容应是预期文本/换行，不要重复转义。CRLF/CR会规范化为LF。仍遵守当前权限与审批；I/O失败不保证未写入。例：{\"path\":\"output/note.txt\",\"content\":\"hello\\n\"}。",

      parameters: {

        type: "object",

        properties: {

          path: {

            type: "string",

            description: "必填非空文件路径；已有目录会被拒绝。优先使用项目相对路径。当前公共解析器也可能接受用户主目录内路径，或将其他路径转到项目 output/同名文件；不要假定强项目沙箱或依赖重定向猜目标。",

          },

          content: {

            type: "string",

            description: "完整UTF-8文本；空字符串可用于明确清空文件。使用JSON字符串转义，禁止猜测缺失内容补全截断调用。",

          },

        },

        required: ["path", "content"],

        additionalProperties: false,

      },

    },

  },

  {

    type: "function",

    function: {

      name: "delete_file",

      description: "按当前权限/审批删除文件或空目录，文件删除前备份。本工具拒绝非空目录：先检查内容并确认删除范围。其他现有工具仍按各自授权与安全合同处理，不得换用命令绕过授权或扩大未经确认的删除范围。目标缺失通常失败；不要假定已删除或盲目重复不确定的删除。例：{\"path\":\"output/obsolete.txt\"}。",

      parameters: {

        type: "object",

        properties: {

          path: {

            type: "string",

            description: "必填非空文件或空目录路径，先确认精确目标。优先使用项目相对路径。当前公共解析器也可能接受用户主目录内路径，或将其他路径转到项目 output/同名文件；不要假定强项目沙箱或依赖重定向猜目标。",

          },

        },

        required: ["path"],

        additionalProperties: false,

      },

    },

  },

  {

    type: "function",

    function: {

      name: "web_fetch",

      description: "抓取网页或 API 内容。用于查阅在线文档、API 参考、错误码说明等。返回纯文本（HTML 会自动剥离标签）。",

      parameters: {

        type: "object",

        properties: {

          url: {

            type: "string",

            description: "要抓取的 URL，如 https://docs.python.org/3/library/re.html。",

          },

        },

        required: ["url"],

        additionalProperties: false,

      },

    },

  },

  {
    type: "function",
    function: {
      name: "save_memory",
      description: "Save important info as a persistent memory for future sessions. Use when user shares preferences, project decisions, or key facts worth remembering.",
      parameters: {
        type: "object",
        properties: {
          name: { type: "string", description: "Short kebab-case identifier, e.g. 'api-design-rules'." },
          description: { type: "string", description: "One-line summary used for recall matching." },
          body: { type: "string", description: "The memory content to persist." },
        },
        required: ["name", "description", "body"],
        additionalProperties: false,
      },
    },
  },

];

  function parseJsonLoose(text = "{}") {
    if (typeof text === "object" && text !== null) return text;
    try {
      return JSON.parse(text || "{}");
    } catch (_) {
      return {};
    }
  }

  function normalizeNativeToolCall(call) {
    const name = call?.function?.name || call?.name || "";
    const args = parseJsonLoose(call?.function?.arguments || call?.arguments || "{}");
    return {
      ...args,
      action: name,
      _native: true,
      _toolCallId: call?.id || `call_${Date.now()}_${Math.random().toString(16).slice(2)}`,
    };
  }

  function normalizeToolCallList(map) {
    return [...map.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([, call]) => buildNativeToolCallMessage(call))
      .filter((call) => call.function.name);
  }

  agent.tools = Object.freeze({
    nativeTools,
    normalizeNativeToolCall,
    normalizeToolCallList,
    parseJsonLoose,
  });
})(window);
