"""Fill the database with a demo account and a real-looking notification history.

The news items are real articles (titles and links) published by the seeded
sources in October 2026. Delivery times and statuses are made up for the demo.

Run from anywhere (uses the same DATABASE_URL as the API):
    python seed_demo.py
    python seed_demo.py --email demo@ainewsletter.dev --password demo1234 --channel-email you@gmail.com

Running it again replaces the demo account and its history, so it is safe to repeat.
"""
import argparse
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Resolve the default sqlite:///./ainews.db next to this file, like `uvicorn` run from api/.
os.chdir(Path(__file__).resolve().parent)

from sqlalchemy import delete, func, select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import init_db  # noqa: E402
from app.models import (  # noqa: E402
    Channel,
    ChannelType,
    Delivery,
    DeliveryStatus,
    FollowedSource,
    ImportanceLevel,
    NewsItem,
    Profile,
    Source,
    User,
)
from app.security import hash_password  # noqa: E402

HIGH, MEDIUM, LOW = ImportanceLevel.high, ImportanceLevel.medium, ImportanceLevel.low

# (source name, title, link, importance, published at UTC "MM-DD HH:MM")
DEMO_NEWS = [
    ("Hugging Face Blog", "Open-sourcing AstaBrief, the fast report-generation model in Asta",
     "https://huggingface.co/blog/allenai/astabrief", MEDIUM, "10-02 15:10"),
    ("Hugging Face Blog", "New in llama.cpp: Decision Models",
     "https://huggingface.co/blog/ggml-org/decision-models-in-llamacpp", LOW, "10-02 18:40"),
    ("Anthropic News", "How Claude designed protein binders against scorpion neurotoxins",
     "https://www.anthropic.com/research/claude-scorpion-toxin-binder-design", LOW, "10-03 16:05"),
    ("OpenAI Blog", "Building advertising for the way people use AI",
     "https://openai.com/index/new-chatgpt-ads-format-and-measurement/", MEDIUM, "10-05 17:30"),
    ("OpenAI Blog", "Sharing AI progress in mathematics",
     "https://openai.com/index/sharing-ai-progress-in-mathematics/", MEDIUM, "10-06 16:00"),
    ("Google DeepMind Blog", "EmbeddingGemma 2 is a best-in-class open model for natively multimodal embeddings",
     "https://blog.google/innovation-and-ai/technology/developers-tools/embeddinggemma-2/", MEDIUM, "10-06 19:15"),
    ("OpenAI Blog", "GPT-6 and Intelligent UI for everyone",
     "https://openai.com/index/gpt-6-for-everyone/", HIGH, "10-07 17:02"),
    ("Anthropic News", "Introducing Claude Haiku 5.5",
     "https://www.anthropic.com/claude-haiku-5-5", HIGH, "10-07 18:20"),
    ("Google DeepMind Blog", "Google expands SynthID Detector for AI content",
     "https://blog.google/innovation-and-ai/models-and-research/google-deepmind/synth-id-ai-content/", MEDIUM, "10-07 20:45"),
    ("Meta AI Blog", "Meta Donates 1,000 AI Glasses to Singapore's Disability Community",
     "https://about.fb.com/news/2026/10/meta-donates-1000-ai-glasses-to-singapores-disability-community/", LOW, "10-08 03:30"),
    ("Anthropic News", "Introducing the Anthropic Cyber Mission",
     "https://www.anthropic.com/news/anthropic-cyber-mission", HIGH, "10-08 15:00"),
    ("Anthropic News", "Building on our commitment to American scientific discovery",
     "https://www.anthropic.com/news/genesis-mission-commitment", MEDIUM, "10-08 19:10"),
    ("TechCrunch AI", "Microsoft's Satya Nadella says AI models need an 'emergency brake'",
     "https://techcrunch.com/2026/10/10/microsofts-satya-nadella-says-ai-models-need-an-emergency-brake/", MEDIUM, "10-10 14:25"),
    ("Meta AI Blog", "Introducing Muse Wonder and Muse Wonder Full: Frontier Models for Agents",
     "https://about.fb.com/news/2026/10/introducing-muse-wonder-models/", HIGH, "10-12 16:00"),
    ("Google DeepMind Blog", "Developing Gemini 4 Argon responsibly and safely",
     "https://blog.google/innovation-and-ai/technology/safety-security/gemini-4-model-safety-security/", HIGH, "10-13 16:30"),
    ("Google DeepMind Blog", "On-Device AI Against Scams: Google DeepMind & MDDI",
     "https://deepmind.google/blog/on-device-ai-scam-detection-mddi/", MEDIUM, "10-14 02:00"),
    ("Google DeepMind Blog", "We're powering European scientific discovery with advanced AI compute and frontier models",
     "https://blog.google/innovation-and-ai/models-and-research/google-deepmind/were-powering-european-scientific-discovery-with-advanced-ai-compute-and-frontier-models/",
     MEDIUM, "10-14 09:00"),
    ("Google DeepMind Blog", "Google Antigravity: Accelerating Antimicrobial Peptide Search",
     "https://deepmind.google/blog/accelerating-antimicrobial-discovery/", LOW, "10-15 15:40"),
    ("TechCrunch AI", "India becomes the latest country to report rogue AI agent activity",
     "https://techcrunch.com/2026/10/16/india-becomes-the-latest-country-to-report-rogue-ai-agent-activity/", HIGH, "10-16 11:50"),
    ("TechCrunch AI", "Jev is Vercel's fastest-adopted AI model ever",
     "https://techcrunch.com/2026/10/16/jev-is-vercels-fastest-adopted-ai-model-ever/", MEDIUM, "10-16 17:05"),
    ("TechCrunch AI", "Elorian's first AI model wants to reason with images, not just about them",
     "https://techcrunch.com/2026/10/16/elorians-first-ai-model-wants-to-reason-with-images-not-just-about-them/", LOW, "10-16 20:30"),
    ("TechCrunch AI", "Replit makes OpenAI its default over Anthropic, CEO says",
     "https://techcrunch.com/2026/10/17/replit-is-no-longer-working-with-anthropic-ceo-says/", MEDIUM, "10-17 18:15"),
    ("Hugging Face Blog", "TorchNeuron: running HF models on AWS Trainium is easier than ever",
     "https://huggingface.co/blog/hf-torchneuron", LOW, "10-19 16:00"),
    ("TechCrunch AI", "OpenAI acquires startup Orchestra Bio to beef up its biotech business",
     "https://techcrunch.com/2026/10/20/openai-acquires-startup-orchestra-bio%E2%81%A0-to-beef-up-its-biotech-business", MEDIUM, "10-20 15:35"),
    ("TechCrunch AI", "Meta's Muse hits 10M US downloads in 40 days, a milestone reached by only 11 other apps",
     "https://techcrunch.com/2026/10/20/metas-muse-hits-10m-u-s-downloads-in-40-days-a-milestone-reached-by-only-11-other-apps", MEDIUM, "10-20 19:00"),
    ("Anthropic News", "Physicist Christopher Stubbs joins Anthropic's Long-Term Benefit Trust",
     "https://anthropic.com/news/christopher-stubbs-joins-long-term-benefit-trust", LOW, "10-21 14:00"),
]

# A few rows that did not go through, so every status badge shows up in the demo.
FAILED = {
    "https://www.anthropic.com/news/genesis-mission-commitment": "SMTP 421 4.7.0 Try again later, closing connection.",
    "https://huggingface.co/blog/hf-torchneuron": "SMTP connection timed out after 30 seconds.",
}
QUEUED = {"https://anthropic.com/news/christopher-stubbs-joins-long-term-benefit-trust"}


def _at(stamp: str) -> datetime:
    return datetime.strptime(f"2026-{stamp}", "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)


def seed(email: str, password: str, channel_email: str) -> None:
    init_db()  # creates tables and the 8 sources if the database is new
    with SessionLocal() as db:
        # Start clean: foreign keys cascade to the profile, channels, sessions and deliveries.
        links = [link for _, _, link, _, _ in DEMO_NEWS]
        db.execute(delete(User).where(func.lower(User.email) == email))
        db.execute(delete(NewsItem).where(NewsItem.link.in_(links)))

        user = User(email=email, password_hash=hash_password(password), created_at=_at("10-01 09:00"))
        db.add(user)
        db.flush()
        # "Everything" so low items in the history match the user's settings.
        db.add(Profile(user_id=user.id, default_threshold=LOW))
        for source_id in db.scalars(select(Source.id).where(Source.is_active)):
            db.add(FollowedSource(user_id=user.id, source_id=source_id))
        channel = Channel(
            user_id=user.id,
            channel_type=ChannelType.email,
            contact=channel_email,
            is_enabled=True,
            is_verified=True,
            created_at=_at("10-01 09:05"),
        )
        db.add(channel)
        db.flush()

        sources = {s.name: s.id for s in db.scalars(select(Source))}
        for name, title, link, level, published in DEMO_NEWS:
            found_at = _at(published) + timedelta(minutes=12)
            item = NewsItem(source_id=sources[name], title=title, link=link, importance_level=level, created_at=found_at)
            db.add(item)
            db.flush()

            d = Delivery(
                user_id=user.id,
                item_id=item.id,
                channel_id=channel.id,
                channel_type=ChannelType.email,
                created_at=found_at + timedelta(minutes=3),
            )
            if link in FAILED:
                d.status, d.attempts, d.last_error = DeliveryStatus.failed, 3, FAILED[link]
            elif link in QUEUED:
                d.status, d.attempts = DeliveryStatus.queued, 0
            else:
                d.status, d.attempts, d.sent_at = DeliveryStatus.sent, 1, d.created_at + timedelta(seconds=40)
            db.add(d)
        db.commit()

    print(f"Demo account: {email} / {password}")
    print(f"Email channel: {channel_email} (verified)")
    print(f"History: {len(DEMO_NEWS)} deliveries ({len(FAILED)} failed, {len(QUEUED)} queued)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", default="demo@ainewsletter.dev")
    parser.add_argument("--password", default="demo1234")
    parser.add_argument("--channel-email", help="address shown on the email channel (default: --email)")
    args = parser.parse_args()
    email = args.email.strip().lower()
    seed(email, args.password, (args.channel_email or email).strip().lower())
