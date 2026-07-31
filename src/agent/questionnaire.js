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

  function userInputAnswerText(question, canceledLabel = "") {
    if (!question) return "";
    if (question.status === "canceled") {
      return question.other ? `${canceledLabel}：${question.other}` : canceledLabel;
    }
    if (question.type === "text") return String(question.text || "").trim();
    const labels = (question.selected || [])
      .map((value) => question.options.find((option) => option.value === value)?.label || value);
    if (question.other) labels.push(question.other);
    return labels.join("、");
  }

  function buildUserInputResult(request, canceledLabel = "") {
    const answers = request.questions.map((question) => ({
      id: question.id,
      prompt: question.prompt,
      type: question.type,
      status: question.status,
      values: question.type === "text" ? undefined : [...(question.selected || [])],
      text: question.type === "text" ? String(question.text || "").trim() : undefined,
      other: String(question.other || "").trim(),
      answer: userInputAnswerText(question, canceledLabel),
    }));
    return {
      ok: true,
      action: "request_user_input",
      requestId: request.id,
      title: request.title,
      answers,
      summary: answers.map((answer) => `${answer.prompt}：${answer.answer || canceledLabel}`).join("\n"),
    };
  }

  agent.questionnaire = Object.freeze({
    buildUserInputResult,
    normalizeUserInputQuestions,
    serializeUserInputRequest,
    userInputAnswerText,
  });
})(window);
