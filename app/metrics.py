from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# counters
requests_total = Counter(
    "motivai_requests_total",
    "Total API requests",
    ["endpoint"]
)

llm_calls_total = Counter(
    "motivai_llm_calls_total",
    "Total LLM calls",
    ["model", "feature"]
)

errors_total = Counter(
    "motivai_errors_total",
    "Total errors",
    ["endpoint"]
)

# histograms
feed_latency = Histogram(
    "motivai_feed_latency_seconds",
    "Feed endpoint latency",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0]
)

agent_latency = Histogram(
    "motivai_agent_latency_seconds",
    "Agent reaction latency",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0]
)