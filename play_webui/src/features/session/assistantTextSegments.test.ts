import { describe, expect, it } from 'vitest'
import {
  ASSISTANT_TEXT_SEGMENT_KIND,
  parseAssistantTextSegments,
} from './assistantTextSegments'

describe('parseAssistantTextSegments fallback compatibility', () => {
  it.each([
    '没有任何标签的原始正文',
    '<rp-narration>没有闭合的叙事正文',
    '<rp-character name="言琴">没有闭合的角色正文',
    '<rp-character name="言琴" 没有结束尖括号',
  ])('preserves malformed or unstructured content verbatim: %j', (content) => {
    const result = parseAssistantTextSegments(content)

    expect(result.structured).toBe(false)
    expect(result.segments).toEqual([
      {
        kind: ASSISTANT_TEXT_SEGMENT_KIND.RAW,
        text: content,
      },
    ])
    expect(result.segments.map((segment) => segment.text).join('')).toBe(content)
  })

  it('keeps visible text in order when raw and structured segments are mixed', () => {
    const result = parseAssistantTextSegments(
      '前置原文<rp-narration>雨还没有停。</rp-narration>后置原文',
    )

    expect(result.structured).toBe(true)
    expect(result.segments).toEqual([
      {
        kind: ASSISTANT_TEXT_SEGMENT_KIND.RAW,
        text: '前置原文',
      },
      {
        kind: ASSISTANT_TEXT_SEGMENT_KIND.NARRATION,
        text: '雨还没有停。',
        speakerName: undefined,
      },
      {
        kind: ASSISTANT_TEXT_SEGMENT_KIND.RAW,
        text: '后置原文',
      },
    ])
    expect(result.segments.map((segment) => segment.text).join('')).toBe(
      '前置原文雨还没有停。后置原文',
    )
  })

  it('preserves a malformed tail after a valid structured segment', () => {
    const malformedTail = '<rp-character name="言琴">别回头'
    const result = parseAssistantTextSegments(
      `<rp-narration>脚步声逼近。</rp-narration>${malformedTail}`,
    )

    expect(result.structured).toBe(true)
    expect(result.segments.at(-1)).toEqual({
      kind: ASSISTANT_TEXT_SEGMENT_KIND.RAW,
      text: malformedTail,
    })
  })
})
