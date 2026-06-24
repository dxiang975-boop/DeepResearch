<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'

type StreamEvent = {
  type: 'status' | 'phase' | 'route' | 'final' | 'error'
  message?: string
  final?: string
  node?: string
}

type ChatMessage = {
  id: string
  role: 'user' | 'assistant' | 'status'
  content: string
}

type AssistantMode = 'industry' | 'science'

type ModeConfig = {
  key: AssistantMode
  label: string
  badge: string
  title: string
  subtitle: string
  greeting: string
  placeholder: string
  instruction: string
  tags: string[]
  metrics: { label: string; value: string }[]
  highlights: { title: string; desc: string }[]
  starterPrompts: { title: string; prompt: string }[]
}

const modeConfigs: Record<AssistantMode, ModeConfig> = {
  industry: {
    key: 'industry',
    label: '行业研究助手',
    badge: '行业研究 / 竞品分析 / 商业落地',
    title: 'DeepResearch 行业研究助手',
    subtitle: '围绕市场、竞品、政策、商业模式和机会判断生成可追溯的行业研究报告。',
    greeting:
      '你好，我现在处于「行业研究助手」模式。你可以让我分析行业趋势、竞品格局、市场规模、政策风险或商业落地路径。',
    placeholder: '输入行业研究问题，例如：帮我调研 AI Agent 平台行业的市场规模、竞品和商业模式',
    instruction:
      '【当前任务模式：行业研究助手】\n请优先围绕行业/市场/竞品/商业模式/政策/产业链/投融资/增长机会进行多源研究。输出时强调市场判断、证据来源、机会风险和可落地建议。',
    tags: ['Market', 'Competitor', 'Strategy'],
    metrics: [
      { label: '研究重点', value: '市场 + 竞品' },
      { label: '证据来源', value: 'Web + Local' },
      { label: '输出结果', value: '报告 + 建议' },
    ],
    highlights: [
      {
        title: '行业全景拆解',
        desc: '从市场规模、趋势、产业链、政策和商业模式多个角度组织研究任务。',
      },
      {
        title: '竞品与机会判断',
        desc: '结合公开资料和本地知识库，对关键玩家、差异化机会和风险做结构化分析。',
      },
      {
        title: '面向落地的报告',
        desc: '最终报告会更关注业务结论、执行建议、证据来源和不确定性。',
      },
    ],
    starterPrompts: [
      {
        title: '行业调研',
        prompt:
          '请调研“企业知识库 Agent 平台”行业，按市场规模、主要竞品、商业模式、机会风险四部分输出，并附上可追溯来源。',
      },
      {
        title: '竞品分析',
        prompt:
          '请对比国内外 AI Agent 平台的代表性产品，分析定位、核心功能、收费模式、优势劣势和适合切入的细分场景。',
      },
      {
        title: '商业落地',
        prompt:
          '如果我要做一个面向中小企业的 DeepResearch 产品，请分析目标客户、核心卖点、MVP 功能、定价和两周落地计划。',
      },
      {
        title: '政策风险',
        prompt:
          '请分析生成式 AI 在企业知识管理场景中的政策、数据安全和合规风险，并给出产品设计上的规避建议。',
      },
    ],
  },
  science: {
    key: 'science',
    label: '科研助手',
    badge: '文献综述 / 实验分析 / SOTA 对比',
    title: 'DeepResearch 科研助手',
    subtitle: '结合本地论文、实验结果和在线前沿文献，生成研究综述、实验分析和科研报告。',
    greeting:
      '你好，我现在处于「科研助手」模式。你可以让我分析多篇本地文献、对比 SOTA、解释实验结果，或者整理成研究报告。',
    placeholder: '输入科研任务，例如：分析我的模型实验结果并对比在线 SOTA，写一份研究报告',
    instruction:
      '【当前任务模式：科研助手】\n请优先结合本地文献、实验结果、表格/日志与在线前沿论文/SOTA/benchmark 进行研究。输出时强调方法对比、数据集、指标、实验结论、局限性和后续研究方向。',
    tags: ['Papers', 'Benchmark', 'Experiment'],
    metrics: [
      { label: '研究重点', value: '论文 + 实验' },
      { label: '证据来源', value: 'Local + SOTA' },
      { label: '输出结果', value: '科研报告' },
    ],
    highlights: [
      {
        title: '本地文献整合',
        desc: '适合把论文 PDF、笔记、实验日志和指标表入库后做跨文档分析。',
      },
      {
        title: '前沿论文补充',
        desc: '检索 arXiv、OpenReview、Papers with Code 等来源，补齐最新方法与榜单信息。',
      },
      {
        title: '实验结果解释',
        desc: '围绕 baseline、消融实验、指标变化和误差来源形成可写进论文的分析。',
      },
    ],
    starterPrompts: [
      {
        title: '文献综述',
        prompt:
          '请分析本地知识库中的多篇深度学习预测模型相关文献，并结合在线最新论文，写一份研究综述。',
      },
      {
        title: 'SOTA 对比',
        prompt:
          '请围绕时间序列预测模型检索近两年的 SOTA 方法，按数据集、指标、模型结构和优缺点进行对比。',
      },
      {
        title: '实验分析',
        prompt:
          '请分析我的深度学习预测模型实验结果，结合在线 SOTA 和 baseline，解释指标差异、消融结果和改进方向。',
      },
      {
        title: '论文报告',
        prompt:
          '请根据本地论文、实验表格和在线前沿文献，生成一份包含研究背景、方法对比、实验结论和未来工作的科研报告。',
      },
    ],
  },
}

const userId = ref('user01')
const threadId = ref('thread01')
const tenantId = ref('default_tenant')
const query = ref('')
const loading = ref(false)
const errorMessage = ref('')
const messageListRef = ref<HTMLElement | null>(null)
const composerRef = ref<HTMLTextAreaElement | null>(null)
const progressLogs = ref<string[]>([])
const activeMode = ref<AssistantMode>('industry')

const currentMode = computed(() => modeConfigs[activeMode.value])
const assistantModes = computed(() => Object.values(modeConfigs))
const starterPrompts = computed(() => currentMode.value.starterPrompts)
const capabilityHighlights = computed(() => currentMode.value.highlights)
const landingMetrics = computed(() => currentMode.value.metrics)

const createGreeting = () => ({
  id: `m-${Date.now()}`,
  role: 'assistant' as const,
  content: currentMode.value.greeting,
})

const messages = ref<ChatMessage[]>([createGreeting()])

const escapeHtml = (value: string): string =>
  value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')

const markdownToHtml = (markdown: string): string => {
  const codeBlocks: string[] = []
  let text = markdown.replace(/```([\s\S]*?)```/g, (_, block) => {
    const index = codeBlocks.length
    codeBlocks.push(`<pre><code>${escapeHtml(String(block).trim())}</code></pre>`)
    return `@@CODE_BLOCK_${index}@@`
  })
  const lines = text.split('\n')
  const out: string[] = []
  let inList = false
  const closeList = () => {
    if (inList) {
      out.push('</ul>')
      inList = false
    }
  }
  for (const rawLine of lines) {
    const line = rawLine.trim()
    if (!line) {
      closeList()
      continue
    }
    if (line.startsWith('# ')) {
      closeList()
      out.push(`<h1>${escapeHtml(line.slice(2))}</h1>`)
      continue
    }
    if (line.startsWith('## ')) {
      closeList()
      out.push(`<h2>${escapeHtml(line.slice(3))}</h2>`)
      continue
    }
    if (line.startsWith('### ')) {
      closeList()
      out.push(`<h3>${escapeHtml(line.slice(4))}</h3>`)
      continue
    }
    if (line.startsWith('- ') || line.startsWith('* ')) {
      if (!inList) {
        out.push('<ul>')
        inList = true
      }
      out.push(`<li>${escapeHtml(line.slice(2))}</li>`)
      continue
    }
    closeList()
    out.push(`<p>${escapeHtml(line)}</p>`)
  }
  closeList()
  let html = out.join('')
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  html = html.replace(/\[([^[\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>')
  html = html.replace(/@@CODE_BLOCK_(\d+)@@/g, (_, idx) => codeBlocks[Number(idx)] || '')
  return html
}

const renderMessageHtml = (message: ChatMessage) => markdownToHtml(message.content || '')

const scrollToBottom = async () => {
  await nextTick()
  const el = messageListRef.value
  if (el) {
    el.scrollTop = el.scrollHeight
  }
}

const setMode = (mode: AssistantMode) => {
  if (loading.value || activeMode.value === mode) return
  activeMode.value = mode
  query.value = ''
  errorMessage.value = ''
  progressLogs.value = []
  messages.value = [createGreeting()]
}

const createNewChat = () => {
  messages.value = [
    {
      id: `m-${Date.now()}`,
      role: 'assistant',
      content: `${currentMode.value.label}已开启新会话。你可以继续围绕当前任务提问。`,
    },
  ]
  progressLogs.value = []
  errorMessage.value = ''
  query.value = ''
}

const usePrompt = async (prompt: string) => {
  query.value = prompt
  errorMessage.value = ''
  await nextTick()
  composerRef.value?.focus()
}

const applyStarterByIndex = (index: number) => {
  const target = starterPrompts.value[index]
  if (!target) return
  usePrompt(target.prompt)
}

const pushProgress = (message: string) => {
  const msg = message.trim()
  if (!msg) return
  const last = progressLogs.value[progressLogs.value.length - 1]
  if (last === msg) return
  progressLogs.value.push(msg)
  if (progressLogs.value.length > 6) {
    progressLogs.value = progressLogs.value.slice(-6)
  }
}

const buildModeAwareQuery = (userText: string) => `${currentMode.value.instruction}\n\n用户问题：${userText}`

const runResearch = async () => {
  const userText = query.value.trim()
  if (!userText || loading.value) return
  loading.value = true
  errorMessage.value = ''
  progressLogs.value = []
  query.value = ''
  messages.value.push({ id: `u-${Date.now()}`, role: 'user', content: userText })
  const statusId = `s-${Date.now()}`
  messages.value.push({ id: statusId, role: 'status', content: `正在以「${currentMode.value.label}」模式初始化执行链路...` })
  const renderStatusText = () => {
    const statusMessage = messages.value.find((item) => item.id === statusId)
    if (!statusMessage) return
    const latest = progressLogs.value.slice(-8)
    statusMessage.content = [`正在处理：${currentMode.value.label}`, ...latest].map((line) => `- ${line}`).join('\n')
  }
  renderStatusText()
  await scrollToBottom()
  try {
    const response = await fetch('/api/v1/research/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: buildModeAwareQuery(userText),
        user_id: userId.value.trim() || 'default_user',
        thread_id: threadId.value.trim() || 'default_thread',
        tenant_id: tenantId.value.trim() || 'default_tenant',
      }),
    })
    if (!response.ok) {
      const text = await response.text()
      throw new Error(text || `请求失败: ${response.status}`)
    }
    if (!response.body) {
      throw new Error('流式响应不可用')
    }
    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop() || ''
      for (const part of parts) {
        if (!part.startsWith('data: ')) continue
        const jsonText = part.slice(6).trim()
        if (!jsonText) continue
        const event = JSON.parse(jsonText) as StreamEvent
        if (event.type === 'status' || event.type === 'phase' || event.type === 'route') {
          const prefix = event.type === 'phase' && event.node ? `[${event.node}] ` : ''
          pushProgress(`${prefix}${event.message || ''}`)
          renderStatusText()
        }
        if (event.type === 'final') {
          messages.value = messages.value.filter((item) => item.id !== statusId)
          messages.value.push({
            id: `a-${Date.now()}`,
            role: 'assistant',
            content: event.final || '已完成，但服务端没有返回正文。',
          })
        }
        if (event.type === 'error') {
          throw new Error(event.message || '服务端执行异常')
        }
      }
      await scrollToBottom()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '请求失败'
    messages.value = messages.value.filter((item) => item.id !== statusId)
    messages.value.push({
      id: `e-${Date.now()}`,
      role: 'assistant',
      content: `请求失败：${errorMessage.value}`,
    })
  } finally {
    loading.value = false
    await scrollToBottom()
  }
}
</script>

<template>
  <div class="chat-shell">
    <aside class="chat-sidebar">
      <div class="sidebar-brand">
        <p class="brand-badge">AI Research Copilot</p>
        <h1>DeepResearch</h1>
        <p class="brand-desc">{{ currentMode.subtitle }}</p>
      </div>

      <div class="mode-switch">
        <p class="section-title">任务模式</p>
        <div class="mode-buttons">
          <button
            v-for="mode in assistantModes"
            :key="mode.key"
            class="mode-btn"
            :class="{ active: activeMode === mode.key }"
            :disabled="loading"
            @click="setMode(mode.key)"
          >
            {{ mode.label }}
          </button>
        </div>
      </div>

      <div class="sidebar-head">
        <button class="new-chat-btn" @click="createNewChat">新建会话</button>
      </div>

      <div class="quick-entry">
        <p class="section-title">推荐起手问题</p>
        <button
          v-for="item in starterPrompts.slice(0, 3)"
          :key="item.title"
          class="quick-entry-btn"
          @click="usePrompt(item.prompt)"
        >
          {{ item.title }}
        </button>
      </div>

      <div class="settings-group">
        <label>User ID</label>
        <input v-model="userId" class="sidebar-input" />
      </div>
      <div class="settings-group">
        <label>Thread ID</label>
        <input v-model="threadId" class="sidebar-input" />
      </div>
      <div class="settings-group">
        <label>Tenant ID</label>
        <input v-model="tenantId" class="sidebar-input" />
      </div>
      <p class="hint-text">当前模式：{{ currentMode.label }}；记忆键：{{ userId }} / {{ threadId }}</p>
    </aside>

    <main class="chat-main">
      <header class="main-header">
        <div>
          <h2>{{ currentMode.title }}</h2>
          <p>{{ currentMode.subtitle }}</p>
        </div>
        <div class="header-tags">
          <span v-for="tag in currentMode.tags" :key="tag">{{ tag }}</span>
        </div>
      </header>

      <div ref="messageListRef" class="message-list">
        <section v-if="messages.length <= 1" class="onboarding-panel">
          <div class="hero-panel">
            <p class="hero-badge">{{ currentMode.badge }}</p>
            <h3>先选任务模式，再让 Agent 自动规划、检索、分析和写报告</h3>
            <p class="hero-desc">
              当前任务会随请求发送给后端模型。你只需要说明目标、约束和期望输出，系统会自动进入对应的多 Agent 研究链路。
            </p>
            <div class="hero-actions">
              <button class="hero-btn primary" @click="applyStarterByIndex(0)">使用推荐问题</button>
              <button class="hero-btn" @click="applyStarterByIndex(1)">查看对比任务</button>
            </div>
            <div class="metric-grid">
              <article v-for="item in landingMetrics" :key="item.label">
                <p>{{ item.label }}</p>
                <strong>{{ item.value }}</strong>
              </article>
            </div>
          </div>

          <div class="capability-grid">
            <article v-for="item in capabilityHighlights" :key="item.title" class="capability-card">
              <h4>{{ item.title }}</h4>
              <p>{{ item.desc }}</p>
            </article>
          </div>

          <div class="guide-panel">
            <h4>提问建议</h4>
            <div class="guide-grid">
              <article>
                <h5>1. 说明目标</h5>
                <p>告诉系统你要做行业判断、文献综述、实验解释还是报告写作。</p>
              </article>
              <article>
                <h5>2. 提供上下文</h5>
                <p>补充时间范围、数据集、指标、竞品、业务限制或本地知识库内容。</p>
              </article>
              <article>
                <h5>3. 指定输出</h5>
                <p>例如表格对比、Markdown 报告、行动清单、论文式分析或引用来源。</p>
              </article>
            </div>
          </div>

          <div class="prompt-list">
            <button v-for="item in starterPrompts" :key="item.prompt" class="prompt-chip" @click="usePrompt(item.prompt)">
              {{ item.prompt }}
            </button>
          </div>
        </section>

        <div v-for="message in messages" :key="message.id" class="message-row" :class="`role-${message.role}`">
          <div class="avatar">{{ message.role === 'user' ? '我' : message.role === 'status' ? '...' : 'AI' }}</div>
          <div class="bubble markdown-body" v-html="renderMessageHtml(message)"></div>
        </div>
      </div>

      <div class="composer">
        <textarea
          v-model="query"
          ref="composerRef"
          class="composer-input"
          :disabled="loading"
          :placeholder="currentMode.placeholder"
          @keydown.enter.exact.prevent="runResearch"
        />
        <button class="send-btn" :disabled="loading || !query.trim()" @click="runResearch">
          {{ loading ? '处理中...' : '发送' }}
        </button>
      </div>
      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
    </main>
  </div>
</template>
