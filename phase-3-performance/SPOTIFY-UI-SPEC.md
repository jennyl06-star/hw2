# Spotify Desktop → ChuGL ImGui Mapping Reference

## 1. Spotify Color Palette (exact hex → ChuGL vec4)

```
// All colors normalized 0-1 for ImGui vec4(r,g,b,a)
Main Background    #121212  →  @(0.071, 0.071, 0.071, 1.0)
Sidebar Background #000000  →  @(0.000, 0.000, 0.000, 1.0)
Player Bar BG      #181818  →  @(0.094, 0.094, 0.094, 1.0)
Card/Elevated BG   #282828  →  @(0.157, 0.157, 0.157, 1.0)
Hover BG           #2A2A2A  →  @(0.165, 0.165, 0.165, 1.0)
Selected Row BG    #333333  →  @(0.200, 0.200, 0.200, 1.0)
Spotify Green      #1DB954  →  @(0.114, 0.725, 0.329, 1.0)
Active Green       #1ED760  →  @(0.118, 0.843, 0.376, 1.0)
Primary Text       #FFFFFF  →  @(1.000, 1.000, 1.000, 1.0)
Secondary Text     #B3B3B3  →  @(0.702, 0.702, 0.702, 1.0)
Muted Text         #535353  →  @(0.325, 0.325, 0.325, 1.0)
Divider/Border     #282828  →  @(0.157, 0.157, 0.157, 1.0)
Progress Track     #4D4D4D  →  @(0.302, 0.302, 0.302, 1.0)
Danger Red         #E22134  →  @(0.886, 0.129, 0.204, 1.0)
```

## 2. Spotify Layout (1280×780 window)

```
┌─ Window 1280×780 ──────────────────────────────────────────────────┐
│ (no OS title bar — ChuGL fullscreen ImGui)                         │
├──────────┬─────────────────────────────────────────────────────────┤
│          │                                                         │
│ SIDEBAR  │              MAIN CONTENT AREA                          │
│ 280px    │              (fills remaining width)                    │
│          │                                                         │
│ #000000  │              #121212                                    │
│          │                                                         │
│ ┌──────┐ │                                                         │
│ │ Nav  │ │                                                         │
│ │ Home │ │                                                         │
│ │Search│ │                                                         │
│ └──────┘ │                                                         │
│ ┌──────┐ │                                                         │
│ │Your  │ │                                                         │
│ │Libr- │ │                                                         │
│ │ary   │ │                                                         │
│ │      │ │                                                         │
│ │list  │ │                                                         │
│ │items │ │                                                         │
│ └──────┘ │                                                         │
│          │                                                         │
├──────────┴─────────────────────────────────────────────────────────┤
│                    NOW PLAYING BAR  (~90px)                         │
│ #181818                                                            │
│ ┌────────┬───────────────────────────────────────────┬────────────┐│
│ │AlbumArt│ Title        ◄◄  ▶  ►►         Vol ━━●━━ │  Queue etc ││
│ │ 56x56  │ Artist     ━━━━━━●━━━━━━━━━━             │            ││
│ └────────┴───────────────────────────────────────────┴────────────┘│
└────────────────────────────────────────────────────────────────────┘
```

## 3. ChuGL ImGui Style Overrides

```chuck
// --- Global style (apply at frame start) ---

// Window/Panel
UI.pushStyleVar(UI_StyleVar.WindowRounding, 0.0);     // Spotify: sharp corners
UI.pushStyleVar(UI_StyleVar.WindowBorderSize, 0.0);    // No borders
UI.pushStyleVar(UI_StyleVar.WindowPadding, @(0, 0));   // Edge-to-edge
UI.pushStyleVar(UI_StyleVar.ChildRounding, 8.0);       // Spotify: 8px card radius
UI.pushStyleVar(UI_StyleVar.ChildBorderSize, 0.0);     // No child borders
UI.pushStyleVar(UI_StyleVar.FrameRounding, 500.0);     // Pill-shaped buttons/sliders
UI.pushStyleVar(UI_StyleVar.FramePadding, @(12, 6));   // Button padding
UI.pushStyleVar(UI_StyleVar.ItemSpacing, @(8, 4));     // Tight vertical spacing
UI.pushStyleVar(UI_StyleVar.ScrollbarRounding, 500.0); // Pill scrollbar
UI.pushStyleVar(UI_StyleVar.ScrollbarSize, 8.0);       // Thin scrollbar
UI.pushStyleVar(UI_StyleVar.GrabRounding, 500.0);      // Pill slider grab
UI.pushStyleVar(UI_StyleVar.GrabMinSize, 12.0);        // Slider grab size

// Colors (apply Spotify palette)
UI.pushStyleColor(UI_Color.WindowBg,        @(0.071, 0.071, 0.071, 1.0)); // #121212
UI.pushStyleColor(UI_Color.ChildBg,         @(0.000, 0.000, 0.000, 0.0)); // transparent
UI.pushStyleColor(UI_Color.PopupBg,         @(0.157, 0.157, 0.157, 1.0)); // #282828
UI.pushStyleColor(UI_Color.Border,          @(0.157, 0.157, 0.157, 0.0)); // invisible
UI.pushStyleColor(UI_Color.FrameBg,         @(0.157, 0.157, 0.157, 1.0)); // #282828
UI.pushStyleColor(UI_Color.FrameBgHovered,  @(0.200, 0.200, 0.200, 1.0)); // #333
UI.pushStyleColor(UI_Color.FrameBgActive,   @(0.200, 0.200, 0.200, 1.0));
UI.pushStyleColor(UI_Color.Text,            @(1.0, 1.0, 1.0, 1.0));
UI.pushStyleColor(UI_Color.TextDisabled,    @(0.325, 0.325, 0.325, 1.0)); // #535353
UI.pushStyleColor(UI_Color.Button,          @(0.157, 0.157, 0.157, 1.0)); // #282828
UI.pushStyleColor(UI_Color.ButtonHovered,   @(0.200, 0.200, 0.200, 1.0));
UI.pushStyleColor(UI_Color.ButtonActive,    @(0.114, 0.725, 0.329, 1.0)); // Green
UI.pushStyleColor(UI_Color.Header,          @(0.157, 0.157, 0.157, 1.0));
UI.pushStyleColor(UI_Color.HeaderHovered,   @(0.165, 0.165, 0.165, 1.0));
UI.pushStyleColor(UI_Color.HeaderActive,    @(0.200, 0.200, 0.200, 1.0));
UI.pushStyleColor(UI_Color.Separator,       @(0.157, 0.157, 0.157, 1.0));
UI.pushStyleColor(UI_Color.SliderGrab,      @(1.0, 1.0, 1.0, 1.0));
UI.pushStyleColor(UI_Color.SliderGrabActive,@(0.114, 0.725, 0.329, 1.0));
UI.pushStyleColor(UI_Color.CheckMark,       @(0.114, 0.725, 0.329, 1.0)); // Green checkmark
UI.pushStyleColor(UI_Color.ScrollbarBg,     @(0.071, 0.071, 0.071, 0.0));
UI.pushStyleColor(UI_Color.ScrollbarGrab,   @(0.302, 0.302, 0.302, 0.5));
UI.pushStyleColor(UI_Color.PlotHistogram,   @(0.114, 0.725, 0.329, 1.0)); // Green bars
```

## 4. ChuGL API Cheat Sheet (confirmed working in v0.2.9)

### Available
- `UI.begin(string, UI_Bool, int flags)` / `UI.end()`
- `UI.beginChild(string, vec2 size, int border, int flags)` / `UI.endChild()`
- `UI.setNextWindowPos(vec2, int cond)` / `UI.setNextWindowSize(vec2, int cond)`
- `UI.pushStyleColor(UI_Color, vec4)` / `UI.popStyleColor(int count)`
- `UI.pushStyleVar(UI_StyleVar, float|vec2)` / `UI.popStyleVar(int count)`
- `UI.text(string)` / `UI.textWrapped(string)` / `UI.textDisabled(string)` / `UI.bulletText(string)`
- `UI.button(string)` / `UI.button(string, vec2 size)`
- `UI.colorButton(string, vec4, int flags, vec2 size)` — colored square button
- `UI.checkbox(string, UI_Bool)`
- `UI.slider(string, UI_Float, float min, float max)` / `UI.slider(string, UI_Int, int min, int max)`
- `UI.selectable(string, UI_Bool, int flags)`
- `UI.progressBar(float fraction, vec2 size, string overlay)`
- `UI.combo(string, UI_Int, string[])`
- `UI.separator()` / `UI.separatorText(string)`
- `UI.sameLine(float offset, float spacing)`
- `UI.dummy(vec2 size)` — invisible spacer
- `UI.spacing()` — small vertical gap
- `UI.indent(float)` / `UI.unindent(float)`
- `UI.beginGroup()` / `UI.endGroup()`
- `UI.setCursorPos(vec2)` / `UI.getCursorScreenPos()` → vec2
- `UI.getContentRegionAvail()` → vec2
- `UI.setNextItemWidth(float)`
- `GWindow.framebufferSize()` → vec2

### NOT Available (v0.2.9 build)
- `UI.getWindowDrawList()` — DrawList access not exposed
- `UI.invisibleButton(string, vec2)` — signature mismatch
- `UI.image()` / `UI.imageButton()` — no texture in UI
- `UI.pushFont()` / `UI.popFont()` — commented out in source (see AddFontFromFileTTF)
- `UI.addFontFromFileTTF()` — exists in source but disabled ("can't add font between newFrame/render")

### Font Scaling (DISCOVERED!)
- **`UI_IO.fontGlobalScale(float)`** — scales ALL fonts globally (default 1.0)
- **`UI_IO.fontGlobalScale()`** — returns current scale
- Must be called AFTER `GG.nextFrame() => now` (ImGui needs to be initialized first)
- The font itself is still Proggy Clean (monospace), but scaling makes it more readable
- Recommended: `UI_IO.fontGlobalScale(1.35)` for Spotify-like proportions at 1280×780

## 5. Spotify Element → ChuGL Widget Mapping

| Spotify Element | ChuGL Implementation |
|---|---|
| Sidebar panel | `UI.beginChild("sidebar", @(280, h), false, 0)` + black bg via pushStyleColor |
| Playlist row | `UI.selectable(text, sel, 0)` with Header colors overridden |
| Play/Pause button | `UI.colorButton()` or green-styled `UI.button("▶", @(48, 48))` |
| Skip buttons | `UI.button("⏮", @(32, 32))` / `UI.button("⏭", @(32, 32))` |
| Progress bar | `UI.progressBar(fraction, @(-1, 6), "")` with green PlotHistogram color |
| Volume slider | `UI.setNextItemWidth(120); UI.slider("##vol", ...)` |
| Album art | `UI.colorButton("##art", dominantColor, 0, @(56, 56))` |
| Track title | Bold: `UI.text(title)` with white text color |
| Artist name | `UI.text(artist)` with secondary text color |
| Section header | `UI.text("YOUR LIBRARY")` with muted text + bold |
| Separator | `UI.separator()` with Separator color set to #282828 |
| Clean/Explicit toggle | `UI.checkbox("🔒 Clean Mode", uiClean)` |
| Now playing bottom bar | `UI.beginChild("bar", @(w, 90), false, 0)` with #181818 bg |
