import { describe, expect, it } from 'vitest'

import { parseJsonStringToJsonBuild } from '../useFieldExpressions'

describe('parseJsonStringToJsonBuild', () => {
  describe('basic inputs', () => {
    it('returns null for empty string', () => {
      expect(parseJsonStringToJsonBuild('')).toBeNull()
      expect(parseJsonStringToJsonBuild('   ')).toBeNull()
    })

    it('parses plain JSON without expressions', () => {
      expect(parseJsonStringToJsonBuild('{"key": "value"}')).toEqual({ key: 'value' })
      expect(parseJsonStringToJsonBuild('[1, 2, 3]')).toEqual([1, 2, 3])
      expect(parseJsonStringToJsonBuild('"hello"')).toBe('hello')
    })

    it('returns null for invalid JSON', () => {
      expect(parseJsonStringToJsonBuild('{bad json}')).toBeNull()
    })
  })

  describe('bare @{{...}} expressions (outside JSON strings)', () => {
    it('wraps bare ref expression in quotes so JSON.parse succeeds', () => {
      const result = parseJsonStringToJsonBuild('{"key": @{{abc12345-1234-1234-1234-123456789abc.output}}}')

      expect(result).not.toBeNull()
      expect(result).toHaveProperty('type', 'json_build')

      const node = result as { type: 'json_build'; template: any; refs: Record<string, any> }

      expect(node.template.key).toMatch(/__REF_\d+__/)

      const refKey = Object.keys(node.refs)[0]

      expect(node.refs[refKey]).toEqual({
        type: 'ref',
        instance: 'abc12345-1234-1234-1234-123456789abc',
        port: 'output',
      })
    })

    it('wraps bare var expression in quotes', () => {
      const result = parseJsonStringToJsonBuild('{"x": @{{myVar}}}')

      expect(result).not.toBeNull()

      const node = result as { type: 'json_build'; template: any; refs: Record<string, any> }
      const refKey = Object.keys(node.refs)[0]

      expect(node.refs[refKey]).toEqual({ type: 'var', name: 'myVar' })
    })
  })

  describe('inline @{{...}} expressions (inside JSON strings)', () => {
    it('keeps inline expression without extra quotes', () => {
      const result = parseJsonStringToJsonBuild('{"msg": "Hello @{{abc12345-1234-1234-1234-123456789abc.name}} world"}')

      expect(result).not.toBeNull()

      const node = result as { type: 'json_build'; template: any; refs: Record<string, any> }

      expect(node.template.msg).toContain('Hello ')
      expect(node.template.msg).toContain(' world')
    })
  })

  describe('ref with key extraction', () => {
    it('parses componentId.port::key syntax', () => {
      const result = parseJsonStringToJsonBuild('{"val": @{{abc12345-1234-1234-1234-123456789abc.output::myKey}}}')

      const node = result as { type: 'json_build'; template: any; refs: Record<string, any> }
      const refKey = Object.keys(node.refs)[0]

      expect(node.refs[refKey]).toEqual({
        type: 'ref',
        instance: 'abc12345-1234-1234-1234-123456789abc',
        port: 'output',
        key: 'myKey',
      })
    })
  })

  describe('backslash-escaped quote handling', () => {
    it('handles simple escaped quote (\\") inside a string — odd backslash count', () => {
      const input = '{"key": "say \\"hi\\" ok"}'
      const result = parseJsonStringToJsonBuild(input)

      expect(result).toEqual({ key: 'say "hi" ok' })
    })

    it('handles double backslash before quote (\\\\") — even count, quote is real', () => {
      // Raw chars: {"a":"b\\","c":"d"} — the \\ is an escaped backslash,
      // so the quote after it genuinely closes the string.
      const input = '{"a":"b\\\\","c":"d"}'
      const result = parseJsonStringToJsonBuild(input)

      expect(result).toEqual({ a: 'b\\', c: 'd' })
    })

    it('handles triple backslash before quote (\\\\\\"") — odd count, quote is escaped', () => {
      // Raw chars: {"a":"b\\\"c"} — scanner sees 3 backslashes before the
      // middle quote (odd), so it stays inside the string.
      const input = '{"a":"b\\\\\\"c"}'
      const result = parseJsonStringToJsonBuild(input)

      expect(result).not.toBeNull()
      expect(result).toEqual(JSON.parse(input))
    })

    it('bare expression after string with escaped trailing backslash', () => {
      // {"path":"C:\\\\", "ref": @{{myVar}}}
      // The value of "path" is C:\\ (ends with backslash), and ref is bare expression.
      const input = '{"path":"C:\\\\\\\\", "ref": @{{myVar}}}'
      const result = parseJsonStringToJsonBuild(input)

      expect(result).not.toBeNull()

      const node = result as { type: 'json_build'; template: any; refs: Record<string, any> }

      expect(node.template.path).toBe('C:\\\\')

      const refKey = Object.keys(node.refs)[0]

      expect(node.refs[refKey]).toEqual({ type: 'var', name: 'myVar' })
    })

    it('expression immediately after escaped quote stays inline', () => {
      const input = '{"msg": "say \\"@{{myVar}}\\" done"}'
      const result = parseJsonStringToJsonBuild(input)

      expect(result).not.toBeNull()

      const node = result as { type: 'json_build'; template: any; refs: Record<string, any> }

      expect(node.template.msg).toContain('say "')
      expect(node.template.msg).toContain('" done')
    })
  })

  describe('multiple expressions', () => {
    it('handles multiple bare expressions', () => {
      const result = parseJsonStringToJsonBuild('{"a": @{{varA}}, "b": @{{varB}}}')

      expect(result).not.toBeNull()

      const node = result as { type: 'json_build'; template: any; refs: Record<string, any> }

      expect(Object.keys(node.refs)).toHaveLength(2)
    })

    it('handles mix of bare and inline expressions', () => {
      const result = parseJsonStringToJsonBuild('{"bare": @{{varA}}, "inline": "prefix @{{varB}} suffix"}')

      expect(result).not.toBeNull()

      const node = result as { type: 'json_build'; template: any; refs: Record<string, any> }

      expect(Object.keys(node.refs)).toHaveLength(2)
      expect(node.template.inline).toContain('prefix ')
      expect(node.template.inline).toContain(' suffix')
    })
  })
})
