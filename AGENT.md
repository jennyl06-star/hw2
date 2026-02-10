# CS 470 / Music 356 Winter 2026 – HW2: **Featured Artist**  
**Project Title:** *Deepfake Diss Track*  
**Your Name:** Ryan (Stanford)  
**Date:** February 2026  

---

## 1. Assignment Summary (verbatim from CCRMA Wiki)

**Programming Project #2: "Featured Artist"**  
Course: Music and AI (Music356/CS470)  
Instructor: Prof. Ge Wang  

### Due Dates
- **Milestone** (Phase 1 complete + Phase 2 prototype):  
  Webpage due **Mon 2/2 11:59pm**  
  In-class critique **Tue 2/3**
- **Final Deliverable**: Webpage due **Mon 2/9 11:59pm**
- **In-class Presentation**: **Tue 2/10**

### Phases (required)

#### Phase 1: Extract, Classify, Validate
- Use GTZAN dataset (1000 × 30s clips, 10 genres)
- Extract ≥5 different feature configurations (Centroid, Flux, RMS, RollOff, ZeroX, MFCC, Chroma, Kurtosis)
- Real-time k-NN classifier + cross-validation
- Report which configuration gave the highest score

#### Phase 2: Audio Mosaic Tool
- Build a database of **sound frames** (100 ms – 1 s) → feature vectors
- Curate your own audio (songs/snippets or short effects)
- Real-time, feature-based mosaic generator
- Accepts **any audio input** (mic, file, UGen)
- Interactive controls (keyboard/mouse, pitch via `SndBuf.rate`, window size, subsets)
- **Optional audiovisual extension** using **ChuGL**

#### Phase 3: Musical Mosaic!
- Turn the Phase 2 tool into a **musical statement or performance**
- Optional: **audiovisual** (ChuGL strongly encouraged)
- Deliver: 3–5 minute video of the performance

### Final Webpage Requirements
- Title + description
- **All ChucK code** (Phase 1–3)
- Video of the musical statement
- ~300-word reflection
- Acknowledgements (sources, people, code)

**Sample code base:** https://ccrma.stanford.edu/courses/356-winter-2026/code/featured-artist/  
**ChuGL video example:** https://chuck.stanford.edu/chugl/examples/basic/video.ck

---

## 2. Your Previous Project (Milestone Feedback)

**Core idea (pre-pivot):**  
Podcast audio → real-time KNN search → play closest meme sound clips (18+ memes).  
Visual: simple Spotify-style UI.

**Classmate feedback screenshots (full transcription):**

### Screenshot 1 – Quick notes
- “Meme sound blends into the podcast? Can replace it”
- Use a slider (push to end/“space” button → all music; other end → all podcast)
- More than 18 memes
- Put meme into Audacity → 1 meme → 5 variations
- Or podcast into Audacity → make louder → turn into fluent speech
- Artfully blend into the podcast
- Controlled variation

### Screenshot 2 & 3 – Full Google Doc “Featured Artist (Milestone)”

**Michelle:** Curious about KNN algorithm. Keep Spotify interface. Maybe drop meme sounds like pebbles into a lake → ripples distort bottom image.

**Anthony:** Vine boom is sleeper agent. Emotional. Visual: pebble ripples stacking.

**Ben:** Memesmith pt 2.

**Tianzhe:** Continuous podcast + emerging sound effects prevents fragmentation.

**Richard:** Laughing at deepfake threats. Disconnect is cool. Keep Spotify window. Add splashes of color per effect.

**Kim:** Auto-soundboard! Match meme video with audio. Run on AITA Reddit posts.

**Vicky:** Brain rot gold. Real-life application (loleeaaoeeeaao).

**Sid:** Love sound effects. Wants **interactive GUI** for standardized input.

**Kalu:** Big fan of meme-ish-ness. More **interactive elements** (knobs/sliders) to change audio params.

**Andrew:** Cool concept + AI commentary.

**Ilan:** Awesome. Add “eh eh eh” if missing.

**Li:** Broadcast mix with music → smoother mixing.

**Jillian:** Pop up memes along with audio.

**Michael:** Change source audio? Disconnect with serious deepfake podcast.

**Lejun:** Podcast as meme aggregation? **Bidirectional** – input meme → mosaic podcast.

**Tae Kyu:** Fun play on “someone official getting interrupted”. Make source audio stop and look frustrated.

**Calvin:** Media overload commentary. In ChuGL: cartoon/comic text effects, shock-jock SFX.

**Zoe:** Match image/visual to each sound effect.

**Carlotta:** Visualize the memes as well.

**Sriram:** Use podcasts with videos.

**Taralyn:** Visuals that symbolize meme being played + show input audio.

**Nancy:** (cut off)

---

## 3. Final Concept – **Deepfake Diss Track**

**Core idea:**  
A serious AI deepfake podcast (input) is **constantly interrupted and dissed** by its own cloned rap commentary.  
The more the host talks about deepfakes, the more the rap takes over — visual chaos escalates until the podcast is fully “cloned” and glitched.

**Why it’s perfect for the assignment:**
- Phase 1: Reuse your KNN classifier code (features already extracted)
- Phase 2: Mosaic tool → rap clip database (50–100 short clips)
- Phase 3: Musical statement with **societal commentary** on AI voice theft, authenticity, music industry disruption
- Audiovisual: Full ChuGL performance (encouraged)

**Audio Database (50+ clips – record yourself!)**  
Punchy rap lines (0.5–3 s):
- “AI stole my flow, now the industry echo”
- “Deepfake my bars, watch the real ones fade”
- “Tupac in the cloud, Drake in the grave”
- “BBL Drizzy? Nah, that’s my real diss-y”
- … (record 20–30 base, then generate 2–3 variations each with Audacity or code)

**Real-time behavior**
- Podcast (mic/file) → feature extraction → KNN → trigger closest rap diss
- Variations: `SndBuf.rate` (pitch/speed from MFCC centroid), granular stutter (high Kurtosis), filter ducking
- Smoother blend: ADSR crossfade + podcast gain duck
- Escalation: lower similarity threshold over time → more layers → podcast eventually drowns

**ChuGL Visuals (the show-stopper)**
- **Glitchy lyric pop-ups** (`GText`): exact rap line flies in, scales with RMS, shakes with Flux, color by Chroma
- **Deepfake avatar**: 3D head (monkey mesh) morphs between “real” and glitchy texture + particle burst
- **Ripple system** (Anthony’s idea): each trigger spawns pebble-like expanding circles that stack and distort background (Spotify UI or news ticker)
- **Background**: scrolling deepfake headlines + shattered-mirror particles
- **UI**: Podcast progress bar glitches, thumbnails of cloned rappers pop in
- **Sliders** (Kalu/Sid feedback): Blend %, Glitch Intensity, Similarity Threshold, Ripple Strength

**Performance arc (3–5 min)**
1. Podcast starts serious → first few memes
2. Rap layers build → visuals escalate
3. Final 30 s: total visual/audio meltdown → podcast slows/glitches → rap wins

---

## 4. Technical Implementation Plan

### Audio Pipeline (build on your existing KNN code)
```chuck
// inside your KNN loop
if (distance < threshold) {
    rapBuf[clipIndex].rate(0.7 + distance * 1.3);  // pitch "fake-ness"
    rapEnv.keyOn();                               // smooth fade
    spawnRipple(rms.last());
    displayLyric(rapLyrics[clipIndex]);
}
```

### ChuGL Starter (copy from video.ck)
```chuck
GScene scene;
GText lyric => scene;
Circle ripple => scene;

// on trigger
lyric.text(rapLyrics[clipIndex]);
lyric.pos( Math.random2f(-1,1), Math.random2f(-1,1) );
lyric.scale(1 + rms.last()*4);
```

### UI Sliders (ChuGL built-in)
```chuck
UI_Slider blend("Podcast vs Rap", 0, 100, 50) @=> UI_Slider s;
UI_Slider glitch("Glitch Intensity", 0, 10, 5) @=> UI_Slider g;
```

---

## 5. To-Do List (get this done before 2/9)

1. **Tonight** – Record 20–30 rap clips (phone → Audacity → 44.1 kHz wav)
2. Run `mosaic-extract.ck` on them → build database
3. Add one ChuGL element first (GText + glitch)
4. Add ripple system + sliders
5. Record 3–5 min performance video
6. Write 300-word reflection
7. Build webpage (CCRMA or Medium)

---

## 6. Resources & Links

- Assignment wiki: https://ccrma.stanford.edu/wiki/356-winter-2026/hw2
- Sample code: https://ccrma.stanford.edu/courses/356-winter-2026/code/featured-artist/
- ChuGL docs & examples: https://chuck.stanford.edu/chugl/
- Your previous code (reuse KNN + FeatureCollector)
- GTZAN (only for Phase 1)