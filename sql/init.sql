CREATE TABLE IF NOT EXISTS rides_minute_metrics (
  window_start TIMESTAMP NOT NULL,
  window_end   TIMESTAMP NOT NULL,
  city         TEXT,
  events       BIGINT,
  avg_fare     DOUBLE PRECISION,
  p95_fare     DOUBLE PRECISION,
  avg_duration_sec DOUBLE PRECISION,
  PRIMARY KEY (window_start, window_end, city)
);
