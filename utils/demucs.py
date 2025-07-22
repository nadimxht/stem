import subprocess
import os

import ffmpeg


def convert_to_wav(input_file, output_file):
    (
        ffmpeg
        .input(input_file)
        .output(output_file)
        .run(overwrite_output=True)
    )
def separate_stems(audio_path, output_dir):
    
    os.makedirs(output_dir, exist_ok=True)
    cmd = [
        "demucs",
        "-n", "htdemucs",
        "--mp3",  # or "--flac"
        "-o", output_dir,
        audio_path
    ]
    subprocess.run(cmd, check=True)
    # Find all mp3 files and convert to wav
    stems_dir = os.path.join(output_dir, "htdemucs", os.path.splitext(os.path.basename(audio_path))[0])
    for fname in os.listdir(stems_dir):
        if fname.endswith(".mp3"):
            mp3_path = os.path.join(stems_dir, fname)
            wav_path = os.path.splitext(mp3_path)[0] + ".wav"
            convert_to_wav(mp3_path, wav_path)
    return stems_dir