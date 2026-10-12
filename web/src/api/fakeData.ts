import type { ImportanceLevel, SourceView } from '../types';

// Fake data used by MockApiClient. Headlines are made up for the demo.
// Source points follow Table 6-6a: official blog 30, tech news 20, community 10.

export const FAKE_SOURCES: SourceView[] = [
  { sourceId: 1, name: 'OpenAI Blog', sourceType: 'rss', url: 'https://openai.com/blog/rss.xml', baseWeight: 30, isActive: true },
  { sourceId: 2, name: 'Anthropic News', sourceType: 'html', url: 'https://www.anthropic.com/news', baseWeight: 30, isActive: true },
  { sourceId: 3, name: 'Google DeepMind Blog', sourceType: 'rss', url: 'https://deepmind.google/blog/rss.xml', baseWeight: 30, isActive: true },
  { sourceId: 4, name: 'Meta AI Blog', sourceType: 'html', url: 'https://ai.meta.com/blog/', baseWeight: 30, isActive: true },
  { sourceId: 5, name: 'Hugging Face Blog', sourceType: 'rss', url: 'https://huggingface.co/blog/feed.xml', baseWeight: 30, isActive: true },
  { sourceId: 6, name: 'TechCrunch AI', sourceType: 'rss', url: 'https://techcrunch.com/category/artificial-intelligence/feed/', baseWeight: 20, isActive: true },
  { sourceId: 7, name: 'The Verge AI', sourceType: 'rss', url: 'https://www.theverge.com/rss/ai-artificial-intelligence/index.xml', baseWeight: 20, isActive: true },
  { sourceId: 8, name: 'Hacker News (AI)', sourceType: 'api', url: 'https://hn.algolia.com/api/v1/search?query=AI', baseWeight: 10, isActive: true },
];

interface FakeNews {
  title: string;
  sourceId: number;
  level: ImportanceLevel;
}

export const FAKE_NEWS: FakeNews[] = [
  { title: 'OpenAI launches a new reasoning model for developers', sourceId: 1, level: 'high' },
  { title: 'Anthropic introduces new Claude models with longer context', sourceId: 2, level: 'high' },
  { title: 'Google DeepMind unveils an updated Gemini family', sourceId: 3, level: 'high' },
  { title: 'Older GPT model versions to be retired from the API next quarter', sourceId: 1, level: 'high' },
  { title: 'Meta releases open-weight Llama update', sourceId: 4, level: 'high' },
  { title: 'AI startup raises $400M in Series C funding', sourceId: 6, level: 'medium' },
  { title: 'New API pricing tiers announced for embedding models', sourceId: 1, level: 'medium' },
  { title: 'EU AI Act: what the next compliance deadline means for developers', sourceId: 7, level: 'medium' },
  { title: 'Hugging Face acquires a model evaluation startup', sourceId: 5, level: 'medium' },
  { title: 'Breaking change in the Assistants API: migration guide published', sourceId: 1, level: 'high' },
  { title: 'Show HN: I built a local RAG tool for my notes', sourceId: 8, level: 'low' },
  { title: 'How we evaluate tool use in large language models', sourceId: 2, level: 'low' },
  { title: 'Join us for a webinar on fine-tuning best practices', sourceId: 5, level: 'low' },
  { title: 'State lawmakers propose new rules for AI in hiring', sourceId: 6, level: 'medium' },
  { title: 'DeepMind research paper on protein structure prediction', sourceId: 3, level: 'low' },
  { title: 'Chip maker unveils next-gen AI accelerator', sourceId: 7, level: 'medium' },
  { title: 'Ask HN: Which open models are you using in production?', sourceId: 8, level: 'low' },
  { title: 'Meta AI shares research on multimodal agents', sourceId: 4, level: 'low' },
  { title: 'Image generation model launches with editing features', sourceId: 1, level: 'high' },
  { title: 'Price cut for small models announced', sourceId: 2, level: 'medium' },
  { title: 'Open-source coding assistant released under Apache 2.0', sourceId: 5, level: 'medium' },
  { title: 'We are hiring: research engineers for alignment', sourceId: 2, level: 'low' },
  { title: 'Executive order on AI safety reporting requirements', sourceId: 7, level: 'high' },
  { title: 'Speech-to-text model update improves accuracy in 50 languages', sourceId: 3, level: 'medium' },
  { title: 'Community benchmark compares long-context retrieval', sourceId: 8, level: 'low' },
  { title: 'Video model introduced for short film generation', sourceId: 3, level: 'high' },
  { title: 'Funding round values AI search startup at $9B', sourceId: 6, level: 'medium' },
  { title: 'Legacy completions endpoint shutdown date announced', sourceId: 1, level: 'high' },
];

export function slugLink(title: string, sourceId: number): string {
  const src = FAKE_SOURCES.find((s) => s.sourceId === sourceId);
  const base = src ? new URL(src.url).origin : 'https://example.com';
  const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
  return `${base}/${slug}`;
}
