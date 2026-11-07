import { APIError } from './api';
import type { WorkflowEvent, WorkflowExecution, WorkflowResponse, WorkflowStage, WorkflowStepStatus } from '@/components/chat/types';

function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function status(value: unknown): value is WorkflowStepStatus {
  return value === 'waiting' || value === 'running' || value === 'completed' || value === 'needs_review' || value === 'failed';
}

function plan(value: unknown): value is WorkflowStage[] {
  return Array.isArray(value) && value.length === 3 && value.every((stage, index) =>
    record(stage) && stage.id === ['context', 'parallel', 'synthesis'][index] &&
    Array.isArray(stage.agents) && stage.agents.every((agent: unknown) => typeof agent === 'string')
  );
}

function result(value: unknown): value is WorkflowResponse {
  return record(value) && typeof value.workflow === 'string' &&
    (value.status === 'completed' || value.status === 'needs_review') &&
    typeof value.summary === 'string' && !!value.summary.trim() &&
    Array.isArray(value.steps) && value.steps.length > 0 &&
    value.steps.every((step: unknown) => record(step) && typeof step.agent === 'string' && typeof step.text === 'string') &&
    (value.plan === undefined || plan(value.plan));
}

function event(value: unknown): value is WorkflowEvent {
  if (!record(value)) return false;
  if (value.type === 'plan') return plan(value.plan);
  if (value.type === 'stage') return value.id === 'context' && status(value.status);
  return value.type === 'step' && typeof value.agent === 'string' && status(value.status) &&
    (value.duration_ms === undefined || (typeof value.duration_ms === 'number' && Number.isFinite(value.duration_ms) && value.duration_ms >= 0));
}

export function updateWorkflowExecution(current: WorkflowExecution, update: WorkflowEvent): WorkflowExecution {
  if (update.type === 'plan') return { ...current, plan: update.plan };
  if (update.type === 'stage') return { ...current, context: update.status };
  return { ...current, agents: { ...current.agents, [update.agent]: { status: update.status, duration_ms: update.duration_ms } } };
}

/** Incremental SSE reader: a closed stream is not a successful workflow. */
export async function readWorkflowResponse(response: Response, onEvent: (event: WorkflowEvent) => void): Promise<WorkflowResponse> {
  if (!response.ok) {
    const body: unknown = await response.json();
    throw new APIError(response.status, 'WORKFLOW_FAILED', body);
  }
  if (response.headers.get('content-type')?.includes('application/json')) {
    const body: unknown = await response.json();
    if (!result(body)) throw new Error('WORKFLOW_INVALID_RESULT');
    return body;
  }
  if (!response.body || !response.headers.get('content-type')?.includes('text/event-stream')) {
    throw new Error('WORKFLOW_INVALID_STREAM');
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    while (true) {
      const chunk = await reader.read();
      buffer += decoder.decode(chunk.value, { stream: !chunk.done });
      let boundary: RegExpExecArray | null;
      while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
        const frame = buffer.slice(0, boundary.index);
        buffer = buffer.slice(boundary.index + boundary[0].length);
        const data = frame.split(/\r?\n/).filter(line => line.startsWith('data:'))
          .map(line => line.slice(5).trimStart()).join('\n');
        if (!data) continue;
        const value: unknown = JSON.parse(data);
        if (record(value) && value.type === 'done') {
          if (!result(value.result)) throw new Error('WORKFLOW_INVALID_RESULT');
          return value.result;
        }
        if (record(value) && value.type === 'error') {
          throw new APIError(typeof value.status === 'number' ? value.status : 500, 'WORKFLOW_FAILED', { detail: value.detail });
        }
        if (!event(value)) throw new Error('WORKFLOW_INVALID_EVENT');
        onEvent(value);
      }
      if (chunk.done) throw new Error('WORKFLOW_STREAM_INCOMPLETE');
    }
  } finally {
    await reader.cancel();
    reader.releaseLock();
  }
}
