"""
Reset Published Videos List
Use this to clear the published_videos.json so you can re-process videos
"""
import os
import json

PUBLISHED_LOG = "published_videos.json"

print("=" * 60)
print("RESET PUBLISHED VIDEOS LIST")
print("=" * 60)

if os.path.exists(PUBLISHED_LOG):
    with open(PUBLISHED_LOG, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"\nCurrent published videos: {len(data)}")
    print("\nVideos in the list:")
    for item in data[:10]:
        manual = " (manual)" if item.get('metadata', {}).get('manual_upload') else ""
        print(f"  - {item['video_name']}{manual}")
    if len(data) > 10:
        print(f"  ... and {len(data) - 10} more")
    
    confirm = input("\n⚠️  This will REMOVE all published records. Are you sure? (yes/no): ")
    
    if confirm.lower() == 'yes':
        # Backup first
        backup_name = f"{PUBLISHED_LOG}.backup"
        os.rename(PUBLISHED_LOG, backup_name)
        print(f"\n✅ Backed up to {backup_name}")
        
        # Create empty list
        with open(PUBLISHED_LOG, 'w', encoding='utf-8') as f:
            json.dump([], f, indent=4)
        
        print(f"✅ Published videos list RESET!")
        print("   All videos will be processed again on next run.")
    else:
        print("\n❌ Cancelled. No changes made.")
else:
    print("\n✅ No published_videos.json found. Nothing to reset.")

print("\n" + "=" * 60)
