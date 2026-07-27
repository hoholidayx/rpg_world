(() => {
  'use strict'

  const YQ_FIXTURE = Object.freeze({
    source: '../YQDesignProject/design/current.json',
    revision: 'r000028',
    capturedAt: '2026-07-26',
    story: {
      title: '非公开行程-沁冉',
      opening: '最后一个提问',
      timeSetting: '2019年11月上旬',
      quickReplyCount: 0,
    },
    characters: [
      {
        order: 1,
        stableId: 'character-yan-qin',
        name: '颜沁',
        role: 'Team NII 成员 / 上财学生',
        aliases: ['沁沁', '懒懒', 'N队歌姬'],
        description: '1999年11月23日出生的湖南籍成年女性。开篇为上海财经大学2017级大三学生，同时承担团体排练、公演与 Vocal 工作。',
        present: true,
        player: false,
      },
      {
        order: 2,
        stableId: 'character-shen-tingzhou',
        name: '沈听洲',
        role: '投资人 / 内容合作顾问',
        aliases: ['沈总', '沈顾问', '沈先生', '听洲哥'],
        description: '1991年9月18日出生，上海本地成长。2019年前已积累文化娱乐、内容与消费项目投资履历，并以内容合作顾问身份进入制作现场。',
        present: true,
        player: true,
      },
      {
        order: 3,
        stableId: 'character-liu-jie',
        name: '刘洁',
        role: 'Team NII 成员 / Vocal 同伴',
        aliases: [],
        description: '2019年SNH48 Team NII成员，颜沁的队友与 Vocal 同伴。两人在排练、公演、代役和后台工作中长期共事。',
        present: false,
        player: false,
      },
      {
        order: 4,
        stableId: 'character-liu-shuxian',
        name: '刘姝贤',
        role: 'Team NII 成员',
        aliases: [],
        description: '2019年SNH48 Team NII成员，与颜沁在排练、公演、后台和团体日常中持续相处，是她较熟悉的队友之一。',
        present: false,
        player: false,
      },
      {
        order: 5,
        stableId: 'character-lu-tianhui',
        name: '卢天惠',
        role: 'Team NII 成员 / 室友',
        aliases: [],
        description: '2019年SNH48 Team NII成员，颜沁较熟悉的队友及成员生活中心室友，共享大量排练、公演、候场和晚归日常。',
        present: false,
        player: false,
      },
      {
        order: 6,
        stableId: 'character-song-xinran',
        name: '宋昕冉',
        role: 'Team X 成员',
        aliases: ['冉冉'],
        description: '1997年7月8日出生于山东。2015年加入SNH48 Team X；开篇为2019年11月，已积累多年公演、综艺、竞演与网剧拍摄经历。',
        present: false,
        player: false,
      },
      {
        order: 7,
        stableId: 'character-wang-lan',
        name: '王岚',
        role: '高级项目负责人',
        aliases: ['王姐', '王负责人'],
        description: '2019年丝芭传媒高级项目负责人之一，负责星梦剧院运营、成员项目与跨部门协调，熟悉日程、审批和现场风险处理。',
        present: false,
        player: false,
      },
      {
        order: 8,
        stableId: 'character-he-mingyuan',
        name: '何明远',
        role: '项目执行助理',
        aliases: ['小何', '何助理'],
        description: '2019年负责沈听洲的日程与项目执行，也是沈听洲和星星娱乐常设团队之间的日常协调接口。',
        present: false,
        player: false,
      },
      {
        order: 9,
        stableId: 'character-chen-jianing',
        name: '陈嘉宁',
        role: '上财同届学生',
        aliases: ['嘉宁'],
        description: '上海财经大学2017级学生，与颜沁同届，因共同课程、小组作业和校园日常逐渐熟悉，是稳定的校园同学。',
        present: false,
        player: false,
      },
    ],
    relationships: [
      {
        id: 'yan-qin__shen-tingzhou',
        stableId: 'status-relationship-yan-qin-shen-tingzhou',
        title: '关系状态·颜沁与沈听洲',
        rows: [
          ['亲密', '0/100'],
          ['激情', '0/100'],
          ['信任', '0/100'],
          ['维系意愿', '0/100'],
          ['戒备', '0/100'],
          ['当前状态', '初次留意｜对台上的行业嘉宾产生问题导向的注意，尚未形成私人关系。'],
        ],
      },
      {
        id: 'song-xinran__shen-tingzhou',
        stableId: 'status-relationship-song-xinran-shen-tingzhou',
        title: '关系状态·宋昕冉与沈听洲',
        rows: [
          ['亲密', '0/100'],
          ['激情', '0/100'],
          ['信任', '0/100'],
          ['维系意愿', '0/100'],
          ['戒备', '0/100'],
          ['当前状态', '尚未建立｜尚无已确认的接触或关系倾向。'],
        ],
      },
      {
        id: 'yan-qin__song-xinran',
        stableId: 'status-relationship-yan-qin-song-xinran',
        title: '关系状态·颜沁与宋昕冉',
        rows: [
          ['颜沁→宋昕冉·亲密', '0/100'],
          ['颜沁→宋昕冉·激情', '0/100'],
          ['颜沁→宋昕冉·信任', '0/100'],
          ['颜沁→宋昕冉·维系意愿', '0/100'],
          ['颜沁→宋昕冉·戒备', '0/100'],
          ['宋昕冉→颜沁·亲密', '0/100'],
          ['宋昕冉→颜沁·激情', '0/100'],
          ['宋昕冉→颜沁·信任', '0/100'],
          ['宋昕冉→颜沁·维系意愿', '0/100'],
          ['宋昕冉→颜沁·戒备', '0/100'],
          ['当前状态', '礼貌前后辈｜存在公开身份上的认识，尚未形成稳定私交或活跃竞争。'],
        ],
      },
    ],
    projectFacts: [
      ['当前阶段', '早期再遇｜2019年11月｜校园初见已经发生'],
      ['颜沁·声音短片', '尚未公开征集'],
      ['宋昕冉·个人样片', '首轮名单已确定｜第一版样片待内部看片'],
      ['宋昕冉·《青春有你2》外务', '尚未进入公开外务阶段'],
      ['成员职业观察内容', '尚未立项'],
      ['2020年度总选', '尚未进入备战期｜结果未产生'],
    ],
    detailStates: [
      {
        title: '服装状态·颜沁',
        category: 'wardrobe',
        note: 'objective-current-state · 8 行',
        visibleRows: [
          ['外套/外搭', '奶白色针织开衫，正常穿着'],
          ['上装', '浅灰色薄款圆领针织打底衫'],
          ['下装', '烟灰色厚呢A字短裙'],
          ['连身衣物', '未穿'],
          ['袜装', '黑色厚款打底连裤袜'],
          ['鞋履', '黑色圆头乐福鞋'],
        ],
        hiddenRows: [
          ['内衣', '浅粉色蕾丝细边文胸，正常穿着'],
          ['内裤', '奶白与浅粉配色的成套内裤，正常穿着'],
        ],
      },
      {
        title: '身体生理状态·颜沁',
        category: 'physiology',
        note: 'objective-private-state · 默认折叠',
        visibleRows: [],
        hiddenRows: [
          ['月经期', '进行中｜第3天/5天｜2019年11月4日至11月8日'],
          ['排卵期', '未开始｜预计2019年11月14日至11月23日'],
        ],
      },
      {
        title: '服装状态·宋昕冉',
        category: 'wardrobe',
        note: 'objective-current-state · 8 行',
        visibleRows: [
          ['外套/外搭', '浅驼色双排扣短西装'],
          ['上装', '黑色方领贴身针织上衣'],
          ['下装', '黑色高腰A字短裙'],
          ['连身衣物', '未穿'],
          ['袜装', '黑色薄款连裤丝袜'],
          ['鞋履', '黑色尖头短靴'],
        ],
        hiddenRows: [
          ['内衣', '酒红色蕾丝文胸，正常穿着'],
          ['内裤', '酒红色成套蕾丝内裤，正常穿着'],
        ],
      },
      {
        title: '身体生理状态·宋昕冉',
        category: 'physiology',
        note: 'objective-private-state · 默认折叠',
        visibleRows: [],
        hiddenRows: [
          ['月经期', '本周期已结束｜2019年10月23日至10月27日'],
          ['排卵期', '进行中｜第5天/10天｜2019年11月2日至11月11日'],
        ],
      },
    ],
    events: {
      'side-corridor': {
        title: '散场后的课件',
        description: '星梦剧院侧走廊中的第二次相遇场景。',
        directive: '晚场散后，颜沁换下舞台服，手里压着准备带回学校的小组课件。最上面那页纸滑到沈听洲附近；让场景停在这件很小的事上。',
        suitability: '校园 Opening 已成立、时间自然推进到剧场晚场散后、双方尚未形成私人联系时适宜。',
        scheduled: '2019年11月7日 09:00',
        deadline: null,
        dispatch: 'soft',
        injectedTurn: 12,
      },
      'voice-open-call': {
        title: '公开征集说明',
        description: '启动颜沁的冬季声音短片事业线。',
        directive: '王岚发布冬季声音短片公开征集说明，成员可自行选择内容提交短 demo。',
        suitability: '校园 Opening 与至少一次后续工作接触成立，时间到 2019 年 11 月下旬。',
        scheduled: '2019年11月20日 09:00',
        deadline: '2019年12月20日 00:00',
        dispatch: 'soft',
      },
      'numbered-demo': {
        title: '编号demo',
        description: '颜沁以一份不完美但可判断的作品进入项目流程。',
        directive: '颜沁在课程、公演和排练之间完成第一版短 demo，项目 staff 按统一流程生成编号。',
        suitability: '公开征集已经成立，且仍在截止时间前。',
        scheduled: '2019年12月5日 09:00',
        deadline: '2020年1月31日 00:00',
        dispatch: 'soft',
      },
      'interrupted-phrase': {
        title: '被打断的一小节',
        description: '一次自然排练习惯触碰 2010 年事故现场的模糊记忆。',
        directive: '排练短暂中断时，颜沁下意识把被截断的一小节轻声唱完。',
        suitability: '至少一次后续工作接触已经发生，且共同历史尚未确认。',
        scheduled: '2019年12月10日 09:00',
        deadline: null,
        dispatch: 'soft',
      },
      'second-cut': {
        title: '第二版样片',
        description: '宋昕冉以个人内容样片主动进入星星娱乐合作线。',
        directive: '内部看片会上，宋昕冉公开提出专业异议，项目团队等待内容判断。',
        suitability: '2019 年 11 月后，内容合作已经进入正文且双方尚无私人接触。',
        scheduled: '2019年11月15日 09:00',
        deadline: null,
        dispatch: 'soft',
      },
      'external-notice': {
        title: '外务通知',
        description: '建立宋昕冉进入《青春有你2》的现实工作转折。',
        directive: '工作通知确认宋昕冉将参加外部女团竞演节目。',
        suitability: '个人样片线已进入正文，故事时间进入 2020 年初。',
        scheduled: '2020年1月15日 09:00',
        deadline: '2020年3月12日 00:00',
        dispatch: 'soft',
      },
      airing: {
        title: '节目开播后的距离',
        description: '以节目开播为固定公开节点。',
        directive: '2020年3月12日，《青春有你2》开始公开播出。',
        suitability: '',
        scheduled: '2020年3月12日 20:00',
        deadline: null,
        dispatch: 'forced',
      },
      'rank-19': {
        title: '第19名以后',
        description: '固定第19名结果并送回团体与项目主线。',
        directive: '2020年5月30日，节目公布最终结果，宋昕冉获得第19名。',
        suitability: '',
        scheduled: '2020年5月30日 22:00',
        deadline: null,
        dispatch: 'forced',
      },
      'return-review': {
        title: '归来后的第一次看片',
        description: '外务归来后重新取得个人内容线的主动位置。',
        directive: '返沪后的第一次看片会上，第二版样片已经形成新的粗剪。',
        suitability: '第19名已公布，宋昕冉已自然返沪。',
        scheduled: '2020年6月3日 09:00',
        deadline: '2020年7月15日 00:00',
        dispatch: 'soft',
      },
      'project-kickoff': {
        title: '成员观察内容立项',
        description: '建立双女主事业线的汇流项目。',
        directive: '项目团队提出成员职业观察内容方案，两条事业线分别列明。',
        suitability: '两边事业线已有可使用的项目基础。',
        scheduled: '2020年6月10日 09:00',
        deadline: '2020年7月10日 00:00',
        dispatch: 'soft',
      },
      'same-timeline': {
        title: '同一条成片时间线',
        description: '两位女主第一次在同一制作语境中看到彼此被如何观看。',
        directive: '联合看片中，两人的素材先后出现在同一条剪辑时间线。',
        suitability: '观察内容已立项，双方素材达到可看片程度。',
        scheduled: '2020年6月20日 09:00',
        deadline: '2020年8月1日 00:00',
        dispatch: 'soft',
      },
      'two-positions': {
        title: '总选前的两种位置',
        description: '呈现两位女主不对称的位置与现实筹码。',
        directive: '总选备战会议分别展示两份处境不同的材料。',
        suitability: '观察内容已形成素材，2020 总选进入正式备战。',
        scheduled: '2020年7月15日 09:00',
        deadline: '2020年8月15日 00:00',
        dispatch: 'soft',
      },
      'election-night': {
        title: '总选之夜',
        description: '以公开结果收束第一阶段事业线并打开关系后果。',
        directive: '2020年8月15日公布结果：宋昕冉第3名；颜沁依据已成立事实确定第17至32名之间的具体名次。',
        suitability: '',
        scheduled: '2020年8月15日 20:00',
        deadline: null,
        dispatch: 'forced',
      },
      'old-scans': {
        title: '一份旧扫描件',
        description: '提供能够核实共同历史的旧档案证据。',
        directive: '早期文化项目文件进入正常工作流，其中出现“颜沁”这个名字。',
        suitability: '排练回声已经发生，且存在合理的旧档案清理。',
        scheduled: null,
        deadline: null,
        dispatch: 'soft',
      },
      'hunan-box': {
        title: '湖南旧纸箱',
        description: '颜沁从家庭旧物中接近共同历史。',
        directive: '家人从旧纸箱翻出小学合唱队照片与活动折页。',
        suitability: '自然出现返乡或整理旧物的机会。',
        scheduled: null,
        deadline: null,
        dispatch: 'soft',
      },
    },
    outlines: [
      { name: '第一阶段·颜沁事业线', description: '校园初见、剧场再遇、声音短片与共同历史回声。', nodes: ['side-corridor', 'voice-open-call', 'numbered-demo', 'interrupted-phrase'] },
      { name: '第一阶段·宋昕冉事业线', description: '个人样片、外务、公开竞演与返沪后的内容选择。', nodes: ['second-cut', 'external-notice', 'airing', 'rank-19', 'return-review'] },
      { name: '第一阶段·沁冉汇流与总选', description: '两条事业线汇流，并推进至 2020 年总选。', nodes: ['project-kickoff', 'same-timeline', 'two-positions', 'election-night'] },
    ],
    pools: [
      { name: '颜沁早期再遇事件池', events: ['side-corridor'] },
      { name: '旧疤与共同历史揭示', events: ['interrupted-phrase', 'old-scans', 'hunan-box'] },
      { name: '宋昕冉个人内容样片', events: ['second-cut'] },
      { name: '颜沁·冬季声音短片', events: ['voice-open-call', 'numbered-demo'] },
      { name: '宋昕冉·2020外务', events: ['external-notice', 'airing', 'rank-19', 'return-review'] },
      { name: '沁冉汇流与2020总选', events: ['project-kickoff', 'same-timeline', 'two-positions', 'election-night'] },
    ],
    visualSpecs: [
      { title: '颜沁·核心视觉身份', subject: 'character-yan-qin', anchors: '稳定刘海、深棕长发、裙装主导、粉白浅蓝与黑红对照' },
      { title: '成员生活中心·团体宿舍', subject: 'lore-place-member-living-center-2019', anchors: '普通双人宿舍、书桌、衣架、课程资料与化妆包' },
      { title: '星梦剧院·演出后后台走廊', subject: 'lore-place-xingmeng-theater-2019', anchors: '暖白后台灯、深色防火门、磨损地胶与工作通道' },
      { title: '沈听洲·核心视觉身份', subject: 'character-shen-tingzhou', anchors: '成年男性、简洁深色着装、右手腕内侧淡白旧疤' },
      { title: '宋昕冉·核心视觉身份', subject: 'character-song-xinran', anchors: '鹅蛋脸、明亮眼睛、深色长发、纤细修长轮廓' },
    ],
    log: [
      {
        kind: 'user',
        turn: 12,
        label: '玩家输入',
        meta: '沈听洲 · IC',
        text: '我弯腰捡起那页纸，只看了一眼页眉便递向她。',
      },
      {
        kind: 'decision',
        turn: 12,
        label: '状态目标路由',
        meta: 'Status Preflight · evaluated',
        text: '当前场景进入更新检查；普通状态表没有出现已确认的新值，本轮不调用普通状态写入工具。',
        detail: '目标：当前场景\n结果：继续检查 Scene 字段；其他状态目标保持原值',
      },
      {
        kind: 'tool',
        turn: 12,
        label: 'scene_attr',
        meta: 'tool call + result · success',
        text: '更新“当前事实”，记录课件已经归还、第二次接触进入对话。',
        detail: 'CALL  {"当前事实":"课件已归还；第二次接触进入对话。"}\nRESULT  updated',
      },
      {
        kind: 'decision',
        turn: 12,
        label: 'Plot Scheduler · outline lane',
        meta: '散场后的课件 · triggered',
        text: '候选已到调度时间且适合当前 Scene，本轮选择并注入该事件。',
        detail: 'lane=outline · event=side-corridor · status=triggered',
      },
      {
        kind: 'decision',
        turn: 12,
        label: 'Plot Scheduler · pool lane',
        meta: '散场后的课件 · deferred',
        text: '事件池命中同一 event_id；为避免同轮重复注入，保留大纲 lane 的选择。',
        detail: 'lane=pool · event=side-corridor · status=deferred · reason=same-turn dedupe',
      },
      {
        kind: 'plot',
        turn: 12,
        label: '剧情注入',
        meta: '散场后的课件 · 已注入本轮',
        text: '晚场散后，颜沁已经换下舞台服，手里压着准备带回学校的小组课件；最上面那页纸滑到沈听洲附近。',
      },
      {
        kind: 'thinking',
        turn: 12,
        label: '公开 thinking 摘要',
        meta: 'stream summary',
        text: '把回应限制在已经发生的递还动作与 NPC 反应，不替玩家决定后续行动。',
      },
      {
        kind: 'tool',
        turn: 12,
        label: 'rp_story_outcome',
        meta: 'tool call + result · success',
        text: '对递还课件能否自然建立第二次接触进行剧情裁定。',
        detail: 'CALL  {"reason":"递还课件并自然建立第二次接触","actor":"沈听洲"}\nRESULT  success',
      },
      {
        kind: 'outcome',
        turn: 12,
        label: '剧情裁定 · success',
        meta: 'Narrative Outcome',
        text: '课件被自然归还，第二次接触成立；没有替玩家决定后续行动。',
      },
      {
        kind: 'assistant',
        turn: 12,
        label: 'assistant 正文',
        meta: 'canonical content',
        text: '纸页落在走廊边缘。颜沁先看见那页课件，又看见你胸前的内容合作顾问工作证，脚步停了很短的一瞬。',
      },
      {
        kind: 'assistant',
        turn: 12,
        label: '颜沁',
        meta: 'rp-character',
        text: '“谢谢。我记得你——前天分享会最后那个问题。”',
      },
    ],
  })

  const DIALOGUE = Object.freeze([
    {
      speaker: '旁白',
      role: '星梦剧院 · 晚场散后',
      character: 'narrator',
      text: '纸页落在走廊边缘。观众散去后的喧闹已经退到防火门另一侧，最上方只印着一行课程小组的页眉。',
    },
    {
      speaker: '颜沁',
      role: 'Team NII 成员 / 上财学生',
      character: 'yan-qin',
      text: '她先看见那页课件，又看见你胸前的内容合作顾问工作证，停顿很短。“不好意思，能帮我捡一下吗？”',
    },
    {
      speaker: '颜沁',
      role: '第二次见面',
      character: 'yan-qin',
      text: '接过纸页后，她重新看了你一眼。“谢谢。我记得你——前天分享会最后那个问题。”',
    },
  ])

  const TYPE_INTERVAL_MS = 22
  const AUTO_ADVANCE_MS = 2300
  const PAGE_TARGET = 44
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

  const refs = {
    room: document.querySelector('#sessionRoom'),
    dialogueBox: document.querySelector('#dialogueBox'),
    dialogueText: document.querySelector('#dialogueText'),
    dialogueAnnouncement: document.querySelector('#dialogueAnnouncement'),
    speakerName: document.querySelector('#speakerName'),
    speakerRole: document.querySelector('#speakerRole'),
    advanceLabel: document.querySelector('[data-advance-label]'),
    composer: document.querySelector('#actionComposer'),
    composerTrigger: document.querySelector('[data-action="composer"]'),
    actionInput: document.querySelector('#actionInput'),
    backdrop: document.querySelector('.drawer-backdrop'),
    stageMenu: document.querySelector('#stageMenu'),
    menuTrigger: document.querySelector('[data-action="menu"]'),
    cinematicReturn: document.querySelector('[data-action="restore-cinematic"]'),
    toast: document.querySelector('#toast'),
  }

  const state = {
    lineIndex: 0,
    pageIndex: 0,
    pages: [],
    typing: false,
    typingTimer: null,
    auto: false,
    autoTimer: null,
    activeDrawer: null,
    drawerCloseTimer: null,
    lastFocus: null,
    toastTimer: null,
    menuOpen: false,
    cinematic: false,
    spoilerProtection: true,
  }

  function element(tag, className, text) {
    const node = document.createElement(tag)
    if (className) node.className = className
    if (text !== undefined) node.textContent = text
    return node
  }

  function appendDefinitionList(target, rows) {
    rows.forEach(([key, value]) => {
      const row = element('div')
      row.append(element('dt', '', key), element('dd', '', value))
      target.append(row)
    })
  }

  function initials(name) {
    return [...name].slice(0, 1).join('')
  }

  function renderCharacters() {
    const target = document.querySelector('#characterRoster')
    YQ_FIXTURE.characters.forEach((character) => {
      const card = element('details', `status-character-card status-character-card--fixture${character.player ? ' status-character-card--player' : ''}`)
      card.dataset.characterId = character.stableId
      const summary = element('summary', 'status-character-card__summary')
      summary.setAttribute('aria-label', `展开${character.name}角色卡`)
      const portrait = element('div', 'status-character-card__portrait status-character-card__portrait--initial')
      portrait.append(element('span', '', initials(character.name)))

      const identity = element('div', 'status-character-card__identity')
      identity.append(
        element('span', '', character.player ? 'PLAYER CHARACTER' : 'STORY CHARACTER'),
        element('h4', '', character.name),
        element('p', '', `${character.role} · 设计顺序 ${String(character.order).padStart(2, '0')}`),
      )
      const stable = element('small', 'character-stable-id', character.stableId)
      identity.append(stable)

      const badge = element('span', `status-character-card__tag${character.present ? ' is-present' : ''}`, character.present ? '在场' : '未在场')
      const affordance = element('span', 'status-character-card__affordance', '展开角色卡')
      summary.append(portrait, identity, badge, affordance)

      const expanded = element('section', 'status-character-card__expanded')
      expanded.append(element('p', '', character.description))
      const facts = element('dl')
      appendDefinitionList(facts, [
        ['设计引用', character.stableId],
        ['运行时 ID', 'storyCharacterId 待导入'],
        ['别名', character.aliases.length ? character.aliases.join('、') : '无'],
        ['当前 Scene', character.present ? '在场' : '未在场'],
      ])
      expanded.append(facts)
      card.append(summary, expanded)
      card.addEventListener('toggle', () => {
        const action = card.open ? '收起' : '展开'
        summary.setAttribute('aria-label', `${action}${character.name}角色卡`)
        affordance.textContent = `${action}角色卡`
      })
      target.append(card)
    })
  }

  function renderRelationships() {
    const target = document.querySelector('#relationshipList')
    YQ_FIXTURE.relationships.forEach((relationship, index) => {
      const card = element('article', `relationship-card${index === 0 ? ' relationship-card--focus' : ''}`)
      const heading = element('div', 'relationship-card__heading relationship-card__heading--fixture')
      const identity = element('div')
      identity.append(
        element('strong', '', relationship.title),
        element('small', '', `${relationship.stableId} · ${relationship.rows.length} 行`),
      )
      heading.append(identity)
      card.append(heading)

      const fields = element('dl', 'relationship-raw-rows')
      relationship.rows.forEach(([label, value]) => {
        const row = element('div', label === '当前状态' ? 'is-summary' : '')
        row.append(element('dt', '', label), element('dd', '', value))
        fields.append(row)
      })
      card.append(fields)
      target.append(card)
    })
  }

  function renderProjectFacts() {
    appendDefinitionList(document.querySelector('#projectFacts'), YQ_FIXTURE.projectFacts)
  }

  function renderDetailStates() {
    const target = document.querySelector('#detailStates')
    YQ_FIXTURE.detailStates.forEach((table) => {
      const details = element('details', `detail-state detail-state--${table.category}`)
      const summary = element('summary')
      const title = element('span')
      title.append(element('strong', '', table.title), element('small', '', table.note))
      summary.append(title, element('i', '', '展开'))
      details.append(summary)

      if (table.visibleRows.length) {
        const visible = element('section', 'detail-state__section')
        visible.append(element('h4', '', '常用可见层'))
        const list = element('dl')
        appendDefinitionList(list, table.visibleRows)
        visible.append(list)
        details.append(visible)
      }

      const hidden = element('section', 'detail-state__section detail-state__section--advanced')
      hidden.append(element('h4', '', table.category === 'wardrobe' ? 'normally-hidden · 详细层' : 'objective-private-state · 客观详细状态'))
      const list = element('dl')
      appendDefinitionList(list, table.hiddenRows)
      hidden.append(list)
      hidden.append(element('p', '', '默认折叠只影响信息层级，不代表权限或服务端脱敏。'))
      details.append(hidden)
      target.append(details)
    })
  }

  function eventIsRevealed(eventId, position) {
    if (!state.spoilerProtection) return true
    const event = YQ_FIXTURE.events[eventId]
    return position === 0 || Boolean(event.injectedTurn)
  }

  function eventBadge(event) {
    if (event.injectedTurn) return `已注入 · Turn ${event.injectedTurn}`
    if (event.dispatch === 'forced') return '强制调度'
    return '适宜时调度'
  }

  function renderEventNode(eventId, position, sourceKind) {
    const event = YQ_FIXTURE.events[eventId]
    const revealed = eventIsRevealed(eventId, position)
    const item = element('article', `plot-node${event.injectedTurn ? ' is-injected' : ''}${revealed ? '' : ' is-hidden'}`)
    item.dataset.eventId = eventId

    if (!revealed) {
      item.append(
        element('span', 'plot-node__index', String(position + 1)),
        element('strong', 'plot-node__masked', '••••••••'),
        element('small', '', '尚未注入 · 事件内容由服务端防剧透隐藏'),
      )
      return item
    }

    const top = element('div', 'plot-node__top')
    top.append(element('span', 'plot-node__index', String(position + 1)))
    const title = element('div')
    title.append(element('strong', '', event.title), element('small', '', event.description))
    top.append(title, element('b', '', eventBadge(event)))
    item.append(top)

    const timing = element('p', 'plot-node__timing')
    timing.textContent = `${event.scheduled || '无起始时间'}${event.deadline ? ` → 截止 ${event.deadline}` : ' · 无截止'}`
    item.append(timing)

    const details = element('details', 'plot-node__details')
    const summary = element('summary', '', '查看事件详情')
    const body = element('div')
    body.append(element('h5', '', '剧情指引'), element('p', '', event.directive))
    if (event.suitability) body.append(element('h5', '', '适宜条件'), element('p', '', event.suitability))
    body.append(element('small', '', `${sourceKind} · ${event.dispatch === 'forced' ? 'forced' : 'soft'} · 不重复`))
    details.append(summary, body)
    item.append(details)
    return item
  }

  function renderPlot() {
    const outlineTarget = document.querySelector('#outlineList')
    const poolTarget = document.querySelector('#poolList')
    outlineTarget.replaceChildren()
    poolTarget.replaceChildren()

    YQ_FIXTURE.outlines.forEach((outline) => {
      const card = element('article', 'plot-line')
      const header = element('header')
      const title = element('div')
      title.append(element('span', '', 'OUTLINE'), element('h4', '', outline.name), element('p', '', outline.description))
      header.append(title, element('b', '', `${outline.nodes.length} 个节点`))
      card.append(header)
      const nodes = element('div', 'plot-nodes')
      outline.nodes.forEach((eventId, position) => nodes.append(renderEventNode(eventId, position, '大纲节点')))
      card.append(nodes)
      outlineTarget.append(card)
    })

    YQ_FIXTURE.pools.forEach((pool) => {
      const card = element('article', 'plot-line plot-line--pool')
      const header = element('header')
      const title = element('div')
      title.append(element('span', '', 'EVENT POOL'), element('h4', '', pool.name))
      header.append(title, element('b', '', `${pool.events.length} 个事件`))
      card.append(header)
      const nodes = element('div', 'plot-nodes plot-nodes--compact')
      pool.events.forEach((eventId, position) => nodes.append(renderEventNode(eventId, position, '事件池')))
      card.append(nodes)
      poolTarget.append(card)
    })
  }

  function renderVisualSpecs() {
    const target = document.querySelector('#visualSpecList')
    YQ_FIXTURE.visualSpecs.forEach((spec, index) => {
      const card = element('article', 'visual-spec-card')
      card.append(
        element('span', '', String(index + 1).padStart(2, '0')),
        element('h4', '', spec.title),
        element('small', '', spec.subject),
        element('p', '', spec.anchors),
        element('b', '', 'ARCHIVE ONLY'),
      )
      target.append(card)
    })
  }

  function renderLog() {
    const target = document.querySelector('#storyLog')
    YQ_FIXTURE.log.forEach((entry) => {
      const item = element('li', `story-log__item story-log__item--${entry.kind}`)
      const marks = {
        assistant: '叙',
        decision: '判',
        outcome: '裁',
        plot: '注',
        thinking: '思',
        tool: '工',
        user: '玩',
      }
      const mark = element('span', 'story-log__mark', marks[entry.kind] || '记')
      const content = element('div', 'story-log__content')
      const meta = element('div', 'story-log__meta')
      const identity = element('div', 'story-log__identity')
      identity.append(element('strong', '', entry.label), element('span', '', entry.meta))
      meta.append(identity, element('small', '', `Turn ${entry.turn}`))
      content.append(meta, element('p', '', entry.text))
      if (entry.detail) content.append(element('pre', 'story-log__detail', entry.detail))

      if (entry.kind === 'assistant') {
        const actions = element('div', 'log-actions')
        ;['复制', 'TTS', '从此派生'].forEach((label) => {
          const button = element('button', '', label)
          button.type = 'button'
          button.dataset.logAction = label
          actions.append(button)
        })
        content.append(actions)
      }

      item.append(mark, content)
      target.append(item)
    })
  }

  function paginateText(text) {
    const pages = []
    let cursor = 0
    while (cursor < text.length) {
      let end = Math.min(cursor + PAGE_TARGET, text.length)
      if (end < text.length) {
        const windowText = text.slice(cursor, end)
        const boundary = Math.max(
          windowText.lastIndexOf('。'),
          windowText.lastIndexOf('！'),
          windowText.lastIndexOf('？'),
          windowText.lastIndexOf('；'),
          windowText.lastIndexOf('，'),
        )
        if (boundary >= Math.floor(PAGE_TARGET * 0.58)) end = cursor + boundary + 1
      }
      pages.push(text.slice(cursor, end))
      cursor = end
    }
    return pages.length ? pages : ['']
  }

  function currentLine() {
    return DIALOGUE[state.lineIndex]
  }

  function clearTimer(name) {
    if (state[name]) window.clearTimeout(state[name])
    state[name] = null
  }

  function updateActiveCharacter(character) {
    refs.room.dataset.activeSpeaker = character
    document.querySelectorAll('[data-character]').forEach((figure) => {
      figure.classList.toggle('is-active', character === 'narrator' ? figure.dataset.character === 'yan-qin' : figure.dataset.character === character)
    })
  }

  function updateAdvanceLabel() {
    if (state.typing) {
      refs.advanceLabel.textContent = '点击补全'
      return
    }
    if (state.pageIndex < state.pages.length - 1) {
      refs.advanceLabel.textContent = `继续阅读 · ${state.pageIndex + 1}/${state.pages.length}`
      return
    }
    if (state.lineIndex < DIALOGUE.length - 1) {
      refs.advanceLabel.textContent = '下一段'
      return
    }
    refs.advanceLabel.textContent = '等待你的行动'
  }

  function typePage(text) {
    clearTimer('typingTimer')
    state.typing = false
    refs.dialogueText.textContent = ''

    if (prefersReducedMotion || !text) {
      refs.dialogueText.textContent = text
      refs.dialogueAnnouncement.textContent = text
      updateAdvanceLabel()
      scheduleAuto()
      return
    }

    state.typing = true
    let cursor = 0
    const step = () => {
      cursor += 1
      refs.dialogueText.textContent = text.slice(0, cursor)
      if (cursor < text.length) {
        state.typingTimer = window.setTimeout(step, TYPE_INTERVAL_MS)
        return
      }
      state.typing = false
      state.typingTimer = null
      refs.dialogueAnnouncement.textContent = currentLine().text
      updateAdvanceLabel()
      scheduleAuto()
    }
    step()
    updateAdvanceLabel()
  }

  function showLine(index, pageIndex = 0) {
    state.lineIndex = index
    state.pageIndex = pageIndex
    const line = currentLine()
    state.pages = paginateText(line.text)
    refs.speakerName.textContent = line.speaker
    refs.speakerRole.textContent = line.role
    updateActiveCharacter(line.character)
    refs.composer.hidden = true
    refs.dialogueBox.hidden = false
    refs.composerTrigger.setAttribute('aria-expanded', 'false')
    typePage(state.pages[state.pageIndex])
  }

  function completeTyping() {
    if (!state.typing) return false
    clearTimer('typingTimer')
    state.typing = false
    refs.dialogueText.textContent = state.pages[state.pageIndex]
    refs.dialogueAnnouncement.textContent = currentLine().text
    updateAdvanceLabel()
    scheduleAuto()
    return true
  }

  function advanceDialogue() {
    if (state.activeDrawer || state.menuOpen || state.cinematic) return
    if (completeTyping()) return
    clearTimer('autoTimer')
    if (state.pageIndex < state.pages.length - 1) {
      state.pageIndex += 1
      typePage(state.pages[state.pageIndex])
      return
    }
    if (state.lineIndex < DIALOGUE.length - 1) {
      showLine(state.lineIndex + 1)
      return
    }
    openComposer()
  }

  function scheduleAuto() {
    clearTimer('autoTimer')
    if (!state.auto || state.typing || state.activeDrawer || state.menuOpen || state.cinematic) return
    if (state.lineIndex === DIALOGUE.length - 1 && state.pageIndex === state.pages.length - 1) return
    state.autoTimer = window.setTimeout(advanceDialogue, AUTO_ADVANCE_MS)
  }

  function toggleAuto() {
    state.auto = !state.auto
    document.querySelector('[data-action="auto"]').setAttribute('aria-pressed', String(state.auto))
    document.querySelector('[data-action="auto"]').classList.toggle('is-active', state.auto)
    showToast(state.auto ? 'AUTO 已开启 · 工作台或输入出现时自动暂停' : 'AUTO 已关闭')
    scheduleAuto()
  }

  function openComposer() {
    state.auto = false
    clearTimer('autoTimer')
    document.querySelector('[data-action="auto"]').setAttribute('aria-pressed', 'false')
    document.querySelector('[data-action="auto"]').classList.remove('is-active')
    refs.dialogueBox.hidden = true
    refs.composer.hidden = false
    refs.composerTrigger.setAttribute('aria-expanded', 'true')
    refs.actionInput.focus()
  }

  function closeComposer() {
    refs.composer.hidden = true
    refs.dialogueBox.hidden = false
    refs.composerTrigger.setAttribute('aria-expanded', 'false')
    updateAdvanceLabel()
    refs.dialogueBox.focus()
  }

  function showToast(message) {
    clearTimer('toastTimer')
    refs.toast.textContent = message
    refs.toast.hidden = false
    requestAnimationFrame(() => refs.toast.classList.add('is-visible'))
    state.toastTimer = window.setTimeout(() => {
      refs.toast.classList.remove('is-visible')
      state.toastTimer = window.setTimeout(() => {
        refs.toast.hidden = true
        state.toastTimer = null
      }, 220)
    }, 3200)
  }

  function drawerFor(name) {
    return document.querySelector(`[data-drawer="${name}"]`)
  }

  function setDrawerTriggers(name, expanded) {
    document.querySelectorAll(`[data-drawer-trigger="${name}"]`).forEach((button) => {
      button.setAttribute('aria-expanded', String(expanded))
    })
  }

  function closeMenu({ restoreFocus = false } = {}) {
    if (!state.menuOpen) return
    state.menuOpen = false
    refs.stageMenu.hidden = true
    refs.menuTrigger.setAttribute('aria-expanded', 'false')
    if (restoreFocus) refs.menuTrigger.focus()
  }

  function openDrawer(name, trigger) {
    const drawer = drawerFor(name)
    if (!drawer) return
    if (state.activeDrawer) closeDrawer({ restoreFocus: false, immediate: true })
    closeMenu()
    clearTimer('drawerCloseTimer')
    state.activeDrawer = name
    state.lastFocus = trigger || document.activeElement
    drawer.hidden = false
    drawer.setAttribute('aria-hidden', 'false')
    refs.backdrop.hidden = false
    document.body.classList.add('has-open-drawer')
    setDrawerTriggers(name, true)
    requestAnimationFrame(() => {
      drawer.classList.add('is-open')
      refs.backdrop.classList.add('is-visible')
      drawer.querySelector('.drawer-header button')?.focus()
    })
  }

  function closeDrawer({ restoreFocus = true, immediate = false } = {}) {
    if (!state.activeDrawer) return
    const name = state.activeDrawer
    const drawer = drawerFor(name)
    const focusTarget = state.lastFocus
    state.activeDrawer = null
    state.lastFocus = null
    drawer.classList.remove('is-open')
    drawer.setAttribute('aria-hidden', 'true')
    refs.backdrop.classList.remove('is-visible')
    document.body.classList.remove('has-open-drawer')
    setDrawerTriggers(name, false)
    const finish = () => {
      drawer.hidden = true
      refs.backdrop.hidden = true
      if (restoreFocus && focusTarget instanceof HTMLElement) focusTarget.focus()
    }
    if (immediate || prefersReducedMotion) finish()
    else state.drawerCloseTimer = window.setTimeout(finish, 260)
  }

  function toggleMenu() {
    if (state.activeDrawer) closeDrawer({ restoreFocus: false, immediate: true })
    state.menuOpen = !state.menuOpen
    refs.stageMenu.hidden = !state.menuOpen
    refs.menuTrigger.setAttribute('aria-expanded', String(state.menuOpen))
    if (state.menuOpen) refs.stageMenu.querySelector('[role="menuitem"]')?.focus()
  }

  function enterCinematic() {
    if (state.activeDrawer) closeDrawer({ restoreFocus: false, immediate: true })
    closeMenu()
    closeComposer()
    state.cinematic = true
    refs.room.dataset.cinematicMode = 'true'
    const hiddenLayers = document.querySelectorAll('.scene-header, .scene-caption, .stage-asset-notice, .dialogue-dock')
    hiddenLayers.forEach((layer) => {
      layer.setAttribute('aria-hidden', 'true')
      layer.inert = true
    })
    refs.cinematicReturn.hidden = false
    refs.cinematicReturn.focus()
  }

  function leaveCinematic() {
    if (!state.cinematic) return
    state.cinematic = false
    refs.room.dataset.cinematicMode = 'false'
    const hiddenLayers = document.querySelectorAll('.scene-header, .scene-caption, .stage-asset-notice, .dialogue-dock')
    hiddenLayers.forEach((layer) => {
      layer.removeAttribute('aria-hidden')
      layer.inert = false
    })
    refs.cinematicReturn.hidden = true
    refs.menuTrigger.focus()
  }

  function toggleSpoilerProtection() {
    state.spoilerProtection = !state.spoilerProtection
    const button = document.querySelector('[data-action="spoiler"]')
    button.setAttribute('aria-pressed', String(state.spoilerProtection))
    button.querySelector('[data-spoiler-label]').textContent = state.spoilerProtection ? '已开启' : '原型预览关闭'
    renderPlot()
    showToast(state.spoilerProtection ? '防剧透已开启 · 隐藏未注入内容' : '仅原型预览：生产环境应重新请求服务端投影')
  }

  function selectStoryTab(tabName) {
    document.querySelectorAll('[data-story-tab]').forEach((button) => {
      button.setAttribute('aria-selected', String(button.dataset.storyTab === tabName))
    })
    document.querySelectorAll('[data-story-panel]').forEach((panel) => {
      panel.hidden = panel.dataset.storyPanel !== tabName
    })
  }

  function trapDrawerFocus(event) {
    if (event.key !== 'Tab' || !state.activeDrawer) return
    const drawer = drawerFor(state.activeDrawer)
    const focusable = [...drawer.querySelectorAll('button:not(:disabled), [href], summary, textarea:not(:disabled), [tabindex]:not([tabindex="-1"])')]
      .filter((node) => !node.hidden)
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

  function handleAction(action, trigger) {
    if (action === 'close-drawer') closeDrawer()
    if (action === 'menu') toggleMenu()
    if (action === 'cinematic') enterCinematic()
    if (action === 'restore-cinematic') leaveCinematic()
    if (action === 'auto') toggleAuto()
    if (action === 'advance') advanceDialogue()
    if (action === 'composer') refs.composer.hidden ? openComposer() : closeComposer()
    if (action === 'restart-demo') {
      closeComposer()
      showLine(0)
      showToast('YQ 压力样例已从第一段重播；没有修改任何 Story 数据')
    }
    if (action === 'spoiler') toggleSpoilerProtection()
    if (action === 'settings') {
      closeMenu()
      showToast('生产实现复用现有 SessionSettingsMenu；静态原型不复制设置业务')
      trigger?.focus()
    }
    if (action === 'dream') showToast('生产实现跳转现有 Dream 管理页；Dream 故障不影响对话')
    if (action === 'media-studio') showToast('生产实现打开现有 Session 图像工作室')
    if (action === 'exit') showToast('静态设计稿：生产实现返回原 Session 来源页面')
  }

  renderCharacters()
  renderRelationships()
  renderProjectFacts()
  renderDetailStates()
  renderPlot()
  renderVisualSpecs()
  renderLog()
  showLine(0)

  document.querySelectorAll('[data-drawer-trigger]').forEach((button) => {
    button.addEventListener('click', () => openDrawer(button.dataset.drawerTrigger, button))
  })

  document.addEventListener('click', (event) => {
    const actionTarget = event.target.closest('[data-action]')
    if (actionTarget) handleAction(actionTarget.dataset.action, actionTarget)

    const logAction = event.target.closest('[data-log-action]')
    if (logAction) showToast(`${logAction.dataset.logAction}：生产实现复用现有 Timeline action`)

    if (
      state.menuOpen
      && !event.target.closest('#stageMenu')
      && !event.target.closest('[data-action="menu"]')
    ) closeMenu()
  })

  document.querySelectorAll('[data-story-tab]').forEach((button) => {
    button.addEventListener('click', () => selectStoryTab(button.dataset.storyTab))
  })

  refs.composer.addEventListener('submit', (event) => {
    event.preventDefault()
    const text = refs.actionInput.value.trim()
    if (!text) {
      showToast('请先写下行动；当前 Story 没有 QuickReply')
      return
    }
    refs.actionInput.value = ''
    showToast('静态原型不发送 Turn；生产实现走共享 Composer / stream / commit 链路')
  })

  refs.actionInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      refs.composer.requestSubmit()
    }
  })

  document.addEventListener('keydown', (event) => {
    trapDrawerFocus(event)
    if (event.key === 'Escape') {
      if (state.activeDrawer) {
        event.preventDefault()
        closeDrawer()
      } else if (state.menuOpen) {
        event.preventDefault()
        closeMenu({ restoreFocus: true })
      } else if (state.cinematic) {
        event.preventDefault()
        leaveCinematic()
      } else if (!refs.composer.hidden) {
        event.preventDefault()
        closeComposer()
      }
      return
    }

    if (event.metaKey || event.ctrlKey || event.altKey || event.target.matches('textarea, input, select')) return
    if (event.key.toLowerCase() === 's') {
      event.preventDefault()
      openDrawer('status', document.querySelector('[data-drawer-trigger="status"]'))
    }
    if (event.key.toLowerCase() === 'l') {
      event.preventDefault()
      openDrawer('log', document.querySelector('[data-drawer-trigger="log"]'))
    }
    if (event.key.toLowerCase() === 'h') {
      event.preventDefault()
      state.cinematic ? leaveCinematic() : enterCinematic()
    }
    if (event.key === 'Enter' && !state.activeDrawer && !state.menuOpen && !state.cinematic) {
      event.preventDefault()
      advanceDialogue()
    }
  })
})()
