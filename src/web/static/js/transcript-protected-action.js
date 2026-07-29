/**
 * Shared controller for authenticated transcript actions and their task polling.
 * The module owns request/retry/timer state and deliberately leaves dialogs and
 * page rendering to injected adapters.
 */
(function installProtectedAction(root, factory) {
    'use strict';

    const api = factory(root);
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    if (root) root.VideoTranscriptProtectedAction = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function createApi(root) {
    'use strict';

    const ACTION_ENDPOINTS = Object.freeze({
        recalibrate: '/api/recalibrate',
        resummarize: '/api/resummarize',
        generate_notes: '/api/generate_notes',
    });
    const POLL_STATUSES = new Set(['queued', 'processing', 'calibrating', 'success', 'failed']);
    const POLL_INTERVAL_MS = 3000;
    const POLL_TIMEOUT_MS = 600000;
    const POLL_ERROR_LIMIT = 10;
    const REQUIRED_AUTH_METHODS = [
        'readAuthToken',
        'snapshotAuthToken',
        'buildAuthHeaders',
        'clearAuthTokenIfMatch',
        'writeAuthToken',
    ];

    function isNonEmptyToken(token) {
        return typeof token === 'string' && token.trim().length > 0;
    }

    function isAbortError(error) {
        return Boolean(error && error.name === 'AbortError');
    }

    function makeAbortError() {
        if (typeof DOMException === 'function') return new DOMException('aborted', 'AbortError');
        const error = new Error('aborted');
        error.name = 'AbortError';
        return error;
    }

    function responseJson(response, kind) {
        if (!response || typeof response.json !== 'function') {
            return Promise.reject(new Error(`non-JSON ${kind} response`));
        }
        return Promise.resolve().then(() => response.json()).catch(() => {
            throw new Error(`non-JSON ${kind} response`);
        });
    }

    function runFetch(fetchImpl, url, options, kind) {
        let request;
        try {
            request = fetchImpl(url, options);
        } catch (error) {
            request = Promise.reject(error);
        }
        return Promise.resolve(request).catch((error) => {
            if (isAbortError(error)) throw error;
            throw new Error(`${kind} network failure`);
        });
    }

    function createContext(controllerOptions) {
        const AbortControllerImpl = controllerOptions.AbortControllerImpl;
        const abortController = typeof AbortControllerImpl === 'function'
            ? new AbortControllerImpl()
            : null;
        let resolvePromise;
        let rejectPromise;
        const context = {
            abortController,
            aborted: false,
            finished: false,
            inFlight: false,
            replayed: false,
            consecutiveErrors: 0,
            startedAt: controllerOptions.now(),
            timer: null,
            successCalled: false,
            promise: new Promise((resolve, reject) => {
                resolvePromise = resolve;
                rejectPromise = reject;
            }),
            resolve: resolvePromise,
            reject: rejectPromise,
        };
        return context;
    }

    function createProtectedActionController(dependencies) {
        const options = dependencies || {};
        const authStorage = options.authStorage;
        const fetchImpl = options.fetchImpl || (root && root.fetch);
        const promptToken = options.promptToken;
        const eventTarget = options.eventTarget || (root && root.window) || root;
        const setTimeoutImpl = options.setTimeoutImpl || (root && root.setTimeout) || setTimeout;
        const clearTimeoutImpl = options.clearTimeoutImpl || (root && root.clearTimeout) || clearTimeout;
        const now = options.now || Date.now;
        const AbortControllerImpl = options.AbortControllerImpl ||
            (root && root.AbortController) ||
            (typeof AbortController === 'function' ? AbortController : null);
        const onSuccess = typeof options.onSuccess === 'function' ? options.onSuccess : () => {};

        const authReady = authStorage && REQUIRED_AUTH_METHODS.every(
            (method) => typeof authStorage[method] === 'function'
        );
        if (!authReady || typeof fetchImpl !== 'function' || typeof promptToken !== 'function') {
            throw new Error('Protected action dependencies missing');
        }

        let promptInFlight = null;
        const contexts = new Set();

        function promptForToken() {
            if (promptInFlight) return promptInFlight;
            promptInFlight = Promise.resolve()
                .then(() => promptToken())
                .then((token) => {
                    if (!isNonEmptyToken(token)) throw new Error('Protected action token prompt cancelled');
                    if (authStorage.writeAuthToken(token) === false) {
                        throw new Error('Protected action token save failed');
                    }
                    return token;
                })
                .finally(() => {
                    promptInFlight = null;
                });
            return promptInFlight;
        }

        async function refreshTokenAfter401(snapshot) {
            const cleared = authStorage.clearAuthTokenIfMatch(snapshot);
            if (cleared || !isNonEmptyToken(authStorage.readAuthToken())) {
                await promptForToken();
            }
        }

        function clearTimer(context) {
            if (context.timer === null) return;
            clearTimeoutImpl(context.timer);
            context.timer = null;
        }

        function finishContext(context, error, value) {
            if (context.finished) return;
            context.finished = true;
            clearTimer(context);
            contexts.delete(context);
            if (error) context.reject(error);
            else context.resolve(value);
        }

        function schedulePoll(context, pollOnce) {
            if (context.finished || context.aborted) return;
            if (now() - context.startedAt >= POLL_TIMEOUT_MS) {
                finishContext(context, new Error('Polling timeout'));
                return;
            }
            clearTimer(context);
            context.timer = setTimeoutImpl(() => {
                context.timer = null;
                pollOnce();
            }, POLL_INTERVAL_MS);
        }

        async function pollTask(context, taskId) {
            const pollOnce = async () => {
                if (context.finished || context.aborted || context.inFlight) return;
                if (now() - context.startedAt >= POLL_TIMEOUT_MS) {
                    finishContext(context, new Error('Polling timeout'));
                    return;
                }
                context.inFlight = true;
                const snapshot = authStorage.snapshotAuthToken();
                try {
                    const response = await runFetch(
                        fetchImpl,
                        `/api/task/${encodeURIComponent(taskId)}`,
                        {
                            headers: authStorage.buildAuthHeaders(),
                            signal: context.abortController && context.abortController.signal,
                        },
                        'Polling'
                    );
                    if (response.status === 401) {
                        if (context.replayed) throw new Error('HTTP 401 after one replay');
                        context.replayed = true;
                        await refreshTokenAfter401(snapshot);
                        context.inFlight = false;
                        return pollOnce();
                    }
                    if ([403, 404, 409].includes(response.status)) {
                        throw new Error(`HTTP ${response.status}`);
                    }
                    if (!response.ok) throw new Error(`Polling HTTP ${response.status}`);
                    const body = await responseJson(response, 'polling');
                    const status = body && body.data && body.data.status;
                    if (typeof status !== 'string' || !status) {
                        throw new Error('missing task status');
                    }
                    if (!POLL_STATUSES.has(status)) throw new Error('unknown task status');
                    if (status === 'failed') throw new Error('Task failed');
                    if (status === 'success') {
                        context.consecutiveErrors = 0;
                        if (!context.successCalled) {
                            context.successCalled = true;
                            onSuccess({ taskId, body });
                        }
                        finishContext(context, null, body);
                        return;
                    }
                    context.consecutiveErrors = 0;
                    schedulePoll(context, pollOnce);
                } catch (error) {
                    if (context.finished) return;
                    if (context.aborted || isAbortError(error)) {
                        finishContext(context, makeAbortError());
                        return;
                    }
                    if (
                        error &&
                        (error.message === 'missing task status' ||
                            error.message === 'unknown task status' ||
                            error.message === 'non-JSON polling response' ||
                            error.message === 'Task failed' ||
                            error.message === 'HTTP 401 after one replay' ||
                            /^HTTP (403|404|409)/.test(error.message) ||
                            error.message === 'Polling timeout')
                    ) {
                        finishContext(context, error);
                        return;
                    }
                    context.consecutiveErrors += 1;
                    if (context.consecutiveErrors >= POLL_ERROR_LIMIT) {
                        finishContext(context, new Error('consecutive polling errors'));
                        return;
                    }
                    schedulePoll(context, pollOnce);
                } finally {
                    context.inFlight = false;
                }
            };
            await pollOnce();
        }

        async function postAction(context, actionName, viewToken, attempt) {
            if (context.aborted) throw makeAbortError();
            const token = authStorage.readAuthToken();
            if (!isNonEmptyToken(token)) {
                await promptForToken();
            }
            const snapshot = authStorage.snapshotAuthToken();
            let response;
            try {
                response = await runFetch(
                    fetchImpl,
                    ACTION_ENDPOINTS[actionName],
                    {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            ...authStorage.buildAuthHeaders(),
                        },
                        body: JSON.stringify({ view_token: viewToken }),
                        signal: context.abortController && context.abortController.signal,
                    },
                    'POST'
                );
            } catch (error) {
                if (context.aborted || isAbortError(error)) throw makeAbortError();
                throw error;
            }
            if (response.status === 401) {
                if (attempt >= 1 || context.replayed) throw new Error('HTTP 401 after one replay');
                context.replayed = true;
                await refreshTokenAfter401(snapshot);
                return postAction(context, actionName, viewToken, attempt + 1);
            }
            if ([403, 404, 409].includes(response.status)) throw new Error(`HTTP ${response.status}`);
            if (!response.ok) throw new Error(`POST HTTP ${response.status}`);
            const body = await responseJson(response, 'POST');
            if (!body || body.code !== 202) {
                throw new Error('POST response missing task_id (body code must be 202)');
            }
            const taskId = body.data && body.data.task_id;
            if (!taskId) throw new Error('POST response missing task_id');
            return { taskId, body };
        }

        function abortContext(context) {
            if (context.finished || context.aborted) return;
            context.aborted = true;
            clearTimer(context);
            if (context.abortController) context.abortController.abort();
            finishContext(context, makeAbortError());
        }

        function handlePagehide() {
            for (const context of Array.from(contexts)) abortContext(context);
        }

        if (eventTarget && typeof eventTarget.addEventListener === 'function') {
            eventTarget.addEventListener('pagehide', handlePagehide);
        }

        /** Run one authenticated transcript action and poll its task to a terminal status. */
        function runProtectedAction(actionName, viewToken) {
            if (!Object.prototype.hasOwnProperty.call(ACTION_ENDPOINTS, actionName)) {
                throw new Error('Unsupported protected action');
            }
            if (!isNonEmptyToken(viewToken)) throw new Error('Protected action view_token missing');
            const context = createContext({
                now,
                AbortControllerImpl,
            });
            contexts.add(context);
            // Keep an internal rejection handler so a pagehide or timer failure
            // cannot become an unhandled rejection before the caller awaits it.
            context.promise.catch(() => {});
            (async () => {
                try {
                    const { taskId } = await postAction(context, actionName, viewToken, 0);
                    if (context.aborted || context.finished) return;
                    await pollTask(context, taskId);
                } catch (error) {
                    if (context.finished) return;
                    finishContext(context, context.aborted || isAbortError(error) ? makeAbortError() : error);
                }
            })();
            return context.promise;
        }

        function dispose() {
            for (const context of Array.from(contexts)) abortContext(context);
            if (eventTarget && typeof eventTarget.removeEventListener === 'function') {
                eventTarget.removeEventListener('pagehide', handlePagehide);
            }
        }

        return {
            runProtectedAction,
            dispose,
        };
    }

    return {
        /**
         * Create an authenticated transcript-action controller; polling timers
         * use milliseconds, allow one replay per action, and abort on pagehide.
         */
        createProtectedActionController,
    };
});
