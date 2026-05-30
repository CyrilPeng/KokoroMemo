import { describe, it, expect } from 'vitest'
import { friendlyError } from './api'

describe('friendlyError', () => {
  it('returns network error message for Failed to fetch', () => {
    expect(friendlyError('Failed to fetch')).toContain('后端服务')
  })

  it('returns timeout message for timeout errors', () => {
    expect(friendlyError('request timed out')).toContain('超时')
  })

  it('returns API key message for 401 unauthorized', () => {
    expect(friendlyError('HTTP 401: Invalid API key')).toContain('API Key')
  })

  it('returns rate limit message for 429', () => {
    expect(friendlyError('HTTP 429: too many requests')).toContain('限流')
  })

  it('returns server error message for 500', () => {
    expect(friendlyError('HTTP 500: internal server error')).toContain('内部错误')
  })

  it('returns upstream message for 502/503/504', () => {
    const r = friendlyError('HTTP 502: bad gateway')
    expect(r).toContain('上游')
  })

  it('returns context length message for token limit', () => {
    expect(friendlyError('context length exceeded')).toContain('过长')
  })

  it('returns model not found message', () => {
    expect(friendlyError('invalid model')).toContain('模型')
  })

  it('returns dimension mismatch message', () => {
    expect(friendlyError('dimension mismatch in embedding')).toContain('维度')
  })

  it('returns disk full message', () => {
    expect(friendlyError('no space left on device')).toContain('磁盘')
  })

  it('returns db locked message', () => {
    expect(friendlyError('database locked')).toContain('锁定')
  })

  it('falls back to truncated raw message', () => {
    const longError = 'some random error ' + 'x'.repeat(200)
    const result = friendlyError(longError)
    expect(result.length).toBeLessThanOrEqual(125) // 120 + '...'
  })

  it('returns generic error for empty string', () => {
    expect(friendlyError('')).toBe('未知错误')
  })

  it('handles short unknown errors gracefully', () => {
    const result = friendlyError('short unknown error')
    expect(result).toBe('short unknown error')
  })
})
