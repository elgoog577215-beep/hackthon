import { ref, type Ref } from 'vue'
import * as echarts from 'echarts'
import { timeStrToSeconds } from '../lib/videoReportUtils'

export interface VideoChartRefs {
  radarChartRef: Ref<HTMLDivElement | null>
  speechRateChartRef: Ref<HTMLDivElement | null>
  volumeChartRef: Ref<HTMLDivElement | null>
  fillerChartRef: Ref<HTMLDivElement | null>
  designPieRef: Ref<HTMLDivElement | null>
  densityChartRef: Ref<HTMLDivElement | null>
  knowledgeTreeRef: Ref<HTMLDivElement | null>
  interactionScatterRef: Ref<HTMLDivElement | null>
  whPieRef: Ref<HTMLDivElement | null>
}

export function useVideoCharts(seekVideoToTime: (timeSec: number) => void) {
  const radarChartRef = ref<HTMLDivElement | null>(null)
  const speechRateChartRef = ref<HTMLDivElement | null>(null)
  const volumeChartRef = ref<HTMLDivElement | null>(null)
  const fillerChartRef = ref<HTMLDivElement | null>(null)
  const designPieRef = ref<HTMLDivElement | null>(null)
  const densityChartRef = ref<HTMLDivElement | null>(null)
  const knowledgeTreeRef = ref<HTMLDivElement | null>(null)
  const interactionScatterRef = ref<HTMLDivElement | null>(null)
  const whPieRef = ref<HTMLDivElement | null>(null)

  const chartMap = new Map<HTMLDivElement, echarts.ECharts>()
  const chartSeekHandlers = new Map<echarts.ECharts, (event: { offsetX: number; offsetY: number }) => void>()

  function getOrCreateChart(el: HTMLDivElement | null) {
    if (!el) return null
    let chart = chartMap.get(el)
    if (!chart) {
      chart = echarts.init(el)
      chartMap.set(el, chart)
    }
    return chart
  }

  function setChartScrollWidth(el: HTMLDivElement | null, dataLen: number, pxPerPoint = 4) {
    if (!el || dataLen <= 0) return
    const parent = el.parentElement
    if (!parent) return
    const minWidth = parent.clientWidth
    const desiredWidth = dataLen * pxPerPoint + 120
    el.style.width = Math.max(minWidth, desiredWidth) + 'px'
  }

  function bindSeekableLineChart(chart: echarts.ECharts, xLabels: string[]) {
    const prev = chartSeekHandlers.get(chart)
    if (prev) chart.getZr().off('click', prev)
    if (!xLabels.length) return

    const handler = (event: { offsetX: number; offsetY: number }) => {
      const point: [number, number] = [event.offsetX, event.offsetY]
      if (!chart.containPixel({ gridIndex: 0 }, point)) return
      const coord = chart.convertFromPixel({ xAxisIndex: 0, yAxisIndex: 0 }, point)
      if (!coord) return
      let index: number
      if (typeof coord[0] === 'string') {
        index = xLabels.indexOf(coord[0])
      } else if (Number.isFinite(Number(coord[0]))) {
        index = Math.round(Number(coord[0]))
      } else {
        return
      }
      if (index < 0) index = 0
      if (index >= xLabels.length) index = xLabels.length - 1
      seekVideoToTime(timeStrToSeconds(xLabels[index]))
    }
    chartSeekHandlers.set(chart, handler)
    chart.getZr().on('click', handler)
  }

  function bindSeekableMinutesAxisChart(chart: echarts.ECharts) {
    const prev = chartSeekHandlers.get(chart)
    if (prev) chart.getZr().off('click', prev)
    chart.off('click')

    chart.on('click', (params) => {
      if (params.componentType !== 'series' || !Array.isArray(params.data)) return
      const minutes = Number(params.data[0])
      if (!Number.isFinite(minutes)) return
      seekVideoToTime(Math.max(0, minutes * 60))
    })

    const zrHandler = (event: { offsetX: number; offsetY: number }) => {
      const point: [number, number] = [event.offsetX, event.offsetY]
      if (!chart.containPixel({ gridIndex: 0 }, point)) return
      if (chart.containPixel({ seriesIndex: 0 }, point)) return
      const coord = chart.convertFromPixel({ xAxisIndex: 0, yAxisIndex: 0 }, point)
      if (!coord || !Number.isFinite(Number(coord[0]))) return
      seekVideoToTime(Math.max(0, Number(coord[0]) * 60))
    }
    chartSeekHandlers.set(chart, zrHandler)
    chart.getZr().on('click', zrHandler)
  }

  function initRadarChart(report: Record<string, unknown>) {
    const chart = getOrCreateChart(radarChartRef.value)
    if (!chart) return
    const rd = (report.radar_data as Array<Record<string, unknown>> | undefined) ?? []
    chart.setOption({
      tooltip: {},
      radar: {
        indicator: rd.map((d) => ({ name: String(d.dimension ?? ''), max: 100 })),
        radius: '65%',
        axisName: { color: '#666' },
      },
      series: [{
        type: 'radar',
        data: [{
          value: rd.map((d) => Number(d.score ?? 0)),
          name: '得分',
          areaStyle: { color: 'rgba(19, 88, 228, 0.2)' },
          lineStyle: { color: '#1358e4', width: 2 },
          itemStyle: { color: '#1358e4' },
        }],
      }],
    }, true)
  }

  function initSpeechRateChart(speechRate: Record<string, unknown> | undefined) {
    const chart = getOrCreateChart(speechRateChartRef.value)
    if (!chart) return
    const result = (speechRate?.result as number[] | undefined) ?? []
    setChartScrollWidth(speechRateChartRef.value, result.length, 3)
    const total = Number(speechRate?.total_duration ?? 0)
    const xLabels = result.map((_, i) => {
      const sec = (total / result.length) * i
      const m = Math.floor(sec / 60)
      const s = Math.floor(sec % 60)
      return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    })
    chart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'line', snap: true } },
      grid: { left: 50, right: 50, top: 20, bottom: 30 },
      xAxis: { type: 'category', data: xLabels, axisLabel: { interval: Math.floor(result.length / 6) } },
      yAxis: { type: 'value', name: 'CPM' },
      series: [{
        type: 'line',
        data: result,
        smooth: true,
        lineStyle: { color: '#1358e4', width: 2 },
        areaStyle: { color: 'rgba(19, 88, 228, 0.1)' },
        markLine: {
          silent: true,
          data: [
            { yAxis: Number(speechRate?.avg_cpm ?? 0), lineStyle: { color: '#999', type: 'dashed' }, label: { formatter: '平均' } },
          ],
        },
      }],
    }, true)
    chart.resize()
    bindSeekableLineChart(chart, xLabels)
  }

  function initVolumeChart(volume: Record<string, unknown> | undefined) {
    const chart = getOrCreateChart(volumeChartRef.value)
    if (!chart) return
    const result = (volume?.result as number[] | undefined) ?? []
    setChartScrollWidth(volumeChartRef.value, result.length, 3)
    const total = Number(volume?.total_duration ?? 0)
    const xLabels = result.map((_, i) => {
      const sec = (total / result.length) * i
      const m = Math.floor(sec / 60)
      const s = Math.floor(sec % 60)
      return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    })
    chart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'line', snap: true } },
      grid: { left: 50, right: 50, top: 30, bottom: 30 },
      xAxis: { type: 'category', data: xLabels, axisLabel: { interval: Math.floor(result.length / 6) } },
      yAxis: { type: 'value', name: 'dB' },
      series: [{
        type: 'line',
        data: result,
        smooth: true,
        lineStyle: { color: '#1358e4', width: 2 },
        areaStyle: { color: 'rgba(19, 88, 228, 0.15)' },
        markLine: {
          silent: true,
          data: [
            { yAxis: Number(volume?.avg_spl ?? 0), lineStyle: { color: '#999', type: 'dashed' }, label: { formatter: '平均' } },
          ],
        },
      }],
    }, true)
    chart.resize()
    bindSeekableLineChart(chart, xLabels)
  }

  function initFillerChart(conciseness: Record<string, unknown> | undefined) {
    const chart = getOrCreateChart(fillerChartRef.value)
    if (!chart) return
    const top = (conciseness?.top_filler_words as Array<Record<string, unknown>> | undefined) ?? []
    const data = [...top].reverse()
    chart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 80, right: 20, top: 10, bottom: 20 },
      xAxis: { type: 'value' },
      yAxis: { type: 'category', data: data.map((d) => String(d.term ?? '')), axisLabel: { fontSize: 12 } },
      series: [{
        type: 'bar',
        data: data.map((d) => Number(d.count ?? 0)),
        itemStyle: { color: '#1358e4', borderRadius: [0, 4, 4, 0] },
      }],
    }, true)
  }

  function initDesignPie(typeDistribution: Array<Record<string, unknown>>) {
    const chart = getOrCreateChart(designPieRef.value)
    if (!chart) return
    chart.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: {c}%' },
      legend: { orient: 'vertical', right: 10, top: 'center', textStyle: { fontSize: 12 } },
      series: [{
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['40%', '50%'],
        data: typeDistribution.map((d) => {
          const ratio = Number(d.ratio ?? 0)
          return { name: String(d.type ?? ''), value: Math.round(ratio * 10000) / 100 }
        }),
        label: { formatter: '{b}\n{d}%', fontSize: 11 },
      }],
    }, true)
  }

  function initDensityChart(densityData: number[], densityMeta: Record<string, unknown> | undefined) {
    const chart = getOrCreateChart(densityChartRef.value)
    if (!chart) return
    setChartScrollWidth(densityChartRef.value, densityData.length, 3)
    const windowSize = Number(densityMeta?.window_size_seconds ?? 30)
    const xLabels = densityData.map((_, i) => {
      const sec = i * windowSize
      const m = Math.floor(sec / 60)
      const s = Math.floor(sec % 60)
      return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    })
    chart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'line', snap: true } },
      grid: { left: 50, right: 50, top: 30, bottom: 30 },
      xAxis: { type: 'category', data: xLabels, axisLabel: { interval: Math.floor(densityData.length / 6) } },
      yAxis: { type: 'value', name: '密度', max: 1 },
      series: [{
        type: 'line',
        data: densityData,
        smooth: true,
        lineStyle: { color: '#5470c6', width: 2 },
        areaStyle: { color: 'rgba(84, 112, 198, 0.2)' },
      }],
    }, true)
    chart.resize()
    bindSeekableLineChart(chart, xLabels)
  }

  function initKnowledgeTree(knowledgeTree: Array<Record<string, unknown>>) {
    const chart = getOrCreateChart(knowledgeTreeRef.value)
    if (!chart) return
    function build(nodes: Array<Record<string, unknown>>): Array<Record<string, unknown>> {
      return nodes.map((n) => ({
        name: String(n.title ?? ''),
        value: String(n.start_time ?? '') + ' - ' + String(n.end_time ?? ''),
        children: n.children ? build(n.children as Array<Record<string, unknown>>) : [],
      }))
    }
    chart.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: {c}' },
      series: [{
        type: 'tree',
        data: build(knowledgeTree),
        top: '5%', left: '8%', bottom: '5%', right: '18%',
        symbolSize: 8,
        label: { position: 'left', verticalAlign: 'middle', align: 'right', fontSize: 12 },
        leaves: { label: { position: 'right', verticalAlign: 'middle', align: 'left' } },
        expandAndCollapse: true,
        animationDuration: 200,
      }],
    }, true)
  }

  function initInteractionScatter(
    interactionEvents: Array<Record<string, unknown>>,
    typeStatistics: Record<string, number>,
    interactionGaps: Array<Record<string, unknown>>,
  ) {
    const chart = getOrCreateChart(interactionScatterRef.value)
    if (!chart) return

    const typeOrder = Object.entries(typeStatistics)
      .sort((a, b) => b[1] - a[1])
      .map(([k]) => k)
    if (!typeOrder.length) {
      typeOrder.push('记忆型', '理解型', '应用型', '分析型', '评价型', '创新型')
    }
    const typeIndex = (t: string) => {
      const idx = typeOrder.indexOf(t)
      return idx >= 0 ? idx : typeOrder.length
    }

    const data = interactionEvents.map((e) => {
      const t = String(e.type ?? '')
      const startSec = timeStrToSeconds(e.start_time)
      return [startSec / 60, typeIndex(t), t, String(e.text ?? '').slice(0, 60)]
    })

    const markAreas = interactionGaps.map((g) => {
      const s = timeStrToSeconds(g.start) / 60
      const ed = timeStrToSeconds(g.end) / 60
      return [
        { xAxis: s, yAxis: -0.5 },
        { xAxis: ed, yAxis: typeOrder.length - 0.5 },
      ]
    })

    chart.setOption({
      tooltip: {
        formatter: (p: any) => {
          const d = p.data
          return `${d[2]}<br/>${(d[0] as number).toFixed(1)}min<br/>${d[3]}`
        },
      },
      grid: { left: 70, right: 20, top: 20, bottom: 30 },
      xAxis: {
        type: 'value',
        name: '时间(min)',
        axisLabel: {
          formatter: (v: number) => {
            const m = Math.floor(v)
            const s = Math.floor((v - m) * 60)
            return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
          },
        },
      },
      yAxis: {
        type: 'category',
        data: typeOrder,
        axisLabel: { fontSize: 12 },
      },
      series: [{
        type: 'scatter',
        data,
        symbolSize: 14,
        itemStyle: { color: '#5470c6' },
        markArea: markAreas.length
          ? {
              silent: true,
              itemStyle: { color: 'rgba(245, 34, 45, 0.08)' },
              label: { show: true, position: 'insideTop', color: '#f5222d', fontSize: 11 },
              data: markAreas,
            }
          : undefined,
      }],
    }, true)
    bindSeekableMinutesAxisChart(chart)
  }

  function initWhPie(whDistribution: Record<string, Record<string, unknown>>) {
    const chart = getOrCreateChart(whPieRef.value)
    if (!chart) return
    const data = Object.entries(whDistribution).map(([name, item]) => ({
      name,
      value: Number(item.count ?? 0),
    })).filter((d) => d.value > 0)
    chart.setOption({
      tooltip: { trigger: 'item' },
      series: [{
        type: 'pie',
        radius: ['35%', '65%'],
        data,
        label: { formatter: '{b}\n{c}' },
      }],
    }, true)
  }

  function resizeAll() {
    chartMap.forEach((chart) => chart.resize())
  }

  function fitScrollChartsForPrint() {
    for (const el of [speechRateChartRef.value, volumeChartRef.value, densityChartRef.value]) {
      if (el) el.style.width = '100%'
    }
  }

  function getChartDataURL(el: HTMLDivElement | null): string | undefined {
    if (!el) return undefined
    const chart = chartMap.get(el)
    return chart?.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#fff' })
  }

  function dispose() {
    chartSeekHandlers.forEach((handler, chart) => {
      chart.getZr().off('click', handler)
    })
    chartSeekHandlers.clear()
    chartMap.forEach((chart) => chart.dispose())
    chartMap.clear()
  }

  return {
    radarChartRef,
    speechRateChartRef,
    volumeChartRef,
    fillerChartRef,
    designPieRef,
    densityChartRef,
    knowledgeTreeRef,
    interactionScatterRef,
    whPieRef,
    chartMap,
    resizeAll,
    fitScrollChartsForPrint,
    getChartDataURL,
    dispose,
    initRadarChart,
    initSpeechRateChart,
    initVolumeChart,
    initFillerChart,
    initDesignPie,
    initDensityChart,
    initKnowledgeTree,
    initInteractionScatter,
    initWhPie,
  }
}
