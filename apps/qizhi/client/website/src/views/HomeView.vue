<template>
  <div class="home-view" :style="{ backgroundImage: `url(${bgUrl})` }">
    <main class="home-main">
      <section class="home-snap-page home-snap-page--intro" aria-label="首页标题">
        <div class="home-snap-page-inner">
        <p v-if="oauthStatus === 'busy'" class="oauth-hint oauth-hint-busy">正在完成统一身份认证登录…</p>
        <p v-else-if="oauthStatus === 'error'" class="oauth-hint oauth-hint-err">登录失败，请稍后重试</p>

        <header class="home-intro">
          <div class="home-intro-text">
            <div class="home-intro-heading">
              <div class="home-logos-row">
                <img class="title-logos" :src="logosUrl" alt="" />
              </div>
            <div class="home-intro-title-row">
              <div class="title-cn">教师教学智能体<span class="home-beta-badge">内测版</span></div>
            </div>
              <div class="home-intro-en-block">
                <div class="title-en">Teaching Intelligent Agent</div>
                <div class="home-intro-cta-row">
              <button type="button" class="cta-btn" @click="handleExperience">
                <span class="cta-btn-label">开始体验 <span class="cta-btn-mentor">MENTOR AI</span></span>
                <svg class="cta-btn-arrow" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path
                    d="M5 12h14M13 6l6 6-6 6"
                    stroke="currentColor"
                    stroke-width="1.75"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </button>
                </div>
              </div>
            </div>
          </div>
        </header>

        <div class="home-intro-features" aria-label="核心功能">
          <template v-for="entry in introFeatureEntries" :key="entry.key">
            <article
              v-if="entry.key === 'my-courses'"
              id="course-version-card"
              class="intro-feature-card intro-feature-card--versioned"
            >
              <div class="intro-feature-card-head">
                <span class="intro-feature-card-icon" aria-hidden="true">
                  <svg
                    class="intro-feature-card-icon-svg"
                    viewBox="0 0 24 24"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                    aria-hidden="true"
                  >
                    <path
                      :d="entry.iconPath"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="1.5"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                  </svg>
                </span>
                <h3 class="intro-feature-card-title">{{ entry.title }}</h3>
              </div>
              <div class="intro-feature-card-body">
                <p class="intro-feature-card-desc">{{ entry.desc }}</p>
                <div class="course-version-actions" aria-label="选择课程版本">
                  <router-link
                    to="/lingzhi-entry"
                    class="course-version-action course-version-action--new"
                    aria-label="进入新版课程（灵知）"
                  >新版</router-link>
                  <router-link
                    to="/my-courses"
                    class="course-version-action course-version-action--classic"
                    aria-label="进入旧版课程（原启智课程）"
                  >旧版</router-link>
                </div>
              </div>
            </article>

            <router-link v-else :to="entry.to" class="intro-feature-card">
              <div class="intro-feature-card-head">
                <span class="intro-feature-card-icon" aria-hidden="true">
                  <svg
                    class="intro-feature-card-icon-svg"
                    viewBox="0 0 24 24"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                    aria-hidden="true"
                  >
                    <path
                      :d="entry.iconPath"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="1.5"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                  </svg>
                </span>
                <h3 class="intro-feature-card-title">{{ entry.title }}</h3>
              </div>
              <div class="intro-feature-card-body">
                <p class="intro-feature-card-desc">{{ entry.desc }}</p>
              </div>
            </router-link>
          </template>
        </div>
        </div>
      </section>

      <section class="home-snap-page home-snap-page--plaza" aria-label="智能体广场">
        <div class="home-snap-page-inner home-snap-page-inner--plaza">
        <div class="home-plaza-row">
          <section
            class="agent-market plaza-panel agent-market--full"
            :style="{ backgroundImage: `url(${marketBgUrl})` }"
            aria-label="智能体广场"
          >
            <div class="plaza-panel-main">
            <div class="plaza-panel-body">
          <div class="plaza-panel-left agent-market-left">
            <div class="plaza-panel-badge agent-market-badge">
              <svg class="plaza-panel-badge-icon agent-market-storefront" viewBox="0 0 24 24" aria-hidden="true">
                <path
                  fill="currentColor"
                  d="M5.06 3C4.63 3 4.22 3.14 3.84 3.42C3.46 3.7 3.24 4.06 3.14 4.5L2.11 8.91C1.86 10 2.06 10.92 2.69 11.73C2.81 11.85 2.93 11.97 3.04 12.07C3.63 12.64 4.28 13 5.22 13C6.16 13 6.91 12.59 7.47 12.05C8.1 12.67 8.86 13 9.8 13C10.64 13 11.44 12.63 12 12.07C12.68 12.7 13.45 13 14.3 13C15.17 13 15.91 12.67 16.54 12.05C17.11 12.62 17.86 13 18.81 13C19.76 13 20.43 12.65 21 12.06C21.09 11.97 21.18 11.87 21.28 11.77C21.94 10.95 22.14 10 21.89 8.91L20.86 4.5C20.73 4.06 20.5 3.7 20.13 3.42C19.77 3.14 19.38 3 18.94 3M18.89 4.97L19.97 9.38C20.06 9.81 19.97 10.2 19.69 10.55C19.44 10.86 19.13 11 18.75 11C18.44 11 18.17 10.9 17.95 10.66C17.73 10.43 17.61 10.16 17.58 9.84L16.97 5M5.06 5H7.03L6.42 9.84C6.3 10.63 5.91 11 5.25 11C4.84 11 4.53 10.86 4.31 10.55C4.03 10.2 3.94 9.81 4.03 9.38M9.05 5H11V9.7C11 10.05 10.89 10.35 10.64 10.62C10.39 10.88 10.08 11 9.7 11C9.36 11 9.07 10.88 8.84 10.59C8.61 10.3 8.5 10 8.5 9.66V9.5M13 5H14.95L15.5 9.5C15.58 9.92 15.5 10.27 15.21 10.57C14.95 10.87 14.61 11 14.2 11C13.89 11 13.61 10.88 13.36 10.62C13.11 10.35 13 10.05 13 9.7M3 14.03V19C3 20.11 3.89 21 5 21C9.67 21 14.33 21 19 21C20.1 21 21 20.11 21 19V14.05C20.45 14.63 19.75 14.96 19 15C18 15.03 17.25 14.74 16.54 14.05C15.94 14.65 15.14 15 14.3 15C13.4 15 12.6 14.64 12 14.07C11.43 14.64 10.65 15 9.78 15C8.87 15 8.07 14.65 7.47 14.05C6.89 14.64 6.1 15 5.23 15C4.33 15 3.66 14.65 3 14.03Z"
                />
              </svg>
              <span class="plaza-panel-badge-text agent-market-badge-text">AGENT MARKETPLACE</span>
            </div>
            <div class="plaza-panel-title agent-market-title">
              智能体广场<br/>
              探索更多使用场景
            </div>

            <p class="plaza-panel-desc agent-market-desc">
              Discover a new paradigm of teaching for the AI era, empowering educators to enhance teaching quality and
              efficiency.
            </p>

            <div class="agent-market-actions">
              <a
                class="agent-market-apply-btn"
                href="https://wj.qq.com/s2/25037129/b805/"
                target="_blank"
                rel="noopener noreferrer"
              >
                <span>提交入驻申请</span>
                <svg class="agent-market-arrow" viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    fill="currentColor"
                    d="M13.2 5.6a1 1 0 0 0 0 1.4l4.99 5H4.5a1 1 0 1 0 0 2h13.69l-4.99 5a1 1 0 1 0 1.42 1.4l6.7-6.7a1 1 0 0 0 0-1.4l-6.7-6.7a1 1 0 0 0-1.42 0Z"
                  />
                </svg>
              </a>
              <div class="agent-market-actions-gap" aria-hidden="true"></div>
              <button type="button" class="agent-market-link" @click="onPlazaMoreClick">
                <span>查看更多</span>
                <svg class="agent-market-arrow" viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    fill="currentColor"
                    d="M13.2 5.6a1 1 0 0 0 0 1.4l4.99 5H4.5a1 1 0 1 0 0 2h13.69l-4.99 5a1 1 0 1 0 1.42 1.4l6.7-6.7a1 1 0 0 0 0-1.4l-6.7-6.7a1 1 0 0 0-1.42 0Z"
                  />
                </svg>
              </button>
            </div>
          </div>

          <div
            ref="agentMarketRightRef"
            class="plaza-panel-right agent-market-right"
            aria-label="智能体卡片"
          >
            <button
              v-for="card in previewAgentCards"
              :key="card.id"
              type="button"
              class="agent-card"
              @click="handleAgentCardClick(card)"
            >
              <div class="agent-card-main">
                <div class="agent-card-badge" :style="{ backgroundColor: card.badgeBg }" aria-hidden="true">
                  <svg class="agent-card-badge-icon" viewBox="0 0 24 24" :style="{ color: card.badgeFg }">
                    <path fill="currentColor" :d="card.iconPath" />
                  </svg>
                </div>

                <div class="agent-card-body">
                  <div class="agent-card-header">
                    <div class="agent-card-title">{{ card.title }}</div>
                    <div v-if="showPopular && card.popular" class="agent-card-popular">POPULAR</div>
                  </div>

                  <div class="agent-card-desc">
                    {{ card.desc }}
                  </div>

                  <div v-if="showHashtags" class="agent-card-tags" aria-label="hashtags">
                    <span v-for="tag in card.tags" :key="tag" class="agent-card-tag">{{ tag }}</span>
                  </div>
                </div>
              </div>
            </button>
          </div>
            </div>
            </div>
          </section>
        </div>
        </div>
      </section>

      <section class="home-snap-page home-snap-page--oss" aria-label="开源社区支持">
        <div class="home-snap-page-inner home-snap-page-inner--oss">
        <section class="oss-support" aria-label="开源社区支持">
          <img class="oss-bg oss-bg-lb" :src="lbBlurUrl" alt="" aria-hidden="true" />
          <img class="oss-bg oss-bg-rt" :src="rtBlurUrl" alt="" aria-hidden="true" />
          <img class="oss-bg oss-bg-wave" :src="waveUrl" alt="" aria-hidden="true" />

          <div class="oss-content">
            <div class="oss-title">
              <img class="oss-icon" :src="opensourceIconUrl" alt="" aria-hidden="true" />
              <div class="oss-title-cn">开源社区支持</div>
              <p class="oss-title-en">
                EduEnhance thrives on community collaboration. Join our open-source initiative to build better tools for
                educators worldwide. Contribute, learn, and grow with us.
              </p>
            </div>

            <div class="oss-links" aria-label="浙大智海 Mo">
              <a
                class="oss-btn oss-btn-mo"
                href="https://mo.zju.edu.cn/"
                target="_blank"
                rel="noopener noreferrer"
              >
                <img class="oss-btn-mo-logo" :src="moLogoUrl" alt="" aria-hidden="true" />
                <span>浙大智海Mo</span>
              </a>
            </div>
          </div>
        </section>
        </div>
      </section>
    </main>

    <footer class="home-footer" aria-label="页脚">
      <div class="footer-logos">
        <img class="footer-logo-img" :src="logoUndergraduateUrl" alt="浙江大学本科生院" />
        <span class="footer-logo-divider" aria-hidden="true"></span>
        <img class="footer-logo-img" :src="logoChaoxingUrl" alt="超星" />
      </div>
      <div class="footer-text">
        <span>技术支持：北京世纪超星信息技术发展有限责任公司</span>
        <span>Copyright© 2026 浙江大学本科生院 版权所有</span>
      </div>
    </footer>

    <Teleport to="body">
      <div
        v-if="showAgentMore"
        class="teaching-more-overlay"
        @click.self="closeAgentMore"
      >
        <div
          class="teaching-more-panel teaching-more-panel--agents"
          :style="agentMorePanelStyle"
          role="dialog"
          aria-modal="true"
          aria-labelledby="agent-more-title"
        >
          <header class="teaching-more-header">
            <h3 id="agent-more-title" class="teaching-more-title">更多智能体</h3>
            <button
              type="button"
              class="teaching-more-close"
              aria-label="关闭"
              @click="closeAgentMore"
            >
              &times;
            </button>
          </header>
          <p class="teaching-more-subtitle">探索更多教学智能体能力</p>
          <div
            class="teaching-more-agents-grid"
            :class="{ 'is-metrics-synced': agentMoreMetricsReady }"
            :style="agentMoreGridStyle"
            role="list"
          >
            <button
              v-for="card in moreAgentCards"
              :key="card.id"
              type="button"
              class="agent-card agent-card--in-more"
              role="listitem"
              @click="onAgentMoreCardClick(card)"
            >
              <div class="agent-card-main">
                <div class="agent-card-badge" :style="{ backgroundColor: card.badgeBg }" aria-hidden="true">
                  <svg class="agent-card-badge-icon" viewBox="0 0 24 24" :style="{ color: card.badgeFg }">
                    <path fill="currentColor" :d="card.iconPath" />
                  </svg>
                </div>
                <div class="agent-card-body">
                  <div class="agent-card-header">
                    <div class="agent-card-title">{{ card.title }}</div>
                    <div v-if="showPopular && card.popular" class="agent-card-popular">POPULAR</div>
                  </div>
                  <div class="agent-card-desc">
                    {{ card.desc }}
                  </div>
                  <div v-if="showHashtags" class="agent-card-tags" aria-label="hashtags">
                    <span v-for="tag in card.tags" :key="tag" class="agent-card-tag">{{ tag }}</span>
                  </div>
                </div>
              </div>
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchPublicAgents, visitAgent } from '../api/agents'
import type { PublicAgentDetail } from '../api/types'
import { exchangeOAuthCodeForSession } from '../composables/useOAuthSession'
import { extractOAuthCodeFromRoute } from '../utils/oauthQuery'
import { CHAOXING_PPT_COURSEWARE_URL } from '../utils/chaoxingPpt'
import bgUrl from '../../image_materials/image 1.png'
import logoUndergraduateUrl from '../../image_materials/logo_undergraduate.png'
import logoChaoxingUrl from '../../image_materials/logo_chaoxing.png'
import logosUrl from '../../image_materials/logos2.png'
import marketBgUrl from '../../image_materials/market_bg.png'
import lbBlurUrl from '../../image_materials/LB_blur.png'
import rtBlurUrl from '../../image_materials/RT_blur.png'
import waveUrl from '../../image_materials/wave.png'
import opensourceIconUrl from '../../image_materials/opensource_icon.png'
import moLogoUrl from '../../image_materials/mo_logo.png'

const route = useRoute()
const router = useRouter()
const previewPath = ref('')
const oauthStatus = ref<'idle' | 'busy' | 'error'>('idle')
const oauthError = ref('')
const chaoxingPptUrl = CHAOXING_PPT_COURSEWARE_URL

const DOCUMENT_LINE_ICON =
  'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zM9 9h6M9 13h6M9 17h4'

type IntroFeatureEntry = {
  key: string
  to: string
  title: string
  desc: string
  iconPath: string
}

/** 首页第一屏核心功能入口（全员展示；进入各页后的权限由路由 meta / 守卫控制） */
const introFeatureEntries: IntroFeatureEntry[] = [
  {
    key: 'my-courses',
    to: '/my-courses',
    title: '我的课程',
    desc: '进入新版灵知课程空间，或继续使用原启智课程。',
    iconPath: 'M6 3h12v18H6zM9 7.5h6M9 11h6M9 14.5h4',
  },
  {
    key: 'chat',
    to: '/chat',
    title: '智能对话',
    desc: '与教学智能体自然语言交流，辅助备课、答疑与思路拓展。',
    iconPath: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z',
  },
  {
    key: 'resource-analysis',
    to: '/resource-analysis',
    title: '资源分析',
    desc: '对教学资源做结构化分析与可视化报告，把握内容要点。',
    iconPath: 'M3 20h18M7 20V11M12 20V7M17 20V14',
  },
]

const showAgentMore = ref(false)
const agentMarketRightRef = ref<HTMLElement | null>(null)
/** 从广场主区实测的卡片尺寸，供「更多」弹窗与外侧网格对齐 */
const agentMoreMetrics = ref({ width: 0, height: 0, gap: 14 })

function syncAgentCardMetrics() {
  const grid = agentMarketRightRef.value
  if (!grid) return
  const card = grid.querySelector('.agent-card') as HTMLElement | null
  if (!card) return
  const rect = card.getBoundingClientRect()
  if (rect.width < 1 || rect.height < 1) return
  const gapRaw = getComputedStyle(grid).gap
  const gap = gapRaw ? parseFloat(gapRaw) || 14 : 14
  agentMoreMetrics.value = {
    width: Math.round(rect.width),
    height: Math.round(rect.height),
    gap: Math.round(gap),
  }
}

const agentMoreGridStyle = computed(() => {
  const { width, height, gap } = agentMoreMetrics.value
  if (!width || !height) return undefined
  return {
    '--agent-card-measured-w': `${width}px`,
    '--agent-card-measured-h': `${height}px`,
    '--agent-card-measured-gap': `${gap}px`,
    width: `${width * 2 + gap}px`,
  }
})

const agentMorePanelStyle = computed(() => {
  const { width, gap } = agentMoreMetrics.value
  if (!width) return undefined
  const contentW = width * 2 + gap
  return {
    width: `min(${contentW + 44}px, calc(100vw - 32px))`,
  }
})

const agentMoreMetricsReady = computed(
  () => agentMoreMetrics.value.width > 0 && agentMoreMetrics.value.height > 0
)

/** 智能体广场主区域最多展示 6 张（2 列 × 3 行） */
const AGENT_PLAZA_PREVIEW_COUNT = 6

type AgentCard = {
  id: string
  title: string
  desc: string
  tags: string[]
  popular?: boolean
  badgeBg: string
  badgeFg: string
  iconPath: string
  href?: string
  to?: string
  cardKey?: string
}

/** 首页智能体广场置顶：论文分析（固定第一位，在 SOL 模拟器等 API 卡片之前） */
const ESSAY_AGENT_FRONT_CARD: AgentCard = {
  id: '__front-essay-check__',
  title: '论文分析',
  desc: '上传论文，进行格式与内容相关检查，集中管理分析任务。',
  tags: [],
  badgeBg: 'rgba(245, 237, 230, 1)',
  badgeFg: '#8a5528',
  iconPath: DOCUMENT_LINE_ICON,
  to: '/essay-check',
  cardKey: 'essay-check',
}

const agentCards = ref<AgentCard[]>([])

function isEssayCheckAgent(card: { title: string; cardKey?: string }): boolean {
  return card.cardKey === 'essay-check' || card.title === '论文分析'
}

function mapAgent(detail: PublicAgentDetail): AgentCard {
  return {
    id: detail.id,
    title: detail.title,
    desc: detail.description,
    tags: detail.tags || [],
    popular: Boolean(detail.popular),
    badgeBg: detail.badge_bg,
    badgeFg: detail.badge_fg,
    iconPath: detail.icon_path,
    href: detail.href ?? undefined,
    to: detail.route_to ?? undefined,
    cardKey: detail.card_key ?? undefined,
  }
}

async function loadAgents() {
  try {
    const list = await fetchPublicAgents()
    agentCards.value = list.map(mapAgent)
  } catch (e) {
    if (typeof console !== 'undefined') {
      console.warn('[HomeView] 拉取智能体广场失败，将展示空列表', e)
    }
    agentCards.value = []
  }
  await nextTick()
  syncAgentCardMetrics()
}

const allAgentCards = computed(() => {
  const rest = agentCards.value.filter((c) => !isEssayCheckAgent(c))
  return [ESSAY_AGENT_FRONT_CARD, ...rest]
})

const previewAgentCards = computed(() =>
  allAgentCards.value.slice(0, AGENT_PLAZA_PREVIEW_COUNT),
)

const moreAgentCards = computed(() =>
  allAgentCards.value.slice(AGENT_PLAZA_PREVIEW_COUNT),
)

const showPopular = false
const showHashtags = false

async function onPlazaMoreClick() {
  syncAgentCardMetrics()
  showAgentMore.value = true
  await nextTick()
  syncAgentCardMetrics()
  requestAnimationFrame(() => syncAgentCardMetrics())
}

function closeAgentMore() {
  showAgentMore.value = false
}

function onAgentMoreCardClick(card: AgentCard) {
  handleAgentCardClick(card)
  closeAgentMore()
}

function onPlazaMoreKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    closeAgentMore()
  }
}

watch(showAgentMore, async (agentOpen) => {
  if (typeof window === 'undefined') return
  if (agentOpen) {
    window.addEventListener('keydown', onPlazaMoreKeydown)
    window.addEventListener('resize', syncAgentCardMetrics)
    await nextTick()
    syncAgentCardMetrics()
    requestAnimationFrame(() => syncAgentCardMetrics())
  } else {
    window.removeEventListener('keydown', onPlazaMoreKeydown)
    window.removeEventListener('resize', syncAgentCardMetrics)
  }
})

onUnmounted(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('keydown', onPlazaMoreKeydown)
  }
})

function handleAgentCardClick(card: AgentCard) {
  if (!card.id.startsWith('__front-')) {
    visitAgent(card.id)
  }
  if (card.href) {
    window.open(card.href, '_blank', 'noopener,noreferrer')
    return
  }
  router.push(card.to ?? '/')
}

onMounted(async () => {
  loadAgents()

  const err = typeof route.query.error === 'string' ? route.query.error : ''
  const errDesc =
    typeof route.query.error_description === 'string' ? route.query.error_description : ''
  if (err) {
    oauthStatus.value = 'error'
    oauthError.value = errDesc ? `${err}：${errDesc}` : err
    return
  }

  const code = extractOAuthCodeFromRoute(route)
  if (!code) return

  oauthStatus.value = 'busy'
  try {
    await exchangeOAuthCodeForSession(code)
    const q = { ...route.query } as Record<string, string | string[] | undefined | null>
    delete q.code
    delete q.state
    delete q.error
    delete q.error_description
    await router.replace({ path: '/', query: q })
    oauthStatus.value = 'idle'
  } catch (e) {
    oauthStatus.value = 'error'
    console.error('[OAuth] 统一身份认证登录失败', e)
    oauthError.value = 'failed'
  }

})

function handlePreviewChange(e: Event) {
  const el = e.target as HTMLSelectElement
  const value = el.value
  previewPath.value = value
  if (!value) return
  if (/^https?:\/\//i.test(value)) {
    window.open(value, '_blank', 'noopener,noreferrer')
    el.value = ''
    previewPath.value = ''
    return
  }
  router.push(value)
}

function handleExperience() {
  const card = document.getElementById('course-version-card')
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  card?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'center' })
  window.setTimeout(() => {
    card?.querySelector<HTMLElement>('.course-version-action--new')?.focus()
  }, reduceMotion ? 0 : 220)
}
</script>

<style scoped>
.home-view {
  --home-nav-height: 64px;
  --home-content-pad-top: 166px;
  --home-content-pad-bottom: 223px;
  --home-section-gap: 150px;
  --home-snap-pad-x: 48px;
  --agent-card-gap: 14px;
  width: 100%;
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  background-repeat: no-repeat;
  background-size: cover;
  background-position: center;
  background-attachment: fixed;
}

.home-main {
  flex: 1 0 auto;
  width: 100%;
  box-sizing: border-box;
  padding-top: var(--home-content-pad-top);
  padding-bottom: var(--home-content-pad-bottom);
  display: flex;
  flex-direction: column;
}

.home-main > .home-snap-page + .home-snap-page {
  margin-top: var(--home-section-gap);
}

.home-snap-page {
  box-sizing: border-box;
  width: 100%;
  padding: 0 var(--home-snap-pad-x);
  display: flex;
  flex-direction: column;
}

.home-snap-page--intro {
  justify-content: flex-start;
}

.home-snap-page-inner {
  width: 92%;
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  flex: 0 0 auto;
  min-height: 0;
  box-sizing: border-box;
}

.home-intro {
  width: 100%;
}

.oauth-hint {
  width: 100%;
  margin: 0 0 16px 0;
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.5;
}
.oauth-hint-busy {
  background: rgba(255, 255, 255, 0.55);
  border: 1px solid rgba(0, 85, 255, 0.25);
  color: #333;
}
.oauth-hint-err {
  background: rgba(211, 47, 47, 0.08);
  border: 1px solid rgba(211, 47, 47, 0.35);
  color: #c62828;
}

.preview-bar {
  width: 100%;
  margin: 0 0 18px 0;
}

.preview-select {
  width: 260px;
  height: 40px;
  padding: 0 12px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.45);
  background: rgba(255, 255, 255, 0.35);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  color: #333;
  font-size: 14px;
  outline: none;
}

.preview-select:focus {
  border-color: rgba(0, 85, 255, 0.5);
}

.home-logos-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 28px 0;
}

.title-logos {
  display: block;
  height: 45px;
  object-fit: contain;
  object-position: left center;
  margin: 0;
}

.home-beta-badge {
  display: inline-flex;
  align-items: center;
  vertical-align: super;
  margin-left: 10px;
  height: 28px;
  padding: 0 10px;
  font-size: 16px;
  font-weight: 600;
  color: #e67e22;
  background: rgba(255, 255, 255, 0.85);
  border: 1.5px solid rgba(230, 126, 34, 0.4);
  border-radius: 4px;
  white-space: nowrap;
  letter-spacing: 0.5px;
  line-height: 1;
}

.title-cn {
  font-size: 50px;
  font-weight: 700;
  color: #003F89;
  margin: 0;
  line-height: 1.5;
  letter-spacing: 0.2px;
}

.title-en {
  font-size: 30px;
  font-weight: 700;
  color: rgba(0, 63, 137, 0.65);
  line-height: 1.35;
  margin: 0;
  white-space: normal;
}

.home-intro {
  width: 100%;
}

.home-intro-text {
  position: relative;
  width: 100%;
}

.home-intro-heading {
  width: 100%;
}

.home-intro-title-row {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 24px;
  flex-wrap: wrap;
  margin: 0 0 0 0;
}

.home-intro-en-block {
  display: flex;
  flex-direction: row;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  width: 100%;
  margin-top: 0;
}

.home-intro-en-block .title-en {
  flex: 1 1 auto;
  min-width: 0;
}

.home-intro-cta-row {
  display: flex;
  flex-shrink: 0;
  justify-content: flex-end;
  align-items: flex-end;
  width: auto;
  margin: 0;
}

.home-snap-page--intro .home-snap-page-inner {
  justify-content: flex-start;
  gap: 100px;
}

.home-intro-features {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: clamp(12px, 1.4vw, 20px);
  width: 100%;
  flex: 0 0 auto;
}

.intro-feature-card {
  box-sizing: border-box;
  min-height: 200px;
  height: 200px;
  width: 100%;
  justify-self: stretch;
  padding: 24px;
  border-radius: 12px;
  background: #fff;
  border: 1px solid rgba(255, 255, 255, 0.92);
  text-decoration: none;
  color: inherit;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  overflow: hidden;
  box-shadow: 0 2px 12px rgba(19, 88, 228, 0.06);
  transition:
    transform 0.22s cubic-bezier(0.22, 1, 0.36, 1),
    box-shadow 0.22s ease,
    border-color 0.22s ease;
}

.intro-feature-card-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.intro-feature-card-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  color: #3d51e3;
}

.intro-feature-card-icon-svg {
  width: 28px;
  height: 28px;
  display: block;
  transition: transform 0.22s cubic-bezier(0.22, 1, 0.36, 1);
}

.intro-feature-card-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: #333;
  line-height: 1.35;
  letter-spacing: 0.02em;
}

.intro-feature-card-body {
  margin-top: 15px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  text-align: left;
  flex: 1;
  min-height: 0;
}

.intro-feature-card-desc {
  margin: 0;
  font-size: 16px;
  font-weight: 300;
  line-height: 1.55;
  color: rgba(17, 17, 17, 0.78);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.intro-feature-card:hover {
  transform: translateY(-5px);
  border-color: rgba(61, 81, 227, 0.28);
  box-shadow:
    0 14px 36px rgba(61, 81, 227, 0.16),
    0 0 0 1px rgba(61, 81, 227, 0.08);
}

.intro-feature-card:hover .intro-feature-card-icon-svg {
  transform: scale(1.08);
}

.intro-feature-card:hover .intro-feature-card-title {
  color: #3d51e3;
}

.intro-feature-card:active {
  transform: translateY(-2px);
  box-shadow: 0 8px 22px rgba(61, 81, 227, 0.12);
}

.intro-feature-card:focus-visible {
  outline: 2px solid rgba(61, 81, 227, 0.5);
  outline-offset: 3px;
}

.intro-feature-card--versioned {
  cursor: default;
}

.intro-feature-card--versioned .intro-feature-card-desc {
  -webkit-line-clamp: 2;
  line-clamp: 2;
}

.intro-feature-card--versioned:active {
  transform: translateY(-5px);
}

.course-version-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  width: 100%;
  margin-top: auto;
  padding-top: 14px;
}

.course-version-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 38px;
  padding: 0 14px;
  border: 1px solid transparent;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  line-height: 1;
  text-decoration: none;
  transition:
    background-color 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease;
}

.course-version-action--new {
  background: #3d51e3;
  color: #fff;
  box-shadow: 0 4px 12px rgba(61, 81, 227, 0.2);
}

.course-version-action--new:hover {
  background: #3042c7;
}

.course-version-action--classic {
  border-color: rgba(61, 81, 227, 0.28);
  background: #fff;
  color: #3d51e3;
}

.course-version-action--classic:hover {
  border-color: rgba(61, 81, 227, 0.52);
  background: rgba(61, 81, 227, 0.06);
}

.course-version-action:focus-visible {
  outline: 2px solid rgba(61, 81, 227, 0.58);
  outline-offset: 2px;
}

.cta-btn {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-width: 291px;
  height: 48px;
  padding: 0 28px;
  margin: 0;
  border-radius: 999px;
  border: none;
  background: #3d51e3;
  color: #fff;
  font-size: 15px;
  font-weight: 300;
  letter-spacing: 0.02em;
  cursor: pointer;
  box-shadow: 0 8px 24px rgba(61, 81, 227, 0.35);
  transition:
    box-shadow 0.2s,
    transform 0.12s,
    background 0.2s,
    filter 0.2s;
}

.cta-btn-label {
  line-height: 1.2;
  white-space: nowrap;
  font-weight: 300;
}

.cta-btn-mentor {
  font-weight: 300;
  letter-spacing: 0.06em;
}

.cta-btn-arrow {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  color: #fff;
  transition: transform 0.2s ease;
}

.cta-btn:hover {
  background: #4a5fe8;
  box-shadow: 0 10px 28px rgba(61, 81, 227, 0.42);
  filter: brightness(1.03);
}

.cta-btn:hover .cta-btn-arrow {
  transform: translateX(3px);
}

.cta-btn:active {
  transform: translateY(1px);
  box-shadow: 0 6px 18px rgba(61, 81, 227, 0.32);
}

.cta-btn:focus-visible {
  outline: 2px solid rgba(255, 255, 255, 0.9);
  outline-offset: 3px;
}

.home-plaza-row {
  width: 100%;
  margin-top: 0;
  display: flex;
  flex-direction: row;
  align-items: stretch;
  gap: 20px;
  box-sizing: border-box;
  flex: 1;
  min-height: 0;
}

.plaza-panel {
  position: relative;
  flex: 1 1 0;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-radius: 18px;
  background-repeat: no-repeat;
  background-size: cover;
  background-position: center;
  background-color: rgba(255, 255, 255, 0.6);
  box-shadow: 0 18px 44px rgba(25, 35, 70, 0.12);
  overflow: hidden;
  padding: 22px 20px 52px;
  box-sizing: border-box;
}

.plaza-panel-main {
  flex: 1 1 auto;
  min-height: 0;
  width: 100%;
  display: flex;
  align-items: center;
}

.plaza-panel-main > .plaza-panel-body {
  width: 100%;
}

.plaza-panel-body {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 18px;
  min-height: 0;
}

.plaza-panel-left {
  flex: 0 0 auto;
  width: 100%;
  max-width: none;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
}

.plaza-panel-right {
  flex: 1 1 auto;
  min-width: 0;
  width: 100%;
}

.plaza-panel-badge {
  flex: 0 0 auto;
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: #86aaf2;
  margin-bottom: 0;
}

.plaza-panel-badge-icon {
  width: 22px;
  height: 22px;
  flex: 0 0 auto;
}

.plaza-panel-badge-text {
  font-size: 14px;
  letter-spacing: 0.8px;
  font-weight: 600;
}

.plaza-panel-title {
  font-size: 28px;
  margin-top: 0;
  font-weight: 700;
  color: #111;
  line-height: 1.2;
  margin-bottom: 12px;
}

.plaza-panel-desc {
  margin: 12px 0 0;
  max-width: 520px;
  font-size: 16px;
  font-weight: 400;
  line-height: 1.6;
  color: rgba(17, 17, 17, 0.82);
}

.agent-market {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.agent-market .plaza-panel-badge {
  margin-bottom: 24px;
}

.agent-market-left {
  justify-content: flex-start;
  gap: 0;
  height: 100%;
  min-height: 0;
}

.agent-market-title {
  margin-top: 0;
  margin-bottom: 12px;
}

.agent-market-desc {
  max-width: 100%;
  margin-top: 12px;
  margin-bottom: 24px;
}

.agent-market--full {
  flex: 1 1 100%;
  width: 100%;
  max-width: 100%;
  height: 537px;
  min-height: 537px;
  max-height: 537px;
  padding: 0 48px;
  box-sizing: border-box;
  overflow: hidden;
}

.agent-market--full .plaza-panel-main {
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
  align-items: stretch;
  box-sizing: border-box;
  height: 100%;
  padding: 47px 0 62px;
}

.agent-market--full .plaza-panel-body {
  min-height: 0;
  height: 100%;
}

.agent-market--full .agent-market-right {
  overflow-x: hidden;
}

.agent-market--full .agent-card {
  width: 100%;
  height: 100%;
  min-height: 0;
  max-height: none;
  overflow: hidden;
}

@media (min-width: 900px) {
  .agent-market--full .agent-market-right {
    height: 100%;
    max-height: 100%;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    grid-template-rows: repeat(3, minmax(0, 1fr));
    gap: var(--agent-card-gap);
    justify-items: stretch;
    align-content: stretch;
    overflow: hidden;
  }
}

@media (max-width: 899px) {
  .agent-market--full .agent-market-right {
    overflow-y: auto;
    align-content: start;
    grid-template-rows: none;
  }
}

@media (min-width: 1100px) {
  .home-plaza-row .plaza-panel-body {
    flex-direction: row;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
  }

  .home-plaza-row .plaza-panel-left {
    flex: 0 1 38%;
    max-width: 38%;
  }

  .agent-market .plaza-panel-body {
    gap: 32px;
    justify-content: flex-start;
    align-items: stretch;
  }

  .agent-market .agent-market-left {
    flex: 0 0 auto;
    width: auto;
    max-width: 300px;
    align-self: stretch;
    height: 100%;
  }

  .agent-market .agent-market-right {
    flex: 1 1 auto;
    min-width: 0;
    height: 100%;
    align-self: stretch;
  }
}

.home-feature-frame {
  flex: 1 1 auto;
  width: 100%;
  min-width: 0;
  display: grid;
  grid-template-columns: 1fr;
  gap: 14px;
  align-content: center;
  padding: 0;
  box-sizing: border-box;
  background: transparent;
  border: none;
  box-shadow: none;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  overflow: visible;
}

@media (min-width: 900px) {
  .home-feature-frame {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.feature-entry-card {
  height: 196px;
  width: 100%;
  border: 1px solid rgba(255, 255, 255, 0.85);
  background: rgba(255, 255, 255, 0.92);
  border-radius: 18px;
  padding: 18px 16px 14px;
  text-align: center;
  text-decoration: none;
  color: inherit;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  gap: 0;
  box-sizing: border-box;
  transition: transform 0.08s, background-color 0.2s, border-color 0.2s, box-shadow 0.2s;
}

button.feature-entry-card {
  font: inherit;
}

.feature-entry-card:hover {
  background: rgba(255, 255, 255, 0.96);
  border-color: rgba(255, 255, 255, 0.98);
  box-shadow: 0 10px 24px rgba(25, 35, 70, 0.12);
}

.feature-entry-card:active {
  transform: translateY(1px);
}

.feature-entry-card:focus-visible {
  outline: 2px solid rgba(0, 85, 255, 0.45);
  outline-offset: 3px;
}

.feature-entry-card--no-nav:active {
  transform: translateY(1px);
}

.feature-entry-icon {
  width: 52px;
  height: 52px;
  flex: 0 0 auto;
  border-radius: 12px;
  display: grid;
  place-items: center;
  margin-bottom: 10px;
}

.feature-entry-icon-svg {
  width: 28px;
  height: 28px;
  display: block;
}

.feature-entry-header {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  flex: 0 0 auto;
}

.feature-entry-title {
  width: 100%;
  font-size: 16px;
  font-weight: 700;
  color: #111;
  line-height: 1.3;
  text-align: center;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.feature-entry-divider {
  width: 72%;
  max-width: 140px;
  height: 1px;
  margin: 10px 0;
  flex: 0 0 auto;
  background: rgba(17, 17, 17, 0.12);
}

.feature-entry-desc {
  margin: 0;
  width: 100%;
  flex: 1 1 auto;
  min-height: 0;
  font-size: 13px;
  font-weight: 300;
  line-height: 1.5;
  text-align: center;
  color: rgba(17, 17, 17, 0.72);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.teaching-more-overlay {
  position: fixed;
  inset: 0;
  z-index: 1100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  box-sizing: border-box;
  background: rgba(15, 23, 42, 0.38);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}

.teaching-more-panel {
  width: min(420px, 100%);
  padding: 22px 22px 18px;
  border-radius: 18px;
  background: linear-gradient(
    165deg,
    rgba(255, 255, 255, 0.98) 0%,
    rgba(236, 244, 255, 0.95) 100%
  );
  border: 1px solid rgba(255, 255, 255, 0.9);
  box-shadow:
    0 24px 56px rgba(25, 35, 70, 0.18),
    0 0 0 1px rgba(0, 85, 255, 0.08) inset;
  box-sizing: border-box;
}

.teaching-more-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}

.teaching-more-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: #111;
  line-height: 1.3;
}

.teaching-more-close {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  padding: 0;
  border: none;
  border-radius: 8px;
  background: rgba(0, 63, 137, 0.06);
  color: #666;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
  transition: background-color 0.2s, color 0.2s;
}

.teaching-more-close:hover {
  background: rgba(0, 85, 255, 0.1);
  color: #333;
}

.teaching-more-subtitle {
  margin: 0 0 16px;
  font-size: 13px;
  color: rgba(17, 17, 17, 0.62);
  line-height: 1.5;
}

.teaching-more-panel .feature-entry-card {
  margin: 0;
  height: auto;
  min-height: 176px;
}

.teaching-more-footnote {
  margin: 12px 0 0;
  font-size: 12px;
  color: rgba(17, 17, 17, 0.5);
  text-align: center;
  line-height: 1.45;
}

.teaching-more-panel--agents {
  width: min(calc(100vw - 32px), 100%);
  max-height: min(82vh, 720px);
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}

.teaching-more-agents-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: var(--agent-card-measured-h, auto);
  gap: var(--agent-card-measured-gap, var(--agent-card-gap));
  align-content: start;
  justify-content: center;
  overflow-y: auto;
  max-height: min(58vh, 520px);
  padding-right: 4px;
  margin-right: -4px;
  box-sizing: border-box;
  max-width: 100%;
}

/* 与 .agent-market--full .agent-card 相同：填满网格单元格 */
.teaching-more-agents-grid .agent-card {
  width: 100%;
  height: 100%;
  min-height: 0;
  max-height: none;
  overflow: hidden;
}

.teaching-more-agents-grid:not(.is-metrics-synced) .agent-card {
  min-height: 108px;
  height: auto;
}

.agent-market {
  margin-top: 0;
}

.oss-support {
  width: 100%;
  margin-top: 0;
  flex: 1 1 auto;
  min-height: 0;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.6);
  box-shadow: 0 18px 44px rgba(25, 35, 70, 0.12);
  overflow: hidden;
  position: relative;
  padding: 28px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
}

.oss-bg {
  position: absolute;
  pointer-events: none;
  user-select: none;
  opacity: 1;
}
.oss-bg-lb {
  left: -12px;
  bottom: -18px;
  width: 360px;
  height: auto;
  opacity: 0.9;
}
.oss-bg-rt {
  right: -12px;
  top: -16px;
  width: 360px;
  height: auto;
  opacity: 0.9;
}
.oss-bg-wave {
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 100%;
  height: auto;
  opacity: 0.65;
}

.oss-content {
  position: relative;
  z-index: 1;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 50px;
}

.oss-icon {
  width: 37px;
  object-fit: contain;
  margin: 0 auto 10px;
  display: block;
}
.oss-title-cn {
  font-size: 24px;
  margin-top: 20px;
  font-weight: 700;
  color: #111;
  line-height: 1.2;
  margin-bottom: 12px;
}
.oss-title-en {
  margin: 0;
  max-width: 500px;
  font-size: 16px;
  line-height: 1.7;
  color: #494552;
  white-space: pre-line;
}

.oss-links {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  flex-wrap: wrap;
}
.oss-btn {
  height: 44px;
  min-width: 148px;
  padding: 0 18px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  text-decoration: none;
  font-size: 14px;
  font-weight: 700;
  box-shadow: 0 10px 22px rgba(17, 28, 45, 0.12);
  transition: transform 0.05s, filter 0.2s;
}
.oss-btn:active {
  transform: translateY(1px);
}
.oss-btn-mo-logo {
  width: 22px;
  height: 22px;
  object-fit: contain;
  flex: 0 0 auto;
  display: block;
}
.oss-btn-mo {
  background: #ecf1ff;
  color: #263143;
}
.oss-btn:hover {
  filter: brightness(1.02);
}

/* agent-market-left 等复用 .plaza-panel-*，保留别名便于覆盖 */

.agent-market-actions {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  align-items: flex-start;
  gap: 0;
  margin-top: 0;
  min-height: 0;
  width: 100%;
}

.agent-market-actions-gap {
  flex: 1 1 auto;
  min-height: 74px;
  width: 100%;
}

.agent-market-apply-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  box-sizing: border-box;
  min-width: 132px;
  height: 40px;
  padding: 0 18px;
  margin-top: 0;
  border: 1px solid #86aaf2;
  border-radius: 999px;
  background-color: #86aaf2;
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  line-height: 1;
  text-decoration: none;
  white-space: nowrap;
  cursor: pointer;
  transition:
    background-color 0.2s,
    border-color 0.2s,
    box-shadow 0.2s;
}

.agent-market-apply-btn:hover {
  background-color: #7a9ee8;
  border-color: #7a9ee8;
  color: #fff;
  text-decoration: none;
}

.agent-market-apply-btn:focus-visible {
  outline: 2px solid rgba(134, 170, 242, 0.55);
  outline-offset: 3px;
}

.agent-market-apply-btn .agent-market-arrow {
  color: #fff;
}

.agent-market-link {
  display: inline-flex;
  align-items: center;
  margin-top: 0;
  gap: 10px;
  text-decoration: none;
  color: #674bb5;
  font-size: 14px;
  font-weight: 600;
  line-height: 1;
  padding: 0;
}

button.agent-market-link {
  border: none;
  background: transparent;
  cursor: pointer;
  font-family: inherit;
}

.agent-market-link:hover {
  text-decoration: underline;
}

button.agent-market-link:focus-visible {
  outline: 2px solid rgba(103, 75, 181, 0.45);
  outline-offset: 3px;
  border-radius: 4px;
}

.agent-market-arrow {
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  color: #674BB5;
}

.agent-market-right {
  flex: 1 1 auto;
  min-width: 0;
  width: 100%;
  max-width: min(930px, 100%);
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--agent-card-gap, 14px);
  align-content: start;
}

@media (min-width: 900px) {
  .home-plaza-row .agent-market-right {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.agent-card {
  height: auto;
  min-height: 108px;
  width: 100%;
  border: 1px solid rgba(255, 255, 255, 0.85);
  background: rgba(255, 255, 255, 0.92);
  border-radius: 12px;
  padding: 20px;
  text-align: left;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: stretch;
  box-sizing: border-box;
  transition: transform 0.08s, background-color 0.2s, border-color 0.2s, box-shadow 0.2s;
}

.agent-card-main {
  display: flex;
  flex-direction: row;
  align-items: flex-start;
  gap: 20px;
  width: 100%;
  min-width: 0;
}

.agent-card:hover {
  background: rgba(255, 255, 255, 0.96);
  border-color: rgba(255, 255, 255, 0.98);
  box-shadow: 0 10px 24px rgba(25, 35, 70, 0.12);
}

.agent-card:active {
  transform: translateY(1px);
}

.agent-card-badge {
  width: 44px;
  height: 44px;
  flex: 0 0 auto;
  border-radius: 12px;
  display: grid;
  place-items: center;
}

.agent-card-badge-icon {
  width: 24px;
  height: 24px;
}

.agent-card-body {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: stretch;
}

.agent-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.agent-card-title {
  font-size: 16px;
  font-weight: 700;
  color: #111;
  line-height: 1.25;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.agent-card-popular {
  flex: 0 0 auto;
  padding: 4px 8px;
  border-radius: 999px;
  background: #DEE8FF;
  color: #494552;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.4px;
}

.agent-card-desc {
  margin-top: 6px;
  color: rgba(17, 17, 17, 0.72);
  font-size: 16px;
  font-weight: 300;
  line-height: 1.5;
  max-height: 3em;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
  word-break: break-word;
}

.agent-card-tags {
  margin-top: auto;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding-top: 10px;
}

.agent-card-tag {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  background: #E7EEFF;
  color: #674BB5;
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
}

.home-footer {
  flex-shrink: 0;
  width: 100%;
  min-height: 60px;
  margin: 0;
  background: #86aaf2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px clamp(16px, 4vw, 48px) 14px clamp(24px, 6vw, 96px);
  box-sizing: border-box;
  border-radius: 0;
}

.footer-logos {
  display: flex;
  align-items: center;
  gap: 24px;
  flex-shrink: 0;
}

.footer-logo-img {
  height: 36px;
  width: auto;
  object-fit: contain;
  display: block;
}

.footer-logo-divider {
  width: 2px;
  height: 32px;
  background: #fff;
  flex-shrink: 0;
}

.footer-text {
  display: flex;
  align-items: center;
  gap: 36px;
  color: #fff;
  font-size: 14px;
  font-weight: 300;
  line-height: 1.4;
  white-space: nowrap;
}

@media (max-width: 1100px) {
  .home-intro-features {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .intro-feature-card {
    height: auto;
    min-height: 200px;
  }
}

@media (max-width: 960px) {
  .home-plaza-row {
    flex-direction: column;
    margin-top: 0;
    gap: 16px;
  }

  .home-intro-en-block {
    flex-direction: column;
    align-items: stretch;
  }

  .home-intro-cta-row {
    justify-content: flex-end;
    margin-top: 12px;
  }

  .home-intro-cta-row .cta-btn {
    min-width: 0;
    width: 100%;
    max-width: 291px;
  }
}

@media (max-width: 768px) {
  .home-view {
    --home-content-pad-top: calc(var(--home-nav-height) + 12px);
    --home-content-pad-bottom: 48px;
    --home-snap-pad-x: 16px;
  }
  .title-logos {
    /* 用高度收紧，避免按宽度等比放大后图像过高（源图比例近正方形） */
    height: 48px;
    width: auto;
    max-width: 80%;
  }
  .title-cn {
    font-size: 26px;
  }
  .title-en {
    font-size: 18px;
  }

  .home-intro-features {
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .intro-feature-card {
    min-height: 180px;
    height: auto;
    padding: 24px;
  }

  .home-feature-frame {
    gap: 10px;
  }

  .feature-entry-card {
    height: auto;
    min-height: 176px;
    padding: 14px 12px 12px;
  }

  .feature-entry-icon {
    width: 44px;
    height: 44px;
    border-radius: 12px;
    margin-bottom: 8px;
  }

  .feature-entry-icon-svg {
    width: 24px;
    height: 24px;
  }

  .feature-entry-divider {
    margin: 8px 0;
  }

  .feature-entry-title {
    font-size: 14px;
  }

  .feature-entry-desc {
    font-size: 12px;
  }

  /* 平板/大屏手机：页脚不再左右两列拼，整体居中堆叠，避免右侧文案
     在窄列里被强行换到角落甚至贴到屏幕边。 */
  .home-footer {
    height: auto;
    min-height: 60px;
    padding: 14px 16px;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    gap: 10px;
  }
  .footer-text {
    flex-direction: column;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    white-space: normal;
    text-align: center;
    line-height: 1.5;
  }

  .plaza-panel {
    padding: 18px 16px 48px;
  }

  .agent-market--full {
    height: 537px;
    min-height: 537px;
    max-height: 537px;
    padding: 0 48px;
  }

  .agent-market--full .plaza-panel-main {
    padding: 47px 0 62px;
  }

  .agent-market-left {
    flex: 0 0 auto;
    max-width: none;
    width: 100%;
  }
  .agent-market-right {
    flex: 0 0 auto;
    width: 100%;
    max-width: none;
    grid-template-columns: 1fr;
  }

  .oss-support {
    padding: 28px 18px 24px;
  }
  .oss-bg-lb,
  .oss-bg-rt {
    width: 260px;
    opacity: 0.85;
  }
  .oss-bg-wave {
    width: min(520px, 92%);
    opacity: 0.55;
  }
  .oss-title-en {
    font-size: 13px;
  }
  .oss-btn {
    width: 100%;
    max-width: 320px;
  }
}

/* ≤640px：导航栏高度降到 56px */
@media (max-width: 640px) {
  .home-view {
    --home-nav-height: 56px;
  }
}

@media (max-width: 480px) {
  .home-view {
    --home-snap-pad-x: 12px;
  }

  .home-snap-page-inner {
    width: 100%;
  }
  .title-logos {
    height: 40px;
    margin-bottom: 22px;
  }
  .title-cn {
    font-size: 22px;
  }
  .title-en {
    font-size: 15px;
  }
  .cta-btn {
    max-width: none;
    height: 44px;
    font-size: 14px;
    padding: 0 20px;
  }
  .home-feature-frame {
    gap: 10px;
  }
  .feature-entry-card {
    min-height: 168px;
    padding: 12px 10px 10px;
  }
  .feature-entry-icon {
    width: 40px;
    height: 40px;
    margin-bottom: 6px;
  }
  .feature-entry-icon-svg {
    width: 22px;
    height: 22px;
  }
  .feature-entry-title {
    font-size: 14px;
  }
  .feature-entry-desc {
    font-size: 12px;
  }
  .agent-market .plaza-panel-badge {
    margin-bottom: 0;
  }

  .agent-market-title {
    font-size: 20px;
    margin-top: 0;
  }
  .agent-market-desc {
    margin-top: 12px;
    font-size: 13px;
  }
  .agent-market--full .agent-card {
    height: auto;
    min-height: 108px;
    max-height: none;
  }

  .agent-card {
    padding: 20px;
    gap: 10px;
  }
  .agent-card-badge {
    width: 42px;
    height: 42px;
    border-radius: 8px;
  }
  .agent-card-badge-icon {
    width: 22px;
    height: 22px;
  }
  .agent-card-title {
    font-size: 14px;
  }
  .agent-card-desc {
    font-size: 14px;
    max-height: 3em;
    -webkit-line-clamp: 2;
    line-clamp: 2;
  }
  .oss-title-cn {
    font-size: 20px;
  }
  .oss-title-en {
    font-size: 12px;
  }
  .home-footer {
    padding: 10px 12px;
    gap: 8px;
  }
  .footer-text {
    font-size: 11px;
  }
}

</style>
