<script lang="ts">
  let { games, max }: { games: number; max: number } = $props()
</script>

<!-- the bar fills from the left, the most played row of the table fills it -->
<span class="count"><i style:width="{(100 * games) / Math.max(max, 1)}%"></i></span>{games}

<style>
  .count {
    display: inline-block;
    width: 90px;
    height: 6px;
    margin-right: 8px;
    border-radius: 2px;
    background: var(--raised);
    vertical-align: 1px;
    overflow: hidden;
  }
  .count i {
    display: block;
    height: 100%;
    background: var(--series-1);
  }
</style>
