package main

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log/slog"
	"math"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
)

type Config struct {
	Port        string
	DatabaseURL string
	ValkeyHost  string
	ValkeyPort  string
	SecretKey   string
}

type Server struct {
	dbPool    *pgxpool.Pool
	valkey    *redis.Client
	secretKey string
	logger    *slog.Logger
}

type JWTClaims struct {
	Sub            string `json:"sub"`
	Exp            int64  `json:"exp"`
	Role           string `json:"role"`
	TenantID       string `json:"tenant_id"`
	OrganizationID string `json:"organization_id"`
	IsSuperuser    bool   `json:"is_superuser"`
}

type TelemetryRecord struct {
	TransformerID  string  `json:"transformer_id"`
	VoltageV       float64 `json:"voltage_v"`
	CurrentA       float64 `json:"current_a"`
	PowerFactor    float64 `json:"power_factor"`
	FrequencyHz    float64 `json:"frequency_hz"`
	TimestampEpoch float64 `json:"timestamp_epoch"`
}

type UserItem struct {
	ID             string    `json:"id"`
	Email          string    `json:"email"`
	FullName       string    `json:"full_name"`
	IsActive       bool      `json:"is_active"`
	IsSuperuser    bool      `json:"is_superuser"`
	OrganizationID *string   `json:"organization_id"`
	Role           string    `json:"role"`
	CreatedAt      time.Time `json:"created_at"`
	UpdatedAt      time.Time `json:"updated_at"`
}

func parseJWT(authHeader, secretKey string) (*JWTClaims, bool) {
	if !strings.HasPrefix(authHeader, "Bearer ") {
		return nil, false
	}
	tokenStr := strings.TrimSpace(strings.TrimPrefix(authHeader, "Bearer "))
	parts := strings.Split(tokenStr, ".")
	if len(parts) != 3 {
		return nil, false
	}

	mac := hmac.New(sha256.New, []byte(secretKey))
	mac.Write([]byte(parts[0] + "." + parts[1]))
	expectedSig := mac.Sum(nil)

	sig, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil || !hmac.Equal(expectedSig, sig) {
		return nil, false
	}

	payloadBytes, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return nil, false
	}
	var claims JWTClaims
	if err := json.Unmarshal(payloadBytes, &claims); err != nil {
		return nil, false
	}
	if claims.Exp > 0 && claims.Exp < time.Now().Unix() {
		return nil, false
	}
	return &claims, true
}

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()

	cfg := Config{
		Port:        getEnv("PORT", "18002"),
		DatabaseURL: getEnv("DATABASE_URL", "postgres://app_user:dev_Sp6ezCNs9XRi11t407yH@127.0.0.1:5432/app_db?sslmode=disable"),
		ValkeyHost:  getEnv("VALKEY_HOST", "127.0.0.1"),
		ValkeyPort:  getEnv("VALKEY_PORT", "6379"),
		SecretKey:   getEnv("SECRET_KEY", "d4b701543ffa55b4423be1d7993a4e3f6efdf8eaaf406165eee1c37d59ad3974"),
	}

	poolConfig, err := pgxpool.ParseConfig(cfg.DatabaseURL)
	if err != nil {
		logger.Error("Failed to parse database URL", "error", err)
		os.Exit(1)
	}
	poolConfig.MaxConns = 15
	poolConfig.MinConns = 2
	poolConfig.MaxConnLifetime = 30 * time.Minute
	poolConfig.MaxConnIdleTime = 5 * time.Minute

	dbPool, err := pgxpool.NewWithConfig(ctx, poolConfig)
	if err != nil {
		logger.Error("Failed to create database pool", "error", err)
		os.Exit(1)
	}
	defer dbPool.Close()

	valkeyClient := redis.NewClient(&redis.Options{
		Addr:         fmt.Sprintf("%s:%s", cfg.ValkeyHost, cfg.ValkeyPort),
		DialTimeout:  2 * time.Second,
		ReadTimeout:  1 * time.Second,
		WriteTimeout: 1 * time.Second,
		PoolSize:     25,
	})
	defer valkeyClient.Close()

	srv := &Server{
		dbPool:    dbPool,
		valkey:    valkeyClient,
		secretKey: cfg.SecretKey,
		logger:    logger,
	}

	mux := http.NewServeMux()
	mux.HandleFunc("GET /health/ready", srv.handleReadiness)
	mux.HandleFunc("GET /health/live", srv.handleLiveness)
	mux.HandleFunc("GET /health", srv.handleLiveness)
	mux.HandleFunc("GET /api/v1/users", srv.handleUsersList)
	mux.HandleFunc("POST /api/v1/telemetry/ingest", srv.handleTelemetryIngest)

	httpServer := &http.Server{
		Addr:         ":" + cfg.Port,
		Handler:      mux,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	go func() {
		logger.Info("Go Baseline Parity Service listening", "port", cfg.Port)
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Error("HTTP server error", "error", err)
			os.Exit(1)
		}
	}()

	<-ctx.Done()
	logger.Info("Shutdown signal received, shutting down gracefully...")
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer shutdownCancel()
	_ = httpServer.Shutdown(shutdownCtx)
	logger.Info("Go Baseline Service terminated.")
}

func (s *Server) handleLiveness(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(`{"status":"alive"}`))
}

// W1: GET /health/ready
func (s *Server) handleReadiness(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()

	var dbStatus string
	if err := s.dbPool.Ping(ctx); err != nil {
		dbStatus = "unhealthy"
	} else {
		dbStatus = "healthy"
	}

	var valkeyStatus string
	if err := s.valkey.Ping(ctx).Err(); err != nil {
		valkeyStatus = "unhealthy"
	} else {
		valkeyStatus = "healthy"
	}

	status := "ready"
	if dbStatus != "healthy" || valkeyStatus != "healthy" {
		status = "unhealthy"
	}

	w.Header().Set("Content-Type", "application/json")
	if status != "ready" {
		w.WriteHeader(http.StatusServiceUnavailable)
	} else {
		w.WriteHeader(http.StatusOK)
	}
	_ = json.NewEncoder(w).Encode(map[string]any{
		"status": status,
		"dependencies": map[string]string{
			"database": dbStatus,
			"valkey":   valkeyStatus,
		},
	})
}

// W2: GET /api/v1/users (paginated, RLS enabled)
func (s *Server) handleUsersList(w http.ResponseWriter, r *http.Request) {
	claims, ok := parseJWT(r.Header.Get("Authorization"), s.secretKey)
	if !ok {
		http.Error(w, `{"error":"Unauthorized"}`, http.StatusUnauthorized)
		return
	}

	limit := 50
	skip := 0
	if l := r.URL.Query().Get("limit"); l != "" {
		if v, err := strconv.Atoi(l); err == nil && v > 0 && v <= 100 {
			limit = v
		}
	}
	if s := r.URL.Query().Get("skip"); s != "" {
		if v, err := strconv.Atoi(s); err == nil && v >= 0 {
			skip = v
		}
	}

	ctx := r.Context()
	tx, err := s.dbPool.Begin(ctx)
	if err != nil {
		http.Error(w, `{"error":"Transaction begin failed"}`, http.StatusInternalServerError)
		return
	}
	defer tx.Rollback(ctx)

	// Set RLS local context on transaction connection
	role := claims.Role
	if claims.IsSuperuser {
		role = "superadmin"
	}
	tenantID := claims.TenantID
	if tenantID == "" {
		tenantID = claims.OrganizationID
	}

	_, err = tx.Exec(ctx,
		"SELECT set_config('app.current_user_id', $1, true), "+
			"set_config('app.current_tenant_id', $2, true), "+
			"set_config('app.current_role', $3, true)",
		claims.Sub, tenantID, role,
	)
	if err != nil {
		http.Error(w, `{"error":"RLS context setting failed"}`, http.StatusInternalServerError)
		return
	}

	rows, err := tx.Query(ctx,
		"SELECT id, email, full_name, is_active, is_superuser, organization_id, role, created_at, updated_at "+
			"FROM platform_users ORDER BY created_at ASC LIMIT $1 OFFSET $2",
		limit, skip,
	)
	if err != nil {
		http.Error(w, `{"error":"Query execution failed"}`, http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	users := make([]UserItem, 0, limit)
	for rows.Next() {
		var u UserItem
		var orgID *uuid.UUID
		if err := rows.Scan(&u.ID, &u.Email, &u.FullName, &u.IsActive, &u.IsSuperuser, &orgID, &u.Role, &u.CreatedAt, &u.UpdatedAt); err != nil {
			http.Error(w, `{"error":"Row scan failed"}`, http.StatusInternalServerError)
			return
		}
		if orgID != nil {
			s := orgID.String()
			u.OrganizationID = &s
		}
		users = append(users, u)
	}

	_ = tx.Commit(ctx)

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(map[string]any{
		"items": users,
		"total": len(users),
		"limit": limit,
		"skip":  skip,
	})
}

// W4: POST /api/v1/telemetry/ingest
func (s *Server) handleTelemetryIngest(w http.ResponseWriter, r *http.Request) {
	if _, ok := parseJWT(r.Header.Get("Authorization"), s.secretKey); !ok {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusUnauthorized)
		_ = json.NewEncoder(w).Encode(map[string]string{"error": "Unauthorized"})
		return
	}

	r.Body = http.MaxBytesReader(w, r.Body, 4<<20)

	var records []TelemetryRecord
	if err := json.NewDecoder(r.Body).Decode(&records); err != nil {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadRequest)
		_ = json.NewEncoder(w).Encode(map[string]string{"error": "Invalid payload"})
		return
	}

	if len(records) == 0 {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		_ = json.NewEncoder(w).Encode(map[string]any{"accepted": 0, "transformers_updated": 0})
		return
	}

	for _, rec := range records {
		if rec.TransformerID == "" || rec.VoltageV < 0 || rec.FrequencyHz <= 0 || rec.TimestampEpoch <= 0 {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusUnprocessableEntity)
			_ = json.NewEncoder(w).Encode(map[string]string{"error": "Validation failed"})
			return
		}
	}

	now := time.Now().UTC()
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
		http.Error(w, `{"error":"Database copy failed"}`, http.StatusInternalServerError)
		return
	}

	if len(latestMap) > 0 {
		pipe := s.valkey.Pipeline()
		const stateTTL = 24 * time.Hour
		for tid, rec := range latestMap {
			if data, err := json.Marshal(rec); err == nil {
				key := fmt.Sprintf("transformer:state:%s", tid)
				pipe.Set(r.Context(), key, data, stateTTL)
			}
		}
		pipeCtx, pipeCancel := context.WithTimeout(r.Context(), 500*time.Millisecond)
		_, _ = pipe.Exec(pipeCtx)
		pipeCancel()
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusAccepted)
	_ = json.NewEncoder(w).Encode(map[string]any{
		"accepted":             copyCount,
		"transformers_updated": len(latestMap),
		"engine":               "go-native-parity",
	})
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
