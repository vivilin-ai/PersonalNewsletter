#!/usr/bin/env node

import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';
import { resolveCredentials } from '../skills/personal-newsletter/scripts/vendor/bird-search/lib/cookies.js';
import { TwitterClientBase } from '../skills/personal-newsletter/scripts/vendor/bird-search/lib/twitter-client-base.js';
import { withSearch } from '../skills/personal-newsletter/scripts/vendor/bird-search/lib/twitter-client-search.js';

const SearchClient = withSearch(TwitterClientBase);

const INPUT_PATH = 'data/x-lists/swyx_ai_high_signal_members_raw.json';
const OUTPUT_PATH = 'data/x-lists/swyx_ai_high_signal_expert_pool_v1.json';
const SINCE_DATE = '2026-02-01';
const CONTENT_SAMPLE_COUNT = 8;
const MIN_FOLLOWERS_FOR_WEAK_PROFILE = 300;
const MAX_CONTENT_REVIEWS = 100;
const REQUEST_DELAY_MS = 1800;

const profilePositiveTerms = [
  'research',
  'researcher',
  'engineer',
  'engineering',
  'scientist',
  'technical staff',
  'member of technical staff',
  'training',
  'inference',
  'eval',
  'evaluation',
  'alignment',
  'multimodal',
  'llm',
  'ml',
  'deep learning',
  'rl',
  'professor',
  'phd',
  'postdoc',
  'maintainer',
  'creator',
  'author',
  'open source',
  'interpretability',
  'benchmark',
  'agentic',
  'rag',
  'compiler',
  'pytorch',
  'transformers',
  'reasoning',
  'safety',
];

const personalClueTerms = [
  'opinions are my own',
  'all opinions are my own',
  'prev',
  'ex-',
  'phd',
  'professor',
  'researcher',
  'engineer',
  'scientist',
  'maintainer',
  'creator',
  'founder',
  'cofounder',
  'co-founder',
  'ceo',
  'cto',
  'vp',
  'director',
  'head of',
  'lead ',
  'mts',
  'mots',
  'working on',
  'building',
];

const mediaTerms = [
  'newsletter',
  'podcast',
  'news',
  'digest',
  'community account',
  'weekly',
  'roundup',
  'media',
  'timeline',
  'explained',
  'spaces',
];

const orgTerms = [
  'official',
  'company',
  'platform',
  'api',
  'studio',
  'labs',
  'lab',
  'foundation',
  'school',
  'community',
  'cloud',
  'research group',
];

const technicalContentTerms = [
  'model',
  'models',
  'llm',
  'rl',
  'reasoning',
  'inference',
  'train',
  'training',
  'benchmark',
  'eval',
  'evaluation',
  'agent',
  'agents',
  'post-training',
  'pretraining',
  'multimodal',
  'transformer',
  'pytorch',
  'cuda',
  'context',
  'token',
  'dataset',
  'paper',
  'weights',
  'open source',
  'rag',
  'compiler',
  'latency',
  'throughput',
];

const lowSignalContentTerms = [
  'subscribe',
  'join the waitlist',
  'waitlist',
  'newsletter',
  'podcast',
  'new episode',
  'follow for',
  'discord',
  'youtube',
];

function countMatches(text, terms) {
  const haystack = ` ${text.toLowerCase()} `;
  return terms.reduce((count, term) => count + (haystack.includes(term) ? 1 : 0), 0);
}

function classifyProfile(user) {
  const name = user.name || '';
  const description = user.description || '';
  const text = `${name} ${description}`.toLowerCase();

  let org = countMatches(text, orgTerms);
  const pos = countMatches(text, profilePositiveTerms);
  const media = countMatches(text, mediaTerms);
  const personal = countMatches(text, personalClueTerms);

  if (
    description.startsWith('We ') ||
    description.startsWith('We are') ||
    description.startsWith("We're") ||
    description.startsWith('Built by') ||
    description.startsWith('Makers of') ||
    description.startsWith('An AI') ||
    description.startsWith('A high-throughput') ||
    description.startsWith('The AI') ||
    description.startsWith('The fastest')
  ) {
    org += 2;
  }

  const likelyOrg =
    description.startsWith('We ') ||
    description.startsWith('We are') ||
    description.startsWith("We're") ||
    description.startsWith('Built by') ||
    description.startsWith('Makers of') ||
    description.startsWith('An AI') ||
    description.startsWith('A high-throughput') ||
    description.startsWith('The AI') ||
    description.startsWith('The fastest') ||
    text.includes('official updates') ||
    text.includes('developer platform') ||
    text.includes('research company') ||
    text.includes('applied ai lab') ||
    text.includes('join us') ||
    text.includes('join the waitlist');

  const profileScore = pos * 2 + personal - media * 2 - org;

  let kind = 'unclear';
  if (media >= 1 && pos <= 2) {
    kind = 'media_community';
  } else if (likelyOrg && personal === 0) {
    kind = 'org_signal';
  } else if (org >= 2 && personal === 0 && pos <= 2) {
    kind = 'org_signal';
  } else if ((personal >= 1 && pos >= 1) || pos >= 3) {
    kind = 'expert_personal';
  } else if (org >= 1 && pos >= 2 && personal === 0) {
    kind = 'org_signal';
  }

  return {
    kind,
    profileScore,
    pos,
    media,
    org,
    personal,
    likelyOrg,
  };
}

function shouldReviewContent(user, profile) {
  const followers = user.followersCount || 0;
  const description = (user.description || '').trim();

  if (profile.kind === 'media_community') {
    return false;
  }
  if (profile.kind === 'org_signal') {
    return false;
  }
  if (followers < MIN_FOLLOWERS_FOR_WEAK_PROFILE && profile.profileScore < 8) {
    return false;
  }
  if (!description && followers < 2000) {
    return false;
  }
  return profile.kind === 'expert_personal' || (profile.kind === 'unclear' && profile.profileScore >= 4);
}

function scoreContent(posts) {
  if (!posts || posts.length === 0) {
    return {
      contentScore: 0,
      originalPosts: 0,
      technicalOriginalPosts: 0,
      longOriginalPosts: 0,
      replyRatio: 1,
      lowSignalPosts: 0,
    };
  }

  const originals = posts.filter((post) => {
    const text = (post.text || '').trim();
    return !post.inReplyToStatusId && !text.startsWith('@');
  });

  const technicalOriginalPosts = originals.filter((post) =>
    countMatches(post.text || '', technicalContentTerms) > 0,
  );
  const longOriginalPosts = originals.filter((post) => (post.text || '').length >= 140);
  const lowSignalPosts = originals.filter((post) =>
    countMatches(post.text || '', lowSignalContentTerms) > 0,
  );
  const replyRatio = posts.length === 0 ? 1 : (posts.length - originals.length) / posts.length;

  let contentScore = 0;
  if (originals.length >= 2) contentScore += 2;
  if (technicalOriginalPosts.length >= 1) contentScore += 2;
  if (technicalOriginalPosts.length >= 4) contentScore += 1;
  if (longOriginalPosts.length >= 2) contentScore += 1;
  if (replyRatio > 0.6) contentScore -= 2;
  if (lowSignalPosts.length >= 3) contentScore -= 2;
  if (originals.length === 0) contentScore -= 3;

  return {
    contentScore,
    originalPosts: originals.length,
    technicalOriginalPosts: technicalOriginalPosts.length,
    longOriginalPosts: longOriginalPosts.length,
    replyRatio,
    lowSignalPosts: lowSignalPosts.length,
  };
}

function decideTier(user, profile, content) {
  const totalScore = profile.profileScore + content.contentScore;
  const followers = user.followersCount || 0;

  if (
    totalScore >= 11 &&
    content.technicalOriginalPosts >= 2 &&
    content.originalPosts >= 2 &&
    content.replyRatio <= 0.5
  ) {
    return 'core';
  }

  if (
    totalScore >= 8 &&
    content.technicalOriginalPosts >= 1 &&
    content.originalPosts >= 1 &&
    content.replyRatio <= 0.75
  ) {
    return 'signal';
  }

  if (
    totalScore >= 8 &&
    followers >= 5000 &&
    content.technicalOriginalPosts >= 1 &&
    content.originalPosts >= 2
  ) {
    return 'signal';
  }

  return null;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchRecentPosts(client, handle) {
  const query = `from:${handle} since:${SINCE_DATE}`;
  const result = await client.search(query, CONTENT_SAMPLE_COUNT);
  if (!result.success) {
    return [];
  }
  return result.tweets || [];
}

const raw = JSON.parse(await readFile(INPUT_PATH, 'utf8'));
const users = raw.users;

const { cookies } = await resolveCredentials({});
const client = new SearchClient({
  cookies: {
    authToken: cookies.authToken,
    ct0: cookies.ct0,
    cookieHeader: cookies.cookieHeader,
  },
  timeoutMs: 30000,
});

const reviewedCandidates = [];
const orgSignalPool = [];
const rejectedByProfile = [];

for (const user of users) {
  const profile = classifyProfile(user);
  if (profile.kind === 'org_signal') {
    orgSignalPool.push({
      handle: user.username,
      label: user.name,
      followersCount: user.followersCount || 0,
      profileScore: profile.profileScore,
      reason: 'organization_or_project_signal',
      description: user.description || '',
    });
    continue;
  }
  if (profile.kind === 'media_community') {
    rejectedByProfile.push({
      handle: user.username,
      label: user.name,
      reason: 'media_or_community',
      description: user.description || '',
    });
    continue;
  }
  if (shouldReviewContent(user, profile)) {
    reviewedCandidates.push({ user, profile });
  } else {
    rejectedByProfile.push({
      handle: user.username,
      label: user.name,
      reason: 'weak_profile_signal',
      description: user.description || '',
    });
  }
}

reviewedCandidates.sort((a, b) => {
  const scoreDelta = b.profile.profileScore - a.profile.profileScore;
  if (scoreDelta !== 0) return scoreDelta;
  return (b.user.followersCount || 0) - (a.user.followersCount || 0);
});
const limitedCandidates = reviewedCandidates.slice(0, MAX_CONTENT_REVIEWS);

const finalExperts = [];
const borderline = [];

for (let index = 0; index < limitedCandidates.length; index += 1) {
  const candidate = limitedCandidates[index];
  const { user, profile } = candidate;
  console.error(
    `content ${index + 1}/${limitedCandidates.length} ${user.username} profile=${profile.profileScore}`,
  );
  const posts = await fetchRecentPosts(client, user.username);
  const content = scoreContent(posts);
  const tier = decideTier(user, profile, content);
  const record = {
    handle: user.username,
    label: user.name,
    description: user.description || '',
    followersCount: user.followersCount || 0,
    followingCount: user.followingCount || 0,
    isBlueVerified: Boolean(user.isBlueVerified),
    createdAt: user.createdAt || null,
    profileScore: profile.profileScore,
    contentScore: content.contentScore,
    originalPosts: content.originalPosts,
    technicalOriginalPosts: content.technicalOriginalPosts,
    longOriginalPosts: content.longOriginalPosts,
    replyRatio: Number(content.replyRatio.toFixed(3)),
    contentSampleCount: posts.length,
    kind: profile.kind,
  };

  if (tier) {
    finalExperts.push({
      ...record,
      tier,
    });
  } else {
    borderline.push(record);
  }
  await sleep(REQUEST_DELAY_MS);
}

finalExperts.sort((a, b) => {
  const tierRank = { core: 2, signal: 1 };
  const tierDelta = tierRank[b.tier] - tierRank[a.tier];
  if (tierDelta !== 0) return tierDelta;
  const scoreDelta = (b.profileScore + b.contentScore) - (a.profileScore + a.contentScore);
  if (scoreDelta !== 0) return scoreDelta;
  return b.followersCount - a.followersCount;
});

orgSignalPool.sort((a, b) => b.followersCount - a.followersCount);

const output = {
  source: {
    input_path: INPUT_PATH,
    output_path: OUTPUT_PATH,
    fetched_at: '2026-05-10',
    since_date: SINCE_DATE,
    candidate_count: users.length,
    reviewed_content_count: limitedCandidates.length,
  },
  rules: {
    profile: 'Research/engineering-heavy bios are favored; media/community and obvious org accounts are separated.',
    content:
      'Recent posts must show enough non-reply original AI content with technical keywords; reply-heavy or promo-heavy accounts are filtered.',
  },
  summary: {
    final_expert_count: finalExperts.length,
    core_count: finalExperts.filter((item) => item.tier === 'core').length,
    signal_count: finalExperts.filter((item) => item.tier === 'signal').length,
    org_signal_count: orgSignalPool.length,
    rejected_profile_count: rejectedByProfile.length,
    borderline_count: borderline.length,
  },
  experts: finalExperts,
  org_signal_pool: orgSignalPool,
  borderline,
};

await mkdir(dirname(OUTPUT_PATH), { recursive: true });
await writeFile(OUTPUT_PATH, `${JSON.stringify(output, null, 2)}\n`, 'utf8');
console.log(
  JSON.stringify(
    {
      output_path: OUTPUT_PATH,
      summary: output.summary,
    },
    null,
    2,
  ),
);
