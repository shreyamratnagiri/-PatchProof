import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, client } from './client';

const mockResponse = (payload: unknown, status = 200): Response =>
  ({ ok: status >= 200 && status < 300, status, text: async () => JSON.stringify(payload) } as Response);

afterEach(() => vi.unstubAllGlobals());

describe('typed API client', () => {
  it('retains HTTP status for explicit API errors', () => {
    expect(new ApiError(401, 'unauthorized').status).toBe(401);
  });

  it('attaches the configured key and handles pagination response', async () => {
    const request = vi.fn().mockResolvedValue(mockResponse({ items: [] }));
    vi.stubGlobal('fetch', request);
    const result = await client('testing-key').repos();
    expect(result.items).toEqual([]);
    expect(request).toHaveBeenCalledWith('/api/repositories', expect.objectContaining({
      headers: expect.objectContaining({ 'X-PatchProof-Key': 'testing-key' }),
    }));
  });

  it('imports ZIP files as multipart without forcing an invalid JSON content type', async () => {
    const request = vi.fn().mockResolvedValue(mockResponse({ id: 'repo-id' }, 201));
    vi.stubGlobal('fetch', request);
    const file = new File(['ZIP'], 'fixture.zip', { type: 'application/zip' });
    await client('key').import(file);
    const init = request.mock.calls[0]?.[1] as RequestInit | undefined;
    expect(init?.body).toBeInstanceOf(FormData);
    expect((init?.headers as Record<string, string>)['Content-Type']).toBeUndefined();
  });

  it('preserves failed verification and authorization errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(mockResponse({ detail: 'not authorized' }, 403)));
    await expect(client('bad-key').verify('run', 'candidate'))
      .rejects.toMatchObject({ status: 403, message: 'not authorized' });
  });

  it('fails explicitly on malformed server errors rather than inventing success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, status: 502, text: async () => 'gateway unavailable',
    }));
    await expect(client('key').modelHealth()).rejects.toMatchObject({ status: 502 });
  });
});
