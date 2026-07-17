(() => {
  'use strict'

  const INITIAL_RELATIONSHIPS = Object.freeze({
    xiacheng: Object.freeze({
      fields: Object.freeze({ trust: 64, intimacy: 58, dependence: 42 }),
      phase: '默契期',
      description: '相处自然，已经能读懂彼此话里的停顿。',
      lastChange: '夏澄开始主动分享重要决定',
    }),
    sufu: Object.freeze({
      fields: Object.freeze({ trust: 48, curiosity: 76, vigilance: 31 }),
      phase: '试探期',
      description: '彼此保留着好奇，最近的花束似乎另有用意。',
      lastChange: '友善，但双方仍在观察彼此边界',
    }),
    linyu: Object.freeze({
      fields: Object.freeze({ trust: 71, familiarity: 84, distance: 23 }),
      phase: '旧友',
      description: '多年默契仍在，但明日的约定可能改变相处方式。',
      lastChange: '林羽尚未说明这次邀约的真正目的',
    }),
  })
  const RELATIONSHIP_FIELD_LABELS = Object.freeze({
    trust: '信任',
    intimacy: '亲密',
    dependence: '依赖',
  })
  const INITIAL_TURN = 18
  const TYPE_INTERVAL_MS = 24
  const AUTO_ADVANCE_MS = 2200
  const DIALOGUE_PAGE_TARGET = 32
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

  const initialSequence = [
    {
      speaker: '旁白',
      role: 'Rainy afternoon',
      character: 'narrator',
      kind: 'narration',
      text: '雨声刚刚停下。玻璃窗上的水珠把街灯揉成一片温柔的金色，靠窗第三桌依旧空着一把椅子。',
    },
    {
      speaker: '夏澄',
      role: '白鸢咖啡馆店长',
      character: 'xiacheng',
      kind: 'dialogue',
      text: '你还是来了。我本来还在想，只写一句“老位置见”，会不会显得太任性。',
    },
    {
      speaker: '言沁',
      role: '由你扮演',
      character: 'yanqin',
      kind: 'dialogue',
      text: '因为是你发来的消息，我才不会装作没看见。况且，雨后的这里一直很好看。',
    },
    {
      speaker: '夏澄',
      role: '白鸢咖啡馆店长',
      character: 'xiacheng',
      kind: 'dialogue',
      choicesAfter: true,
      text: '夏澄笑了一下，却把身后的纸袋藏得更严实了些。“最后一份莓果塔给你留着。不过在那之前，我有件事想听听你的答案。”',
    },
  ]

  const choices = [
    {
      id: 'listen',
      title: '先坐到她对面，认真听她说',
      meta: '温柔回应 · 多项关系状态变化',
      relationshipChange: {
        fields: { trust: 4, intimacy: 2, dependence: 2 },
        phase: '信赖加深',
        description: '信任正在变得明确，重要的决定已经愿意交给彼此。',
        lastChange: '夏澄主动提出交付白鸢咖啡馆的备用钥匙',
      },
      toast: '夏澄明显放松了下来 · 关系状态已同步',
      userLine: '我把伞靠在桌边，在她对面坐下。“好啊。你慢慢说，我今天没有别的安排。”',
      response: '“那我就不绕弯了。”夏澄在你面前放下那只纸袋，声音轻得几乎被窗外的车声盖过去，“我想把白鸢的备用钥匙交给你。”',
      epilogue: '纸袋里不是礼物，而是一把系着浅粉丝带的黄铜钥匙。你忽然意识到，这场约定比一份甜点郑重得多。',
    },
    {
      id: 'observe',
      title: '先观察她藏在身后的纸袋',
      meta: '敏锐观察 · 发现新线索',
      relationshipChange: {
        fields: { trust: 2, intimacy: 1 },
        phase: '默契期',
        description: '你读懂了她藏东西时的犹豫，她也不再继续掩饰。',
        lastChange: '言沁察觉纸袋线索，夏澄坦率说明钥匙的存在',
      },
      toast: '发现线索「粉色钥匙扣」· 关系描述已更新',
      clue: {
        title: '粉色钥匙扣',
        detail: '纸袋边缘露出一枚白鸢形状的旧钥匙扣。',
      },
      userLine: '我没有立刻接话，视线落在她身后的纸袋上。“你今天藏东西的技术，好像没有平时那么好。”',
      response: '夏澄顺着你的目光低头，忍不住笑出声。“被你发现了。不是惊喜，是一把我考虑了很久才决定交出去的钥匙。”',
      epilogue: '她把纸袋推向桌子中央。白鸢形状的钥匙扣轻轻晃动，像替主人做了最后一次犹豫。',
    },
    {
      id: 'dessert',
      title: '笑着说：“先让我尝一口莓果塔”',
      meta: '轻松打趣 · 氛围变得柔软',
      relationshipChange: {
        fields: { trust: 1, intimacy: 3 },
        phase: '轻松相伴',
        description: '紧张被熟悉的玩笑化开，彼此又回到自然亲近的节奏。',
        lastChange: '夏澄重新露出平日的笑意，并愿意稍后坦白',
      },
      toast: '紧张的气氛被你化开了 · 亲密与描述状态已更新',
      userLine: '我故意看向桌上的甜点。“重要的话也需要一点勇气。要不先让我尝一口莓果塔？”',
      response: '“你总有办法把气氛变轻松。”夏澄把叉子递给你，眼里终于有了平日的笑意，“那就吃完再说。反正钥匙不会跑掉。”',
      epilogue: '酸甜的莓果味在舌尖化开。窗外又落下几滴雨，却已经没有人急着离开。',
    },
  ]

  const initialTrace = [
    {
      speaker: '系统事件',
      kind: 'system',
      turn: 17,
      time: '17:39',
      badge: '上下文已同步',
      text: '已载入玩家角色、当前场景、3 组关系与 5 张运行中状态表。',
      detail: '玩家角色：言沁 · 场景：白鸢咖啡馆/临窗座 · 在场角色：言沁、夏澄',
    },
    {
      speaker: '玩家决策',
      kind: 'choice',
      turn: 17,
      time: '17:40',
      badge: '自由行动',
      text: '言沁收起伞，走向两个人第一次见面的靠窗第三桌。',
    },
    {
      speaker: '思考摘要',
      kind: 'thinking',
      turn: 17,
      time: '17:40',
      badge: '公开摘要',
      text: '本轮重点是重逢后的情绪变化；场景与夏澄的角色状态可能需要更新。',
      detail: '候选目标：当前场景状态表、夏澄·角色状态。未触发人物关系字段更新。',
    },
    {
      speaker: '工具记录',
      kind: 'tool',
      turn: 17,
      time: '17:40',
      badge: 'scene_attr',
      text: '更新当前场景「在场角色」与「氛围」。',
      detail: '在场角色 → 言沁、夏澄\n氛围 → 安静、温暖、略有期待',
    },
    {
      speaker: '剧情裁定',
      kind: 'outcome',
      turn: 17,
      time: '17:41',
      badge: '自然推进',
      text: '重逢顺利发生，没有触发随机分支；夏澄愿意继续这次谈话。',
    },
  ]

  const refs = {
    room: document.querySelector('#sessionRoom'),
    dialogueBox: document.querySelector('#dialogueBox'),
    dialogueText: document.querySelector('#dialogueText'),
    dialogueAnnouncement: document.querySelector('#dialogueAnnouncement'),
    speakerName: document.querySelector('#speakerName'),
    speakerRole: document.querySelector('#speakerRole'),
    advanceLabel: document.querySelector('[data-advance-label]'),
    choicePanel: document.querySelector('#choicePanel'),
    choiceList: document.querySelector('#choiceList'),
    composer: document.querySelector('#actionComposer'),
    composerTrigger: document.querySelector('[data-action="composer"]'),
    actionInput: document.querySelector('#actionInput'),
    storyLog: document.querySelector('#storyLog'),
    backdrop: document.querySelector('.drawer-backdrop'),
    toast: document.querySelector('#toast'),
    clueList: document.querySelector('#clueList'),
    relationshipNote: document.querySelector('#relationshipNote'),
    stageMenu: document.querySelector('#stageMenu'),
    menuTrigger: document.querySelector('[data-action="menu"]'),
    cinematicReturn: document.querySelector('[data-action="restore-cinematic"]'),
  }

  const state = {
    sequence: [],
    lineIndex: 0,
    pages: [],
    pageIndex: 0,
    typing: false,
    typingTimer: null,
    fullText: '',
    auto: false,
    autoTimer: null,
    generating: false,
    generationTimers: [],
    relationships: cloneRelationships(),
    turn: INITIAL_TURN,
    activeDrawer: null,
    drawerCloseTimer: null,
    lastFocus: null,
    toastTimer: null,
    soundOn: true,
    menuOpen: false,
    cinematic: false,
    cinematicReturnFocus: null,
  }

  function freshSequence() {
    return initialSequence.map((line) => ({ ...line, logged: false, resolved: false }))
  }

  function cloneRelationships() {
    return Object.fromEntries(Object.entries(INITIAL_RELATIONSHIPS).map(([id, relationship]) => [
      id,
      {
        ...relationship,
        fields: { ...relationship.fields },
      },
    ]))
  }

  function currentLine() {
    return state.sequence[state.lineIndex]
  }

  function paginateText(text) {
    if (text.length <= DIALOGUE_PAGE_TARGET) return [text]

    const clauses = text.match(/[^，。！？；…]+[，。！？；…]?/g) ?? [text]
    const pages = []
    let page = ''

    clauses.forEach((clause) => {
      if (
        page
        && page.length + clause.length > DIALOGUE_PAGE_TARGET
        && page.length >= Math.floor(DIALOGUE_PAGE_TARGET * 0.52)
      ) {
        pages.push(page.trim())
        page = ''
      }
      page += clause
    })

    if (page.trim()) pages.push(page.trim())
    return pages.length ? pages : [text]
  }

  function hasMoreDialoguePages() {
    return state.pageIndex < state.pages.length - 1
  }

  function continueReadingLabel() {
    return `继续阅读 · ${state.pageIndex + 1}/${state.pages.length}`
  }

  function clearTimer(key) {
    if (!state[key]) return
    window.clearTimeout(state[key])
    window.clearInterval(state[key])
    state[key] = null
  }

  function clearGenerationTimers() {
    state.generationTimers.forEach((timer) => window.clearTimeout(timer))
    state.generationTimers = []
  }

  function setActiveCharacter(character) {
    refs.room.dataset.activeSpeaker = character
    document.querySelectorAll('[data-character]').forEach((figure) => {
      figure.classList.toggle('is-active', figure.dataset.character === character)
    })
  }

  function updateAdvanceLabel(label) {
    refs.advanceLabel.textContent = label
  }

  function finishTyping() {
    clearTimer('typingTimer')
    refs.dialogueText.textContent = state.fullText
    refs.dialogueAnnouncement.textContent = state.fullText
    state.typing = false
    const line = currentLine()
    if (hasMoreDialoguePages()) {
      updateAdvanceLabel(continueReadingLabel())
      scheduleAutoAdvance()
      return
    }
    if (line?.choicesAfter && !line.resolved) {
      showChoices()
      return
    }
    updateAdvanceLabel(state.lineIndex >= state.sequence.length - 1 ? '等待你的行动' : '点击继续')
    scheduleAutoAdvance()
  }

  function typeText(text) {
    clearTimer('typingTimer')
    state.fullText = text
    refs.dialogueText.textContent = ''
    refs.dialogueAnnouncement.textContent = ''

    if (prefersReducedMotion || text.length < 4) {
      refs.dialogueText.textContent = text
      state.typing = false
      finishTyping()
      return
    }

    state.typing = true
    let cursor = 0
    state.typingTimer = window.setInterval(() => {
      cursor += 1
      refs.dialogueText.textContent = text.slice(0, cursor)
      if (cursor >= text.length) finishTyping()
    }, TYPE_INTERVAL_MS)
  }

  function lineMark(entry) {
    const marks = {
      choice: '选',
      narration: '叙',
      tool: '具',
      thinking: '思',
      outcome: '裁',
      system: '系',
    }
    return marks[entry.kind] ?? entry.speaker.slice(0, 1)
  }

  function appendLog(entry) {
    const item = document.createElement('li')
    item.className = 'story-log__item'
    item.dataset.kind = entry.kind
    item.dataset.turn = String(entry.turn ?? state.turn)

    const mark = document.createElement('span')
    mark.className = 'story-log__mark'
    mark.textContent = lineMark(entry)

    const content = document.createElement('div')
    content.className = 'story-log__content'

    const meta = document.createElement('div')
    meta.className = 'story-log__meta'
    const identity = document.createElement('span')
    identity.className = 'story-log__identity'
    const speaker = document.createElement('strong')
    speaker.textContent = entry.speaker
    identity.append(speaker)
    if (entry.badge) {
      const badge = document.createElement('i')
      badge.className = 'story-log__badge'
      badge.textContent = entry.badge
      identity.append(badge)
    }
    const turn = document.createElement('span')
    turn.textContent = `Turn ${entry.turn ?? state.turn} · ${entry.time ?? '17:42'}`
    meta.append(identity, turn)

    const text = document.createElement('p')
    text.textContent = entry.text
    content.append(meta, text)
    if (entry.detail) {
      const detail = document.createElement('div')
      detail.className = 'story-log__detail'
      detail.textContent = entry.detail
      content.append(detail)
    }
    item.append(mark, content)

    refs.storyLog.append(item)
  }

  function seedInitialTrace() {
    initialTrace.forEach((entry) => appendLog(entry))
  }

  function ensureLineLogged(line) {
    if (!line || line.logged) return
    appendLog({ speaker: line.speaker, text: line.text, kind: line.kind, turn: state.turn })
    line.logged = true
  }

  function renderLine({ instant = false } = {}) {
    clearTimer('autoTimer')
    hideChoices()
    const line = currentLine()
    if (!line) return

    state.pages = paginateText(line.text)
    state.pageIndex = 0

    refs.speakerName.textContent = line.speaker
    refs.speakerRole.textContent = line.role
    setActiveCharacter(line.character)
    ensureLineLogged(line)
    updateAdvanceLabel('点击完成')

    if (instant) {
      state.fullText = state.pages[0]
      refs.dialogueText.textContent = state.fullText
      refs.dialogueAnnouncement.textContent = state.fullText
      state.typing = false
      if (hasMoreDialoguePages()) updateAdvanceLabel(continueReadingLabel())
      else if (line.choicesAfter && !line.resolved) showChoices()
      else updateAdvanceLabel(state.lineIndex >= state.sequence.length - 1 ? '等待你的行动' : '点击继续')
      return
    }

    typeText(state.pages[0])
  }

  function advanceDialogue() {
    if (state.generating) {
      showToast('夏澄正在回应，请稍等片刻。')
      return
    }
    if (!refs.composer.hidden) return
    if (state.typing) {
      finishTyping()
      return
    }

    if (hasMoreDialoguePages()) {
      state.pageIndex += 1
      updateAdvanceLabel('点击完成')
      typeText(state.pages[state.pageIndex])
      return
    }

    const line = currentLine()
    if (line?.choicesAfter && !line.resolved) {
      showToast('选择一个回应，或使用“自由行动”。')
      showChoices()
      return
    }

    if (state.lineIndex >= state.sequence.length - 1) {
      showToast('当前演示已推进到最新位置。你可以自由行动、查看日志，或重置体验。')
      updateAdvanceLabel('等待你的行动')
      return
    }

    state.lineIndex += 1
    renderLine()
  }

  function buildChoiceButton(choice, index) {
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'choice-button'
    button.dataset.choiceId = choice.id

    const number = document.createElement('span')
    number.className = 'choice-button__number'
    number.textContent = String(index + 1).padStart(2, '0')

    const copy = document.createElement('span')
    copy.className = 'choice-button__copy'
    const title = document.createElement('strong')
    title.textContent = choice.title
    const meta = document.createElement('small')
    meta.textContent = choice.meta
    copy.append(title, meta)

    const arrow = document.createElement('span')
    arrow.className = 'choice-button__arrow'
    arrow.setAttribute('aria-hidden', 'true')
    arrow.textContent = '›'

    button.append(number, copy, arrow)
    button.addEventListener('click', () => selectChoice(choice))
    return button
  }

  function showChoices() {
    if (!refs.composer.hidden || state.generating) return
    refs.choiceList.replaceChildren(...choices.map(buildChoiceButton))
    refs.choicePanel.hidden = false
    updateAdvanceLabel('请选择行动')
    clearTimer('autoTimer')
  }

  function hideChoices() {
    refs.choicePanel.hidden = true
  }

  function updateRelationship(change = {}, relationshipId = 'xiacheng') {
    const relationship = state.relationships[relationshipId]
    if (!relationship) return null

    const before = {
      ...relationship,
      fields: { ...relationship.fields },
    }
    Object.entries(change.fields ?? {}).forEach(([field, delta]) => {
      const currentValue = relationship.fields[field]
      if (!Number.isFinite(currentValue) || !Number.isFinite(delta)) return
      relationship.fields[field] = Math.max(0, Math.min(100, currentValue + delta))
    })
    ;['phase', 'description', 'lastChange'].forEach((field) => {
      if (typeof change[field] === 'string' && change[field].trim()) {
        relationship[field] = change[field].trim()
      }
    })

    if (relationshipId === 'xiacheng') {
      Object.entries(relationship.fields).forEach(([field, value]) => {
        document.querySelectorAll(`[data-rel-field="${field}"]`).forEach((element) => {
          element.textContent = String(value)
        })
      })
      document.querySelectorAll('[data-rel-phase]').forEach((element) => {
        element.textContent = relationship.phase
      })
      document.querySelectorAll('[data-rel-description]').forEach((element) => {
        element.textContent = relationship.description
      })
      document.querySelectorAll('[data-rel-last-change]').forEach((element) => {
        element.textContent = relationship.lastChange
      })
    }

    return {
      before,
      after: {
        ...relationship,
        fields: { ...relationship.fields },
      },
    }
  }

  function describeRelationshipChange(result, change) {
    if (!result) return '关系状态未发生变化。'
    const fieldChanges = Object.keys(change.fields ?? {}).map((field) => {
      const label = RELATIONSHIP_FIELD_LABELS[field] ?? field
      return `${label} ${result.before.fields[field]} → ${result.after.fields[field]}`
    })
    if (result.before.phase !== result.after.phase) {
      fieldChanges.push(`阶段 ${result.before.phase} → ${result.after.phase}`)
    }
    if (result.before.description !== result.after.description) {
      fieldChanges.push('关系描述已更新')
    }
    return fieldChanges.join('；') || '关系状态保持不变。'
  }

  function updateTurn(delta = 0) {
    state.turn += delta
    document.querySelectorAll('[data-turn-value]').forEach((element) => {
      element.textContent = String(state.turn)
    })
  }

  function addClue(clue) {
    if (!clue || refs.clueList.querySelector('[data-dynamic-clue]')) return
    const item = document.createElement('li')
    item.dataset.dynamicClue = 'true'
    const number = document.createElement('span')
    number.textContent = '03'
    const text = document.createElement('p')
    const title = document.createElement('strong')
    title.textContent = clue.title
    text.append(title, document.createTextNode(clue.detail))
    item.append(number, text)
    refs.clueList.append(item)
    document.querySelectorAll('[data-clue-count]').forEach((element) => {
      element.textContent = '3 条'
    })
  }

  function selectChoice(choice) {
    if (state.generating) return
    const line = currentLine()
    if (!line || line.resolved) return

    line.resolved = true
    hideChoices()
    updateTurn(1)
    const relationshipResult = updateRelationship(choice.relationshipChange)
    addClue(choice.clue)
    appendLog({
      speaker: '玩家决策',
      text: choice.title,
      kind: 'choice',
      badge: '预设行动',
      turn: state.turn,
    })
    appendLog({
      speaker: '思考摘要',
      text: '本次回应会直接影响夏澄的情绪与当前关系，优先同步关系状态后继续叙事。',
      kind: 'thinking',
      badge: '公开摘要',
      detail: '状态目标：人物关系状态表 / 夏澄。其余两组关系保持不变。',
      turn: state.turn,
    })
    appendLog({
      speaker: '工具记录',
      text: '夏澄的人物关系状态表完成多字段同步。',
      kind: 'tool',
      badge: 'status_table_set_values',
      detail: `人物关系状态表 · 夏澄：${describeRelationshipChange(relationshipResult, choice.relationshipChange)}`,
      turn: state.turn,
    })
    appendLog({
      speaker: '剧情裁定',
      text: choice.toast,
      kind: 'outcome',
      badge: '分支结果',
      turn: state.turn,
    })

    const branchLines = [
      {
        speaker: '言沁',
        role: '由你扮演',
        character: 'yanqin',
        kind: 'dialogue',
        text: choice.userLine,
      },
      {
        speaker: '夏澄',
        role: '白鸢咖啡馆店长',
        character: 'xiacheng',
        kind: 'dialogue',
        text: choice.response,
      },
      {
        speaker: '旁白',
        role: 'Scene narration',
        character: 'narrator',
        kind: 'narration',
        text: choice.epilogue,
      },
    ].map((entry) => ({ ...entry, logged: false, resolved: false }))

    state.sequence.splice(state.lineIndex + 1, 0, ...branchLines)
    showToast(choice.toast)
    state.lineIndex += 1
    renderLine()
  }

  function scheduleAutoAdvance() {
    clearTimer('autoTimer')
    if (!state.auto || state.generating || state.activeDrawer || state.menuOpen || state.cinematic || !refs.composer.hidden) return
    const line = currentLine()
    if (!line || (!hasMoreDialoguePages() && line.choicesAfter && !line.resolved)) return
    if (!hasMoreDialoguePages() && state.lineIndex >= state.sequence.length - 1) return
    state.autoTimer = window.setTimeout(advanceDialogue, AUTO_ADVANCE_MS)
  }

  function setAuto(enabled) {
    state.auto = enabled
    document.querySelectorAll('[data-action="auto"]').forEach((button) => {
      button.setAttribute('aria-pressed', String(enabled))
    })
    showToast(enabled ? '自动播放已开启' : '自动播放已暂停')
    if (enabled && !state.typing) scheduleAutoAdvance()
    else clearTimer('autoTimer')
  }

  function toggleComposer(forceOpen) {
    if (state.generating) return
    const open = typeof forceOpen === 'boolean' ? forceOpen : refs.composer.hidden
    refs.composer.hidden = !open
    refs.dialogueBox.hidden = open
    refs.composerTrigger.setAttribute('aria-expanded', String(open))

    if (open) {
      hideChoices()
      clearTimer('autoTimer')
      window.requestAnimationFrame(() => refs.actionInput.focus())
    } else {
      refs.actionInput.value = ''
      const line = currentLine()
      if (!hasMoreDialoguePages() && line?.choicesAfter && !line.resolved) showChoices()
      refs.dialogueBox.focus()
      scheduleAutoAdvance()
    }
  }

  function setGenerating(enabled) {
    state.generating = enabled
    refs.room.dataset.roomState = enabled ? 'generating' : 'playing'
    const submitButton = refs.composer.querySelector('button[type="submit"]')
    submitButton.disabled = enabled
    refs.actionInput.disabled = enabled
  }

  function submitFreeAction(text) {
    const line = currentLine()
    if (line?.choicesAfter) line.resolved = true
    hideChoices()
    toggleComposer(false)
    updateTurn(1)
    const relationshipChange = {
      fields: { trust: 1, intimacy: 1 },
      description: '夏澄认真听完了你的自由行动，并愿意用更坦率的方式继续谈话。',
      lastChange: '言沁自由表达了此刻的行动，夏澄给予正面回应',
    }
    const relationshipResult = updateRelationship(relationshipChange)

    appendLog({
      speaker: '玩家决策',
      text,
      kind: 'choice',
      badge: '自由行动',
      turn: state.turn,
    })
    appendLog({
      speaker: '思考摘要',
      text: '自由行动已接收；下一步将结合当前场景、夏澄状态与关系网络生成回应。',
      kind: 'thinking',
      badge: '公开摘要',
      detail: '候选状态目标：当前场景状态表、人物关系状态表。',
      turn: state.turn,
    })

    const userLine = {
      speaker: '言沁',
      role: '由你扮演 · 自由行动',
      character: 'yanqin',
      kind: 'dialogue',
      text,
      logged: false,
      resolved: false,
    }
    const responseLine = {
      speaker: '夏澄',
      role: '白鸢咖啡馆店长',
      character: 'xiacheng',
      kind: 'dialogue',
      text: '夏澄认真听完，指尖在纸袋的折边上停了停。“嗯，我明白你的意思了。那这次，就让我也坦率一点吧。”',
      logged: false,
      resolved: false,
    }

    state.sequence.splice(state.lineIndex + 1, 0, userLine, responseLine)
    state.lineIndex += 1
    renderLine({ instant: true })
    setGenerating(true)
    refs.room.dataset.roomState = 'playing'
    updateAdvanceLabel('等待回应')

    state.generationTimers.push(window.setTimeout(() => {
      refs.room.dataset.roomState = 'generating'
      refs.speakerName.textContent = '夏澄'
      refs.speakerRole.textContent = '正在回应'
      refs.dialogueText.textContent = '夏澄垂下眼想了片刻'
      setActiveCharacter('xiacheng')
    }, 520))

    state.generationTimers.push(window.setTimeout(() => {
      setGenerating(false)
      appendLog({
        speaker: '工具记录',
        text: '自由行动已写入会话轨迹，夏澄的关系字段与描述状态已同步。',
        kind: 'tool',
        badge: 'status_table_set_values',
        detail: `人物关系状态表 · 夏澄：${describeRelationshipChange(relationshipResult, relationshipChange)}`,
        turn: state.turn,
      })
      state.lineIndex += 1
      renderLine()
      showToast('自由行动已写入本次回忆')
    }, 1450))
  }

  function showToast(message) {
    clearTimer('toastTimer')
    refs.toast.textContent = message
    refs.toast.hidden = false
    state.toastTimer = window.setTimeout(() => {
      refs.toast.hidden = true
    }, 2300)
  }

  function stageMenuItems() {
    return [...refs.stageMenu.querySelectorAll('[role="menuitem"]')]
  }

  function closeStageMenu({ returnFocus = false } = {}) {
    if (!state.menuOpen) return
    state.menuOpen = false
    refs.stageMenu.hidden = true
    refs.menuTrigger.setAttribute('aria-expanded', 'false')
    if (returnFocus) refs.menuTrigger.focus()
    scheduleAutoAdvance()
  }

  function openStageMenu() {
    if (state.cinematic) return
    if (state.activeDrawer) closeDrawer({ returnFocus: false, immediate: true })
    state.menuOpen = true
    clearTimer('autoTimer')
    refs.stageMenu.hidden = false
    refs.menuTrigger.setAttribute('aria-expanded', 'true')
    window.requestAnimationFrame(() => stageMenuItems()[0]?.focus())
  }

  function toggleStageMenu() {
    if (state.menuOpen) closeStageMenu({ returnFocus: true })
    else openStageMenu()
  }

  function setCinematicMode(enabled) {
    if (state.cinematic === enabled) return
    state.cinematic = enabled

    const layers = document.querySelectorAll(
      '.scene-header, .scene-caption, .relationship-ribbon, .choice-panel, .dialogue-dock, .stage-menu, .drawer-backdrop, .info-drawer, .toast',
    )

    if (enabled) {
      state.cinematicReturnFocus = refs.menuTrigger
      clearTimer('autoTimer')
      closeStageMenu()
      if (state.activeDrawer) closeDrawer({ returnFocus: false, immediate: true })
      if (!refs.composer.hidden) toggleComposer(false)
      refs.room.dataset.cinematicMode = 'true'
      document.body.classList.add('is-cinematic')
      layers.forEach((element) => {
        element.dataset.previousAriaHidden = element.getAttribute('aria-hidden') ?? ''
        element.setAttribute('aria-hidden', 'true')
        element.inert = true
      })
      refs.cinematicReturn.hidden = false
      window.requestAnimationFrame(() => refs.cinematicReturn.focus())
      return
    }

    delete refs.room.dataset.cinematicMode
    document.body.classList.remove('is-cinematic')
    layers.forEach((element) => {
      element.inert = false
      const previousValue = element.dataset.previousAriaHidden
      if (previousValue) element.setAttribute('aria-hidden', previousValue)
      else element.removeAttribute('aria-hidden')
      delete element.dataset.previousAriaHidden
    })
    refs.cinematicReturn.hidden = true
    const returnTarget = state.cinematicReturnFocus
    state.cinematicReturnFocus = null
    if (returnTarget instanceof HTMLElement) returnTarget.focus()
    scheduleAutoAdvance()
  }

  function drawerFor(name) {
    return document.querySelector(`[data-drawer="${name}"]`)
  }

  function setDrawerTriggerState(name, expanded) {
    document.querySelectorAll(`[data-drawer-trigger="${name}"]`).forEach((button) => {
      button.setAttribute('aria-expanded', String(expanded))
    })
  }

  function closeDrawer({ returnFocus = true, immediate = false } = {}) {
    if (!state.activeDrawer) return
    clearTimer('drawerCloseTimer')
    const name = state.activeDrawer
    const drawer = drawerFor(name)
    state.activeDrawer = null
    drawer.classList.remove('is-open')
    drawer.setAttribute('aria-hidden', 'true')
    setDrawerTriggerState(name, false)
    refs.backdrop.hidden = true

    const finish = () => {
      drawer.hidden = true
      if (returnFocus && state.lastFocus instanceof HTMLElement) state.lastFocus.focus()
      state.lastFocus = null
      scheduleAutoAdvance()
    }

    if (immediate || prefersReducedMotion) finish()
    else state.drawerCloseTimer = window.setTimeout(() => {
      state.drawerCloseTimer = null
      finish()
    }, 280)
  }

  function openDrawer(name, trigger) {
    if (state.activeDrawer === name) {
      closeDrawer()
      return
    }
    if (state.activeDrawer) closeDrawer({ returnFocus: false, immediate: true })

    const drawer = drawerFor(name)
    if (!drawer) return
    const returnTarget = trigger?.closest('#stageMenu') ? refs.menuTrigger : trigger
    closeStageMenu()
    clearTimer('drawerCloseTimer')
    state.activeDrawer = name
    state.lastFocus = returnTarget ?? document.activeElement
    clearTimer('autoTimer')
    drawer.hidden = false
    drawer.setAttribute('aria-hidden', 'false')
    refs.backdrop.hidden = false
    setDrawerTriggerState(name, true)
    window.requestAnimationFrame(() => {
      drawer.classList.add('is-open')
      drawer.querySelector('.drawer-header button')?.focus()
    })
  }

  function resetExperience({ announce = true } = {}) {
    clearTimer('typingTimer')
    clearTimer('autoTimer')
    clearGenerationTimers()
    setGenerating(false)
    if (state.cinematic) setCinematicMode(false)
    closeStageMenu()
    if (state.activeDrawer) closeDrawer({ returnFocus: false, immediate: true })
    refs.composer.hidden = true
    refs.dialogueBox.hidden = false
    refs.composerTrigger.setAttribute('aria-expanded', 'false')
    refs.actionInput.value = ''
    refs.storyLog.replaceChildren()
    refs.clueList.querySelectorAll('[data-dynamic-clue]').forEach((item) => item.remove())
    document.querySelectorAll('[data-clue-count]').forEach((element) => {
      element.textContent = '2 条'
    })

    state.sequence = freshSequence()
    state.lineIndex = 0
    state.auto = false
    state.relationships = cloneRelationships()
    state.turn = INITIAL_TURN
    document.querySelectorAll('[data-action="auto"]').forEach((button) => {
      button.setAttribute('aria-pressed', 'false')
    })
    updateRelationship()
    updateTurn(0)
    seedInitialTrace()
    renderLine()
    if (announce) showToast('推演已经回到雨停后的初始状态。')
  }

  function toggleSound(button) {
    state.soundOn = !state.soundOn
    button.setAttribute('aria-pressed', String(state.soundOn))
    button.setAttribute('aria-label', state.soundOn ? '关闭环境音' : '开启环境音')
    button.querySelector('[data-sound-icon]').textContent = state.soundOn ? '♪' : '∅'
    showToast(state.soundOn ? '环境音已开启（静态演示）' : '环境音已关闭')
  }

  function interactiveTarget(target) {
    return target instanceof Element && Boolean(target.closest('button, textarea, input, select, a'))
  }

  function trapDrawerFocus(event) {
    if (event.key !== 'Tab' || !state.activeDrawer) return
    const drawer = drawerFor(state.activeDrawer)
    const focusable = [...drawer.querySelectorAll('button:not(:disabled), [href], textarea:not(:disabled), [tabindex]:not([tabindex="-1"])')]
      .filter((element) => element.offsetParent !== null)
    if (!focusable.length) return
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  refs.dialogueBox.addEventListener('click', advanceDialogue)

  refs.composer.addEventListener('submit', (event) => {
    event.preventDefault()
    const text = refs.actionInput.value.trim()
    if (!text) {
      showToast('先写下一句行动或台词。')
      refs.actionInput.focus()
      return
    }
    submitFreeAction(text)
  })

  refs.actionInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      refs.composer.requestSubmit()
    }
  })

  refs.stageMenu.addEventListener('focusout', () => {
    window.requestAnimationFrame(() => {
      if (state.menuOpen && !refs.stageMenu.contains(document.activeElement)) closeStageMenu()
    })
  })

  document.querySelectorAll('[data-drawer-trigger]').forEach((button) => {
    button.addEventListener('click', () => openDrawer(button.dataset.drawerTrigger, button))
  })

  document.addEventListener('click', (event) => {
    const action = event.target.closest('[data-action]')?.dataset.action
    if (action === 'composer') toggleComposer()
    if (action === 'close-drawer') closeDrawer()
    if (action === 'reset') resetExperience()
    if (action === 'auto') setAuto(!state.auto)
    if (action === 'sound') toggleSound(event.target.closest('button'))
    if (action === 'menu') toggleStageMenu()
    if (action === 'cinematic') setCinematicMode(true)
    if (action === 'restore-cinematic') setCinematicMode(false)
    if (action === 'exit') showToast('静态设计稿不会离开页面；正式版本可在此返回会话中心。')

    if (
      state.menuOpen
      && !refs.stageMenu.contains(event.target)
      && !refs.menuTrigger.contains(event.target)
    ) closeStageMenu()
  })

  document.addEventListener('keydown', (event) => {
    const key = event.key.toLowerCase()

    if (state.cinematic) {
      if (event.key === 'Escape' || key === 'h') {
        event.preventDefault()
        setCinematicMode(false)
      }
      return
    }

    trapDrawerFocus(event)

    if (event.key === 'Escape') {
      if (state.activeDrawer) {
        event.preventDefault()
        closeDrawer()
        return
      }
      if (state.menuOpen) {
        event.preventDefault()
        closeStageMenu({ returnFocus: true })
        return
      }
      if (!refs.composer.hidden) {
        event.preventDefault()
        toggleComposer(false)
      }
      return
    }

    if (state.menuOpen && ['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
      event.preventDefault()
      const items = stageMenuItems()
      const currentIndex = Math.max(0, items.indexOf(document.activeElement))
      let nextIndex = currentIndex
      if (event.key === 'ArrowDown') nextIndex = (currentIndex + 1) % items.length
      if (event.key === 'ArrowUp') nextIndex = (currentIndex - 1 + items.length) % items.length
      if (event.key === 'Home') nextIndex = 0
      if (event.key === 'End') nextIndex = items.length - 1
      items[nextIndex]?.focus()
      return
    }

    if (interactiveTarget(event.target)) return

    if (!refs.choicePanel.hidden && ['1', '2', '3'].includes(event.key)) {
      event.preventDefault()
      selectChoice(choices[Number(event.key) - 1])
      return
    }
    if (key === 's') {
      event.preventDefault()
      openDrawer('status', document.querySelector('[data-drawer-trigger="status"]'))
      return
    }
    if (key === 'l') {
      event.preventDefault()
      openDrawer('log', document.querySelector('[data-drawer-trigger="log"]'))
      return
    }
    if (key === 'h') {
      event.preventDefault()
      setCinematicMode(true)
      return
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      advanceDialogue()
    }
  })

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) clearTimer('autoTimer')
    else scheduleAutoAdvance()
  })

  resetExperience({ announce: false })
})()
