<script lang="ts">
  import type { Snippet } from 'svelte'

  // a small ? that tells how to read a chart or table, on hover, keyboard focus or a tap; the page keeps only a short caption
  let { children }: { children: Snippet } = $props()
  const id = $props.id()
  let at = $state<{ top?: number; bottom?: number; left: number } | null>(null)

  // fixed, not absolute: cards scroll sideways (overflow-x), which would cut an absolute box off
  function show(e: Event) {
    const r = (e.currentTarget as Element).getBoundingClientRect()
    const left = Math.max(8, Math.min(r.left - 8, innerWidth - 440))
    at = r.top > innerHeight / 2 ? { bottom: innerHeight - r.top + 6, left } : { top: r.bottom + 6, left }
  }
  const hide = () => (at = null)
</script>

<button type="button" class="about" aria-label="How to read this" aria-describedby={id}
  onpointerenter={show} onpointerleave={hide} onfocus={show} onblur={hide} onkeydown={(e) => e.key === 'Escape' && hide()}>?</button>
<span {id} role="tooltip" class="tip" hidden={!at} style:top={at?.top === undefined ? null : `${at.top}px`}
  style:bottom={at?.bottom === undefined ? null : `${at.bottom}px`} style:left="{at?.left}px">{@render children()}</span>

<style>
  .about {
    display: inline-grid;
    place-items: center;
    width: 18px;
    height: 18px;
    margin: 0 4px;
    padding: 0;
    border: 1px solid var(--border);
    border-radius: 50%;
    background: none;
    color: var(--muted);
    font-size: 12px;
    font-weight: 700;
    line-height: 1;
    vertical-align: middle;
    cursor: help;
  }
  .about:hover,
  .about:focus-visible {
    color: var(--text);
    border-color: var(--text-2);
  }
  .tip {
    position: fixed;
    z-index: 20;
    width: min(420px, calc(100vw - 16px));
    padding: 10px 12px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
    color: var(--text-2);
    font-size: 13px;
    font-weight: 400;
    line-height: 1.45;
    text-transform: none;
    letter-spacing: normal;
    text-align: left;
    white-space: normal;
  }
  .tip[hidden] {
    display: none;
  }
</style>
