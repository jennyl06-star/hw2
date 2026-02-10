// deepfake-diss.ck
// "Deepfake Diss Track" — podcast interrupted by KNN-matched rap clips
// that gradually morph into AI deepfake versions.
// usage: chuck deepfake-diss.ck:rap_db.txt

string FEATURES_FILE;
if( me.args() >= 1 ) me.arg(0) => FEATURES_FILE;
else
{
    <<< "usage: chuck deepfake-diss.ck:RAP_DB", "" >>>;
    me.exit();
}


// podcast library
class PodcastInfo
{
    string file;
    string title;
    string subtitle;
    string host;
    string videoFile;
    fun void set( string f, string t, string s, string h )
    { f => file; t => title; s => subtitle; h => host; "" => videoFile; }
    fun void setWithVideo( string f, string t, string s, string h, string v )
    { f => file; t => title; s => subtitle; h => host; v => videoFile; }
}

PodcastInfo podLib[0];
{
    // WSJ always first
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
// try loading extra podcasts, auto-detect matching video
fun void tryAddPodcast( string file, string title, string sub, string host )
{
    FileIO test;
    if( test.open( me.dir() + file, FileIO.READ ) )
    {
        test.close();
        PodcastInfo p;
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


// audio pipeline
SndBuf podcast => Gain podGain => dac;
podcast => FFT fft;

// load first podcast
me.dir() + podLib[0].file => podcast.read;
0.85 => podGain.gain;

// feature extraction (centroid + flux + rms + mfcc20)
FeatureCollector combo => blackhole;
fft =^ Centroid centroid =^ combo;
fft =^ Flux flux =^ combo;
fft =^ RMS rms =^ combo;
fft =^ MFCC mfcc =^ combo;

20 => mfcc.numCoeffs;
10 => mfcc.numFilters;

4096 => fft.size;
fft.size() => podcast.chunks;
Windowing.hann(fft.size()) => fft.window;
(fft.size()/2)::samp => dur HOP;

combo.upchuck();
combo.fvals().size() => int NUM_DIMENSIONS;

// rap voice output (sequential, non-overlapping)
SndBuf rapBuf => ADSR rapEnv => Gain rapGain => dac;
0.85 => rapGain.gain;
rapEnv.set( 30::ms, 100::ms, 1.0, 60::ms );


// load feature database + KNN
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


// load lyrics + deepfake clip lists (clean & explicit variants)
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


// performance state
true  => int cleanMode;
false => int isPaused;
0     => int triggerCount;
0     => int dfTriggerCount;

now => time performanceStart;
45::second => dur TOTAL_DURATION;

// UI-exposed timing knobs
UI_Float uiListenTime;   4.0 => uiListenTime.val;
UI_Float uiCooldown;     1.0 => uiCooldown.val;
UI_Float uiThreshold;    0.6 => uiThreshold.val;
UI_Int   uiK;            5   => uiK.val;
UI_Float uiPodVol;       0.85 => uiPodVol.val;
UI_Float uiRapVol;       0.85 => uiRapVol.val;
UI_Bool  uiClean;        1   => uiClean.val;
UI_Bool  uiPaused;       0   => uiPaused.val;

// current trigger display
"" => string lastLyric;
"" => string lastArtist;
"" => string lastClipFile;
false => int   lastWasDeepfake;
0.0   => float lastTriggerTime;

fun float progress() { return Math.min(1.0, (now - performanceStart) / TOTAL_DURATION); }
fun int currentAct()
{
    progress() => float p;
    if( p < 0.25 ) return 1;
    if( p < 0.7  ) return 2;
    return 3;
}

// clean/explicit mode helpers
fun string[] activeLyrics()
{ if( cleanMode ) return rapLyricsClean; return rapLyricsAll; }
fun string[] activeDfClips()
{ if( cleanMode ) return dfClipsClean; return dfClipsAll; }
fun string[] activeDfLyrics()
{ if( cleanMode ) return dfLyricsClean; return dfLyricsAll; }


// ChuGL window + scene
GWindow.windowed(1280, 780);
GWindow.title("DEEPFAKE DISS TRACK");

GCamera cam --> GG.scene();
cam.pos(@(0, 0, 8));
cam.lookAt(@(0, 0, 0));
GG.scene().backgroundColor(@(0.071, 0.071, 0.071));

// podcast video plane (background, muted — audio from SndBuf)
null @=> Video @ podVideo;
Gain podVidMute => blackhole;
false => int podVideoLoaded;

GPlane podVideoPlane --> GG.scene();
FlatMaterial podVidMat;
podVideoPlane.mat(podVidMat);
podVideoPlane.pos(@(0.8, -0.4, -0.5));
podVideoPlane.sca(@(6.8, -3.82, 1.0));
podVideoPlane.sca(@(0, 0, 0));  // hidden until loaded

// rap music video plane (flashes on trigger)
null @=> Video @ rapVideo;
Gain rapVidMute => blackhole;
false => int rapVideoLoaded;
0.0   => float rapVideoLife;
"" => string rapVideoCurrentSong;

GPlane rapVideoPlane --> GG.scene();
FlatMaterial rapVidMat;
rapVideoPlane.mat(rapVidMat);
rapVideoPlane.pos(@(2.38, -1.55, 0.2));
rapVideoPlane.sca(@(0, 0, 0));  // hidden until triggered

// song index → rap video file mapping
string rapVideoMap[0];

fun void scanRapVideos()
{
    // known songs with music videos
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

// load initial podcast video
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
    podVideoPlane.sca(@(6.8, -3.82, 1.0));
}
loadPodcastVideo(0);

// trigger rap music video for a clip
fun void triggerRapVideo( string clipFile )
{
    // extract 3-digit song index from filename
    "" => string idxStr;
    if( clipFile.find("rap_clips/") == 0 && clipFile.length() >= 13 )
        clipFile.substring(10, 3) => idxStr;
    else if( clipFile.find("deepfake_clips/df_ara_") == 0 && clipFile.length() >= 25 )
        clipFile.substring(22, 3) => idxStr;
    else if( clipFile.find("deepfake_clips/df_") == 0 && clipFile.length() >= 21 )
        clipFile.substring(18, 3) => idxStr;

    if( idxStr == "" || !rapVideoMap.isInMap(idxStr) )
    {
        false => rapVideoLoaded;
        rapVideoPlane.sca(@(0, 0, 0));
        return;
    }

    // only reload if switching to a different song
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
    rapVideoPlane.sca(@(1.6, -0.9, 1.0));
    4.0 => rapVideoLife;
}


false => int isPlayingClip;

32 => int MAX_ACC_FRAMES;
float accFeatures[MAX_ACC_FRAMES][NUM_DIMENSIONS];
float featureMean[NUM_DIMENSIONS];


// Spotify-style ImGui UI loop
fun void uiLoop()
{
    // Spotify color palette
    @(0.0, 0.0, 0.0, 0.0) => vec4 mainBg;
    @(0.000, 0.000, 0.000, 1.0) => vec4 sidebarBg;
    @(0.094, 0.094, 0.094, 1.0) => vec4 playerBg;
    @(0.110, 0.110, 0.110, 1.0) => vec4 cardBg;
    @(0.165, 0.165, 0.165, 1.0) => vec4 hoverBg;
    @(0.200, 0.200, 0.200, 1.0) => vec4 selectedBg;
    @(0.114, 0.725, 0.329, 1.0) => vec4 spGreen;
    @(0.118, 0.843, 0.376, 1.0) => vec4 activeGreen;
    @(1.0,   1.0,   1.0,   1.0) => vec4 textPrimary;
    @(0.702, 0.702, 0.702, 1.0) => vec4 textSecondary;
    @(0.325, 0.325, 0.325, 1.0) => vec4 textMuted;
    @(0.302, 0.302, 0.302, 1.0) => vec4 progressTrack;
    @(0.886, 0.129, 0.204, 1.0) => vec4 dangerRed;

    280.0 => float SIDEBAR_W;
    90.0  => float PLAYER_H;
    8.0   => float GAP;

    while( true )
    {
        GG.nextFrame() => now;
        GG.dt() => float dt;
        progress() => float p;
        currentAct() => int act;

        // sync UI state
        uiClean.val()  => cleanMode;
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
            loadPodcastVideo(currentPodcastIdx);
        }

        GG.scene().backgroundColor(@(0.04, 0.04, 0.05));

        // rap video fade-out
        if( rapVideoLife > 0 )
        {
            dt -=> rapVideoLife;
            if( rapVideoLife <= 0 )
            {
                rapVideoPlane.sca(@(0, 0, 0));
                false => rapVideoLoaded;
            }
        }

        // global style overrides
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

        // full-viewport root window
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

            // left sidebar
            UI.pushStyleColor(UI_Color.ChildBg, sidebarBg);
            UI.pushStyleVar(UI_StyleVar.WindowPadding, @(8, 8));
            if( UI.beginChild("##sidebar", @(SIDEBAR_W, contentH), false, 0) )
            {
                // nav card
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

                // library card
                UI.pushStyleColor(UI_Color.ChildBg, cardBg);
                UI.pushStyleVar(UI_StyleVar.WindowPadding, @(12, 12));
                if( UI.beginChild("##lib_card", @(SIDEBAR_W - 16, contentH - 80), false, 0) )
                {
                    // header
                    UI.pushStyleColor(UI_Color.Text, textSecondary);
                    UI.text("Your Library");
                    UI.popStyleColor(1);
                    UI.sameLine(0, 8);
                    if( UI.button("+", @(24, 24)) ) { }

                    UI.dummy(@(0, 8));

                    // podcast list
                    for( int i; i < podLib.size(); i++ )
                    {
                        false => int rowClicked;

                        // brand color per network
                        vec4 hostColor;
                        if( podLib[i].host == "WSJ" )       @(0.80, 0.62, 0.25, 1.0) => hostColor;
                        else if( podLib[i].host == "TED" )  @(0.90, 0.12, 0.10, 1.0) => hostColor;
                        else if( podLib[i].host == "CBS" )  @(0.18, 0.35, 0.78, 1.0) => hostColor;
                        else if( podLib[i].host == "BBC" )  @(0.75, 0.10, 0.20, 1.0) => hostColor;
                        else if( podLib[i].host == "CNBC" ) @(0.02, 0.48, 0.76, 1.0) => hostColor;
                        else if( podLib[i].host == "VICE" ) @(0.15, 0.15, 0.15, 1.0) => hostColor;
                        else if( podLib[i].host == "Vox" )  @(0.93, 0.84, 0.10, 1.0) => hostColor;
                        else if( podLib[i].host == "NBC" )  @(0.35, 0.22, 0.70, 1.0) => hostColor;
                        else                                @(0.30, 0.30, 0.30, 1.0) => hostColor;

                        // album art
                        if( i == currentPodcastIdx )
                        { if( UI.colorButton("##pa" + i, spGreen, 0, @(44, 44)) ) true => rowClicked; }
                        else
                        { if( UI.colorButton("##pa" + i, hostColor, 0, @(44, 44)) ) true => rowClicked; }

                        UI.sameLine(0, 12);

                        // title + subtitle button
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

                    // sliders
                    UI.pushStyleColor(UI_Color.Text, textSecondary);
                    UI.text("Controls");
                    UI.popStyleColor(1);
                    UI.dummy(@(0, 4));

                    SIDEBAR_W - 112 => float sliderW;

                    // volume
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

            // main content area
            UI.pushStyleColor(UI_Color.ChildBg, @(0.0, 0.0, 0.0, 0.0));
            UI.pushStyleVar(UI_StyleVar.WindowPadding, @(32, 24));
            if( UI.beginChild("##content", @(win.x - SIDEBAR_W, contentH), false, 0) )
            {
                // title + act badge
                UI.text("Deepfake Diss Track");

                UI.sameLine(0, 20);

                // act badge
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

                UI.dummy(@(0, 8));

                // escalation progress
                win.x - SIDEBAR_W - 88 => float cardW;
                UI.pushStyleColor(UI_Color.ChildBg, cardBg);
                UI.pushStyleVar(UI_StyleVar.WindowPadding, @(12, 8));
                if( UI.beginChild("##esc_card", @(cardW, 44), false, 0) )
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

                UI.dummy(@(0, 6));

                // "now dissing" / last diss card
                UI.pushStyleColor(UI_Color.ChildBg, cardBg);
                UI.pushStyleVar(UI_StyleVar.WindowPadding, @(12, 8));
                if( UI.beginChild("##diss_card", @(cardW, 80), false, 0) )
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
                        UI.dummy(@(0, 2));
                        UI.textWrapped("\"" + lastLyric + "\"");
                        UI.pushStyleColor(UI_Color.Text, textSecondary);
                        UI.text(lastClipFile);
                        UI.popStyleColor(1);
                    }
                    else
                    {
                        UI.dummy(@(0, 4));
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
            UI.popStyleColor(1);  // content area

            // bottom now-playing bar
            UI.pushStyleColor(UI_Color.ChildBg, playerBg);
            UI.pushStyleVar(UI_StyleVar.WindowPadding, @(16, 12));
            if( UI.beginChild("##player_bar", @(win.x, PLAYER_H), false, 0) )
            {
                // track info
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

                // transport controls
                UI.beginGroup();
                UI.dummy(@(0, 2));

                // Play/Pause
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

                // progress bar
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

                // progress slider
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

                // volume
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

        } // end root
        UI.end();

        UI.popStyleColor(22);
        UI.popStyleVar(12);

        // keyboard shortcuts
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


// main loop: listen → match → play

<<< "=== DEEPFAKE DISS TRACK ===" >>>;
<<< "  db:", FEATURES_FILE, "(", numPoints, "points )" >>>;
<<< "  dims:", NUM_DIMENSIONS >>>;
<<< "  podcasts:", podLib.size() >>>;
<<< "  deepfakes:", dfClipsAll.size(), "all /", dfClipsClean.size(), "clean" >>>;

while( true )
{
    // listen to podcast
    false => isPlayingClip;

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

    if( isPaused ) continue;

    // mean feature vector
    for( int d; d < NUM_DIMENSIONS; d++ )
    {
        0.0 => featureMean[d];
        for( int j; j < numFrames; j++ )
            accFeatures[j][d] +=> featureMean[d];
        numFrames /=> featureMean[d];
    }

    // KNN search
    uiK.val() => K;
    if( K < 1 ) 1 => K;
    if( knnResult.size() != K ) knnResult.size(K);
    knn.search( featureMean, K, knnResult );

    // pick from K results (bias closer matches later in performance)
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

    // deepfake swap decision
    false => int useDeepfake;
    activeDfClips() @=> string dfClips[];
    if( dfClips.size() > 0 )
    {
        if( p < 0.25 )
            false => useDeepfake;
        else if( p < 0.7 )
        {
            (p - 0.25) / 0.45 * 0.8 => float dfProb;
            Math.random2f(0,1) < dfProb => useDeepfake;
        }
        else
            Math.random2f(0,1) < 0.9 => useDeepfake;
    }

    // load and play clip
    true => isPlayingClip;
    triggerCount++;
    if( useDeepfake ) dfTriggerCount++;

    if( useDeepfake )
    {
        // find matching deepfake by base name
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
            // no matching deepfake, use real clip
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

    // rate modulation by act
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

    // update display state
    useDeepfake => lastWasDeepfake;
    if( win.fileIndex < rapLyricsAll.size() )
        rapLyricsAll[win.fileIndex] => lastLyric;
    else
        "" => lastLyric;
    (now - performanceStart) / second => lastTriggerTime;

    triggerRapVideo(lastClipFile);

    // duck podcast
    podGain.gain() => float savedPodGain;
    savedPodGain * (0.15 + (1.0 - p) * 0.15) => podGain.gain;

    // play clip with envelope
    rapEnv.keyOn();

    rapBuf.samples() => int clipSamps;
    rapBuf.rate() => float absRate;
    if( absRate < 0 ) -1.0 * absRate => absRate;
    if( absRate < 0.1 ) 0.1 => absRate;
    (clipSamps / (absRate * 44100.0)) => float clipDurSec;
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

    // wait for clip to finish
    (clipDurSec::second) - rapEnv.releaseTime() => dur playDur;
    if( playDur < 0::samp ) 0::samp => playDur;
    playDur => now;

    rapEnv.keyOff();
    rapEnv.releaseTime() => now;

    savedPodGain => podGain.gain;

    // cooldown
    uiCooldown.val()::second => now;

    // loop podcast if ended
    if( podcast.pos() >= podcast.samples() )
    {
        0 => podcast.pos;
        <<< "--- podcast looped ---" >>>;
    }
}


// utility: load feature database file
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
