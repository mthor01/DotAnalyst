<script lang="ts">
  import { percent } from './api'

  let { wins, games }: { wins: number; games: number } = $props()
  const rate = $derived(percent(wins, games))
</script>

<!-- the bar grows from the middle line: right and green above 50 %, left and red below -->
<span class="rate"><i class:losing={rate < 50} style:left="{Math.min(rate, 50)}%" style:width="{Math.abs(rate - 50)}%"></i></span>
{rate}%

<style>
  .rate {
    position: relative;
    display: inline-block;
    width: 90px;
    height: 6px;
    margin-right: 8px;
    border-radius: 2px;
    background: linear-gradient(var(--axis), var(--axis)) center / 1px 100% no-repeat, var(--raised);
    vertical-align: 1px;
    overflow: hidden;
  }
  .rate i {
    position: absolute;
    top: 0;
    bottom: 0;
    background: var(--good);
  }
  .rate i.losing {
    background: var(--critical);
  }
</style>
