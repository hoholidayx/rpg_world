export const ASSISTANT_TEXT_TAG = {
  NARRATION: 'rp-narration',
  CHARACTER: 'rp-character',
} as const

export const ASSISTANT_TEXT_ATTR = {
  CHARACTER_NAME: 'name',
} as const

export const ASSISTANT_TEXT_SEGMENT_KIND = {
  NARRATION: 'narration',
  CHARACTER: 'character',
  RAW: 'raw',
} as const

export type AssistantTextSegmentKind =
  (typeof ASSISTANT_TEXT_SEGMENT_KIND)[keyof typeof ASSISTANT_TEXT_SEGMENT_KIND]

export type AssistantTextSegment = {
  kind: AssistantTextSegmentKind
  text: string
  speakerName?: string
}

export type AssistantTextParseResult = {
  segments: AssistantTextSegment[]
  structured: boolean
}

type OpeningTag = {
  kind: Exclude<AssistantTextSegmentKind, typeof ASSISTANT_TEXT_SEGMENT_KIND.RAW>
  openEnd: number
  tagName: string
  speakerName?: string
}

type ClosingTag = {
  start: number
  end: number
}

const DEFAULT_CHARACTER_NAME = '角色'
const TAG_NAMES = [ASSISTANT_TEXT_TAG.NARRATION, ASSISTANT_TEXT_TAG.CHARACTER] as const

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function tagBoundary(tagName: string) {
  return `${escapeRegExp(tagName)}(?=[\\s>/]|$)`
}

function looseClosingTagBoundary(tagName: string) {
  return `${escapeRegExp(tagName)}(?=[\\s>]|$|[^A-Za-z0-9_-])`
}

function openingTagRe(tagName: string) {
  return new RegExp(`^<\\s*${tagBoundary(tagName)}([^<>]*)>`)
}

function incompleteOpeningTagRe(tagName: string) {
  return new RegExp(`^<\\s*${tagBoundary(tagName)}\\s*`)
}

const PROTOCOL_OPEN_RE = new RegExp(`<\\s*(?:${TAG_NAMES.map(tagBoundary).join('|')})`, 'g')
const ATTRIBUTE_NAME_RE = new RegExp(
  `(?:^|\\s)${escapeRegExp(ASSISTANT_TEXT_ATTR.CHARACTER_NAME)}\\s*=\\s*(?:"([^"]*)"|'([^']*)'|([^\\s"'>]+))`,
)

function findNextProtocolTag(content: string, start: number) {
  PROTOCOL_OPEN_RE.lastIndex = start
  return PROTOCOL_OPEN_RE.exec(content)?.index ?? -1
}

function parseCharacterName(attrs: string) {
  const match = attrs.match(ATTRIBUTE_NAME_RE)
  return (match?.[1] ?? match?.[2] ?? match?.[3] ?? '').trim()
}

function skipWhitespace(content: string, start: number) {
  let index = start
  while (index < content.length && /\s/.test(content[index] ?? '')) index += 1
  return index
}

function parseCompleteOpeningTag(content: string, start: number, tagName: string) {
  const match = content.slice(start).match(openingTagRe(tagName))
  if (!match) return null
  return {
    attrs: match[1] ?? '',
    openEnd: start + match[0].length,
  }
}

function parseIncompleteOpeningTag(content: string, start: number, tagName: string) {
  const match = content.slice(start).match(incompleteOpeningTagRe(tagName))
  if (!match) return null
  const tagEnd = start + match[0].length
  if (tagName === ASSISTANT_TEXT_TAG.CHARACTER) {
    const rest = content.slice(tagEnd)
    const attrMatch = rest.match(ATTRIBUTE_NAME_RE)
    if (attrMatch && attrMatch.index !== undefined) {
      const attrEnd = tagEnd + attrMatch.index + attrMatch[0].length
      return {
        attrs: rest.slice(0, attrMatch.index + attrMatch[0].length),
        openEnd: skipWhitespace(content, attrEnd),
      }
    }
  }
  return {
    attrs: '',
    openEnd: tagEnd,
  }
}

function findClosingTag(content: string, tagName: string, start: number): ClosingTag | null {
  const closeRe = new RegExp(`</\\s*${looseClosingTagBoundary(tagName)}\\s*>?`, 'g')
  closeRe.lastIndex = start
  const match = closeRe.exec(content)
  if (!match) return null
  return {
    start: match.index,
    end: match.index + match[0].length,
  }
}

function parseOpeningTag(content: string, start: number): OpeningTag | null {
  const narration =
    parseCompleteOpeningTag(content, start, ASSISTANT_TEXT_TAG.NARRATION) ??
    parseIncompleteOpeningTag(content, start, ASSISTANT_TEXT_TAG.NARRATION)
  if (narration) {
    return {
      kind: ASSISTANT_TEXT_SEGMENT_KIND.NARRATION,
      openEnd: narration.openEnd,
      tagName: ASSISTANT_TEXT_TAG.NARRATION,
    }
  }

  const character =
    parseCompleteOpeningTag(content, start, ASSISTANT_TEXT_TAG.CHARACTER) ??
    parseIncompleteOpeningTag(content, start, ASSISTANT_TEXT_TAG.CHARACTER)
  if (!character) return null

  const speakerName = parseCharacterName(character.attrs) || DEFAULT_CHARACTER_NAME
  return {
    kind: ASSISTANT_TEXT_SEGMENT_KIND.CHARACTER,
    openEnd: skipWhitespace(content, character.openEnd),
    tagName: ASSISTANT_TEXT_TAG.CHARACTER,
    speakerName,
  }
}

function appendSegment(segments: AssistantTextSegment[], segment: AssistantTextSegment) {
  if (!segment.text) return
  const last = segments.at(-1)
  if (last?.kind === ASSISTANT_TEXT_SEGMENT_KIND.RAW && segment.kind === ASSISTANT_TEXT_SEGMENT_KIND.RAW) {
    last.text += segment.text
    return
  }
  segments.push(segment)
}

export function parseAssistantTextSegments(content: string): AssistantTextParseResult {
  const segments: AssistantTextSegment[] = []
  let index = 0
  let structured = false

  while (index < content.length) {
    const nextTag = findNextProtocolTag(content, index)
    if (nextTag < 0) {
      appendSegment(segments, { kind: ASSISTANT_TEXT_SEGMENT_KIND.RAW, text: content.slice(index) })
      break
    }

    if (nextTag > index) {
      appendSegment(segments, {
        kind: ASSISTANT_TEXT_SEGMENT_KIND.RAW,
        text: content.slice(index, nextTag),
      })
      index = nextTag
      continue
    }

    const opening = parseOpeningTag(content, index)
    if (!opening) {
      const afterMalformed = findNextProtocolTag(content, index + 1)
      const rawEnd = afterMalformed < 0 ? content.length : afterMalformed
      appendSegment(segments, {
        kind: ASSISTANT_TEXT_SEGMENT_KIND.RAW,
        text: content.slice(index, rawEnd),
      })
      index = rawEnd
      continue
    }

    const closing = findClosingTag(content, opening.tagName, opening.openEnd)
    if (!closing) {
      appendSegment(segments, {
        kind: ASSISTANT_TEXT_SEGMENT_KIND.RAW,
        text: content.slice(index),
      })
      break
    }

    const nestedTag = findNextProtocolTag(content, opening.openEnd)
    if (nestedTag >= 0 && nestedTag < closing.start) {
      appendSegment(segments, {
        kind: ASSISTANT_TEXT_SEGMENT_KIND.RAW,
        text: content.slice(index, closing.end),
      })
      index = closing.end
      continue
    }

    appendSegment(segments, {
      kind: opening.kind,
      text: content.slice(opening.openEnd, closing.start),
      speakerName: opening.speakerName,
    })
    structured = true
    index = closing.end
  }

  return { segments, structured }
}
