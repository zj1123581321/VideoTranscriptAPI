/**
 * Browser Bearer-token storage shared by the submit, history, and transcript
 * pages.  The module deliberately has no UI dependency so each page can use
 * the same migration and compare-and-clear semantics.
 */
(function installAuthStorage(root) {
    'use strict';

    /** Canonical and legacy keys; key names are part of the browser contract. */
    const AUTH_STORAGE_KEYS = Object.freeze({
        canonical: 'vta_bearer_token',
        legacyApi: 'api_key',
        legacyPersistent: 'vta_api_key_persist',
        legacySession: 'vta_api_key',
        migration: 'vta_auth_migration_v1',
        encryptionSuffix: 'vta_encrypt_key_2024',
    });

    let memoryToken = null;
    let memorySealed = false;
    let memoryFallbackActive = false;
    let storageWarningShown = false;
    let warningStorageIdentity = null;

    function isStorageFailure(error) {
        return Boolean(
            error &&
            (error.name === 'SecurityError' || error.name === 'QuotaExceededError')
        );
    }

    function warnStorageFallback() {
        let storageIdentity = null;
        try {
            storageIdentity = root && root.localStorage ? root.localStorage : null;
        } catch (_error) {
            storageIdentity = null;
        }
        if (storageIdentity !== warningStorageIdentity) {
            warningStorageIdentity = storageIdentity;
            storageWarningShown = false;
        }
        if (storageWarningShown) return;
        storageWarningShown = true;
        const logger =
            (typeof console !== 'undefined' && console && typeof console.warn === 'function' && console) ||
            (root && root.console && typeof root.console.warn === 'function' && root.console);
        if (logger) {
            logger.warn('Browser localStorage unavailable; using memory fallback.');
        }
    }

    function getStorage(name) {
        try {
            return root && root[name] ? root[name] : null;
        } catch (error) {
            if (name === 'localStorage' && isStorageFailure(error)) {
                memoryFallbackActive = true;
                warnStorageFallback();
            }
            return null;
        }
    }

    function readStorageValue(name, key) {
        const storage = getStorage(name);
        if (!storage) return null;
        try {
            return storage.getItem(key);
        } catch (error) {
            if (name === 'localStorage' && isStorageFailure(error)) {
                memoryFallbackActive = true;
                warnStorageFallback();
            }
            return null;
        }
    }

    function writeStorageValue(name, key, value) {
        const storage = getStorage(name);
        if (!storage) return false;
        try {
            storage.setItem(key, value);
            return true;
        } catch (error) {
            if (name === 'localStorage' && isStorageFailure(error)) {
                memoryFallbackActive = true;
                warnStorageFallback();
            }
            return false;
        }
    }

    function removeStorageValue(name, key) {
        const storage = getStorage(name);
        if (!storage) return false;
        try {
            storage.removeItem(key);
            return true;
        } catch (error) {
            if (name === 'localStorage' && isStorageFailure(error)) {
                memoryFallbackActive = true;
                warnStorageFallback();
            }
            return false;
        }
    }

    function hasControlCharacter(value) {
        return /[\u0000-\u001f\u007f]/.test(value);
    }

    function utf8Bytes(value) {
        if (typeof TextEncoder === 'function') {
            return new TextEncoder().encode(value);
        }
        const encoded = encodeURIComponent(value);
        const bytes = [];
        for (let index = 0; index < encoded.length; index += 1) {
            if (encoded[index] === '%') {
                bytes.push(parseInt(encoded.slice(index + 1, index + 3), 16));
                index += 2;
            } else {
                bytes.push(encoded.charCodeAt(index));
            }
        }
        return Uint8Array.from(bytes);
    }

    function decodeUtf8(bytes) {
        if (typeof TextDecoder === 'function') {
            return new TextDecoder().decode(bytes);
        }
        let encoded = '';
        for (const byte of bytes) {
            encoded += `%${byte.toString(16).padStart(2, '0')}`;
        }
        return decodeURIComponent(encoded);
    }

    /**
     * Encode a token with the historical UTF-8 Base64 then reverse format.
     * Control characters are rejected before persistence to keep headers safe.
     */
    function encodeAuthToken(token) {
        if (typeof token !== 'string' || !token || hasControlCharacter(token)) {
            return '';
        }
        try {
            const bytes = utf8Bytes(token + AUTH_STORAGE_KEYS.encryptionSuffix);
            let binary = '';
            for (const byte of bytes) binary += String.fromCharCode(byte);
            return root.btoa(binary).split('').reverse().join('');
        } catch (_error) {
            return '';
        }
    }

    /**
     * Decode and verify the historical payload; malformed or tampered values
     * are absent rather than returned as a possibly unsafe credential.
     */
    function decodeAuthToken(encoded) {
        if (typeof encoded !== 'string' || !encoded) return null;
        try {
            const reversed = encoded.split('').reverse().join('');
            if (!/^[A-Za-z0-9+/]*={0,2}$/.test(reversed) || reversed.length % 4 === 1) {
                return null;
            }
            const binary = root.atob(reversed);
            const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
            const decoded = decodeUtf8(bytes);
            if (!decoded.endsWith(AUTH_STORAGE_KEYS.encryptionSuffix)) return null;
            const token = decoded.slice(0, -AUTH_STORAGE_KEYS.encryptionSuffix.length);
            return token && !hasControlCharacter(token) ? token : null;
        } catch (_error) {
            return null;
        }
    }

    function readLegacyToken() {
        const aliases = [
            ['localStorage', AUTH_STORAGE_KEYS.legacyApi],
            ['localStorage', AUTH_STORAGE_KEYS.legacyPersistent],
            ['sessionStorage', AUTH_STORAGE_KEYS.legacySession],
        ];
        for (const [storageName, key] of aliases) {
            const value = readStorageValue(storageName, key);
            if (typeof value === 'string' && value && !hasControlCharacter(value)) {
                return value;
            }
        }
        return null;
    }

    /**
     * Read a token using canonical > api_key > persistent alias > session alias.
     * Once migration v1 is sealed, aliases are never consulted again.
     */
    function readAuthToken() {
        if (memoryFallbackActive) return memoryToken;
        const canonical = decodeAuthToken(
            readStorageValue('localStorage', AUTH_STORAGE_KEYS.canonical)
        );
        if (canonical) return canonical;
        const sealed = memorySealed ||
            readStorageValue('localStorage', AUTH_STORAGE_KEYS.migration) === '1';
        if (sealed) return null;
        return readLegacyToken();
    }

    /**
     * Persist a selected token canonically, remove every legacy alias, and seal
     * migration.  Replacement clears the old canonical first; if that clear
     * fails, return false while retaining the previous identity.
     * Other storage failures retain the token only in page memory.
     */
    function writeAuthToken(token, _options) {
        if (typeof token !== 'string' || !token || hasControlCharacter(token)) return false;
        const encoded = encodeAuthToken(token);
        if (!encoded) return false;
        const previousMemoryToken = memoryToken;
        const previousMemorySealed = memorySealed;
        const previousMemoryFallbackActive = memoryFallbackActive;
        memoryToken = token;
        memorySealed = true;
        const previousCanonical = readStorageValue('localStorage', AUTH_STORAGE_KEYS.canonical);
        if (previousCanonical && !removeStorageValue('localStorage', AUTH_STORAGE_KEYS.canonical)) {
            warnStorageFallback();
            memoryToken = previousMemoryToken;
            memorySealed = previousMemorySealed;
            memoryFallbackActive = previousMemoryFallbackActive;
            return false;
        }
        const persisted = writeStorageValue(
            'localStorage',
            AUTH_STORAGE_KEYS.canonical,
            encoded
        );
        if (!persisted) {
            memoryFallbackActive = true;
            warnStorageFallback();
            removeStorageValue('localStorage', AUTH_STORAGE_KEYS.legacyApi);
            removeStorageValue('localStorage', AUTH_STORAGE_KEYS.legacyPersistent);
            removeStorageValue('sessionStorage', AUTH_STORAGE_KEYS.legacySession);
            writeStorageValue('localStorage', AUTH_STORAGE_KEYS.migration, '1');
            return true;
        }
        memoryFallbackActive = false;
        removeStorageValue('localStorage', AUTH_STORAGE_KEYS.legacyApi);
        removeStorageValue('localStorage', AUTH_STORAGE_KEYS.legacyPersistent);
        removeStorageValue('sessionStorage', AUTH_STORAGE_KEYS.legacySession);
        writeStorageValue('localStorage', AUTH_STORAGE_KEYS.migration, '1');
        return true;
    }

    /**
     * Migrate a valid canonical token first, otherwise the highest-priority
     * legacy alias, exactly once into canonical storage; an explicit token is
     * treated as the user's selected value.
     */
    function migrateAuthToken(selectedToken) {
        if (memorySealed || readStorageValue('localStorage', AUTH_STORAGE_KEYS.migration) === '1') {
            return readAuthToken();
        }
        const token = selectedToken === undefined
            ? decodeAuthToken(readStorageValue('localStorage', AUTH_STORAGE_KEYS.canonical)) || readLegacyToken()
            : selectedToken;
        if (!token || !writeAuthToken(token, { remember: true })) return null;
        return token;
    }

    /**
     * Clear canonical and legacy credentials and seal migration so stale aliases
     * cannot resurrect after a user-initiated clear.
     */
    function clearAuthToken() {
        memoryToken = null;
        memorySealed = true;
        const canonicalRemoved = removeStorageValue('localStorage', AUTH_STORAGE_KEYS.canonical);
        removeStorageValue('localStorage', AUTH_STORAGE_KEYS.legacyApi);
        removeStorageValue('localStorage', AUTH_STORAGE_KEYS.legacyPersistent);
        removeStorageValue('sessionStorage', AUTH_STORAGE_KEYS.legacySession);
        writeStorageValue('localStorage', AUTH_STORAGE_KEYS.migration, '1');
        if (!canonicalRemoved && !getStorage('localStorage')) memoryFallbackActive = true;
        else memoryFallbackActive = false;
        return true;
    }

    /**
     * Snapshot the current token value; callers pass this exact value to the
     * compare-and-clear operation after a 401 response.
     */
    function snapshotAuthToken() {
        return readAuthToken();
    }

    /** Read persisted canonical state before compare-clear; unavailable storage keeps memory semantics. */
    function readPersistedCanonicalTokenForCompare() {
        const storage = getStorage('localStorage');
        if (!storage) return { available: false, token: null };
        try {
            return {
                available: true,
                token: decodeAuthToken(storage.getItem(AUTH_STORAGE_KEYS.canonical)),
            };
        } catch (error) {
            if (isStorageFailure(error)) {
                memoryFallbackActive = true;
                warnStorageFallback();
            }
            return { available: false, token: null };
        }
    }

    /**
     * Clear only when the current token still equals the request snapshot.
     * A newer token saved by another tab is therefore preserved.
     */
    function compareAndClearAuthToken(snapshot) {
        const persisted = readPersistedCanonicalTokenForCompare();
        if (persisted.available && persisted.token && persisted.token !== snapshot) return false;
        if (snapshotAuthToken() !== snapshot) return false;
        clearAuthToken();
        return true;
    }

    /** Backwards-compatible explicit name for compare-and-clear callers. */
    const clearAuthTokenIfMatch = compareAndClearAuthToken;

    /**
     * Build request headers without mutating caller headers or exposing tokens
     * in logs; absent credentials produce no Authorization header.
     */
    function buildAuthHeaders(extraHeaders) {
        const headers = extraHeaders ? { ...extraHeaders } : {};
        const token = readAuthToken();
        if (token) headers.Authorization = `Bearer ${token}`;
        return headers;
    }

    /**
     * Handle cross-tab storage changes.  A migration/clear event removes the
     * session alias immediately and seals this tab against stale aliases.
     */
    function handleAuthStorageEvent(event) {
        const key = event && event.key;
        if (key === AUTH_STORAGE_KEYS.canonical) {
            const syncedToken = event.newValue === null ? null : decodeAuthToken(event.newValue);
            memoryToken = syncedToken;
            memoryFallbackActive = false;
            memorySealed = true;
        }
        if (
            key === AUTH_STORAGE_KEYS.migration ||
            key === AUTH_STORAGE_KEYS.canonical ||
            key === AUTH_STORAGE_KEYS.legacyApi ||
            key === AUTH_STORAGE_KEYS.legacyPersistent ||
            key === AUTH_STORAGE_KEYS.legacySession
        ) {
            if (key === AUTH_STORAGE_KEYS.migration && event.newValue !== '1') return;
            removeStorageValue('sessionStorage', AUTH_STORAGE_KEYS.legacySession);
            if (key === AUTH_STORAGE_KEYS.migration || (key === AUTH_STORAGE_KEYS.canonical && event.newValue === null)) {
                memorySealed = true;
            }
        }
    }

    const AUTH_STORAGE_API = {
        AUTH_STORAGE_KEYS,
        encodeAuthToken,
        decodeAuthToken,
        readAuthToken,
        writeAuthToken,
        migrateAuthToken,
        clearAuthToken,
        snapshotAuthToken,
        compareAndClearAuthToken,
        clearAuthTokenIfMatch,
        buildAuthHeaders,
        handleAuthStorageEvent,
    };

    const eventTarget = root && root.window && typeof root.window.addEventListener === 'function'
        ? root.window
        : root;
    if (eventTarget && typeof eventTarget.addEventListener === 'function') {
        eventTarget.addEventListener('storage', handleAuthStorageEvent);
    }
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = AUTH_STORAGE_API;
    }
    if (root) root.VideoTranscriptAuthStorage = AUTH_STORAGE_API;
})(typeof globalThis !== 'undefined' ? globalThis : this);
