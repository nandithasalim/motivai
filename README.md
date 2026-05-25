# MotivAI

TikTok-style motivational reels personalized by your goals.

## Live URL
https://motivai-ecjl.onrender.com

## Endpoints
POST /v1/goals_embedding     - onboard user with 3 goals
GET  /v1/feed_return         - get personalized feed
POST /v1/upload_reel         - upload reel (async Celery pipeline)
GET  /v1/celery_status/{id}  - check upload status
POST /v1/tasks               - create task
PATCH /v1/tasks/{id}/complete - complete task
POST /v1/agent/past_tasks    - get similar past tasks

## Stack
FastAPI, pgvector, Redis, Celery, OpenAI, Docker
