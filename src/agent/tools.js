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

      description: "列出项目目录中的文件和文件夹，用于了解目录结构。默认只返回一层，可设置 maxDepth 做浅层递归。",

      parameters: {

        type: "object",

        properties: {

          path: {

            type: "string",

            description: "可选的相对目录，留空表示项目根目录。",

          },

          maxDepth: {

            type: "integer",

            description: "递归层数，建议 1-3，默认 1。",

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

      description: "读取项目目录或 attachments/ 下的文本与图片文件。文本支持按行读取；图片读取后会自动作为视觉输入提供给模型。",

      parameters: {

        type: "object",

        properties: {

          path: {

            type: "string",

            description: "相对项目根目录的文件路径，例如 code/app.js",

          },

          startLine: {

            type: "integer",

            description: "可选，起始行号，从 1 开始。",

          },

          endLine: {

            type: "integer",

            description: "可选，结束行号，包含该行。",

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

      description: "按文件名和文件内容搜索项目内文件，支持关键词、正则、文件类型过滤和上下文行。默认跳过 node_modules、.git、构建产物等目录。",

      parameters: {

        type: "object",

        properties: {

          query: {

            type: "string",

            description: "搜索关键词（子串匹配）或正则表达式（当 regex=true 时）。",

          },

          path: {

            type: "string",

            description: "可选的相对搜索目录，留空表示项目根目录。",

          },

          regex: {

            type: "boolean",

            description: "是否启用正则匹配，默认 false。",

          },

          type: {

            type: "string",

            description: "文件类型过滤，如 \"js,ts,py\" 只搜索这些扩展名的文件。",

          },

          glob: {

            type: "string",

            description: "文件名 glob 模式，如 \"**/*.ts\" 只搜索匹配该模式的文件。",

          },

          contextAround: {

            type: "integer",

            description: "每个匹配行前后显示的行数，默认 0。",

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

      description: "按 glob 模式匹配项目中的文件名和路径，用于快速查找符合命名规范的文件。默认跳过依赖、构建产物等目录。",

      parameters: {

        type: "object",

        properties: {

          pattern: {

            type: "string",

            description: "glob 模式，如 \"**/*.py\"、\"*.js\"、\"src/**/*.tsx\"。",

          },

          path: {

            type: "string",

            description: "可选的搜索起始目录，留空表示项目根目录。",

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

      description: "生成文件修改方案和 unified diff。该工具不会直接写入文件，必须等待用户点击应用修改。",

      parameters: {

        type: "object",

        properties: {

          path: {

            type: "string",

            description: "相对项目根目录的文件路径。",

          },

          oldText: {

            type: "string",

            description: "需要替换的原文片段。局部修改时使用。",

          },

          newText: {

            type: "string",

            description: "替换后的新片段。局部修改时使用。",

          },

          newContent: {

            type: "string",

            description: "完整的新文件内容。新建文件或整文件重写时使用。",

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

      description: "加载一个已安装的 Skill 来获取专业指导。必须单独调用并等待返回后，才能选择或调用其他工具；不要在同一轮并发调用 task。返回受信任的可执行 runtimeResources 时，只能使用其精确路径和所选依赖运行时，不得搜索或复制资源。传入 name 参数指定 Skill 名称。",

      parameters: {

        type: "object",

        properties: {

          name: { type: "string", description: "Skill 名称，如 python-testing。" },

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

      description: "创建新文件或覆盖已有文件。会自动备份原文件到 data/file-backups/。需要用户确认后才会执行。",

      parameters: {

        type: "object",

        properties: {

          path: {

            type: "string",

            description: "相对项目根目录的文件路径。",

          },

          content: {

            type: "string",

            description: "文件的完整内容。",

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

      description: "删除项目内的文件或空目录。文件会自动备份到 data/file-backups/。需要用户确认后才会执行。",

      parameters: {

        type: "object",

        properties: {

          path: {

            type: "string",

            description: "相对项目根目录的文件或空目录路径。",

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
