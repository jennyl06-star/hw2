// extract-rap-db.ck
// builds a feature database from rap clips for KNN matching
// usage: chuck --silent extract-rap-db.ck
//        chuck --silent extract-rap-db.ck:my-clips.txt:my-db.txt

"rap-clips.txt" => string INPUT;
"rap_db.txt" => string OUTPUT_FILE;
if( me.args() > 0 ) me.arg(0) => INPUT;
if( me.args() > 1 ) me.arg(1) => OUTPUT_FILE;

// analysis chain: centroid + flux + rms + mfcc
SndBuf audioFile => FFT fft;
FeatureCollector combo => blackhole;
fft =^ Centroid centroid =^ combo;
fft =^ Flux flux =^ combo;
fft =^ RMS rms =^ combo;
fft =^ MFCC mfcc =^ combo;

20 => mfcc.numCoeffs;
10 => mfcc.numFilters;

combo.upchuck();
combo.fvals().size() => int NUM_DIMENSIONS;

4096 => fft.size;
Windowing.hann(fft.size()) => fft.window;
(fft.size()/2)::samp => dur HOP;
4 => int NUM_FRAMES;

float featureFrame[NUM_DIMENSIONS];
0 => int NUM_FILES;

// set up output
cherr @=> IO @ theOut;
FileIO fout;
if( OUTPUT_FILE != "" )
{
    <<< "opening file for output:", OUTPUT_FILE >>>;
    fout.open( me.dir() + OUTPUT_FILE, FileIO.WRITE );
    if( !fout.good() )
    {
        <<< "cannot open file for writing:", OUTPUT_FILE >>>;
        me.exit();
    }
    fout @=> theOut;
}

// read file list
string filenames[0];
if( !parseInput( INPUT, filenames ) ) me.exit();
<<< "processing", filenames.size(), "files..." >>>;

for( int i; i < filenames.size(); i++)
{
    if( !extractTrajectory( me.dir()+filenames[i], filenames[i], i, theOut ) )
    {
        cherr <= "problem extracting (skipping): " <= filenames[i] <= IO.newline();
        continue;
    }
}

theOut.flush();
theOut.close();
<<< "done. wrote", NUM_FILES, "files to", OUTPUT_FILE >>>;


// extract feature trajectory for one audio file
fun int extractTrajectory( string inputFilePath, string shortName, int fileIndex, IO out )
{
    NUM_FILES++;
    cherr <= "[" <= NUM_FILES <= "] " <= shortName <= IO.newline();

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


// parse input: either a single .wav/.aiff or a .txt list of files
fun int parseInput( string input, string results[] )
{
    results.clear();
    if( input.rfind( ".wav" ) > 0 || input.rfind( ".aiff" ) > 0 )
    {
        results << input;
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
            if( line != "" ) results << line;
        }
    }
    return true;
}
