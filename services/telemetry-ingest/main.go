package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
)

// TelemetryRecord mirrors app.domain.telemetry.schemas.TelemetryRecord
type TelemetryRecord struct {
	TransformerID  string  `json:"transformer_id"`
	VoltageV       float64 `json:"voltage_v"`
	CurrentA       float64 `json:"current_a"`
	PowerFactor    float64 `json:"power_factor"`
	FrequencyHz    float64 `json:"frequency_hz"`
	TimestampEpoch float64 `json:"timestamp_epoch"`
}

type Server struct {
	dbPool *pgxpool.Pool
	valkey *redis.Client
}

func main() {
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()

	port := getEnv("PORT", "8001")
	dbURL := getDatabaseURL()
	valkeyHost := getEnv("VALKEY_HOST", "localhost")
	valkeyPort := getEnv("VALKEY_PORT", "6379")

	// 1. Initialize PostgreSQL / TimescaleDB Connection Pool
	poolConfig, err := pgxpool.ParseConfig(dbURL)
	if err != nil {
		log.Fatalf("Failed to parse database config: %v", err)
	}
	poolConfig.MaxConns = 30
	poolConfig.MinConns = 5
	poolConfig.MaxConnLifetime = 30 * time.Minute
	poolConfig.MaxConnIdleTime = 5 * time.Minute

	dbPool, err := pgxpool.NewWithConfig(ctx, poolConfig)
	if err != nil {
		log.Fatalf("Failed to connect to database: %v", err)
	}
	defer dbPool.Close()

	if err := dbPool.Ping(ctx); err != nil {
		log.Printf("Warning: initial DB ping failed: %v", err)
	} else {
		log.Println("Connected to PostgreSQL/TimescaleDB with binary pgx protocol")
	}

	// 2. Initialize Valkey (Redis-compatible) client
	valkeyClient := redis.NewClient(&redis.Options{
		Addr:         fmt.Sprintf("%s:%s", valkeyHost, valkeyPort),
		DialTimeout:  2 * time.Second,
		ReadTimeout:  1 * time.Second,
		WriteTimeout: 1 * time.Second,
		PoolSize:     50,
	})
	defer valkeyClient.Close()

	if err := valkeyClient.Ping(ctx).Err(); err != nil {
		log.Printf("Warning: initial Valkey ping failed: %v", err)
	} else {
		log.Println("Connected to Valkey in-memory cache")
	}

	srv := &Server{
		dbPool: dbPool,
		valkey: valkeyClient,
	}

	// 3. Register HTTP Routes
	mux := http.NewServeMux()
	mux.HandleFunc("POST /api/v1/telemetry/ingest", srv.handleTelemetryIngest)
	mux.HandleFunc("GET /health/live", srv.handleLiveness)
	mux.HandleFunc("GET /health/ready", srv.handleReadiness)
	mux.HandleFunc("GET /health", srv.handleLiveness)

	httpServer := &http.Server{
		Addr:         ":" + port,
		Handler:      loggingMiddleware(mux),
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	go func() {
		log.Printf("High-Throughput Go Telemetry Ingest Bypass active on port :%s", port)
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("HTTP server error: %v", err)
		}
	}()

	<-ctx.Done()
	log.Println("Shutdown signal received, draining connections...")

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer shutdownCancel()

	if err := httpServer.Shutdown(shutdownCtx); err != nil {
		log.Printf("HTTP shutdown error: %v", err)
	}
	log.Println("Telemetry Ingest service terminated cleanly.")
}

func (s *Server) handleTelemetryIngest(w http.ResponseWriter, r *http.Request) {
	var records []TelemetryRecord
	if err := json.NewDecoder(r.Body).Decode(&records); err != nil {
		http.Error(w, `{"error":"Invalid JSON payload: expected list of telemetry records"}`, http.StatusBadRequest)
		return
	}

	if len(records) == 0 {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		_ = json.NewEncoder(w).Encode(map[string]any{"accepted": 0, "transformers_updated": 0})
		return
	}

	now := time.Now().UTC()

	// ── 1. Batch High-Speed Binary Ingestion using PostgreSQL CopyFrom ────────
	// This streams directly over the PostgreSQL binary wire protocol, achieving 100k+ rows/sec.
	rows := make([][]any, len(records))
	latestMap := make(map[string]TelemetryRecord, len(records))

	for i, rec := range records {
		recID := uuid.New()
		sec, dec := math.Modf(rec.TimestampEpoch)
		recordedAt := time.Unix(int64(sec), int64(dec*1e9)).UTC()

		rows[i] = []any{
			recID,
			rec.TransformerID,
			rec.VoltageV,
			rec.CurrentA,
			rec.PowerFactor,
			rec.FrequencyHz,
			recordedAt,
			now,
		}

		// Keep only newest record per transformer
		existing, ok := latestMap[rec.TransformerID]
		if !ok || rec.TimestampEpoch > existing.TimestampEpoch {
			latestMap[rec.TransformerID] = rec
		}
	}

	copyCount, err := s.dbPool.CopyFrom(
		r.Context(),
		pgx.Identifier{"telemetry_readings"},
		[]string{"id", "transformer_id", "voltage_v", "current_a", "power_factor", "frequency_hz", "recorded_at", "ingested_at"},
		pgx.CopyFromRows(rows),
	)
	if err != nil {
		log.Printf("CopyFrom ingestion error: %v", err)
		http.Error(w, fmt.Sprintf(`{"error":"Database ingestion failed: %s"}`, err.Error()), http.StatusInternalServerError)
		return
	}

	// ── 2. Fan-out latest state per transformer to Valkey concurrently ────────
	var wg sync.WaitGroup
	pipe := s.valkey.Pipeline()
	const stateTTL = 24 * time.Hour

	for tid, rec := range latestMap {
		data, err := json.Marshal(rec)
		if err == nil {
			key := fmt.Sprintf("transformer:state:%s", tid)
			pipe.Set(r.Context(), key, data, stateTTL)
		}
	}

	wg.Add(1)
	go func() {
		defer wg.Done()
		if _, pipeErr := pipe.Exec(context.Background()); pipeErr != nil {
			log.Printf("Valkey pipeline cache update error: %v", pipeErr)
		}
	}()
	wg.Wait()

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusAccepted)
	_ = json.NewEncoder(w).Encode(map[string]any{
		"accepted":             copyCount,
		"transformers_updated": len(latestMap),
		"engine":               "go-binary-copyfrom",
	})
}

func (s *Server) handleLiveness(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(`{"status":"alive","service":"telemetry-ingest-go"}`))
}

func (s *Server) handleReadiness(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()

	deps := map[string]string{
		"database": "healthy",
		"valkey":   "healthy",
	}
	allHealthy := true

	if err := s.dbPool.Ping(ctx); err != nil {
		deps["database"] = fmt.Sprintf("error: %v", err)
		allHealthy = false
	}

	if err := s.valkey.Ping(ctx).Err(); err != nil {
		deps["valkey"] = fmt.Sprintf("error: %v", err)
		allHealthy = false
	}

	status := http.StatusOK
	if !allHealthy {
		status = http.StatusServiceUnavailable
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]any{
		"status":       map[bool]string{true: "ready", false: "not_ready"}[allHealthy],
		"dependencies": deps,
	})
}

func loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		rw := &responseWriter{ResponseWriter: w, statusCode: http.StatusOK}
		next.ServeHTTP(rw, r)
		log.Printf("%s - \"%s %s %s\" %d (%s)",
			r.RemoteAddr, r.Method, r.URL.Path, r.Proto, rw.statusCode, time.Since(start))
	})
}

type responseWriter struct {
	http.ResponseWriter
	statusCode int
}

func (rw *responseWriter) WriteHeader(code int) {
	rw.statusCode = code
	rw.ResponseWriter.WriteHeader(code)
}

func getEnv(key, defaultVal string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultVal
}

func getDatabaseURL() string {
	if raw := os.Getenv("DATABASE_URL"); raw != "" {
		// Clean Python asyncpg/psycopg prefixes if passed from root .env
		cleaned := strings.Replace(raw, "postgresql+asyncpg://", "postgres://", 1)
		cleaned = strings.Replace(cleaned, "postgresql+psycopg2://", "postgres://", 1)
		return cleaned
	}

	user := getEnv("POSTGRES_USER", "app_user")
	pass := getEnv("POSTGRES_PASSWORD", "secure_dev_password")
	host := getEnv("POSTGRES_HOST", "localhost")
	port := getEnv("POSTGRES_PORT", "5432")
	db := getEnv("POSTGRES_DB", "app_db")

	return fmt.Sprintf("postgres://%s:%s@%s:%s/%s?sslmode=disable", user, pass, host, port, db)
}
