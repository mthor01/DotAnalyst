<script lang="ts" module>
  import { BarChart, LineChart } from 'echarts/charts'
  import {
    GridComponent,
    MarkLineComponent,
    TitleComponent,
    TooltipComponent,
  } from 'echarts/components'
  import * as echarts from 'echarts/core'
  import { LabelLayout } from 'echarts/features'
  import { CanvasRenderer } from 'echarts/renderers'

  echarts.use([
    BarChart,
    LineChart,
    GridComponent,
    MarkLineComponent,
    TitleComponent,
    TooltipComponent,
    LabelLayout,
    CanvasRenderer,
  ])

  const FONT = 'Archivo, system-ui, sans-serif'
  /** Colours a chart may use, read from the page's CSS variables so they are defined in one place. */
  const INK_KEYS = [
    'surface', 'raised', 'text', 'text-2', 'muted', 'grid', 'axis',
    'series-1', 'series-2', 'series-3', 'series-4', 'series-5', 'radiant', 'dire',
  ] as const // prettier-ignore
  export type Ink = Record<(typeof INK_KEYS)[number], string>
</script>

<script lang="ts">
  import type { EChartsCoreOption } from 'echarts/core'
  import { onMount } from 'svelte'

  let { option, label, height = 320 }: { option: (ink: Ink) => EChartsCoreOption; label: string; height?: number } =
    $props()

  let el: HTMLDivElement

  onMount(() => {
    const chart = echarts.init(el)
    const resize = new ResizeObserver(() => chart.resize())
    resize.observe(el)
    return () => {
      resize.disconnect()
      chart.dispose()
    }
  })

  $effect(() => {
    const css = getComputedStyle(el)
    const ink = Object.fromEntries(INK_KEYS.map((k) => [k, css.getPropertyValue(`--${k}`).trim()])) as Ink
    const made = option(ink) as { tooltip?: object }
    // every chart shares the font and the look of its tooltip
    const tooltip = made.tooltip && {
      backgroundColor: ink.raised,
      borderColor: ink.axis,
      textStyle: { color: ink.text, fontFamily: FONT },
      ...made.tooltip,
    }
    echarts.getInstanceByDom(el)?.setOption({ ...made, textStyle: { fontFamily: FONT }, tooltip }, true)
  })
</script>

<div bind:this={el} role="img" aria-label={label} style:height="{height}px"></div>
