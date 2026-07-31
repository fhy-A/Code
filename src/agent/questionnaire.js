(function initializeCodeAgentQuestionnaire(global) {
  "use strict";

  const agent = global.Code && global.Code.agent;
  if (!agent) throw new Error("Code agent namespace must load before questionnaire");

  function normalizeUserInputQuestions(sourceQuestions) {
    return (Array.isArray(sourceQuestions) ? sourceQuestions : [])
      .slice(0, 3)
      .map((question, index) => {
        const type = ["single", "multiple", "text"].includes(question?.type) ? question.type : "single";
        const options = type === "text" ? [] : (Array.isArray(question?.options) ? question.options : [])
          .slice(0, 8)
          .map((option, optionIndex) => ({
            value: String(option?.value || `option_${optionIndex + 1}`),
            label: String(option?.label || option?.value || `${optionIndex + 1}`),
            description: String(option?.description || ""),
          }));
        return {
          id: String(question?.id || `question_${index + 1}`),
          prompt: String(question?.prompt || "").trim(),
          type,
          required: question?.required !== false,
          allowOther: Boolean(question?.allowOther),
          options,
          status: "pending",
          selected: [],
          text: "",
          other: "",
          answer: null,
        };
      })
      .filter((question) => question.prompt && (question.type === "text" || question.options.length));
  }

  function serializeUserInputRequest(request) {
    if (!request) return null;
    const { abortSignal, abortHandler, _finishing, ...serializable } = request;
    return JSON.parse(JSON.stringify(serializable));
  }

  agent.questionnaire = Object.freeze({
    normalizeUserInputQuestions,
    serializeUserInputRequest,
  });
})(window);
