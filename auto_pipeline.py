"""
Main Automation Pipeline for GitHub Actions
1. Fetch ONE video from Google Drive
2. Process (upscale + remove watermark)
3. Upload to social media platforms

IF NO NEW VIDEOS: Repost already processed videos (weighted random selection)
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()


def run_pipeline():
    """
    Complete automation pipeline:
    Google Drive → Process → Upload to Social Media

    FALLBACK: If no new videos, repost old videos from Drive
    (weighted random selection - less posted = more likely)
    """
    print("\n" + "=" * 60)
    print("🚀 STARTING AUTOMATION PIPELINE")
    print("=" * 60 + "\n")

    # Step 1: Try fetching a NEW video first
    print("📥 STEP 1: Fetching video from Google Drive...")
    from google_drive_fetch import fetch_one_video_from_drive

    # First try: fetch new (unpublished) video
    downloaded = fetch_one_video_from_drive(allow_repost=False)

    if not downloaded:
        print("\n⚠️  No new videos in Google Drive")
        print("🔄 REPOST MODE: Fetching random published video for repost...\n")

        # Fallback: fetch random already-published video (weighted by repost count)
        downloaded = fetch_one_video_from_drive(allow_repost=True)

        if not downloaded:
            print("\n✅ No videos available to post. Pipeline complete.")
            print("   💡 Add new videos to Google Drive or check credentials")
            return

        print(f"\n✅ Repost Mode: Using existing video\n")

    print(f"\n✅ Step 1 complete: Video downloaded\n")

    # Step 2: Process video (upscale + watermark removal)
    print("🎬 STEP 2: Processing video (upscaling + watermark removal)...")
    from process_videos import process_single_video

    processed_video = process_single_video(downloaded)

    if not processed_video or not os.path.exists(processed_video):
        print("\n❌ Video processing failed!")
        sys.exit(1)

    print("\n✅ Step 2 complete: Video processed\n")

    # Step 3: Upload to social media
    print("📤 STEP 3: Uploading to social media platforms...")
    print("   Platforms: Instagram, Facebook, Threads, YouTube")
    print("\n" + "=" * 60 + "\n")

    # Run the daily publisher with the processed video
    from daily_publisher import main as publish_video
    sys.argv = ["daily_publisher.py", processed_video]
    publish_video()

    print("\n" + "=" * 60)
    print("🎉 AUTOMATION PIPELINE COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    run_pipeline()
