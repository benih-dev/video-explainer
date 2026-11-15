---
name: explainer-video
description: "Turn any topic, article, codebase, or URL into a ~1-minute explainer video (60 to 75s target, 2-minute max) in Motion (default), Illustrated, or 3D style with web media, optional voiceover, synchronized captions, and a frame-pinned browser review page. Use when someone wants an animated explainer video."
---

# Explainer Video

Input: a topic, article, codebase, or rough notes. Output: a single `renders/<slug>-vN.mp4` at 1920x1080 (`16:9`) and 30 fps (or `9:16` / `1:1` when requested), plus the `script.md`, `media/`, and `graphics/` files that produced it (pass `--share` to `render.py` only when a smaller 720p copy in `renders/share/` is requested).

You write the script, narration, and scene code; the scripts fetch media, synthesize voice, align words, compile HyperFrames, render MP4, run 10-check QA, and serve the review page. Commands, `script.md` syntax, engine APIs, and `style.json` keys live in [reference.md](reference.md).

On first use, run `setup.sh` (or `setup.sh --voice` when using spoken narration). If tools are missing, list them and ask before installing. Put optional `GEMINI_API_KEY=...` in `~/.config/explainer-video/.env` rather than chat.

## 1. Pick a visual mode

Support three visual modes (`Mode:` in `script.md`, default `motion`):

1. **Motion (default)** (`Mode: motion`): Full-frame 2D kinetic graphics, live SVG routes and charts, CSS 3D cards or devices, and documentary press clippings on `ExplainerStage`. Fastest and lightest on tokens.
2. **Illustrated** (`Mode: illustrated`): Hand-drawn picture-book animation with procedural gouache, dry pastel, charcoal strokes, cotton-rag paper tooth, 10 fps line boil, and word-synced characters on `StoryBrush` and `IllustratedStage`.
3. **3D** (`Mode: 3d`): Single-take Three.js WebGL camera flythroughs with PBR materials, studio lighting, bloom, camera-facing HUD plaques, and optional headless Blender meshes (`blender_export.py`) on `Studio3D`.

If the user already named a mode or asked to run with defaults, proceed immediately (`Mode: motion` by default). Otherwise, present the numbered list above and let them reply `1`, `2`, or `3` before building.

## 2. Research, source media, and write `script.md`

Create one project folder named with a short slug (`graphics/`, `media/`, `captures/`) where the user asks, else `projects_dir` from `style.json`, else the current folder.

Verify every claim, number, quote, and step against the user's files or primary sources. Pull real photos, product visuals, clips, or page captures when they ground the story (`media.py image`, `media.py clip`, `capture.py`), and inspect each downloaded image so broken or irrelevant assets stay out of the render. Write `script.md`:

- **Keep runtime to 60 to 75 seconds (2-minute cap).** Target `135 to 185` spoken words across `5 to 8` scenes when voiced, or `8 to 12` beats when `Voice: none` (`45 to 60s` / `100 to 150` words for `Audience: eli5`). Stay at or under `120s` (`~260` words) unless the user asks for a longer video (`Max duration: <seconds>`). Cut tangents rather than rushing speech.
- **Default to `Audience: general` (smart non-engineer).** Use plain English, concrete mental models, and everyday cause-and-effect without raw file paths, internal variable or function names, error codes, CLI flags, or unexplained acronyms in speech or visuals. Switch to `eli5` (physical metaphors, zero jargon) or `technical` (architecture names, protocols, tradeoffs) only when requested.
- **Land the hook in 3 seconds and follow one example end-to-end.** Open with a concrete question, tension, or number that reads with the sound off, trace one specific request, dollar, star, or user through every step, and close by answering the opening question.
- **Write clean spoken copy.** Skip throat-clearing openers, binary contrasts, colon reveals, and hype adjectives. Use short sentences and active verbs.
- **Set audio and theme headers:** `Mode: motion | illustrated | 3d`, `Audience: general`, `Voice: kokoro:af_heart` (or `gemini:Kore`, an audio file, or `none`), `Music: synth:cosmic` (`synth:warm`, `synth:minimal`, path, or `none`), `Sound effects: on` with word-anchored `## Sound` cues (`- @s05:iron: rumble 0.8`), and `Style: default | paper | blueprint`.

Go straight from `script.md` into narration, graphics, QA, and the browser review page unless the user asked to approve the script first or requested a paid Gemini API call without a configured key.

## 3. Narrate and align

Run `narrate.py` to synthesize cached per-scene audio, trim dead air, align words with Parakeet, sync `start` and `end` times back into `script.md`, and write `work/transcript.md`. Read `work/transcript.md` before coding graphics so animations and sound cues hit exact spoken words via `stage.cue("s03", "keyword", 1.2)`.

## 4. Build graphics efficiently

Point consecutive rows in `## Scenes` at `graphics/world.html` so `build.py` mounts one continuous composition and auto-injects `stage.css`, `stage.js`, `explainer-data.js`, plus `illustrated.js` (`Mode: illustrated`) or `three.min.js` and `studio3d.js` (`Mode: 3d`).

Keep token use lean while hitting a high visual bar:

- **Use the built-in engines instead of rewriting boilerplate.** Build on `ExplainerStage`, `StoryBrush` / `IllustratedStage`, `Studio3D`, and `blender_export.py` rather than coding custom Perlin noise, WebGL post-processing shaders, or binary mesh packers in project folders.
- **Default to one agent.** A single agent handles `Motion`, `Illustrated`, and standard `3D` scenes cleanly. Use `/swarm` (`@director` + `@act1..3` registering into `Studio3D.registerAct`) only when the user asks for `/swarm` or a multi-environment `3D` flythrough.
- **Fill 60 to 85% of the frame and transform every 2 to 3 seconds.** Avoid static slide cards parked on a grid, running top-left headers, or tiny `200px` diagrams in empty space. Keep callouts to 1 to 4 words (`28px+` labels, `88px to 160px` hero numbers) above the caption band (`y < 860` on `16:9`, `y < 1400` on `9:16`) with WCAG AA contrast.
- **Mode craft:**
  - **Motion:** Pair `.st-stage` (`cosmos`, `paper`, or `blueprint` backdrop) with morphing hero SVG/Canvas visuals, `zoomThrough` dives, `whipTo` pans, `drawStroke` live paths, `.st-clipping` press cutouts with `kenBurns` and `highlightSweep`, `.st-3d-rig` / `.st-phone-shell` stacks, `stampSlam`, and `kineticPunch`. Reserve built-in table primitives (`image:`, `clip:`, `quote:`, `code:`, `page:`, `receipt:`, `number:`, `flow:`, `card:`, `compare:`) for standalone single-beat moments.
  - **Illustrated:** Pre-bake multi-thousand-stroke gouache, pastel, striped knit, and character art once at startup with `StoryBrush.bake` or `StoryBrush.bakeBoil` (3-state 10 fps hand-drawn boil) and composite cached canvases in `stage.onDraw` at 30 fps. Drive character mouths and blinks from `frame.speech` and `stage.blinkAt(t)`.
  - **3D:** Drive everything synchronously from `t` (`Studio3D.create` + `cameraSpline` or `registerAct`, `window.STUDIO_ASSETS` from `blender_export.py` or procedural `THREE` meshes, pre-decoded `CanvasTexture`, zero async `GLTFLoader` / `TextureLoader` calls). Keep exposure near `1.0`, use `makePlaque` + `faceCamera` + `clampAboveCaptions` so 3D labels stay readable and clear of captions, and use headless Blender only when `blender` is installed and sculpted/fractured geometry adds clear value.
- **Keep every frame deterministic on seek.** Bind updates to `stage.onTick` / `stage.onDraw` and end with `.finalize()`. Skip `Math.random()` and CSS `transform` rules on GSAP-animated elements, and put `data-layout-allow-overflow` on full-bleed `<canvas>` or offscreen art.

## 5. Preview, draft, QA, review, and final

1. **Token-light pre-flight:** Run `render.py "$P" --preview` (~3s) and inspect the single tiled `work/preview/contact.jpg` first to catch framing, contrast, or whiteout bugs. Open individual `work/preview/frame-*.png` files only when diagnosing a specific beat.
2. **Draft and QA:** Run `render.py "$P" --draft` and `qa.py "$P"`. Fix any failed check (`10/10` required) and inspect `work/qa/contact.jpg` and `work/qa/opening.jpg` (plus `work/qa/cuts/*.jpg` only around suspect transitions).
3. **Browser review loop:** Start `review.py "$P"` in a background shell, share its URL, and run `review.py --poll "$P/work"` in the foreground. Apply feedback, re-run `narrate.py` only if spoken words changed, render `--draft`, refresh with `review.py "$P" --no-open`, run `review.py --ack "$P/work" BATCH_ID`, and poll again until approved.
4. **Final delivery:** Run `render.py "$P"` and `qa.py "$P"`, verify [eval.md](eval.md), ask the user to check voice pacing and mix balance, and report the final `.mp4` path, duration, and loudness. Offer to save custom theme/caption tweaks to `~/.config/explainer-video/style.json`.
