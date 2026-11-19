# Map performance (ui/perf, 2026-11-19)

How the map was profiled, what the profile found, what changed, and the numbers before and after. REQ-WEB-PERF.

## How it was measured

`web/scripts/profile-map.mjs` serves a built copy of the site and drives it in headless Chromium through Playwright:

- **Home map:** 28 wheel steps in (zoom 11.2 to 15 on desktop), four drag pans, 28 wheel steps out.
- **Time-lapse:** press Play and record 12 seconds.
- **Devices:** desktop at 1280 x 800, and a Pixel 7 profile (412 x 915, 2.625 pixels per CSS pixel) with the CPU slowed 4x through `Emulation.setCPUThrottlingRate`.
- **Recorded:** gaps between animation frames, long tasks (over 50 ms, `PerformanceObserver`), a V8 CPU profile of the main thread and a Chrome trace. Results go to `.local-data/profile/<label>-<device>.json` (not committed).
- **Loads:** the committed sample has 1,009 points. Runs were made with it, and with the points file grown to 12,000 jittered copies (a stand-in for a full-data map).

```
npx vite build --minify false --outDir ../.local-data/profile/dist-NAME --emptyOutDir
node scripts/profile-map.mjs --dist ../.local-data/profile/dist-NAME --label NAME --points 12000 --gl angle --device both
```

Limits: the sandbox has no GPU. `--gl angle` composites on SwiftShader through ANGLE the way a GPU machine composites. The flags in `playwright.config.ts` (`--use-gl=swiftshader`) composite in software, which reads every WebGL canvas back on every frame and adds about 80 s of waiting to one home run. Both setups draw on the CPU, so frame times read slower than on real hardware. The long-task counts and the JS profile do not depend on that, so the numbers below compare runs made the same way. They were not measured on a real phone.

## What the profile found (before)

Home map, 12,000 points, main-thread self time:

| Cost | Desktop | Phone (4x CPU) | Cause |
|---|---|---|---|
| `groupRows` (clustering) | 29.5 s | 117 s, one task of 30 s | Re-run on every render and every half zoom step. The merge loop rescanned every pair after each merge (cubic in the number of clusters). It ran twice per change: once for the layers and once for a `data-cluster-count` attribute. |
| `readPixelsToArray` (picking) | 21.6 s | 26.9 s | deck.gl picked under the mouse on every frame it moved, and again on each press that started a pan. Every pick waits for the GPU to finish the frame. |
| Hit layers | (GPU) | (GPU) | An invisible circle layer (`zombie-hit`) was drawn over every marker on every frame, plus a halo layer on every screen size. |
| Time-lapse | `formatDay` and the marker-key spray SVG | same | A new `Intl.DateTimeFormat` on every frame, and the legend's spray SVGs rebuilt on every frame. The visible-rows array was new every frame, so deck.gl re-ran every accessor over every row. |

The basemap is not a main cost. With no markers, the home run on desktop holds 16.7 ms per frame in every phase (p95 50 ms), so the basemap detail was left alone.

## What changed

- **Cluster index built once** (`web/src/map/density.ts`). Rows are sorted and projected once. Clusters are worked out once per whole zoom level, cached, and re-queried only when the zoom crosses a whole level. Badge merging uses a spatial grid and a heap, which costs about n log n. A property test checks that the result equals the brute-force grouping (300 random maps, with and without a kept marker). Clusters now follow whole zoom levels, where they used to follow half levels.
- **Memoized layers and data** (`MapView.tsx`, `layers.ts`). The grouping is memoized on (rows, zoom level, selection, mode) and passed to `buildLayers`. The bulk-ring rows are cached, so a zoom step hands deck.gl the same arrays.
- **One pickable layer.** The sprite is its own hit area (`pickable`, `alphaCutoff: 0`, so its transparent middle still picks). The `zombie-hit` layer is gone. The 44 px halo has data only on phones.
- **Pick on click only** (`web/src/map/clickOnlyOverlay.ts`). There is no hover picking (the map uses no hover cursor and no onHover), and no pick on the press that starts a pan. A click or tap picks once at the point where it landed.
- **Pixel ratio capped at 2** for both MapLibre (`pixelRatio`) and deck.gl (`useDevicePixels`).
- **Time-lapse appends.** With no trail, the visible rows are a prefix of the timeline, and the same array is handed on until a new row appears. `_dataDiff` tells deck.gl that only the appended rows are new, so it fills in the new tail and nothing else. The date formatters and the legend sprites are built once.

## Before and after

Frame times are gaps between animation frames, in ms. "Long" is the count of long tasks (over 50 ms) and the longest one. All runs use `--gl angle`.

### 12,000 points

| Run | Before p50 / p95 / max | Before long (max) | After p50 / p95 / max | After long (max) |
|---|---|---|---|---|
| Desktop, home map | 66.7 / 800 / 5,467 | 32 (5,782 ms) | 150 / 283 / 433 | **0** |
| Desktop, time-lapse | 50 / 183 / 367 | 0 | 16.7 / 66.6 / 217 | 0 |
| Phone, home map | 33.4 / 883 / 30,282 | 33 (30,253 ms) | 33.4 / 66.7 / 100 | 4 (63 ms) |
| Phone, time-lapse | 66.7 / 567 / 2,650 | 15 (213 ms) | 33.3 / 367 / 483 | 5 (63 ms) |

Main-thread busy time on the home map fell from 58.8 s to 5.0 s on desktop, and from 169 s to 12.8 s on the phone.

The after p50 on the desktop home map (150 ms) comes from the pan phase. The pan runs at zoom 15 with thousands of overlapping 30 px sprites, and SwiftShader fills them on the CPU. The main thread is idle there and no long tasks occur. The wait is GPU fill, which a real GPU handles in a fraction of that time. The before p50 looks lower only because a blocked main thread drew fewer frames. By phase, after: zoom in p50 50 ms, pan p50 150 ms, zoom out p50 50 ms, with 0 long tasks in each.

### 1,009 points (the committed sample)

| Run | Before p50 / p95 / max | Before long (max) | After p50 / p95 / max | After long (max) |
|---|---|---|---|---|
| Desktop, home map | 50 / 83.3 / 717 | 5 (724 ms) | 33.3 / 66.6 / 267 | **0** |
| Desktop, time-lapse | 16.7 / 33.4 / 66.6 | 0 | 16.7 / 16.7 / 16.8 | 0 |
| Phone, home map | 33.4 / 83.2 / 667 | 18 (669 ms) | 16.7 / 50 / 167 | 1 (84 ms) |
| Phone, time-lapse | 33.4 / 117 / 167 | 1 (54 ms) | 16.7 / 33.4 / 50.1 | 0 |

## Against the target

- **Desktop, no long tasks over 50 ms while zooming:** met, with 0 long tasks in every desktop run after the change, at both loads.
- **Phone profile acceptable:** with the sample data the phone home map holds 16.7 ms p50 and 50 ms p95, with one 84 ms task. At 12,000 points it holds 33 ms p50 and 67 ms p95, with four tasks of 63 ms or less. These short tasks come from working out the clusters when the zoom crosses a whole level, at 4x CPU slowdown.
- **Not verified:** frame times on real GPUs and real phones. The sandbox has neither.
