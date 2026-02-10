//------------------------------------------------------------------------------
// name: extract-rap-db.ck
// desc: Feature extraction for the rap clip database (Phase 3).
//       This is a wrapper around the mosaic-extract logic, pre-configured
//       for the rap_clips/ directory.
//
// USAGE:
//   chuck --silent extract-rap-db.ck
//   (reads rap-clips.txt, writes rap_db.txt)
//
// Or with custom input/output:
//   chuck --silent extract-rap-db.ck:my-clips.txt:my-db.txt
//------------------------------------------------------------------------------

// defaults — override via command-line args
"rap-clips.txt" => string INPUT;
"rap_db.txt" => string OUTPUT_FILE;

if( me.args() > 0 ) me.arg(0) => INPUT;
if( me.args() > 1 ) me.arg(1) => OUTPUT_FILE;

//------------------------------------------------------------------------------
// analysis network — must match what deepfake-diss.ck expects
// Centroid(1) + Flux(1) + RMS(1) + MFCC(20) = 23 dimensions
//------------------------------------------------------------------------------
SndBuf audioFile => FFT fft;
FeatureCollector combo => blackhole;
fft =^ Centroid centroid =^ combo;
fft =^ Flux flux =^ combo;
fft =^ RMS rms =^ combo;
fft =^ MFCC mfcc =^ combo;

// MFCC settings
20 => mfcc.numCoeffs;
10 => mfcc.numFilters;

// bootstrap
combo.upchuck();
combo.fvals().size() => int NUM_DIMENSIONS;

// FFT settings
4096 => fft.size;
Windowing.hann(fft.size()) => fft.window;
(fft.size()/2)::samp => dur HOP;
4 => int NUM_FRAMES;

// feature frame buffer
float featureFrame[NUM_DIMENSIONS];
0 => int NUM_FILES;

//------------------------------------------------------------------------------
// output
//------------------------------------------------------------------------------
cherr @=> IO @ theOut;
FileIO fout;
if( OUTPUT_FILE != "" )
{
    <<< "opening file for output:", OUTPUT_FILE >>>;
    fout.open( me.dir() + OUTPUT_FILE, FileIO.WRITE );
    if( !fout.good() )
    {
        <<< " |- cannot open file for writing...", "" >>>;
        me.exit();
    }
    fout @=> theOut;
}

//------------------------------------------------------------------------------
// input: read file list
//------------------------------------------------------------------------------
string filenames[0];
if( !parseInput( INPUT, filenames ) ) me.exit();

<<< "[extract-rap-db] Processing", filenames.size(), "files..." >>>;

// loop over files
for( int i; i < filenames.size(); i++)
{
    if( !extractTrajectory( me.dir()+filenames[i], filenames[i], i, theOut ) )
    {
        cherr <= "[extract-rap-db]: problem extracting (skipping): " <= filenames[i] <= IO.newline();
        continue;
    }
}

theOut.flush();
theOut.close();
<<< "[extract-rap-db] DONE. Wrote", NUM_FILES, "files to", OUTPUT_FILE >>>;

//------------------------------------------------------------------------------
// extractTrajectory — same as mosaic-extract.ck
//------------------------------------------------------------------------------
fun int extractTrajectory( string inputFilePath, string shortName, int fileIndex, IO out )
{    
    NUM_FILES++;
    cherr <= "[" <= NUM_FILES <= "] extracting: " <= shortName <= IO.newline();
    
    fft.size() => audioFile.chunks;
    inputFilePath => audioFile.read;
    int pos;
    int index;
    
    while( audioFile.pos() < audioFile.samples() )
    {
        audioFile.pos() => int pos;
        featureFrame.zero();

        for( int i; i < NUM_FRAMES; i++ )
        {
            HOP => now;
            combo.upchuck();
            for( int d; d < NUM_DIMENSIONS; d++ )
                combo.fval(d) +=> featureFrame[d];
        }
        
        out <= shortName <= " " <= (pos::samp)/second <= " ";
        for( int d; d < NUM_DIMENSIONS; d++ )
        {
            NUM_FRAMES /=> featureFrame[d];
            out <= featureFrame[d] <= " ";
        }
        out <= IO.newline();
        
        if( out != cherr ) { cherr <= "."; cherr.flush(); }
        index++;
    }
    
    if( out != cherr ) cherr <= IO.newline();
    return true;
}

//------------------------------------------------------------------------------
// parseInput — handle .wav or .txt file lists
//------------------------------------------------------------------------------
fun int parseInput( string input, string results[] )
{
    results.clear();
    if( input.rfind( ".wav" ) > 0 || input.rfind( ".aiff" ) > 0 )
    {
        input => string sss;
        results << sss;
    }
    else
    {
        FileIO fio;
        if( !fio.open( me.dir() + input, FileIO.READ ) )
        {
            <<< "cannot open file:", me.dir() + input >>>;
            fio.close();
            return false;
        }
        while( fio.more() )
        {
            fio.readLine().trim() => string line;
            if( line != "" )
            {
                results << line;
            }
        }
    }
    return true;
}
