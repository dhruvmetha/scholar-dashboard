/* Strict public/private configuration. Importing this script performs no I/O. */
(function (global) {
  'use strict';

  class ConfigError extends Error {
    constructor(message) { super(message); this.name = 'ConfigError'; }
  }
  const fail = message => { throw new ConfigError(message); };
  const full = (pattern, value) => {
    if (typeof value !== 'string') return false;
    const match = pattern.exec(value);
    return !!match && match[0].length === value.length;
  };
  // Python str.isspace(), including U+0085 and excluding U+FEFF.
  const whitespace = /[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]/;
  const unsafeURL = /[\u0000-\u0020\u007f\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\\<>"'`?#]/;

  function exactKeys(raw, keys, label) {
    if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) fail(label + ' must be an object');
    const actual = Object.keys(raw);
    if (actual.length !== keys.length || keys.some(key => !Object.prototype.hasOwnProperty.call(raw, key))) fail(label + ' has wrong fields');
    return raw;
  }
  function repo(value) {
    if (typeof value !== 'string') fail('data_repo must be a string');
    const parts = value.split('/');
    if (parts.length !== 2 || !full(/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/, parts[0]) ||
        !full(/^(?!\.{1,2}$)[A-Za-z0-9._-]{1,100}$/, parts[1]) || parts[1].toLowerCase().endsWith('.git')) fail('data_repo must be owner/repo');
    return value;
  }
  function branch(value) {
    if (!full(/^[A-Za-z0-9][A-Za-z0-9._-]*$/, value) || value.includes('..') || value.endsWith('.lock') || value.endsWith('.')) fail('branch must be one safe ref component');
    return value;
  }

  function ipv6(value, label) {
    const scoped = value.split('%');
    if (scoped.length > 2 || (scoped.length === 2 && !scoped[1])) fail(label + ' must have a valid HTTPS host');
    let address = scoped[0];
    // IPv4 is allowed only at the end, with Python's strict decimal spelling.
    if (address.includes('.')) {
      const split = address.lastIndexOf(':');
      const parts = address.slice(split + 1).split('.');
      if (split < 0 || parts.length !== 4 || parts.some(part => !/^(?:0|[1-9][0-9]{0,2})$/.test(part) || Number(part) > 255)) fail(label + ' must have a valid HTTPS host');
      address = address.slice(0, split + 1) + ((Number(parts[0]) << 8) + Number(parts[1])).toString(16) + ':' + ((Number(parts[2]) << 8) + Number(parts[3])).toString(16);
    }
    const halves = address.split('::');
    if (halves.length > 2) fail(label + ' must have a valid HTTPS host');
    const groups = text => text ? text.split(':') : [];
    const left = groups(halves[0]), right = halves.length === 2 ? groups(halves[1]) : [];
    const count = left.length + right.length;
    if ((halves.length === 1 && count !== 8) || (halves.length === 2 && count >= 8) ||
        left.concat(right).some(part => !/^[0-9a-f]{1,4}$/.test(part))) fail(label + ' must have a valid HTTPS host');
    const words = left.map(part => parseInt(part, 16)).concat(Array(8 - count).fill(0), right.map(part => parseInt(part, 16)));
    let result;
    // Python 3.13 renders IPv4-mapped addresses with a dotted suffix, even
    // when the input used hex. Other dotted IPv6 inputs compress to hex.
    if (words.slice(0, 5).every(word => word === 0) && words[5] === 0xffff) {
      result = '::ffff:' + [words[6] >> 8, words[6] & 255, words[7] >> 8, words[7] & 255].join('.');
    } else {
      let start = -1, size = 1;
      for (let i = 0; i < words.length;) {
        if (words[i] !== 0) { i++; continue; }
        let end = i + 1;
        while (end < words.length && words[end] === 0) end++;
        if (end - i > size) { start = i; size = end - i; }
        i = end;
      }
      const hex = words.map(word => word.toString(16));
      result = start < 0 ? hex.join(':') : hex.slice(0, start).join(':') + '::' + hex.slice(start + size).join(':');
    }
    return result + (scoped.length === 2 ? '%' + scoped[1] : '');
  }

  function canonicalHTTPS(value, label, options = {}) {
    if (typeof value !== 'string' || !value) fail(label + ' must be a non-empty HTTPS URL');
    if (unsafeURL.test(value)) fail(label + ' must be a safe HTTPS URL');
    const parsed = /^(https):\/\/([^/]*)(.*)$/i.exec(value);
    if (!parsed || !parsed[2] || parsed[2].includes('@')) fail(label + ' must be a safe HTTPS URL');
    const authority = parsed[2], pathname = parsed[3];
    // urllib rejects Unicode characters whose NFKC form introduces a URL
    // delimiter. Check before treating a scope ID as part of an IPv6 host.
    const withoutDelimiters = authority.replace(/[@:#?]/g, '');
    const folded = withoutDelimiters.normalize('NFKC');
    if (folded !== withoutDelimiters && /[/?#@:]/.test(folded)) fail(label + ' must be a valid HTTPS URL');
    let host, portText = '';
    if (authority.startsWith('[')) {
      const match = /^\[([^\]]+)\](?::([^:]*))?$/.exec(authority);
      if (!match) fail(label + ' must be a valid HTTPS URL');
      host = match[1].toLowerCase();
      portText = match[2] || '';
      // urllib's bracket grammar also accepts IPvFuture spellings. Only a
      // spelling that then satisfies the existing host contract can pass.
      if (!/^v[0-9a-fA-F]+\..+$/.test(match[1])) {
        host = '[' + ipv6(host, label) + ']';
      } else if (host.includes(':')) {
        fail(label + ' must have a valid HTTPS host');
      }
    } else {
      const match = /^([^:\[\]]+)(?::([^:]*))?$/.exec(authority);
      if (!match) fail(label + ' must be a valid HTTPS URL');
      host = match[1].toLowerCase();
      portText = match[2] || '';
    }
    if (!host.startsWith('[') && (host.length > 253 || host.split('.').some(part => !/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(part)))) fail(label + ' must have a valid HTTPS host');
    if (!/^[0-9]*$/.test(portText)) fail(label + ' must be a valid HTTPS URL');
    const port = portText ? Number(portText) : null;
    if (port !== null && (!Number.isInteger(port) || port < 1 || port > 65535)) fail(label + ' must have a valid HTTPS port');
    const normalizedAuthority = host + (port === null || port === 443 ? '' : ':' + port);
    if (options.origin) {
      if (pathname !== '' && pathname !== '/') fail(label + ' must be an HTTPS origin');
      return 'https://' + normalizedAuthority;
    }
    if (options.rootPath && (!pathname.startsWith('/') || !pathname.endsWith('/') || pathname.includes('//') || pathname.includes('%') || pathname.split('/').some(part => part === '.' || part === '..'))) fail(label + ' must have a normalized root path');
    return 'https://' + normalizedAuthority + pathname;
  }

  function validateInstance(raw) {
    exactKeys(raw, ['schema', 'data_repo', 'branch', 'site', 'public_read', 'auth', 'share_pages', 'bridge_origins'], 'instance');
    // JSON.parse intentionally accepts lexical 1.0/1e0 as schema 1. The
    // shared raw-text corpus names this one exception to Python parity.
    if (typeof raw.schema !== 'number' || !Number.isInteger(raw.schema) || ![1, 2].includes(raw.schema)) fail('instance schema must be 1 or 2');
    if (raw.auth !== 'pat' || typeof raw.share_pages !== 'boolean' ||
        (raw.schema === 1 ? raw.public_read !== true : raw.public_read !== false || raw.share_pages !== false)) fail('instance public_read, auth, or share_pages is invalid');
    const site = canonicalHTTPS(raw.site, 'site', { rootPath: true });
    if (!Array.isArray(raw.bridge_origins) || !raw.bridge_origins.length) fail('bridge_origins must be a non-empty list');
    const origins = raw.bridge_origins.map(value => canonicalHTTPS(value, 'bridge_origins', { origin: true }));
    if (new Set(origins).size !== origins.length) fail('bridge_origins must not contain duplicates');
    const siteOrigin = site.slice(0, site.indexOf('/', 'https://'.length));
    if (!origins.includes(siteOrigin)) fail('bridge_origins must contain the site origin');
    return { schema: raw.schema, data_repo: repo(raw.data_repo), branch: branch(raw.branch), site, public_read: raw.public_read, auth: 'pat', share_pages: raw.share_pages, bridge_origins: origins };
  }
  function isPrivate(instance) { return instance.schema === 2; }
  function venuePattern(pattern, flags) {
    if (typeof pattern !== 'string' || typeof flags !== 'string') fail('venue pattern and flags must be strings');
    if (!pattern || Array.from(pattern).length > 200 || (flags !== '' && flags !== 'i')) fail('venue pattern or flags is invalid');
    if (pattern.split('|').some(alt => !alt || !/[A-Za-z0-9]|\\\./.test(alt.replace(/\\b/g, '')))) fail('each venue pattern alternative needs a literal');
    for (let i = 0; i < pattern.length; i++) {
      const char = pattern[i];
      if (char === '\\') {
        if (pattern[i + 1] !== 'b' && pattern[i + 1] !== '.') fail('venue pattern uses unsupported syntax');
        i++;
      } else if (!/^[A-Za-z0-9 :, &'\/^$|-]$/.test(char)) fail('venue pattern uses unsupported syntax');
    }
    try { new RegExp(pattern, flags); } catch (error) { fail('venue pattern is invalid'); }
  }
  function validateScholar(raw) {
    exactKeys(raw, ['schema', 'owner', 'focus', 'group_aliases', 'venues'], 'scholar config');
    if (typeof raw.schema !== 'number' || raw.schema !== 1) fail('scholar config schema must be 1');
    const owner = exactKeys(raw.owner, ['name', 'homepage'], 'owner');
    if (typeof owner.name !== 'string' || !Array.from(owner.name).some(char => !whitespace.test(char))) fail('owner name must be non-empty');
    if (typeof raw.focus !== 'string' || !raw.focus || Array.from(raw.focus).length > 500 || /[\u0000-\u001f\u007f]/.test(raw.focus)) fail('focus must be one line of 1 to 500 characters');
    const aliases = raw.group_aliases;
    if (aliases === null || typeof aliases !== 'object' || Array.isArray(aliases)) fail('group_aliases must contain non-empty pipe-free strings');
    const normalizedAliases = Object.create(null);
    for (const [key, value] of Object.entries(aliases)) {
      if (!key || typeof value !== 'string' || !value || key.includes('|') || value.includes('|')) fail('group_aliases must contain non-empty pipe-free strings');
      if (Object.prototype.hasOwnProperty.call(aliases, value)) fail('group_aliases must not contain chains');
      normalizedAliases[key] = value;
    }
    if (!Array.isArray(raw.venues)) fail('venues must be a list');
    const venues = raw.venues.map(row => {
      if (!Array.isArray(row) || row.length !== 5 || row.some(value => typeof value !== 'string')) fail('each venue must be five strings');
      if (!row[0] || (row[2] !== 'conference' && row[2] !== 'journal')) fail('venue name or kind is invalid');
      venuePattern(row[3], row[4]);
      return row.slice();
    });
    return { schema: 1, owner: { name: owner.name, homepage: canonicalHTTPS(owner.homepage, 'owner homepage') }, focus: raw.focus, group_aliases: normalizedAliases, venues };
  }

  function resolveRoot(pathname) {
    if (typeof pathname !== 'string' || !pathname.startsWith('/') || /[?#]/.test(pathname)) fail('application pathname must be absolute');
    let directory = pathname.endsWith('/index.html') ? pathname.slice(0, -'index.html'.length) : pathname.slice(0, pathname.lastIndexOf('/') + 1);
    directory = directory.replace(/\/p\/[a-z0-9][a-z0-9-]*\/$/, '/');
    return directory || '/';
  }
  function checkSite(location, root, instance) {
    const hostname = String(location.hostname || '').toLowerCase();
    if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname.endsWith('.localhost')) return;
    const checked = validateInstance(instance);
    let expected;
    try {
      // Raw config validation precedes this conversion. The browser pathname
      // encodes Unicode; comparing it to the unencoded schema value fails.
      const site = new URL(checked.site);
      expected = site.origin + site.pathname;
    } catch (error) { fail('configured site cannot be used by this browser'); }
    if (location.origin + root !== expected) fail('This page does not match the configured site.');
  }

  async function load({ fetch: fetcher, origin, root, timeoutMs = 8000 }) {
    if (typeof fetcher !== 'function' || typeof origin !== 'string' || typeof root !== 'string' || !root.startsWith('/') || !root.endsWith('/') || !Number.isFinite(timeoutMs) || timeoutMs <= 0) fail('invalid configuration loader options');
    const limit = 262144, controller = new AbortController(), readers = new Set();
    const cancel = reader => {
      try { Promise.resolve(reader.cancel()).catch(() => {}); } catch (error) {}
      try { reader.releaseLock(); } catch (error) {}
    };
    const stop = () => { controller.abort(); for (const reader of readers) cancel(reader); };
    let timer;
    const timeout = new Promise((resolve, reject) => {
      timer = setTimeout(() => reject(new ConfigError('configuration request timed out')), timeoutMs);
    });
    async function read(filename, validator) {
      let reader;
      try {
        const response = await fetcher(origin + root + filename, { cache: 'no-store', redirect: 'error', credentials: 'same-origin', signal: controller.signal });
        if (!response || response.status !== 200 || response.redirected || controller.signal.aborted) {
          if (response && response.body) { try { Promise.resolve(response.body.cancel()).catch(() => {}); } catch (error) {} }
          fail('cannot load ' + filename);
        }
        if (!response.body || typeof response.body.getReader !== 'function') fail('cannot read ' + filename);
        reader = response.body.getReader(); readers.add(reader);
        const chunks = []; let size = 0;
        while (true) {
          const chunk = await reader.read();
          if (controller.signal.aborted) fail('configuration request aborted');
          if (chunk.done) break;
          if (!(chunk.value instanceof Uint8Array)) fail('cannot read ' + filename);
          size += chunk.value.byteLength;
          if (size > limit) fail(filename + ' exceeds 262144 bytes');
          chunks.push(chunk.value);
        }
        const bytes = new Uint8Array(size); let offset = 0;
        for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
        const text = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes);
        return validator(JSON.parse(text));
      } catch (error) {
        if (reader) cancel(reader);
        if (error instanceof ConfigError) throw error;
        throw new ConfigError('cannot read ' + filename);
      } finally {
        if (reader) { readers.delete(reader); try { reader.releaseLock(); } catch (error) {} }
      }
    }
    try {
      const pair = await Promise.race([Promise.all([read('instance.json', validateInstance), read('scholar.config.json', validateScholar)]), timeout]);
      return { instance: pair[0], scholar: pair[1] };
    } catch (error) { stop(); throw error; }
    finally { clearTimeout(timer); }
  }

  const api = { ConfigError, resolveRoot, validateInstance, validateScholar, isPrivate, load, checkSite };
  global.ScholarConfig = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(globalThis);
