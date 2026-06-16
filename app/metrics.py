from prometheus_client import Counter, Histogram

# counters
requests_total = Counter(
    "motivai_requests_total",
    "Total API requests",
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