import os
import json
import glob
import random
import requests
import shutil
import sys
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
from pathlib import Path
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)

# Import upload functions
try:
    from upload.upload_instagram import upload_to_instagram
    from upload.upload_threads import upload_to_threads
    from upload.upload_facebook import upload_to_facebook, upload_to_facebook_story
    from upload.upload_to_youtube import upload_to_youtube
except ImportError as e:
    print(f"Error importing upload modules: {e}")
    # Still want to proceed or stop?
    pass

PROCESSED_DIR = "Processed_Videos"
PUBLISHED_LOG = "published_videos.json"

def get_already_published():
    if os.path.exists(PUBLISHED_LOG):
        with open(PUBLISHED_LOG, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []


def get_repost_counts():
    """Count how many times each video has been posted."""
    published = get_already_published()
    counts = {}
    for entry in published:
        vname = entry.get("video_name", "")
        counts[vname] = counts.get(vname, 0) + 1
    return counts

def mark_as_published(video_name, metadata):
    published = get_already_published()
    published.append({
        "video_name": video_name,
        "metadata": metadata
    })
    with open(PUBLISHED_LOG, 'w', encoding='utf-8') as f:
        json.dump(published, f, indent=4)

def select_video(specific_video=None):
    published = [item["video_name"] for item in get_already_published()]
    all_videos = sorted(glob.glob(os.path.join(PROCESSED_DIR, "*.mp4")))

    if specific_video:
        # specific_video might be a full path or just a filename
        if os.path.exists(specific_video):
            # It's a full path
            vid_path = specific_video
            name = os.path.basename(specific_video)
        else:
            # It's just a filename, join with PROCESSED_DIR
            vid_path = os.path.join(PROCESSED_DIR, specific_video)
            name = specific_video

        if os.path.exists(vid_path):
            if name in published:
                post_count = sum(1 for p in published if p == name)
                print(f"🔄 Video {name} was already published ({post_count}x) - Re-publishing (recycling)")
            return vid_path, name
        else:
            print(f"❌ Error: Specific video {name} not found")
            return None, None

    # Find unpublished videos first
    unpublished = [(vid, os.path.basename(vid)) for vid in all_videos if os.path.basename(vid) not in published]

    if unpublished:
        vid, name = unpublished[0]
        return vid, name

    # All videos published - use weighted random selection (less posted = more likely)
    if all_videos:
        repost_counts = get_repost_counts()
        weights = []
        for vid in all_videos:
            name = os.path.basename(vid)
            count = repost_counts.get(name, 0)
            weight = max(1, 1000 // (3 ** min(count, 6)))
            weights.append(weight)

        selected_vid = random.choices(all_videos, weights=weights, k=1)[0]
        name = os.path.basename(selected_vid)
        post_count = repost_counts.get(name, 0)
        print(f"🎲 All videos published. Weighted random reuse (posted {post_count}x): {name}")
        return selected_vid, name

    return None, None

def generate_caption():
    import random
    import time

    api_key = os.getenv("POLLINATIONS_API_KEY")
    model = os.getenv("AI_MODEL", "openai")

    fallback_titles = [
        "The Psychology of Happiness — What Science Says",
        "Why Your Brain Defaults to Negative Thinking",
        "The Power of Habits — How Your Brain Builds Them",
        "Cognitive Dissonance — When Beliefs Clash",
        "The Science of Love — What Happens in Your Brain",
        "Why We Dream — The Psychology Behind It",
        "The Bystander Effect — Why We Don't Help",
        "How Your Childhood Shapes Your Personality",
        "The Psychology of Color — How It Affects You",
        "Why We Fear — The Neuroscience of Anxiety",
        "The Stanford Prison Experiment — What It Reveals",
        "Growth Mindset — The Key to Unlocking Potential",
        "Why We Procrastinate — The Psychology of Delay",
        "The Spotlight Effect — You're Not as Noticed as You Think",
        "Classical Conditioning — How It Shapes Your Behavior",
    ]

    fallback_descriptions = [
        "Ever wondered what actually makes us happy? Psychologists have been studying this for decades, and the findings might surprise you. It's not money, fame, or success — it's connection, purpose, and gratitude. Your brain is wired to seek meaning, and when you align your actions with your values, something remarkable happens. In this lesson, we explore the science of well-being and how you can apply these principles to your own life. Like if you believe happiness is a skill we can all learn! 🧠 #psychology #happiness #mentalhealth #mindset #wellbeing #scienceofhappiness #psychologyfacts #selfimprovement #positivepsychology #brain #mentalwellness #growthmindset",
        "Your brain has a negativity bias — it evolved to scan for threats, not blessings. This kept our ancestors alive, but today it fuels anxiety and stress. The good news? You can rewire your brain with practice. Every time you consciously shift your focus to what's going right, you strengthen new neural pathways. This is the foundation of cognitive behavioral therapy and it works. Share this with someone who needs a reminder to look on the bright side! ✨ #psychology #negativitybias #brainhacks #mentalhealth #mindset #cognitivebias #neuroscience #selfawareness #personalgrowth #anxietyrelief #psychologyfacts",
        "Your habits shape your future more than any single decision ever could. Every habit follows the same loop: cue, routine, reward. Once you understand this loop, you can change any habit. The key is to keep the same cue and reward but swap the routine. This is backed by decades of behavioral psychology research. Small changes compound into extraordinary results over time. Comment below what habit you're trying to build right now! 💪 #psychology #habits #behavioralscience #selfimprovement #productivity #brainhacks #habitloop #personalgrowth #goalsetting #motivation #psychologyfacts",
        "Cognitive dissonance — the mental discomfort when your beliefs clash with your actions. Your brain hates inconsistency and will do almost anything to resolve it. This is why people justify bad decisions, change their beliefs to match their behavior, or rationalize away evidence. Understanding this bias gives you incredible self-awareness. You start noticing when your brain is making excuses instead of facing the truth. Like if you've ever caught yourself rationalizing a bad choice! 🤔 #psychology #cognitivedissonance #brainbias #selfawareness #criticalthinking #mentalhealth #mindset #psychologyfacts #behavioralscience #decisionmaking",
        "What happens in your brain when you fall in love? It's a cocktail of dopamine, oxytocin, and serotonin — the same chemicals behind addiction and obsession. That's why new love feels so intoxicating. Your brain's reward system lights up like a Christmas tree. Over time, love matures into attachment, driven by oxytocin — the bonding hormone. Understanding the neuroscience of love helps us build stronger, healthier relationships. Drop a heart if you find the science of love fascinating! 💖 #psychology #love #neuroscience #relationshipgoals #brainchemistry #dopamine #oxytocin #scienceoflove #psychologyfacts #mentalhealth #attachmenttheory",
        "Why do we dream? Theories range from memory consolidation to emotional regulation to threat simulation. Your brain is actually more active during REM sleep than when you're awake. Dreams may help you process emotions, solve problems, and integrate new information. Some researchers believe dreams are your brain's way of running through scenarios — a sort of overnight therapy session. Comment your most memorable dream below! 🌙 #psychology #dreams #sleepscience #neuroscience #subconscious #brain #psychologyfacts #mentalhealth #rem #mind",
        "The bystander effect explains why the more people who witness an emergency, the less likely any one person is to help. We assume someone else will step in. This phenomenon was discovered after the infamous Kitty Genovese case in 1964. But here's the empowering part: just knowing about the bystander effect makes you more likely to overcome it. Awareness is the first step to becoming the person who acts when others hesitate. Share this to spread awareness! 🆘 #psychology #bystandereffect #socialpsychology #humanbehavior #mentalhealth #awareness #empathy #psychologyfacts #helpingothers",
        "Your childhood experiences shape your attachment style — how you relate to others as an adult. Secure, anxious, avoidant, or disorganized — these patterns form early and influence every relationship you'll ever have. But here's the hopeful truth: attachment styles can change. Self-awareness, therapy, and healthy relationships can rewire your patterns. Understanding your attachment style is one of the most powerful things you can do for your relationships. Like if you wish you learned this in school! 🧸 #psychology #attachmenttheory #childhood #relationships #mentalhealth #selfawareness #personalgrowth #psychologyfacts #parenting #emotionalintelligence",
        "Colors affect your mood, your decisions, and even your perception of time. Red increases heart rate and appetite. Blue promotes calm and productivity. Yellow triggers anxiety in some but creativity in others. This isn't just marketing hype — there's real neuroscience behind it. Your brain processes color before it processes shape or text, making it the most immediate influence on your emotional state. Design your environment with intention. What color dominates your space right now? 🎨 #psychology #colorpsychology #neuroscience #design #mentalhealth #mood #productivity #psychologyfacts #brain #creativity #mindset",
        "Fear is your brain's oldest and most powerful survival mechanism. The amygdala scans for threats 24/7, and once it detects danger, your prefrontal cortex goes offline. This is why you can't think clearly when you're scared. Understanding the neuroscience of anxiety takes away some of its power. You learn that your brain is just trying to protect you — even when it's overreacting. The solution isn't to eliminate fear but to teach your amygdala that you're safe. Drop a like if you're working on managing your anxiety! 🌪️ #psychology #fear #anxiety #neuroscience #mentalhealth #amygdala #brain #anxietyrelief #psychologyfacts #mentalwellness #stressmanagement",
        "The Stanford Prison Experiment revealed how ordinary people can commit extraordinary acts when given authority. College students randomly assigned as guards became abusive within days. Prisoners became passive and depressed. The experiment was meant to last two weeks but was shut down after six days. It changed how we understand the power of situations over personality. It also raised major ethical questions about psychological research. What would you have done — guard or prisoner? 🤯 #psychology #stanfordprison #socialpsychology #humanbehavior #obedience #authority #psychologyfacts #ethics",
        "Growth mindset — the belief that your abilities can be developed through effort — is one of the most transformative ideas in modern psychology. People with a growth mindset embrace challenges, persist through setbacks, and see effort as the path to mastery. The amazing news: you can change your mindset. It starts with how you talk to yourself. Switch 'I can't do this' to 'I can't do this yet.' Like if you're choosing growth today! 🌱 #psychology #growthmindset #selfimprovement #mindset #motivation #learning #personalgrowth #psychologyfacts #successmindset #effort #resilience",
        "Procrastination isn't laziness — it's emotional regulation. You avoid the task because it triggers negative feelings: anxiety, boredom, overwhelm. Your brain seeks immediate relief by doing something pleasurable instead. The solution isn't more discipline. It's understanding why you're avoiding and making the task feel less threatening. Break it down. Start for just two minutes. Forgive yourself for past procrastination — research shows this actually helps. Comment your #1 procrastination technique below! ⏰ #psychology #procrastination #productivity #mentalhealth #brainhacks #motivation #selfimprovement #psychologyfacts #timemanagement #behavioralscience",
        "The spotlight effect — we think people are paying way more attention to us than they actually are. You walk into a room and feel like everyone notices your outfit, your hair, your every move. But research shows people are too busy worrying about themselves to focus on you. This bias is rooted in our evolutionary need to be accepted by the group. Knowing about it is liberating. You can relax, be yourself, and stop performing. Like if you needed to hear this today! 🎯 #psychology #spotlighteffect #socialpsychology #selfawareness #anxiety #confidence #mentalhealth #psychologyfacts #mindset #overthinking",
        "Classical conditioning explains why you feel hungry when you smell your favorite restaurant, why certain songs trigger memories, and even why some phobias develop. Your brain constantly makes associations between stimuli without your awareness. This knowledge gives you power — you can intentionally create positive associations and break negative ones. This principle, discovered by Pavlov, is one of the most fundamental in all of psychology. Drop a bell emoji if you love learning about psychology! 🔔 #psychology #classicalconditioning #pavlov #learning #brain #behaviorism #psychologyfacts #neuroscience #conditioning #mentalhealth",
    ]

    if not api_key:
        chosen_title = random.choice(fallback_titles)
        chosen_desc = random.choice(fallback_descriptions)
        print("Warning: POLLINATIONS_API_KEY not found. Using fallback captions.")
        return chosen_title, chosen_desc

    vibes = [
        "educational and insightful — break down psychological concepts clearly so anyone can understand",
        "engaging and conversational — make psychology feel like a fascinating chat with a professor",
        "surprising and mind-blowing — reveal findings that challenge common assumptions",
        "practical and actionable — give viewers something they can apply to their own lives",
        "story-driven and illustrative — use real experiments and cases to bring concepts to life",
        "reflective and thought-provoking — ask deep questions that make viewers pause and think",
        "warm and encouraging — make viewers feel seen, understood, and empowered by the science",
    ]
    chosen_vibe = random.choice(vibes)

    prompt = (
        f"Write a completely unique, long, and captivating title and description for a short video "
        f"for the Facebook page 'Psychology Mindscape'. "
        f"The page teaches fascinating psychology concepts, psychological theories, practical psychology, "
        f"and insights from psychiatric research — making the science of the mind accessible to everyone. "
        f"Speak as a passionate psychology educator who loves opening minds to how the brain works. "
        f"Make the vibe {chosen_vibe}. "
        f"The description should be LONG (4-6 sentences minimum), deeply engaging, and informative. "
        f"Include engagement calls-to-action such as: "
        f"- Like if this psychology fact blew your mind! "
        f"- Comment your thoughts on this concept! "
        f"- Share this with someone who loves learning! "
        f"- Follow Psychology Mindscape for daily mind-expanding lessons! "
        f"Include relevant hashtags in ALL LOWERCASE such as #psychology #brain #neuroscience #mentalhealth #psychologyfacts #mindset #selfimprovement #learning #science #behavioralscience #education #personalgrowth #cognitivebias #humanbehavior. "
        f"Return ONLY a valid JSON object in this format: {{\"title\": \"<title>\", \"description\": \"<description>\"}} "
        f"Do not include any other text or markdown block backticks."
    )

    url = "https://gen.pollinations.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.9,
        "seed": random.randint(1, 999999)
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        content = data.get('choices', [{}])[0].get('message', {}).get('content', '')

        content = content.replace("```json", "").replace("```", "").strip()
        result = json.loads(content)

        chosen_title = random.choice(fallback_titles)
        chosen_desc = random.choice(fallback_descriptions)
        return result.get("title", chosen_title), result.get("description", chosen_desc)
    except Exception as e:
        print(f"Error generating caption: {e}")
        return random.choice(fallback_titles), random.choice(fallback_descriptions)

def main():
    print("=" * 60)
    print("🚀 DAILY AUTOMATION STARTING")
    print("=" * 60)
    
    specific_video = sys.argv[1] if len(sys.argv) > 1 else None
    video_path, video_name = select_video(specific_video)
    if not video_path:
        print("✅ No new videos found to publish. Exiting.")
        return
        
    print(f"👉 Selected Video: {video_name}")
    print("🧠 Generating caption via Pollination AI...")
    title, description = generate_caption()
    
    print(f"📝 Title: {title}")
    print(f"📝 Description:\n{description}")
    
    # Combined caption for platforms that use a single text field
    combined_caption = f"{title}\n\n{description}"
    
    success_flags = {
        "instagram_reel": False,
        "instagram_story": False,
        "facebook_reel": False,
        "facebook_story": False,
        "threads": False,
        "youtube": False
    }
    
    # Instagram Reels
    try:
        result = upload_to_instagram(video_path, combined_caption, is_story=False)
        if result and result.get('status') == 'skipped':
            print(f"⚠️  Instagram Reel: Skipped ({result.get('reason', 'No credentials')})")
        else:
            success_flags["instagram_reel"] = True
    except Exception as e:
        print(f"❌ Instagram Reel upload failed: {e}")
        
    # Instagram Stories
    try:
        result = upload_to_instagram(video_path, combined_caption, is_story=True)
        if result and result.get('status') == 'skipped':
            print(f"⚠️  Instagram Story: Skipped ({result.get('reason', 'No credentials')})")
        else:
            success_flags["instagram_story"] = True
    except Exception as e:
        print(f"❌ Instagram Story upload failed: {e}")
        
    # Facebook Reels
    try:
        result = upload_to_facebook(video_path, description, title=title)
        if result and result.get('status') == 'skipped':
            print(f"⚠️  Facebook Reel: Skipped ({result.get('reason', 'No credentials')})")
        else:
            success_flags["facebook_reel"] = True
    except Exception as e:
        print(f"❌ Facebook Reel upload failed: {e}")
        
    # Facebook Stories
    try:
        result = upload_to_facebook_story(video_path)
        if result and result.get('status') == 'skipped':
            print(f"⚠️  Facebook Story: Skipped ({result.get('reason', 'No credentials')})")
        else:
            success_flags["facebook_story"] = True
    except Exception as e:
        print(f"❌ Facebook Story upload failed: {e}")
        
    # Threads
    try:
        result = upload_to_threads(video_path, combined_caption)
        if result and result.get('status') == 'skipped':
            print(f"⚠️  Threads: Skipped ({result.get('reason', 'No credentials')})")
        else:
            success_flags["threads"] = True
    except Exception as e:
        print(f"❌ Threads upload failed: {e}")
        
    # YouTube Shorts
    try:
        upload_to_youtube(video_path, title, description, tags=["psychology", "brain", "neuroscience", "mental health", "psychology facts", "mindset", "self improvement", "learning", "science", "behavioral science", "education", "personal growth", "cognitive bias", "human behavior", "psychology mindscape"])
        success_flags["youtube"] = True
    except Exception as e:
        print(f"❌ YouTube upload failed: {e}")
        
    # Record as published regardless of partial success,
    # to avoid repeating the same video. Alternatively, only record if fully successful.
    print("\n✅ Marking video as published.")
    
    # Check if this is a recycled video (already in published_videos.json)
    published_list = get_already_published()
    is_recycled = any(item["video_name"] == video_name for item in published_list)
    
    if is_recycled:
        print(f"   🔄 This is a recycled video (re-publishing)")
    
    mark_as_published(video_name, {
        "title": title,
        "description": description,
        "success_flags": success_flags,
        "recycled": is_recycled
    })
    
    # Move the published video to Published_Videos folder
    published_dir = "Published_Videos"
    if not os.path.exists(published_dir):
        os.makedirs(published_dir)
        
    try:
        dest_path = os.path.join(published_dir, video_name)
        shutil.move(video_path, dest_path)
        print(f"📦 Moved published video to {dest_path}")
    except Exception as e:
        print(f"❌ Failed to move published video: {e}")
    
    print("🎉 DAILY AUTOMATION COMPLETE")

if __name__ == "__main__":
    main()
