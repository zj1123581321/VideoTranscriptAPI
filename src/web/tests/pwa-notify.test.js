// Tests for the task terminal-state judgment used by E5 polling (PWA T8).
//
// Contract (design: docs/designs/pwa.md E5, OV round-2 #1):
// GET /api/task/{id} returns HTTP 200 even for failed tasks (body carries
// code=500, data.status='failed'), so the poller MUST judge terminal state
// from the response body: data.status is 'success' | 'failed' -> terminal;
// anything else -> still running. success -> notify; failed -> stop silently.

import { createRequire } from 'node:module';
import { describe, expect, it } from 'vitest';

const require = createRequire(import.meta.url);
const {
  taskTerminalState,
  POLL_INTERVAL_MS,
  MAX_CONSECUTIVE_FAILURES,
  TRACKED_TASKS_KEY,
  parseTrackedTasks,
  upsertTrackedTask,
  removeTrackedTask,
} = require('../static/pwa.js');

describe('taskTerminalState', () => {
  it('success body is terminal success', () => {
    expect(taskTerminalState({ code: 200, data: { status: 'success' } })).toBe('success');
  });

  it('failed body (HTTP 200 + code=500) is terminal failed', () => {
    expect(taskTerminalState({ code: 500, data: { status: 'failed' } })).toBe('failed');
  });

  it('non-terminal statuses keep polling', () => {
    expect(taskTerminalState({ code: 200, data: { status: 'queued' } })).toBeNull();
    expect(taskTerminalState({ code: 200, data: { status: 'processing' } })).toBeNull();
    expect(taskTerminalState({ code: 200, data: { status: 'calibrating' } })).toBeNull();
  });

  it('malformed bodies keep polling (no crash)', () => {
    expect(taskTerminalState(null)).toBeNull();
    expect(taskTerminalState(undefined)).toBeNull();
    expect(taskTerminalState({})).toBeNull();
    expect(taskTerminalState({ code: 200 })).toBeNull();
    expect(taskTerminalState({ data: null })).toBeNull();
    expect(taskTerminalState('garbage')).toBeNull();
  });
});

describe('polling constants', () => {
  it('polls every 15s and gives up after 5 consecutive failures', () => {
    expect(POLL_INTERVAL_MS).toBe(15000);
    expect(MAX_CONSECUTIVE_FAILURES).toBe(5);
  });
});

describe('tracked-task persistence (Codex R1-1)', () => {
  it('storage key is stable', () => {
    expect(TRACKED_TASKS_KEY).toBe('vta_pwa_tracked_tasks');
  });

  it('parseTrackedTasks round-trips a persisted list', () => {
    const list = [
      { task_id: 'a', view_token: 'va' },
      { task_id: 'b', view_token: 'vb' },
    ];
    expect(parseTrackedTasks(JSON.stringify(list))).toEqual(list);
  });

  it('parseTrackedTasks tolerates junk', () => {
    expect(parseTrackedTasks(null)).toEqual([]);
    expect(parseTrackedTasks('')).toEqual([]);
    expect(parseTrackedTasks('not-json')).toEqual([]);
    expect(parseTrackedTasks('{"x":1}')).toEqual([]);
    expect(parseTrackedTasks('[{"view_token":"v"},{"task_id":""},null]')).toEqual([]);
    expect(parseTrackedTasks('[{"task_id":"a"}]')).toEqual([{ task_id: 'a', view_token: '' }]);
  });

  it('upsertTrackedTask appends new tasks', () => {
    const out = upsertTrackedTask([], { task_id: 'a', view_token: 'va' });
    expect(out).toEqual([{ task_id: 'a', view_token: 'va' }]);
  });

  it('upsertTrackedTask dedupes by task_id, keeping the latest', () => {
    const base = [{ task_id: 'a', view_token: 'va' }, { task_id: 'b', view_token: 'vb' }];
    const out = upsertTrackedTask(base, { task_id: 'a', view_token: 'va2' });
    expect(out).toEqual([{ task_id: 'b', view_token: 'vb' }, { task_id: 'a', view_token: 'va2' }]);
  });

  it('removeTrackedTask removes by key, not by index (Codex R1-3)', () => {
    const list = [
      { task_id: 'a', view_token: 'va' },
      { task_id: 'b', view_token: 'vb' },
      { task_id: 'c', view_token: 'vc' },
    ];
    expect(removeTrackedTask(list, 'b')).toEqual([
      { task_id: 'a', view_token: 'va' },
      { task_id: 'c', view_token: 'vc' },
    ]);
    // unknown id is a no-op
    expect(removeTrackedTask(list, 'zzz')).toEqual(list);
  });
});
