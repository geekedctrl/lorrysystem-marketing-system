'use strict';

// Normalize the HTTP Chat Completions envelope without retaining provider errors.
function completionContent(response) {
  const result = {content: null, error: null, finish_reason: null, usage: null};
  const status = response?.statusCode;
  if (status !== undefined && Number(status) !== 200) {
    result.error = `AI_PROVIDER_HTTP_${Number.isInteger(Number(status)) ? Number(status) : 'INVALID'}`;
    return result;
  }
  const body = response?.body ?? response;
  if (response?.error || body?.error) {
    result.error = 'AI_PROVIDER_REQUEST_FAILED';
    return result;
  }
  const choice = Array.isArray(body?.choices) ? body.choices[0] : null;
  result.finish_reason = choice?.finish_reason ?? null;
  if (!choice) result.error = 'AI_PROVIDER_INVALID_RESPONSE';
  else if (choice.finish_reason !== 'stop') result.error = 'AI_PROVIDER_INCOMPLETE_RESPONSE';
  else if (choice.message?.refusal || choice.message?.tool_calls?.length) result.error = 'AI_PROVIDER_UNEXPECTED_MESSAGE';
  else if (typeof choice.message?.content !== 'string' || !choice.message.content.trim()) {
    result.error = 'AI_PROVIDER_EMPTY_CONTENT';
  } else {
    result.content = choice.message.content;
    const usage = body.usage;
    if (usage && ['prompt_tokens','completion_tokens','total_tokens'].every(key =>
      Number.isInteger(usage[key]) && usage[key] >= 0)) {
      result.usage = {prompt_tokens: usage.prompt_tokens, completion_tokens: usage.completion_tokens, total_tokens: usage.total_tokens};
    }
  }
  return result;
}

if (typeof module !== 'undefined') module.exports = {completionContent};
