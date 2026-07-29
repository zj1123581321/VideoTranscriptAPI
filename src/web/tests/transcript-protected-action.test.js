import { createRequire } from 'node:module';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

const require = createRequire(import.meta.url);
const modulePath = require.resolve('../static/js/transcript-protected-action.js');

function loadController() {
  delete require.cache[modulePath];
  return require(modulePath);
}

function response(status, body) {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: vi.fn(async () => body),
  };
}

function authState(token = 'cached-token') {
  return {
    readAuthToken: vi.fn(() => token),
    snapshotAuthToken: vi.fn(() => token),
    buildAuthHeaders: vi.fn(() => token ? { Authorization: `Bearer ${token}` } : {}),
    clearAuthTokenIfMatch: vi.fn(() => true),
    writeAuthToken: vi.fn(() => true),
  };
}

function dependencies(overrides = {}) {
  const authStorage = overrides.authStorage || authState();
  return {
    authStorage,
    fetchImpl: overrides.fetchImpl || vi.fn(),
    promptToken: overrides.promptToken || vi.fn(async () => 'prompted-token'),
    eventTarget: overrides.eventTarget || { addEventListener: vi.fn(), removeEventListener: vi.fn() },
    ...overrides,
  };
}

describe('transcript protected action controller', () => {
  beforeEach(() => vi.useRealTimers());
  afterEach(() => vi.restoreAllMocks());

  it('uses cached token without prompting and submits the canonical POST body', async () => {
    const api = loadController();
    const deps = dependencies();
    deps.fetchImpl
      .mockResolvedValueOnce(response(202, { code: 202, data: { task_id: 'task-1' } }))
      .mockResolvedValueOnce(response(200, { code: 200, data: { status: 'success' } }));
    const controller = api.createProtectedActionController(deps);

    await controller.runProtectedAction('recalibrate', 'view-1');

    expect(deps.promptToken).not.toHaveBeenCalled();
    expect(deps.fetchImpl.mock.calls[0][0]).toBe('/api/recalibrate');
    expect(JSON.parse(deps.fetchImpl.mock.calls[0][1].body)).toEqual({ view_token: 'view-1' });
  });

  it('prompts once when the canonical token is absent before POST', async () => {
    const api = loadController();
    const deps = dependencies();
    deps.authStorage.readAuthToken.mockReturnValue(null);
    deps.authStorage.snapshotAuthToken.mockReturnValue('prompted-token');
    deps.fetchImpl
      .mockResolvedValueOnce(response(202, { code: 202, data: { task_id: 'task-missing-token' } }))
      .mockResolvedValueOnce(response(200, { data: { status: 'success' } }));
    const controller = api.createProtectedActionController(deps);

    await controller.runProtectedAction('recalibrate', 'view-missing-token');

    expect(deps.promptToken).toHaveBeenCalledTimes(1);
    expect(deps.authStorage.writeAuthToken).toHaveBeenCalledWith('prompted-token');
  });

  it('shares one prompt across concurrent 401 responses and replays each POST once', async () => {
    const api = loadController();
    const deps = dependencies();
    deps.authStorage.readAuthToken
      .mockReturnValueOnce('old-token').mockReturnValue('new-token');
    deps.authStorage.snapshotAuthToken
      .mockReturnValueOnce('old-token').mockReturnValue('new-token');
    deps.fetchImpl
      .mockResolvedValueOnce(response(401, { detail: 'expired' }))
      .mockResolvedValueOnce(response(401, { detail: 'expired' }))
      .mockResolvedValueOnce(response(202, { code: 202, data: { task_id: 'task-a' } }))
      .mockResolvedValueOnce(response(202, { code: 202, data: { task_id: 'task-b' } }))
      .mockResolvedValueOnce(response(200, { data: { status: 'success' } }))
      .mockResolvedValueOnce(response(200, { data: { status: 'success' } }));
    deps.promptToken = vi.fn(async () => 'new-token');
    const controller = api.createProtectedActionController(deps);

    await Promise.all([
      controller.runProtectedAction('recalibrate', 'view-a'),
      controller.runProtectedAction('resummarize', 'view-b'),
    ]);

    expect(deps.promptToken).toHaveBeenCalledTimes(1);
    expect(deps.authStorage.clearAuthTokenIfMatch).toHaveBeenCalledTimes(2);
    expect(deps.fetchImpl).toHaveBeenCalledTimes(6);
  });

  it.each([403, 404, 409])('does not prompt or replay on HTTP %s', async (status) => {
    const api = loadController();
    const deps = dependencies();
    deps.fetchImpl.mockResolvedValueOnce(response(status, { detail: 'terminal' }));
    const controller = api.createProtectedActionController(deps);

    await expect(controller.runProtectedAction('resummarize', 'view-2')).rejects.toThrow(`HTTP ${status}`);
    expect(deps.promptToken).not.toHaveBeenCalled();
    expect(deps.fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('never replays an ambiguous POST TypeError', async () => {
    const api = loadController();
    const deps = dependencies();
    deps.fetchImpl.mockRejectedValueOnce(new TypeError('network failed'));
    const controller = api.createProtectedActionController(deps);

    await expect(controller.runProtectedAction('generate_notes', 'view-3')).rejects.toThrow('POST network failure');
    expect(deps.promptToken).not.toHaveBeenCalled();
    expect(deps.fetchImpl).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['missing task_id', { code: 202, data: {} }],
    ['wrong body code', { code: 500, data: { task_id: 'task-4' } }],
  ])('fails explicitly for %s', async (_label, body) => {
    const api = loadController();
    const deps = dependencies();
    deps.fetchImpl.mockResolvedValueOnce(response(202, body));
    const controller = api.createProtectedActionController(deps);

    await expect(controller.runProtectedAction('recalibrate', 'view-4')).rejects.toThrow('task_id');
    expect(deps.fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('fails explicitly for a non-JSON POST response', async () => {
    const api = loadController();
    const deps = dependencies();
    deps.fetchImpl.mockResolvedValueOnce({ status: 202, ok: true, json: vi.fn(async () => { throw new SyntaxError('bad json'); }) });
    const controller = api.createProtectedActionController(deps);

    await expect(controller.runProtectedAction('recalibrate', 'view-5')).rejects.toThrow('non-JSON POST response');
  });

  it('polls queued, processing, calibrating, then success at one timer per task', async () => {
    vi.useFakeTimers();
    const api = loadController();
    const deps = dependencies();
    const success = vi.fn();
    deps.fetchImpl
      .mockResolvedValueOnce(response(202, { code: 202, data: { task_id: 'task-6' } }))
      .mockResolvedValueOnce(response(200, { data: { status: 'queued' } }))
      .mockResolvedValueOnce(response(200, { data: { status: 'processing' } }))
      .mockResolvedValueOnce(response(200, { data: { status: 'calibrating' } }))
      .mockResolvedValueOnce(response(200, { data: { status: 'success' } }));
    const controller = api.createProtectedActionController({ ...deps, onSuccess: success });
    const pending = controller.runProtectedAction('recalibrate', 'view-6');
    await vi.runOnlyPendingTimersAsync();
    await vi.advanceTimersByTimeAsync(3000);
    await vi.advanceTimersByTimeAsync(3000);
    await vi.advanceTimersByTimeAsync(3000);
    await pending;

    expect(deps.fetchImpl.mock.calls.filter(([, init]) => init?.method !== 'POST')).toHaveLength(4);
    expect(success).toHaveBeenCalledTimes(1);
  });

  it('treats HTTP 200 body code 500 failed as a terminal failure', async () => {
    const api = loadController();
    const deps = dependencies();
    deps.fetchImpl
      .mockResolvedValueOnce(response(202, { code: 202, data: { task_id: 'task-7' } }))
      .mockResolvedValueOnce(response(200, { code: 500, data: { status: 'failed' } }));
    const controller = api.createProtectedActionController(deps);

    await expect(controller.runProtectedAction('resummarize', 'view-7')).rejects.toThrow('failed');
  });

  it('fails explicitly when a polling response is not JSON', async () => {
    const api = loadController();
    const deps = dependencies();
    deps.fetchImpl
      .mockResolvedValueOnce(response(202, { code: 202, data: { task_id: 'task-non-json' } }))
      .mockResolvedValueOnce({ status: 200, ok: true, json: vi.fn(async () => { throw new SyntaxError('bad json'); }) });
    const controller = api.createProtectedActionController(deps);

    await expect(controller.runProtectedAction('resummarize', 'view-non-json')).rejects.toThrow(
      'non-JSON polling response'
    );
  });

  it.each([
    { body: { data: { status: 'unknown' } }, message: 'unknown task status' },
    { body: { data: {} }, message: 'missing task status' },
  ])('rejects $message', async ({ body, message }) => {
    const api = loadController();
    const deps = dependencies();
    deps.fetchImpl
      .mockResolvedValueOnce(response(202, { code: 202, data: { task_id: 'task-8' } }))
      .mockResolvedValueOnce(response(200, body));
    const controller = api.createProtectedActionController(deps);

    await expect(controller.runProtectedAction('generate_notes', 'view-8')).rejects.toThrow(message);
  });

  it('stops after ten consecutive polling errors and does not overlap fetches', async () => {
    vi.useFakeTimers();
    const api = loadController();
    const deps = dependencies();
    deps.fetchImpl.mockResolvedValueOnce(response(202, { code: 202, data: { task_id: 'task-9' } }));
    for (let index = 0; index < 10; index += 1) {
      deps.fetchImpl.mockRejectedValueOnce(new Error(`poll-${index}`));
    }
    const controller = api.createProtectedActionController(deps);
    const pending = controller.runProtectedAction('recalibrate', 'view-9');
    for (let index = 0; index < 10; index += 1) await vi.advanceTimersByTimeAsync(3000);
    await expect(pending).rejects.toThrow('consecutive polling errors');
    expect(deps.fetchImpl).toHaveBeenCalledTimes(11);
  });

  it('aborts private POST and polling when pagehide fires', async () => {
    vi.useFakeTimers();
    const api = loadController();
    const listeners = {};
    const deps = dependencies({
      eventTarget: { addEventListener: vi.fn((name, fn) => { listeners[name] = fn; }), removeEventListener: vi.fn() },
    });
    let rejectFetch;
    deps.fetchImpl.mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectFetch = reject; }));
    const controller = api.createProtectedActionController(deps);
    const pending = controller.runProtectedAction('recalibrate', 'view-10');
    listeners.pagehide();
    rejectFetch(new DOMException('aborted', 'AbortError'));
    await expect(pending).rejects.toThrow('aborted');
    expect(deps.eventTarget.addEventListener).toHaveBeenCalledWith('pagehide', expect.any(Function));
  });

  it('requires auth, fetch, and prompt dependencies with a stable error', () => {
    const api = loadController();
    expect(() => api.createProtectedActionController({})).toThrow('Protected action dependencies missing');
  });
});
