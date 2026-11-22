# -*- coding: utf-8 -*-
"""学生能力画像解析任务。

设计取舍：
- 任务状态与画像结果放 Redis，不新增数据库表，避免比赛前做迁移；
- 优先调用 DeepSeek，失败时用服务端规则打分兜底，保证任务一定有结果；
- 输出结构对齐前端 types/studentProfile.ts，前端 normalizeStudentProfile 会补齐标签与派生字段。
"""

import json
import logging
import re

import requests
from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

TASK_CACHE_TTL = 15 * 60
PROFILE_CACHE_TTL = 30 * 24 * 60 * 60

DIMENSION_KEYS = [
    'professional_skill',
    'certificate',
    'innovation',
    'learning',
    'stress_resistance',
    'communication',
    'internship',
    'teamwork',
    'logical_thinking',
    'industry_cognition',
]

DIMENSION_LABELS = {
    'professional_skill': '专业技能',
    'certificate': '证书要求',
    'innovation': '创新能力',
    'learning': '学习能力',
    'stress_resistance': '抗压能力',
    'communication': '沟通能力',
    'internship': '实习能力',
    'teamwork': '团队协作',
    'logical_thinking': '逻辑思维',
    'industry_cognition': '行业认知',
}

COMPLETENESS_FIELDS = [
    ('major', '专业'),
    ('grade', '年级'),
    ('target_job', '意向岗位'),
    ('skills_text', '专业技能'),
    ('certificates_text', '证书资质'),
    ('projects_text', '项目经历'),
    ('internships_text', '实习经历'),
    ('awards_text', '获奖情况'),
    ('gpa', '成绩排名'),
    ('self_evaluation', '自我评价'),
]

BADGE_RULES = [
    ('skill_master', 'professional_skill', 85),
    ('certified', 'certificate', 75),
    ('learning_star', 'learning', 80),
    ('practice_expert', 'internship', 80),
    ('team_star', 'teamwork', 80),
    ('communicator', 'communication', 80),
    ('stress_warrior', 'stress_resistance', 80),
    ('innovator', 'innovation', 80),
    ('logician', 'logical_thinking', 80),
    ('industry_watcher', 'industry_cognition', 80),
]


def task_cache_key(task_id: str) -> str:
    return f'student_profile_task:{task_id}'


def profile_cache_key(user_id: str) -> str:
    return f'student_profile:{user_id}'


def _clamp(value, low=0, high=100):
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0
    return max(low, min(high, int(round(value))))


def _clamp_confidence(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0.6
    return max(0.3, min(0.95, round(value, 2)))


def _level(score: int) -> str:
    if score >= 80:
        return 'high'
    if score >= 60:
        return 'medium'
    return 'low'


def _split_items(text) -> list:
    if not isinstance(text, str):
        return []
    parts = re.split(r'[,，、;；\n\r]+', text)
    return [p.strip() for p in parts if p.strip()]


def _text(payload, key: str, limit: int = 1200) -> str:
    value = payload.get(key, '')
    if value is None:
        return ''
    return str(value).strip()[:limit]


def _rule_scores(payload: dict) -> dict:
    """服务端规则打分：AI 不可用时的确定性兜底。"""
    skills = _split_items(payload.get('skills_text'))
    certs = _split_items(payload.get('certificates_text'))
    projects = _text(payload, 'projects_text')
    internships = _text(payload, 'internships_text')
    awards = _text(payload, 'awards_text')
    gpa = _text(payload, 'gpa')
    self_eval = _text(payload, 'self_evaluation')
    target_industry = _text(payload, 'target_industry')

    def ev(text):
        return [text] if text else []

    return {
        'professional_skill': {
            'score': _clamp(52 + min(len(skills) * 6, 30) + (6 if projects else 0)),
            'confidence': 0.72 if skills else 0.45,
            'evidence': ev(_text(payload, 'skills_text')),
        },
        'certificate': {
            'score': _clamp(48 + min(len(certs) * 12, 42)),
            'confidence': 0.7 if certs else 0.4,
            'evidence': ev(_text(payload, 'certificates_text')),
        },
        'innovation': {
            'score': _clamp(60 + (8 if projects else 0) + (5 if awards else 0)),
            'confidence': 0.62,
            'evidence': ev(projects),
        },
        'learning': {
            'score': _clamp(62 + (8 if projects else 0) + (5 if awards else 0) + (5 if gpa else 0)),
            'confidence': 0.65,
            'evidence': ev(projects or awards or gpa),
        },
        'stress_resistance': {
            'score': _clamp(62 + (8 if internships else 0) + (5 if self_eval else 0)),
            'confidence': 0.6,
            'evidence': ev(self_eval or internships),
        },
        'communication': {
            'score': _clamp(62 + (8 if self_eval else 0) + (5 if internships else 0)),
            'confidence': 0.62,
            'evidence': ev(self_eval or internships),
        },
        'internship': {
            'score': _clamp(50 + (25 if len(internships) > 20 else 12 if internships else 0)),
            'confidence': 0.7 if internships else 0.42,
            'evidence': ev(internships),
        },
        'teamwork': {
            'score': _clamp(62 + (8 if projects else 0) + (5 if self_eval else 0)),
            'confidence': 0.62,
            'evidence': ev(self_eval or projects),
        },
        'logical_thinking': {
            'score': _clamp(62 + (8 if projects else 0) + (5 if gpa else 0)),
            'confidence': 0.62,
            'evidence': ev(projects or gpa),
        },
        'industry_cognition': {
            'score': _clamp(56 + (10 if target_industry else 0) + (5 if self_eval else 0)),
            'confidence': 0.58,
            'evidence': ev(target_industry),
        },
    }


def _ai_api_config():
    api_key = (
        getattr(settings, 'AI_API_KEY', '')
        or getattr(settings, 'DASHSCOPE_API_KEY', '')
    )
    api_url = (
        getattr(settings, 'AI_API_URL', '')
        or getattr(settings, 'DASHSCOPE_API_URL', '')
    ).rstrip('/')
    model = getattr(settings, 'AI_MODEL', 'deepseek-chat')
    if api_url and not api_url.endswith('/chat/completions'):
        api_url = f'{api_url}/chat/completions'
    return api_key, api_url, model


def _call_ai(payload: dict) -> dict:
    api_key, api_url, model = _ai_api_config()
    if not api_key:
        raise RuntimeError('未配置 AI_API_KEY')
    if not api_url:
        raise RuntimeError('未配置 AI_API_URL')

    student_text = json.dumps(
        {key: _text(payload, key, 2000) for key in [
            'major', 'grade', 'target_job', 'target_industry',
            'skills_text', 'certificates_text', 'projects_text',
            'internships_text', 'awards_text', 'gpa',
            'self_evaluation', 'resume_text',
        ]},
        ensure_ascii=False,
    )

    prompt = (
        '你是校园就业能力评估助手。根据学生填写的信息，对十个能力维度打分。\n'
        '只输出一个 JSON 对象，不要 Markdown，不要解释。\n'
        'JSON 结构：\n'
        '{"summary":"一句话总结",'
        '"dimensions":{'
        '"professional_skill":{"score":0-100,"confidence":0-1,"evidence":["学生原话或字段"]},'
        '"certificate":{...},"innovation":{...},"learning":{...},'
        '"stress_resistance":{...},"communication":{...},"internship":{...},'
        '"teamwork":{...},"logical_thinking":{...},"industry_cognition":{...}}}\n'
        '要求：十个 key 必须齐全；分数要参考学生实际填写的内容，不要全部给同分；'
        'evidence 必须来自学生信息，不要编造。\n'
        f'学生信息：{student_text}'
    )

    response = requests.post(
        url=api_url,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json; charset=utf-8',
        },
        json={
            'model': model,
            'messages': [
                {'role': 'system', 'content': '你只输出严格 JSON，不要 Markdown。'},
                {'role': 'user', 'content': prompt},
            ],
            'temperature': 0.2,
            'max_tokens': 2500,
            'stream': False,
        },
        timeout=45,
    )
    response.raise_for_status()
    body = response.json()
    content = body['choices'][0]['message']['content'].strip()

    # 去掉可能的 ```json 包裹
    if content.startswith('```'):
        content = re.sub(r'^```[a-zA-Z]*\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
    start, end = content.find('{'), content.rfind('}')
    if start < 0 or end <= start:
        raise ValueError('大模型未返回 JSON 对象')
    parsed = json.loads(content[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError('大模型返回的 JSON 不是对象')
    return parsed


def _normalize_ai_dimensions(parsed: dict) -> dict:
    raw = parsed.get('dimensions')
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        result = {}
        for item in raw:
            if isinstance(item, dict) and item.get('key'):
                result[str(item['key'])] = item
        return result
    return {}


def _build_dimensions(payload: dict, ai_parsed: dict | None, source: str) -> list:
    rule = _rule_scores(payload)
    ai_dims = _normalize_ai_dimensions(ai_parsed or {})
    dimensions = []

    for key in DIMENSION_KEYS:
        fallback = rule[key]
        raw = ai_dims.get(key) if source == 'qwen' else None
        if not isinstance(raw, dict):
            raw = fallback

        evidence = raw.get('evidence')
        if isinstance(evidence, str):
            evidence = [evidence]
        if not isinstance(evidence, list):
            evidence = fallback.get('evidence') or []
        evidence = [str(item)[:300] for item in evidence if str(item).strip()][:3]

        dimensions.append({
            'key': key,
            'label': DIMENSION_LABELS[key],
            'score': _clamp(raw.get('score', fallback['score'])),
            'level': _level(_clamp(raw.get('score', fallback['score']))),
            'confidence': _clamp_confidence(raw.get('confidence', fallback['confidence'])),
            'source': source,
            'evidence': evidence,
        })

    return dimensions


def _completeness(payload: dict):
    detail = []
    missing = []
    total = 0
    for field, label in COMPLETENESS_FIELDS:
        value = _text(payload, field)
        ratio = 1.0 if len(value) >= 8 else 0.5 if value else 0.0
        score = round(ratio * 10)
        total += score
        detail.append({
            'field': field,
            'label': label,
            'filled': bool(value),
            'ratio': ratio,
            'score': score,
            'fullScore': 10,
        })
        if not value:
            missing.append(label)
    return _clamp(total), detail, missing


def _badges(dimensions: list) -> list:
    score_map = {d['key']: d['score'] for d in dimensions}
    badges = []
    for badge_id, dim_key, threshold in BADGE_RULES:
        score = score_map.get(dim_key, 0)
        badges.append({
            'id': badge_id,
            'unlocked': score >= threshold,
            'progress': round(min(score / threshold, 1), 2) if threshold else 0,
        })

    high_count = sum(1 for score in score_map.values() if score >= 80)
    badges.append({
        'id': 'all_rounder',
        'unlocked': all(score >= 70 for score in score_map.values()),
        'progress': round(sum(1 for score in score_map.values() if score >= 70) / 10, 2),
    })
    badges.append({
        'id': 'hexagon_warrior',
        'unlocked': high_count >= 6,
        'progress': round(min(high_count / 6, 1), 2),
    })
    return badges


def build_student_profile(payload: dict, user_id: str) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    major = _text(payload, 'major')
    if not major:
        raise ValueError('专业不能为空')

    source = 'qwen'
    ai_parsed = None
    try:
        ai_parsed = _call_ai(payload)
    except Exception as exc:
        logger.warning('学生画像 AI 解析失败，使用服务端规则兜底：%s', exc)
        source = 'rule'

    dimensions = _build_dimensions(payload, ai_parsed, source)
    score_map = {d['key']: d['score'] for d in dimensions}
    ordered = sorted(score_map.items(), key=lambda item: item[1], reverse=True)
    completeness, completeness_detail, missing_fields = _completeness(payload)
    competitiveness = _clamp(sum(score_map.values()) / len(score_map))
    confidence = round(sum(d['confidence'] for d in dimensions) / len(dimensions), 2)

    summary = ''
    if isinstance(ai_parsed, dict):
        summary = str(ai_parsed.get('summary') or '').strip()[:300]
    if not summary:
        summary = f'已完成十维能力评估，综合竞争力 {competitiveness} 分。'

    return {
        'student_id': str(user_id),
        'major': major,
        'grade': _text(payload, 'grade'),
        'target_job': _text(payload, 'target_job'),
        'target_industry': _text(payload, 'target_industry'),
        'dimensions': dimensions,
        'completeness': completeness,
        'completeness_detail': completeness_detail,
        'missing_fields': missing_fields,
        'competitiveness': competitiveness,
        'competitiveness_level': _level(competitiveness),
        'strengths': [key for key, _ in ordered[:3]],
        'weaknesses': [key for key, _ in ordered[-3:]],
        'badges': _badges(dimensions),
        'summary': summary,
        'parse_method': source,
        'confidence': confidence,
        'parsed_at': timezone.now().isoformat(),
    }


@shared_task(bind=True, max_retries=0)
def parse_student_profile_task(self, task_id: str, user_id: str, payload: dict):
    key = task_cache_key(task_id)
    try:
        profile = build_student_profile(payload, user_id)
        result = {
            'status': 'SUCCESS',
            'user_id': str(user_id),
            'data': {'profile': profile},
        }
        cache.set(key, result, TASK_CACHE_TTL)
        cache.set(profile_cache_key(user_id), profile, PROFILE_CACHE_TTL)
        return result
    except Exception as exc:
        logger.exception('学生画像任务失败：%s', exc)
        result = {
            'status': 'FAILURE',
            'user_id': str(user_id),
            'error': str(exc),
        }
        cache.set(key, result, TASK_CACHE_TTL)
        return result
