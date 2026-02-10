//------------------------------------------------------------------------------
// name: deepfake-diss.ck
// desc: Phase 3 — "Deepfake Diss Track" performance
//
//       A serious AI deepfake podcast is interrupted by rap clips matched
//       via KNN.  Over time real clips morph into AI deepfake versions.
//       Full Spotify-style ImGui UI with podcast selector, transport,
//       lyrics display, and clean/explicit toggle.
//
// USAGE:
//   chuck deepfake-diss.ck:RAP_DB
//     RAP_DB = rap_db.txt (feature vectors from extract-rap-db.ck)
//
// EXAMPLE:
//   chuck deepfake-diss.ck:rap_db.txt
//
// date: February 2026
//------------------------------------------------------------------------------


//==============================================================================
//  COMMAND LINE ARGS
//==============================================================================
string FEATURES_FILE;
if( me.args() >= 1 ) me.arg(0) => FEATURES_FILE;
else
{
    <<< "usage: chuck deepfake-diss.ck:RAP_DB", "" >>>;
    me.exit();
}


//==============================================================================
//  PODCAST LIBRARY  (user selects from UI)
//==============================================================================
class PodcastInfo
{
    string file;
    string title;
    string subtitle;
    string host;
    string videoFile;  // podcast_videos/podcast_xxx.mpg (or "")
    fun void set( string f, string t, string s, string h )
    { f => file; t => title; s => subtitle; h => host; "" => videoFile; }
    fun void setWithVideo( string f, string t, string s, string h, string v )
    { f => file; t => title; s => subtitle; h => host; v => videoFile; }
}

PodcastInfo podLib[0];
{
    // --- populate podcast list from directory ---
    // The WSJ one is always first
    PodcastInfo p;
    FileIO vidTest;
    if( vidTest.open( me.dir() + "podcast_videos/podcast_wsj.mpg", FileIO.READ ) )
    {
        vidTest.close();
        p.setWithVideo( "podcast_wsj.wav",
               "The Journal",
               "Her Client Was Deepfaked. She Says xAI Is to Blame.",
               "WSJ",
               "podcast_videos/podcast_wsj.mpg" );
    }
    else
    {
        p.set( "podcast_wsj.wav",
               "The Journal",
               "Her Client Was Deepfaked. She Says xAI Is to Blame.",
               "WSJ" );
    }
    podLib << p;
}
// try to load optional extra podcasts (auto-detect matching video)
fun void tryAddPodcast( string file, string title, string sub, string host )
{
    FileIO test;
    if( test.open( me.dir() + file, FileIO.READ ) )
    {
        test.close();
        PodcastInfo p;
        // derive video filename: podcast_xxx.wav → podcast_videos/podcast_xxx.mpg
        file.substring(0, file.length() - 4) => string base;
        "podcast_videos/" + base + ".mpg" => string vidPath;
        FileIO vidTest;
        if( vidTest.open( me.dir() + vidPath, FileIO.READ ) )
        {
            vidTest.close();
            p.setWithVideo( file, title, sub, host, vidPath );
            <<< "[podcast] found:", file, "+ video" >>>;
        }
        else
        {
            p.set( file, title, sub, host );
            <<< "[podcast] found:", file, "(no video)" >>>;
        }
        podLib << p;
    }
}
tryAddPodcast( "podcast_ted.wav",
    "TED Talks",
    "Fake videos of real people — and how to spot them",
    "TED" );
tryAddPodcast( "podcast_60min.wav",
    "60 Minutes",
    "Deepfakes: A threat to society?",
    "CBS" );
tryAddPodcast( "podcast_bbc.wav",
    "BBC News",
    "AI deepfake of me was used to scam my friend",
    "BBC" );
tryAddPodcast( "podcast_cnbc.wav",
    "CNBC",
    "The Rise of AI Deepfakes",
    "CNBC" );
tryAddPodcast( "podcast_60min.wav",
    "60 Minutes",
    "Dark Sides of Artificial Intelligence — Deepfakes",
    "CBS" );
tryAddPodcast( "podcast_bbc.wav",
    "BBC News",
    "Deepfake scams — How AI became the con artist's best tool",
    "BBC" );
tryAddPodcast( "podcast_vice.wav",
    "VICE",
    "Deepfakes: The Danger of Artificial Intelligence",
    "VICE" );
tryAddPodcast( "podcast_vox.wav",
    "Vox",
    "The most urgent threat of deepfakes isn't politics",
    "Vox" );
tryAddPodcast( "podcast_nbc.wav",
    "NBC News",
    "Experts warn deepfakes and AI could threaten elections",
    "NBC" );

0 => int currentPodcastIdx;
false => int podcastSwitchRequested;
0 => int pendingPodcastIdx;


//==============================================================================
//  AUDIO PIPELINE
//==============================================================================

// Podcast → analysis + output
SndBuf podcast => Gain podGain => dac;
podcast => FFT fft;

// load the first podcast
me.dir() + podLib[0].file => podcast.read;
0.85 => podGain.gain;

// feature extraction (same as extraction script: centroid+flux+rms+mfcc20)
FeatureCollector combo => blackhole;
fft =^ Centroid centroid =^ combo;
fft =^ Flux flux =^ combo;
fft =^ RMS rms =^ combo;
fft =^ MFCC mfcc =^ combo;

20 => mfcc.numCoeffs;
10 => mfcc.numFilters;

// FFT settings
4096 => fft.size;
fft.size() => podcast.chunks;
Windowing.hann(fft.size()) => fft.window;
(fft.size()/2)::samp => dur HOP;

// get dimension count
combo.upchuck();
combo.fvals().size() => int NUM_DIMENSIONS;


// --- Single rap voice (sequential, non-overlapping) ---
SndBuf rapBuf => ADSR rapEnv => Gain rapGain => dac;
0.85 => rapGain.gain;
rapEnv.set( 30::ms, 100::ms, 1.0, 60::ms );


//==============================================================================
//  LOAD FEATURE DATABASE + KNN
//==============================================================================
0 => int numPoints;
0 => int numCoeffs;

loadFile( me.dir() + FEATURES_FILE ) @=> FileIO @ fin;
if( !fin.good() ) me.exit();
if( numCoeffs != NUM_DIMENSIONS )
{
    <<< "[error] dimension mismatch:", NUM_DIMENSIONS, "vs", numCoeffs >>>;
    me.exit();
}

class AudioWindow
{
    int uid;
    int fileIndex;
    float windowTime;
    fun void set( int id, int fi, float wt )
    { id => uid; fi => fileIndex; wt => windowTime; }
}

AudioWindow windows[numPoints];
string files[0];
int filename2state[0];
float inFeatures[numPoints][numCoeffs];
int uids[numPoints];
for( int i; i < numPoints; i++ ) i => uids[i];

readData( fin );

KNN2 knn;
5 => int K;
int knnResult[K];
knn.train( inFeatures, uids );


//==============================================================================
//  LOAD LYRICS + DEEPFAKE CLIPS  (both clean & explicit variants)
//==============================================================================
string rapLyricsAll[0];
string rapLyricsClean[0];
string dfClipsAll[0];
string dfClipsClean[0];
string dfLyricsAll[0];
string dfLyricsClean[0];

fun void loadLines( string path, string arr[] )
{
    FileIO lf;
    if( lf.open( me.dir() + path, FileIO.READ ) )
    {
        while( lf.more() )
        {
            lf.readLine().trim() => string line;
            if( line != "" ) arr << line;
        }
        lf.close();
    }
}

loadLines( "clip_lyrics.txt",           rapLyricsAll   );
loadLines( "clip_lyrics_clean.txt",     rapLyricsClean );
loadLines( "deepfake-clips.txt",        dfClipsAll     );
loadLines( "deepfake-clips-clean.txt",  dfClipsClean   );
loadLines( "deepfake_lyrics.txt",       dfLyricsAll    );
loadLines( "deepfake_lyrics_clean.txt", dfLyricsClean  );

<<< "[data] lyrics:", rapLyricsAll.size(), "all /", rapLyricsClean.size(), "clean" >>>;
<<< "[data] deepfakes:", dfClipsAll.size(), "all /", dfClipsClean.size(), "clean" >>>;


//==============================================================================
//  PERFORMANCE STATE
//==============================================================================
true  => int cleanMode;        // start class-safe
false => int isPaused;
false => int glitchMode;
0     => int triggerCount;
0     => int dfTriggerCount;
0.0   => float glitchAmount;

now => time performanceStart;
4::minute => dur TOTAL_DURATION;

// --- timing knobs (exposed in UI) ---
UI_Float uiListenTime;   4.0 => uiListenTime.val;   // seconds of podcast to accumulate
UI_Float uiCooldown;     1.0 => uiCooldown.val;      // gap after clip finishes
UI_Float uiThreshold;    0.6 => uiThreshold.val;      // similarity threshold
UI_Int   uiK;            5   => uiK.val;              // KNN neighbors
UI_Float uiPodVol;       0.85 => uiPodVol.val;        // podcast volume
UI_Float uiRapVol;       0.85 => uiRapVol.val;        // rap clip volume
UI_Bool  uiClean;        1   => uiClean.val;           // clean mode checkbox
UI_Bool  uiGlitch;       0   => uiGlitch.val;          // glitch mode checkbox
UI_Bool  uiPaused;       0   => uiPaused.val;          // pause toggle

// current trigger display
"" => string lastLyric;
"" => string lastArtist;
"" => string lastClipFile;
false => int   lastWasDeepfake;
0.0   => float lastTriggerTime;

fun float progress()
{
    return Math.min(1.0, (now - performanceStart) / TOTAL_DURATION);
}
fun int currentAct()
{
    progress() => float p;
    if( p < 0.25 ) return 1;
    if( p < 0.7  ) return 2;
    return 3;
}

// active-mode helpers
fun string[] activeLyrics()
{ if( cleanMode ) return rapLyricsClean; return rapLyricsAll; }
fun string[] activeDfClips()
{ if( cleanMode ) return dfClipsClean; return dfClipsAll; }
fun string[] activeDfLyrics()
{ if( cleanMode ) return dfLyricsClean; return dfLyricsAll; }


//==============================================================================
//  ChuGL WINDOW + SCENE SETUP
//==============================================================================
GWindow.windowed(1280, 780);
GWindow.title("DEEPFAKE DISS TRACK");

GCamera cam --> GG.scene();
cam.pos(@(0, 0, 8));
cam.lookAt(@(0, 0, 0));
GG.scene().backgroundColor(@(0.071, 0.071, 0.071));  // #121212 matches Spotify dark

//==============================================================================
//  VIDEO PLANES (podcast video + rap music video, shown in 3D scene behind UI)
//==============================================================================

// ── Podcast video (background, always playing, muted — audio from SndBuf) ──
null @=> Video @ podVideo;      // loaded when video file exists
Gain podVidMute => blackhole;   // mute video audio
false => int podVideoLoaded;

GPlane podVideoPlane --> GG.scene();
FlatMaterial podVidMat;
podVideoPlane.mat(podVidMat);
// Position: fills the blank area in main content (below text cards, above player bar)
// Camera at z=8, FOV=45°. At z=0 visible area is ~10.86 x 6.62
// Content area right of sidebar: x from ~-3.0 to 5.4, y from ~-2.6 to 3.3
// Text cards occupy the top ~30%, so video starts around y≈1.0 downward
// Negative scaY flips the video right-side up (UV origin fix)
podVideoPlane.pos(@(1.2, -0.8, -0.5));
podVideoPlane.sca(@(8.5, -3.8, 1.0));
podVideoPlane.sca(@(0, 0, 0));        // hidden until video loads

// ── Rap music video (flashes when a clip triggers) ──
null @=> Video @ rapVideo;
Gain rapVidMute => blackhole;
false => int rapVideoLoaded;
0.0   => float rapVideoLife;     // countdown timer for display
"" => string rapVideoCurrentSong;  // tracks which song's video is loaded

GPlane rapVideoPlane --> GG.scene();
FlatMaterial rapVidMat;
rapVideoPlane.mat(rapVidMat);
// Same area as podcast video but in front (z=0.1), flipped with negative scaY
rapVideoPlane.pos(@(1.2, -0.8, 0.1));
rapVideoPlane.sca(@(0, 0, 0));  // hidden until triggered

// ── Song index → rap video file mapping ──
// Maps 3-digit song index string (e.g. "000") → video path
string rapVideoMap[0];  // assoc array: key=songIdx, val=video path

fun void scanRapVideos()
{
    // List of known songs with music videos
    string knownSongs[0];
    knownSongs << "000_Kendrick_Lamar_HUMBLE";
    knownSongs << "001_Kendrick_Lamar_DNA";
    knownSongs << "003_Kendrick_Lamar_Not_Like_Us";
    knownSongs << "004_Drake_Gods_Plan";
    knownSongs << "005_Drake_Started_From_The_Bottom";
    knownSongs << "008_J_Cole_Middle_Child";
    knownSongs << "010_Travis_Scott_SICKO_MODE";
    knownSongs << "011_Travis_Scott_goosebumps";
    knownSongs << "012_Travis_Scott_HIGHEST_IN_THE_ROOM";
    knownSongs << "014_Tupac_Hit_Em_Up";
    knownSongs << "015_Tupac_Changes";
    knownSongs << "016_Biggie_Juicy";
    knownSongs << "019_ASAP_Rocky_Praise_The_Lord";
    knownSongs << "022_Eminem_Rap_God";
    knownSongs << "024_Kanye_West_Stronger";
    knownSongs << "025_Kanye_West_Gold_Digger";
    knownSongs << "026_Kanye_West_POWER";
    knownSongs << "032_Lil_Wayne_Lollipop";
    knownSongs << "034_Future_Mask_Off";
    knownSongs << "036_Cardi_B_Bodak_Yellow";
    knownSongs << "038_Playboi_Carti_Magnolia";

    0 => int found;
    for( int i; i < knownSongs.size(); i++ )
    {
        "rap_videos/" + knownSongs[i] + ".mpg" => string vPath;
        FileIO vf;
        if( vf.open( me.dir() + vPath, FileIO.READ ) )
        {
            vf.close();
            knownSongs[i].substring(0, 3) => string idxStr;
            vPath => rapVideoMap[idxStr];
            found++;
        }
    }
    <<< "[video] Found", found, "rap music videos" >>>;
}
scanRapVideos();

// ── Load initial podcast video ──
fun void loadPodcastVideo( int idx )
{
    if( idx < 0 || idx >= podLib.size() ) return;
    podLib[idx].videoFile => string vf;
    if( vf == "" )
    {
        false => podVideoLoaded;
        podVideoPlane.sca(@(0, 0, 0));
        <<< "[video] No podcast video for", podLib[idx].title >>>;
        return;
    }

    <<< "[video] Loading podcast video:", vf >>>;
    Video newPodVid( me.dir() + vf );
    newPodVid @=> podVideo;
    podVideo => podVidMute;
    podVideo.loop(1);
    podVideo.rate(1.0);
    podVidMat.colorMap(podVideo.texture());
    true => podVideoLoaded;
    podVideoPlane.sca(@(8.5, -3.8, 1.0));  // negative Y = right-side up
    <<< "[video] Podcast video loaded!" >>>;
}
loadPodcastVideo(0);

// ── Trigger rap music video ──
fun void triggerRapVideo( string clipFile )
{
    // extract song index from clip filename: "rap_clips/000_..."  → "000"
    // or "deepfake_clips/df_ara_000_..." → "000"
    "" => string idxStr;
    if( clipFile.find("rap_clips/") == 0 && clipFile.length() >= 13 )
        clipFile.substring(10, 3) => idxStr;
    else if( clipFile.find("deepfake_clips/df_ara_") == 0 && clipFile.length() >= 25 )
        clipFile.substring(22, 3) => idxStr;
    else if( clipFile.find("deepfake_clips/df_") == 0 && clipFile.length() >= 21 )
        clipFile.substring(18, 3) => idxStr;

    if( idxStr == "" || !rapVideoMap.isInMap(idxStr) )
    {
        // no video for this song — hide rap video plane
        false => rapVideoLoaded;
        rapVideoPlane.sca(@(0, 0, 0));
        return;
    }

    // Only reload if switching to a different song's video
    if( idxStr != rapVideoCurrentSong )
    {
        rapVideoMap[idxStr] => string vPath;
        Video newRapVid( me.dir() + vPath );
        newRapVid @=> rapVideo;
        rapVideo => rapVidMute;
        rapVideo.rate(1.0);
        rapVidMat.colorMap(rapVideo.texture());
        idxStr => rapVideoCurrentSong;
    }

    true => rapVideoLoaded;
    rapVideoPlane.sca(@(8.5, -3.8, 1.0));  // negative Y = right-side up
    4.0 => rapVideoLife;  // show for 4 seconds
}

//--- floating lyric particles (behind UI) ---
8 => int MAX_LYRICS;
GText lyricTexts[MAX_LYRICS];
float lyricLife[MAX_LYRICS];
float lyricVelY[MAX_LYRICS];
for( int i; i < MAX_LYRICS; i++ )
{
    lyricTexts[i] --> GG.scene();
    lyricTexts[i].text("");
    lyricTexts[i].sca(@(0.5, 0.5, 0.5));
    0.0 => lyricLife[i];
}
0 => int nextLyric;

//--- ripple circles ---
8 => int MAX_RIPPLES;
GCircle ripples[MAX_RIPPLES];
float rippleLife[MAX_RIPPLES];
for( int i; i < MAX_RIPPLES; i++ )
{
    ripples[i] --> GG.scene();
    ripples[i].sca(@(0.01, 0.01, 0.01));
    0.0 => rippleLife[i];
}
0 => int nextRipple;

//--- glitch cubes ---
20 => int MAX_PARTICLES;
GCube particles[MAX_PARTICLES];
float particleLife[MAX_PARTICLES];
for( int i; i < MAX_PARTICLES; i++ )
{
    particles[i] --> GG.scene();
    particles[i].sca(@(0.0, 0.0, 0.0));
    0.0 => particleLife[i];
}
0 => int nextParticle;

// spawn helpers
fun void spawnLyric( string text, float rmsVal )
{
    lyricTexts[nextLyric].text(text);
    lyricTexts[nextLyric].pos(@(Math.random2f(-4.5, 4.5), Math.random2f(-2.0, 2.5), 0));
    lyricTexts[nextLyric].sca(@(0.35 + rmsVal * 2.5, 0.35 + rmsVal * 2.5, 1.0));
    4.0 => lyricLife[nextLyric];
    Math.random2f(0.2, 0.8) => lyricVelY[nextLyric];
    (nextLyric + 1) % MAX_LYRICS => nextLyric;
}
fun void spawnRipple( float x, float y )
{
    ripples[nextRipple].pos(@(x, y, -0.1));
    ripples[nextRipple].sca(@(0.1, 0.1, 0.1));
    3.0 => rippleLife[nextRipple];
    (nextRipple + 1) % MAX_RIPPLES => nextRipple;
}
fun void spawnGlitchParticle()
{
    particles[nextParticle].pos(
        @(Math.random2f(-5,5), Math.random2f(-3,3), Math.random2f(-1,1)));
    particles[nextParticle].sca(
        @(Math.random2f(0.05,0.25), Math.random2f(0.05,0.25), Math.random2f(0.01,0.08)));
    1.5 => particleLife[nextParticle];
    (nextParticle + 1) % MAX_PARTICLES => nextParticle;
}


// shared flag so UI knows when clip is playing
false => int isPlayingClip;

// feature accumulation buffers
32 => int MAX_ACC_FRAMES;  // max frames we'll accumulate
float accFeatures[MAX_ACC_FRAMES][NUM_DIMENSIONS];
float featureMean[NUM_DIMENSIONS];


//==============================================================================
//  SPOTIFY-STYLE ImGui UI  (sporked render loop)
//==============================================================================
fun void uiLoop()
{
    // ── Exact Spotify palette (hex → 0-1) ──
    @(0.0, 0.0, 0.0, 0.0) => vec4 mainBg;      // transparent — 3D scene shows through
    @(0.000, 0.000, 0.000, 1.0) => vec4 sidebarBg;    // #000000
    @(0.094, 0.094, 0.094, 1.0) => vec4 playerBg;     // #181818
    @(0.110, 0.110, 0.110, 1.0) => vec4 cardBg;       // #1C1C1C
    @(0.165, 0.165, 0.165, 1.0) => vec4 hoverBg;      // #2A2A2A
    @(0.200, 0.200, 0.200, 1.0) => vec4 selectedBg;   // #333333
    @(0.114, 0.725, 0.329, 1.0) => vec4 spGreen;      // #1DB954
    @(0.118, 0.843, 0.376, 1.0) => vec4 activeGreen;  // #1ED760
    @(1.0,   1.0,   1.0,   1.0) => vec4 textPrimary;  // #FFFFFF
    @(0.702, 0.702, 0.702, 1.0) => vec4 textSecondary; // #B3B3B3
    @(0.325, 0.325, 0.325, 1.0) => vec4 textMuted;    // #535353
    @(0.302, 0.302, 0.302, 1.0) => vec4 progressTrack; // #4D4D4D
    @(0.886, 0.129, 0.204, 1.0) => vec4 dangerRed;    // #E22134

    280.0 => float SIDEBAR_W;
    90.0  => float PLAYER_H;
    8.0   => float GAP;    // gap between sidebar cards

    while( true )
    {
        GG.nextFrame() => now;
        GG.dt() => float dt;
        progress() => float p;
        currentAct() => int act;

        // ── Sync UI state → engine state ──
        uiClean.val()  => cleanMode;
        uiGlitch.val() => glitchMode;
        uiK.val()      => K;
        if( K < 1 ) 1 => K;
        uiPodVol.val()  => podGain.gain;
        uiRapVol.val()  => rapGain.gain;

        if( uiPaused.val() != isPaused )
        {
            uiPaused.val() => isPaused;
            if( isPaused ) 0 => podcast.rate;
            else 1 => podcast.rate;
        }

        if( podcastSwitchRequested )
        {
            false => podcastSwitchRequested;
            pendingPodcastIdx => currentPodcastIdx;
            me.dir() + podLib[currentPodcastIdx].file => podcast.read;
            fft.size() => podcast.chunks;
            0 => podcast.pos;
            if( !isPaused ) 1 => podcast.rate;
            // Load matching video
            loadPodcastVideo(currentPodcastIdx);
        }

        // ── 3D scene bg (dark, behind opaque UI) ──
        GG.scene().backgroundColor(@(0.04, 0.04, 0.05));

        // ── Update 3D lyric/ripple/particle + video systems ──

        // Rap video fade-out
        if( rapVideoLife > 0 )
        {
            dt -=> rapVideoLife;
            if( rapVideoLife <= 0 )
            {
                rapVideoPlane.sca(@(0, 0, 0));
                false => rapVideoLoaded;
            }
        }

        for( int i; i < MAX_LYRICS; i++ )
        {
            if( lyricLife[i] > 0 )
            {
                dt -=> lyricLife[i];
                lyricTexts[i].posY( lyricTexts[i].posY() + lyricVelY[i] * dt );
                lyricTexts[i].sca( lyricTexts[i].sca() * (1.0 - dt * 0.2) );
                if( glitchMode || p > 0.5 )
                    lyricTexts[i].posX(
                        lyricTexts[i].posX() + Math.random2f(-0.02, 0.02) * p * 4);
            }
            else { lyricTexts[i].text(""); }
        }
        for( int i; i < MAX_RIPPLES; i++ )
        {
            if( rippleLife[i] > 0 ) { dt -=> rippleLife[i]; ripples[i].sca(ripples[i].sca()+@(dt*1.8,dt*1.8,0)); }
            else { ripples[i].sca(@(0,0,0)); }
        }
        for( int i; i < MAX_PARTICLES; i++ )
        {
            if( particleLife[i] > 0 ) { dt -=> particleLife[i]; particles[i].posY(particles[i].posY()+dt*Math.random2f(-1,1)); particles[i].rotZ(particles[i].rotZ()+dt*3.0); }
            else { particles[i].sca(@(0,0,0)); }
        }
        if( p > 0.35 && Math.random2f(0,1) < p * 0.25 ) spawnGlitchParticle();

        // ================================================================
        //  GLOBAL SPOTIFY STYLE OVERRIDES
        // ================================================================
        // StyleVars (12)
        UI.pushStyleVar(UI_StyleVar.WindowRounding,    0.0);
        UI.pushStyleVar(UI_StyleVar.WindowBorderSize,  0.0);
        UI.pushStyleVar(UI_StyleVar.WindowPadding,     @(0, 0));
        UI.pushStyleVar(UI_StyleVar.ChildRounding,     8.0);
        UI.pushStyleVar(UI_StyleVar.ChildBorderSize,   0.0);
        UI.pushStyleVar(UI_StyleVar.FrameRounding,     500.0);
        UI.pushStyleVar(UI_StyleVar.FramePadding,      @(12, 6));
        UI.pushStyleVar(UI_StyleVar.ItemSpacing,       @(8, 4));
        UI.pushStyleVar(UI_StyleVar.ScrollbarRounding, 500.0);
        UI.pushStyleVar(UI_StyleVar.ScrollbarSize,     6.0);
        UI.pushStyleVar(UI_StyleVar.GrabRounding,      500.0);
        UI.pushStyleVar(UI_StyleVar.GrabMinSize,       12.0);
        // StyleColors (22)
        UI.pushStyleColor(UI_Color.WindowBg,         mainBg);
        UI.pushStyleColor(UI_Color.ChildBg,          @(0.0, 0.0, 0.0, 0.0));
        UI.pushStyleColor(UI_Color.Border,           @(0.0, 0.0, 0.0, 0.0));
        UI.pushStyleColor(UI_Color.FrameBg,          @(0.157, 0.157, 0.157, 1.0));
        UI.pushStyleColor(UI_Color.FrameBgHovered,   hoverBg);
        UI.pushStyleColor(UI_Color.FrameBgActive,    selectedBg);
        UI.pushStyleColor(UI_Color.Text,             textPrimary);
        UI.pushStyleColor(UI_Color.TextDisabled,     textMuted);
        UI.pushStyleColor(UI_Color.Button,           @(0.0, 0.0, 0.0, 0.0));
        UI.pushStyleColor(UI_Color.ButtonHovered,    hoverBg);
        UI.pushStyleColor(UI_Color.ButtonActive,     selectedBg);
        UI.pushStyleColor(UI_Color.Header,           @(0.0, 0.0, 0.0, 0.0));
        UI.pushStyleColor(UI_Color.HeaderHovered,    hoverBg);
        UI.pushStyleColor(UI_Color.HeaderActive,     selectedBg);
        UI.pushStyleColor(UI_Color.Separator,        @(0.157, 0.157, 0.157, 1.0));
        UI.pushStyleColor(UI_Color.SliderGrab,       textPrimary);
        UI.pushStyleColor(UI_Color.SliderGrabActive, spGreen);
        UI.pushStyleColor(UI_Color.CheckMark,        spGreen);
        UI.pushStyleColor(UI_Color.ScrollbarBg,      @(0.0, 0.0, 0.0, 0.0));
        UI.pushStyleColor(UI_Color.ScrollbarGrab,    progressTrack);
        UI.pushStyleColor(UI_Color.PlotHistogram,    spGreen);
        UI.pushStyleColor(UI_Color.PopupBg,          @(0.157, 0.157, 0.157, 1.0));

        // ── Full-viewport root window ──
        GWindow.framebufferSize() => vec2 win;
        UI.setNextWindowPos(@(0, 0), 0);
        UI.setNextWindowSize(win, 0);

        UI_Bool mainOpen(1);
        if( UI.begin("##spotify", mainOpen,
                UI_WindowFlags.NoTitleBar | UI_WindowFlags.NoResize |
                UI_WindowFlags.NoMove | UI_WindowFlags.NoScrollbar |
                UI_WindowFlags.NoBringToFrontOnFocus) )
        {
            win.y - PLAYER_H => float contentH;

            // ============================================================
            //  LEFT SIDEBAR  (black, Spotify's "Your Library" panel)
            // ============================================================
            UI.pushStyleColor(UI_Color.ChildBg, sidebarBg);
            UI.pushStyleVar(UI_StyleVar.WindowPadding, @(8, 8));
            if( UI.beginChild("##sidebar", @(SIDEBAR_W, contentH), false, 0) )
            {
                // ── Top nav card (rounded dark card) ──
                UI.pushStyleColor(UI_Color.ChildBg, cardBg);
                UI.pushStyleVar(UI_StyleVar.WindowPadding, @(20, 14));
                if( UI.beginChild("##nav_card", @(SIDEBAR_W - 16, 56), false, 0) )
                {
                    UI.pushStyleColor(UI_Color.Text, textSecondary);
                    UI.text("Home");
                    UI.sameLine(0, 24);
                    UI.text("Search");
                    UI.popStyleColor(1);
                }
                UI.endChild();
                UI.popStyleVar(1);
                UI.popStyleColor(1);

                UI.dummy(@(0, GAP));

                // ── Library card (main sidebar card) ──
                UI.pushStyleColor(UI_Color.ChildBg, cardBg);
                UI.pushStyleVar(UI_StyleVar.WindowPadding, @(12, 12));
                if( UI.beginChild("##lib_card", @(SIDEBAR_W - 16, contentH - 80), false, 0) )
                {
                    // Section header row
                    UI.pushStyleColor(UI_Color.Text, textSecondary);
                    UI.text("Your Library");
                    UI.popStyleColor(1);
                    UI.sameLine(0, 8);
                    if( UI.button("+", @(24, 24)) ) { }

                    UI.dummy(@(0, 8));

                    // ── Podcast list items (like playlist rows) ──
                    for( int i; i < podLib.size(); i++ )
                    {
                        false => int rowClicked;

                        // Brand color per network (thumbnail identity)
                        vec4 hostColor;
                        if( podLib[i].host == "WSJ" )       @(0.80, 0.62, 0.25, 1.0) => hostColor;  // gold
                        else if( podLib[i].host == "TED" )  @(0.90, 0.12, 0.10, 1.0) => hostColor;  // red
                        else if( podLib[i].host == "CBS" )  @(0.18, 0.35, 0.78, 1.0) => hostColor;  // blue
                        else if( podLib[i].host == "BBC" )  @(0.75, 0.10, 0.20, 1.0) => hostColor;  // burgundy
                        else if( podLib[i].host == "CNBC" ) @(0.02, 0.48, 0.76, 1.0) => hostColor;  // teal
                        else if( podLib[i].host == "VICE" ) @(0.15, 0.15, 0.15, 1.0) => hostColor;  // dark
                        else if( podLib[i].host == "Vox" )  @(0.93, 0.84, 0.10, 1.0) => hostColor;  // yellow
                        else if( podLib[i].host == "NBC" )  @(0.35, 0.22, 0.70, 1.0) => hostColor;  // purple
                        else                                @(0.30, 0.30, 0.30, 1.0) => hostColor;

                        // Album art square (brand colored, clickable)
                        if( i == currentPodcastIdx )
                        { if( UI.colorButton("##pa" + i, spGreen, 0, @(44, 44)) ) true => rowClicked; }
                        else
                        { if( UI.colorButton("##pa" + i, hostColor, 0, @(44, 44)) ) true => rowClicked; }

                        UI.sameLine(0, 12);

                        // Title+subtitle as a single clickable button (transparent bg)
                        if( i == currentPodcastIdx )
                            UI.pushStyleColor(UI_Color.Text, spGreen);
                        else
                            UI.pushStyleColor(UI_Color.Text, textPrimary);
                        UI.pushStyleColor(UI_Color.Button, @(0, 0, 0, 0));
                        UI.pushStyleColor(UI_Color.ButtonHovered, hoverBg);
                        UI.pushStyleColor(UI_Color.ButtonActive, selectedBg);
                        UI.pushStyleVar(UI_StyleVar.ButtonTextAlign, @(0, 0.5));
                        UI.pushStyleVar(UI_StyleVar.FramePadding, @(6, 4));
                        UI.pushStyleVar(UI_StyleVar.FrameRounding, 4.0);

                        podLib[i].title + "\nPodcast · " + podLib[i].host + "##pt" + i => string label;
                        if( UI.button(label, @(SIDEBAR_W - 96, 44)) )
                            true => rowClicked;

                        UI.popStyleVar(3);
                        UI.popStyleColor(4);

                        if( rowClicked && i != currentPodcastIdx )
                        {
                            i => pendingPodcastIdx;
                            true => podcastSwitchRequested;
                        }

                        UI.dummy(@(0, 4));
                    }

                    UI.dummy(@(0, 12));
                    UI.separator();
                    UI.dummy(@(0, 8));

                    // ── Sliders section ──
                    UI.pushStyleColor(UI_Color.Text, textSecondary);
                    UI.text("Controls");
                    UI.popStyleColor(1);
                    UI.dummy(@(0, 4));

                    SIDEBAR_W - 112 => float sliderW;

                    // Volume controls (prominent placement)
                    UI.setNextItemWidth(sliderW);
                    UI.slider("Pod Vol##sl", uiPodVol, 0.0, 1.0);
                    UI.setNextItemWidth(sliderW);
                    UI.slider("Rap Vol##sl", uiRapVol, 0.0, 1.0);

                    UI.dummy(@(0, 4));
                    UI.separator();
                    UI.dummy(@(0, 4));

                    UI.setNextItemWidth(sliderW);
                    UI.slider("Listen##sl", uiListenTime, 1.0, 8.0);
                    UI.setNextItemWidth(sliderW);
                    UI.slider("Cooldown##sl", uiCooldown, 0.0, 4.0);
                    UI.setNextItemWidth(sliderW);
                    UI.slider("K##sl", uiK, 1, 15);

                    UI.dummy(@(0, 4));
                    UI.checkbox("Glitch Mode", uiGlitch);

                    UI.dummy(@(0, 8));
                    UI.pushStyleColor(UI_Color.Button, @(0.157, 0.157, 0.157, 1.0));
                    if( UI.button("Reset Timer", @(sliderW, 28)) )
                    {
                        now => performanceStart;
                        0 => triggerCount;
                        0 => dfTriggerCount;
                    }
                    UI.popStyleColor(1);
                }
                UI.endChild();
                UI.popStyleVar(1);
                UI.popStyleColor(1);
            }
            UI.endChild();
            UI.popStyleVar(1);
            UI.popStyleColor(1);

            UI.sameLine(0, 0);

            // ============================================================
            //  MAIN CONTENT AREA  (transparent to show video, right of sidebar)
            // ============================================================
            UI.pushStyleColor(UI_Color.ChildBg, @(0.0, 0.0, 0.0, 0.0));
            UI.pushStyleVar(UI_StyleVar.WindowPadding, @(32, 24));
            if( UI.beginChild("##content", @(win.x - SIDEBAR_W, contentH), false, 0) )
            {
                // ── Top row: title + act badge + clean toggle ──
                UI.text("Deepfake Diss Track");

                UI.sameLine(0, 20);

                // Act badge (colored pill button)
                if( act == 1 )
                {
                    UI.pushStyleColor(UI_Color.Button, spGreen);
                    UI.pushStyleColor(UI_Color.Text, @(0.0, 0.0, 0.0, 1.0));
                    UI.button("  ACT 1: REAL RAP  ");
                    UI.popStyleColor(2);
                }
                else if( act == 2 )
                {
                    UI.pushStyleColor(UI_Color.Button, @(0.8, 0.6, 0.1, 1.0));
                    UI.pushStyleColor(UI_Color.Text, @(0.0, 0.0, 0.0, 1.0));
                    UI.button("  ACT 2: DEEPFAKE BLEND  ");
                    UI.popStyleColor(2);
                }
                else
                {
                    UI.pushStyleColor(UI_Color.Button, dangerRed);
                    UI.button("  ACT 3: AI MELTDOWN  ");
                    UI.popStyleColor(1);
                }

                UI.sameLine(0, 20);
                UI.checkbox("Clean Mode", uiClean);

                UI.dummy(@(0, 20));

                // ── Escalation progress card ──
                win.x - SIDEBAR_W - 88 => float cardW;
                UI.pushStyleColor(UI_Color.ChildBg, cardBg);
                UI.pushStyleVar(UI_StyleVar.WindowPadding, @(20, 16));
                if( UI.beginChild("##esc_card", @(cardW, 72), false, 0) )
                {
                    UI.pushStyleVar(UI_StyleVar.FrameRounding, 4.0);
                    UI.setNextItemWidth(cardW - 48);
                    UI.progressBar(p, @(-1, 6), "");
                    UI.popStyleVar(1);

                    "" => string escText;
                    if( act == 1 )      "Act 1 — Real Rap" => escText;
                    else if( act == 2 ) "Act 2 — Deepfake Blend" => escText;
                    else                "Act 3 — AI Meltdown" => escText;
                    UI.pushStyleColor(UI_Color.Text, textSecondary);
                    UI.text(escText + "  " + Std.ftoa(p * 100, 0) + "%"
                        + "    |    Triggers: " + triggerCount
                        + "    Deepfakes: " + dfTriggerCount);
                    UI.popStyleColor(1);
                }
                UI.endChild();
                UI.popStyleVar(1);
                UI.popStyleColor(1);

                UI.dummy(@(0, 16));

                // ── "Now Dissing" / Last diss card ──
                UI.pushStyleColor(UI_Color.ChildBg, cardBg);
                UI.pushStyleVar(UI_StyleVar.WindowPadding, @(20, 16));
                if( UI.beginChild("##diss_card", @(cardW, 140), false, 0) )
                {
                    if( isPlayingClip )
                    {
                        UI.pushStyleColor(UI_Color.Text, spGreen);
                        UI.text("NOW DISSING");
                        UI.popStyleColor(1);
                    }
                    else
                    {
                        UI.pushStyleColor(UI_Color.Text, textSecondary);
                        UI.text("LAST DISS");
                        UI.popStyleColor(1);
                    }

                    if( lastWasDeepfake )
                    {
                        UI.sameLine(0, 12);
                        UI.pushStyleColor(UI_Color.Button, dangerRed);
                        UI.button("AI DEEPFAKE");
                        UI.popStyleColor(1);
                    }

                    if( lastLyric != "" )
                    {
                        UI.dummy(@(0, 8));
                        UI.textWrapped("\"" + lastLyric + "\"");
                        UI.dummy(@(0, 4));
                        UI.pushStyleColor(UI_Color.Text, textSecondary);
                        UI.text(lastClipFile);
                        UI.popStyleColor(1);
                    }
                    else
                    {
                        UI.dummy(@(0, 12));
                        UI.pushStyleColor(UI_Color.Text, textMuted);
                        UI.text("Listening to podcast...");
                        UI.popStyleColor(1);
                    }
                }
                UI.endChild();
                UI.popStyleVar(1);
                UI.popStyleColor(1);
            }
            UI.endChild();
            UI.popStyleVar(1);
            UI.popStyleColor(1);  // main content area transparent bg

            // ============================================================
            //  BOTTOM NOW-PLAYING BAR  (#181818, 90px, full width)
            // ============================================================
            UI.pushStyleColor(UI_Color.ChildBg, playerBg);
            UI.pushStyleVar(UI_StyleVar.WindowPadding, @(16, 12));
            if( UI.beginChild("##player_bar", @(win.x, PLAYER_H), false, 0) )
            {
                // ── LEFT third: track info ──
                // Album art square
                if( lastWasDeepfake )
                    UI.colorButton("##np_art", dangerRed, 0, @(56, 56));
                else if( isPlayingClip )
                    UI.colorButton("##np_art", spGreen, 0, @(56, 56));
                else
                    UI.colorButton("##np_art", @(0.20, 0.20, 0.20, 1.0), 0, @(56, 56));

                UI.sameLine(0, 12);

                UI.beginGroup();
                UI.text(podLib[currentPodcastIdx].title);
                UI.pushStyleColor(UI_Color.Text, textSecondary);
                UI.text(podLib[currentPodcastIdx].host);
                UI.popStyleColor(1);
                UI.endGroup();

                UI.sameLine(0, 40);

                // ── CENTER: transport controls ──
                UI.beginGroup();
                UI.dummy(@(0, 2));

                // Play/Pause pill button
                if( isPaused )
                {
                    UI.pushStyleColor(UI_Color.Button, spGreen);
                    UI.pushStyleColor(UI_Color.ButtonHovered, activeGreen);
                    UI.pushStyleColor(UI_Color.Text, @(0.0, 0.0, 0.0, 1.0));
                    if( UI.button("  PLAY  ", @(80, 32)) )
                    {
                        false => isPaused;
                        0 => uiPaused.val;
                        1 => podcast.rate;
                    }
                    UI.popStyleColor(3);
                }
                else
                {
                    UI.pushStyleColor(UI_Color.Button, textPrimary);
                    UI.pushStyleColor(UI_Color.ButtonHovered, textSecondary);
                    UI.pushStyleColor(UI_Color.Text, @(0.0, 0.0, 0.0, 1.0));
                    if( UI.button("  PAUSE  ", @(80, 32)) )
                    {
                        true => isPaused;
                        1 => uiPaused.val;
                        0 => podcast.rate;
                    }
                    UI.popStyleColor(3);
                }

                // Progress bar row: time — slider — time
                podcast.samples() => int totalSamps;
                0.0 => float podProg;
                if( totalSamps > 0 )
                    podcast.pos() $ float / totalSamps => podProg;
                (podcast.pos() / 44100.0) $ int => int posSec;
                (totalSamps / 44100.0) $ int => int totalSec;

                UI.pushStyleColor(UI_Color.Text, textSecondary);
                Std.itoa(posSec / 60) + ":" + (posSec % 60 < 10 ? "0" : "") +
                    Std.itoa(posSec % 60) => string posStr;
                UI.text(posStr);
                UI.popStyleColor(1);

                UI.sameLine(0, 8);

                // Thin green progress slider
                UI.pushStyleVar(UI_StyleVar.FrameRounding, 4.0);
                UI.pushStyleVar(UI_StyleVar.FramePadding, @(0, 1));
                UI.pushStyleVar(UI_StyleVar.GrabMinSize, 8.0);
                UI.pushStyleColor(UI_Color.FrameBg, progressTrack);
                UI.setNextItemWidth(win.x - 660);
                UI_Float uiPodProg;
                podProg => uiPodProg.val;
                UI.slider("##prog", uiPodProg, 0.0, 1.0);
                UI.popStyleColor(1);
                UI.popStyleVar(3);

                UI.sameLine(0, 8);

                UI.pushStyleColor(UI_Color.Text, textSecondary);
                Std.itoa(totalSec / 60) + ":" + (totalSec % 60 < 10 ? "0" : "") +
                    Std.itoa(totalSec % 60) => string totStr;
                UI.text(totStr);
                UI.popStyleColor(1);

                UI.endGroup();

                UI.sameLine(0, 30);

                // ── RIGHT: volume controls ──
                UI.beginGroup();
                UI.dummy(@(0, 2));

                UI.pushStyleVar(UI_StyleVar.FrameRounding, 4.0);
                UI.pushStyleVar(UI_StyleVar.FramePadding, @(0, 1));
                UI.pushStyleColor(UI_Color.FrameBg, progressTrack);

                UI.pushStyleColor(UI_Color.Text, textSecondary);
                UI.text("Pod");
                UI.popStyleColor(1);
                UI.sameLine(0, 6);
                UI.setNextItemWidth(90);
                UI.slider("##pv", uiPodVol, 0.0, 1.0);

                UI.pushStyleColor(UI_Color.Text, textSecondary);
                UI.text("Rap");
                UI.popStyleColor(1);
                UI.sameLine(0, 6);
                UI.setNextItemWidth(90);
                UI.slider("##rv", uiRapVol, 0.0, 1.0);

                UI.popStyleColor(1);
                UI.popStyleVar(2);

                UI.endGroup();
            }
            UI.endChild();
            UI.popStyleVar(1);
            UI.popStyleColor(1);

        } // end root window
        UI.end();

        // Pop all global styles
        UI.popStyleColor(22);
        UI.popStyleVar(12);

        // ── Keyboard shortcuts ──
        if( GWindow.keyDown(GWindow.Key_Escape) ) me.exit();
        if( GWindow.keyDown(GWindow.Key_Space) )
        {
            !isPaused => isPaused;
            isPaused => uiPaused.val;
            if( isPaused ) 0 => podcast.rate;
            else 1 => podcast.rate;
        }
        if( GWindow.keyDown(GWindow.Key_R) )
        {
            now => performanceStart;
            0 => triggerCount;
            0 => dfTriggerCount;
        }
    }
}
spork ~ uiLoop();


//==============================================================================
//  MAIN LOOP — sequential listen → match → play
//==============================================================================

<<< "=== DEEPFAKE DISS TRACK ===" >>>;
<<< "  Database:", FEATURES_FILE, "(", numPoints, "points )" >>>;
<<< "  Dimensions:", NUM_DIMENSIONS >>>;
<<< "  Podcasts available:", podLib.size() >>>;
<<< "  Deepfake clips:", dfClipsAll.size(), "(all)", dfClipsClean.size(), "(clean)" >>>;
<<< "========================" >>>;

while( true )
{
    // ---- PHASE A: Listen to podcast for uiListenTime seconds ----
    false => isPlayingClip;

    // compute how many FFT hops = listen time
    uiListenTime.val()::second => dur listenDur;
    (listenDur / HOP) $ int => int numFrames;
    if( numFrames < 4 ) 4 => numFrames;
    if( numFrames > MAX_ACC_FRAMES ) MAX_ACC_FRAMES => numFrames;

    // accumulate features
    for( int frame; frame < numFrames; frame++ )
    {
        combo.upchuck();
        for( int d; d < NUM_DIMENSIONS; d++ )
            combo.fval(d) => accFeatures[frame][d];
        HOP => now;
    }

    // skip trigger if paused
    if( isPaused ) continue;

    // compute mean feature vector
    for( int d; d < NUM_DIMENSIONS; d++ )
    {
        0.0 => featureMean[d];
        for( int j; j < numFrames; j++ )
            accFeatures[j][d] +=> featureMean[d];
        numFrames /=> featureMean[d];
    }

    // ---- PHASE B: KNN search ----
    uiK.val() => K;
    if( K < 1 ) 1 => K;
    if( knnResult.size() != K ) knnResult.size(K);
    knn.search( featureMean, K, knnResult );

    // pick from K results (bias toward closest later in performance)
    progress() => float p;
    0 => int pick;
    if( K > 1 )
    {
        if( p < 0.5 )
            Math.random2(0, K-1) => pick;
        else
            Math.random2(0, Math.max(0, (K/2)$int)) => pick;
    }

    knnResult[pick] => int uid;
    windows[uid] @=> AudioWindow @ win;
    files[win.fileIndex] => string fname;

    // ---- PHASE C: Deepfake swap decision ----
    false => int useDeepfake;
    activeDfClips() @=> string dfClips[];
    if( dfClips.size() > 0 )
    {
        if( p < 0.25 )
            false => useDeepfake;                          // Act 1: real
        else if( p < 0.7 )
        {
            (p - 0.25) / 0.45 * 0.8 => float dfProb;
            Math.random2f(0,1) < dfProb => useDeepfake;   // Act 2: blend
        }
        else
            Math.random2f(0,1) < 0.9 => useDeepfake;      // Act 3: mostly AI
    }

    // ---- PHASE D: Load and play the FULL clip ----
    true => isPlayingClip;
    triggerCount++;
    if( useDeepfake ) dfTriggerCount++;

    if( useDeepfake )
    {
        // find the deepfake that matches this real clip by base name
        // real: "rap_clips/032_LilWayne_Lollipop_p023.wav" → base "032_LilWayne_Lollipop_p023"
        fname.substring(10, fname.length() - 14) => string realBase;
        -1 => int dfIdx;
        for( int i; i < dfClips.size() && dfIdx < 0; i++ )
        {
            if( dfClips[i].find(realBase) >= 0 )
                i => dfIdx;
        }
        if( dfIdx >= 0 )
        {
            me.dir() + dfClips[dfIdx] => rapBuf.read;
            0 => rapBuf.pos;
            dfClips[dfIdx] => lastClipFile;
        }
        else
        {
            // no matching deepfake → fall back to real clip
            false => useDeepfake;
            me.dir() + fname => rapBuf.read;
            0 => rapBuf.pos;
            fname => lastClipFile;
        }
    }
    else
    {
        me.dir() + fname => rapBuf.read;
        0 => rapBuf.pos;
        fname => lastClipFile;
    }

    // rate modulation based on act
    if( p < 0.3 )
        1.0 => rapBuf.rate;
    else if( p < 0.7 )
    {
        if( useDeepfake )
            Math.random2f(0.92, 1.08) => rapBuf.rate;
        else
            Math.random2f(0.97, 1.03) => rapBuf.rate;
    }
    else
    {
        (0.6 + p * 0.8) => rapBuf.rate;
        if( Math.random2(0,3) == 0 )
            -1.0 * rapBuf.rate() => rapBuf.rate;
    }

    // update display state — use fileIndex to get correct lyric
    useDeepfake => lastWasDeepfake;
    if( win.fileIndex < rapLyricsAll.size() )
        rapLyricsAll[win.fileIndex] => lastLyric;
    else
        "" => lastLyric;
    (now - performanceStart) / second => lastTriggerTime;

    // trigger music video for this clip
    triggerRapVideo(lastClipFile);

    // duck podcast while clip plays
    podGain.gain() => float savedPodGain;
    savedPodGain * (0.15 + (1.0 - p) * 0.15) => podGain.gain;

    // play the ENTIRE clip with envelope
    rapEnv.keyOn();

    // compute clip duration in samples at current rate
    rapBuf.samples() => int clipSamps;
    rapBuf.rate() => float absRate;
    if( absRate < 0 ) -1.0 * absRate => absRate;
    if( absRate < 0.1 ) 0.1 => absRate;
    (clipSamps / (absRate * 44100.0)) => float clipDurSec;
    // clamp to reasonable range
    if( clipDurSec > 6.0 ) 6.0 => clipDurSec;
    if( clipDurSec < 0.3 ) 0.3 => clipDurSec;

    // log
    chout <= "[#" <= triggerCount <= "] ";
    if( useDeepfake ) chout <= "[AI] ";
    chout <= lastClipFile
          <= " act=" <= currentAct()
          <= " rate=" <= rapBuf.rate()
          <= " dur=" <= Std.ftoa(clipDurSec, 2) <= "s"
          <= " samps=" <= clipSamps
          <= IO.newline();

    // wait for clip to finish (minus release time)
    (clipDurSec::second) - rapEnv.releaseTime() => dur playDur;
    if( playDur < 0::samp ) 0::samp => playDur;
    playDur => now;

    rapEnv.keyOff();
    rapEnv.releaseTime() => now;

    // restore podcast gain
    savedPodGain => podGain.gain;

    // ---- PHASE E: Cooldown ----
    uiCooldown.val()::second => now;

    // ---- Check podcast end ----
    if( podcast.pos() >= podcast.samples() )
    {
        0 => podcast.pos;
        <<< "--- podcast looped ---" >>>;
    }
}


//==============================================================================
//  UTILITY FUNCTIONS (file loading — unchanged from extract format)
//==============================================================================

fun FileIO loadFile( string filepath )
{
    0 => numPoints;
    0 => numCoeffs;

    FileIO fio;
    if( !fio.open( filepath, FileIO.READ ) )
    {
        <<< "cannot open file:", filepath >>>;
        fio.close();
        return fio;
    }

    string str;
    string line;
    while( fio.more() )
    {
        fio.readLine().trim() => str;
        if( str != "" )
        {
            numPoints++;
            str => line;
        }
    }

    StringTokenizer tokenizer;
    tokenizer.set( line );
    -2 => numCoeffs;
    while( tokenizer.more() )
    {
        tokenizer.next();
        numCoeffs++;
    }
    if( numCoeffs < 0 ) 0 => numCoeffs;

    if( numPoints == 0 || numCoeffs <= 0 )
    {
        <<< "no data in file:", filepath >>>;
        fio.close();
        return fio;
    }

    <<< "# data points:", numPoints, "dimensions:", numCoeffs >>>;
    return fio;
}

fun void readData( FileIO fio )
{
    fio.seek( 0 );

    string line;
    StringTokenizer tokenizer;
    0 => int index;
    0 => int fileIndex;
    string filename;
    float windowTime;
    int c;

    while( fio.more() )
    {
        fio.readLine().trim() => line;
        if( line != "" )
        {
            tokenizer.set( line );
            tokenizer.next() => filename;
            tokenizer.next() => Std.atof => windowTime;

            if( filename2state[filename] == 0 )
            {
                filename => string sss;
                files << sss;
                files.size() => filename2state[filename];
            }
            filename2state[filename]-1 => fileIndex;
            windows[index].set( index, fileIndex, windowTime );

            0 => c;
            repeat( numCoeffs )
            {
                tokenizer.next() => Std.atof => inFeatures[index][c];
                c++;
            }
            index++;
        }
    }
}
