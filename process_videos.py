"""
Video Processor - Quality Enhancement (Video + Audio)
1. Extend 6-second videos to 12 seconds (loop once)
2. Upscale video to 1080x1920 with quality enhancement
3. Remove watermark (bottom-right corner)
4. ENHANCE AUDIO (normalize volume, improve clarity) - if audio exists
"""
import os
import subprocess
import sys
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

input_dir = "Videos"
output_dir = "Processed_Videos"

if not os.path.exists(output_dir):
    os.makedirs(output_dir)


def get_video_duration(video_path):
    """Get the duration of a video in seconds."""
    cmd_probe = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    try:
        duration = float(subprocess.check_output(cmd_probe).decode("utf-8").strip())
        return duration
    except Exception as e:
        print(f"Failed to get duration: {e}")
        return None


def process_single_video(video_path):
    if not os.path.exists(video_path):
        print(f"Error: Video not found: {video_path}")
        return None

    filename = os.path.basename(video_path)
    out_path = os.path.join(output_dir, filename)

    if os.path.exists(out_path):
        print(f"Skipping {filename} - already processed")
        return out_path

    # Get video duration to determine if we need to loop it
    duration = get_video_duration(video_path)
    needs_looping = duration is not None and duration < 10  # Loop videos shorter than 10 seconds

    if needs_looping:
        print(f"Video duration: {duration:.2f}s - Will loop to extend to ~{duration * 2:.1f} seconds")
    else:
        print(f"Video duration: {duration:.2f}s - No looping needed")

    cmd_probe = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0",
        video_path
    ]
    try:
        res = subprocess.check_output(cmd_probe).decode("utf-8").strip()
        width, height = map(int, res.split("x"))
    except Exception as e:
        print(f"Failed to get resolution for {video_path}: {e}")
        return None

    cmd_audio = [
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0",
        video_path
    ]
    try:
        audio_check = subprocess.check_output(cmd_audio).decode("utf-8").strip()
        has_audio = bool(audio_check)
    except:
        has_audio = False

    print(f"Original size: {width}x{height}")
    print(f"Has audio: {'Yes' if has_audio else 'No'}")

    w_delogo = 180
    h_delogo = 80
    x_delogo = 1080 - w_delogo - 5
    y_delogo = 1920 - h_delogo - 5

    print(f"Processing {filename}...")
    print(f"  Upscaling to: 1080x1920")
    print(f"  Removing watermark at: x={x_delogo}, y={y_delogo}, w={w_delogo}, h={h_delogo}")
    print(f"  Video: ENHANCED (sharpen + clarity boost)")
    if needs_looping:
        print(f"  Extension: Looping video (6s → 12s)")
    if has_audio:
        print(f"  Audio: ENHANCED (normalize volume + improve clarity)")
    else:
        print(f"  Audio: No audio in original video")

    # Build the video filter chain
    # If video needs looping, we concatenate it with itself
    if needs_looping:
        # Loop the video twice and apply enhancements
        # Use simpler filter chain without intermediate labels
        vf_filter = (
            f"[0:v]split[v0][v1];"
            f"[v0]scale=1080:1920:flags=lanczos,unsharp=5:5:1.0:5:5:0.0,delogo=x={x_delogo}:y={y_delogo}:w={w_delogo}:h={h_delogo}[s0];"
            f"[v1]scale=1080:1920:flags=lanczos,unsharp=5:5:1.0:5:5:0.0,delogo=x={x_delogo}:y={y_delogo}:w={w_delogo}:h={h_delogo}[s1];"
            f"[s0][s1]concat=n=2:v=1:a=0[v]"
        )
    else:
        # No looping needed, just enhance
        vf_filter = f"[0:v]scale=1080:1920:flags=lanczos,unsharp=5:5:1.0:5:5:0.0,delogo=x={x_delogo}:y={y_delogo}:w={w_delogo}:h={h_delogo}[v]"

    if has_audio:
        if needs_looping:
            # Use aloop filter for audio (simpler and more efficient)
            af_filter = f"[0:a]aloop=loop=1:size=2e+09[a1];[a1]loudnorm=I=-16:TP=-1.5:LRA=11,dynaudnorm=50:3:0.5[a]"
        else:
            af_filter = f"[0:a]loudnorm=I=-16:TP=-1.5:LRA=11,dynaudnorm=50:3:0.5[a]"

        cmd_ffmpeg = [
            "ffmpeg", "-y", "-i", video_path,
            "-filter_complex", f"{vf_filter};{af_filter}",
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264", "-preset", "slow", "-crf", "16",
            "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            out_path
        ]
    else:
        cmd_ffmpeg = [
            "ffmpeg", "-y", "-i", video_path,
            "-filter_complex", vf_filter,
            "-map", "[v]",
            "-c:v", "libx264", "-preset", "slow", "-crf", "16",
            "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-an",
            out_path
        ]

    print("  Processing... (enhancement in progress)")
    result = subprocess.run(cmd_ffmpeg, capture_output=True, text=True)

    if result.returncode == 0:
        print(f"✅ Saved: {out_path} (ENHANCED)")
        return out_path
    else:
        print(f"❌ FFmpeg failed with return code {result.returncode}")
        print(f"❌ Full error output:")
        print(result.stderr)
        return None


def main():
    specific_video = sys.argv[1] if len(sys.argv) > 1 else None

    if specific_video:
        result = process_single_video(specific_video)
        if result:
            print("\n" + "=" * 60)
            print("PROCESSING COMPLETE - VIDEO & AUDIO ENHANCED")
            print("=" * 60)
        else:
            sys.exit(1)
    else:
        videos = [f for f in os.listdir(input_dir) if f.endswith('.mp4')]
        print(f"Found {len(videos)} videos to process.")

        for filename in videos:
            vid_path = os.path.join(input_dir, filename)
            process_single_video(vid_path)

        print("\n" + "=" * 60)
        print("PROCESSING COMPLETE")
        print("=" * 60)


if __name__ == "__main__":
    main()
