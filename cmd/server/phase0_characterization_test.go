package main

import (
	"context"
	"database/sql"
	"errors"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"
	"time"
)

func newPhase0DB(t *testing.T) *sql.DB {
	t.Helper()
	db, err := openDB(filepath.Join(t.TempDir(), "phase0.db"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = db.Close() })
	return db
}

func TestPhase0AuthCharacterizationSingleSessionRawToken(t *testing.T) {
	ctx := context.Background()
	store, err := newAuthStore(ctx, newPhase0DB(t))
	if err != nil {
		t.Fatal(err)
	}

	created, err := store.SeedAdmin(ctx, "owner@example.test", "correct-horse-battery-staple")
	if err != nil || !created {
		t.Fatalf("first SeedAdmin should create owner: created=%v err=%v", created, err)
	}
	created, err = store.SeedAdmin(ctx, "other@example.test", "another-strong-password")
	if err != nil || created {
		t.Fatalf("second SeedAdmin must be idempotent: created=%v err=%v", created, err)
	}

	user, firstToken, err := store.Login(ctx, "OWNER@example.test", "correct-horse-battery-staple")
	if err != nil {
		t.Fatal(err)
	}
	if !user.HasRole(RoleAdmin) || len(firstToken) != 64 {
		t.Fatalf("unexpected owner/token contract: user=%+v tokenLength=%d", user, len(firstToken))
	}

	var persisted string
	if err := store.db.QueryRowContext(ctx, `SELECT token FROM auth_tokens WHERE user_id = ?`, user.ID).Scan(&persisted); err != nil {
		t.Fatal(err)
	}
	if persisted != firstToken {
		t.Fatal("legacy behavior changed: authentication token is expected to be stored verbatim")
	}

	_, secondToken, err := store.Login(ctx, "owner@example.test", "correct-horse-battery-staple")
	if err != nil {
		t.Fatal(err)
	}
	if secondToken == firstToken {
		t.Fatal("a new login must rotate the single active session token")
	}
	if _, err := store.UserByToken(ctx, firstToken); !errors.Is(err, ErrUserNotFound) {
		t.Fatalf("old token should be revoked after new login, got %v", err)
	}
}

func TestPhase0MessageCharacterizationIdempotencyOrderingAndSessionBoundary(t *testing.T) {
	ctx := context.Background()
	store, err := newMessageStore(ctx, newPhase0DB(t))
	if err != nil {
		t.Fatal(err)
	}

	first := MessageRow{
		ID: "message-1", SessionID: "session-a", ChatJID: "551100000001@s.whatsapp.net",
		SenderJID: "551100000001@s.whatsapp.net", Ts: 1000, Kind: "image",
		Body: "caption", MediaMime: "image/jpeg", MediaURL: "/api/media/in/message-1.jpg",
		FileName: "message-1.jpg", FileSize: 128,
	}
	if err := store.Insert(ctx, first); err != nil {
		t.Fatal(err)
	}
	// Characterize the self-echo path: empty media fields must not erase the
	// local copy previously persisted by the upload/download path.
	echo := first
	echo.Body = ""
	echo.MediaURL = ""
	echo.FileName = ""
	echo.FileSize = 0
	if err := store.Insert(ctx, echo); err != nil {
		t.Fatal(err)
	}
	got, ok, err := store.Get(ctx, first.SessionID, first.ID)
	if err != nil || !ok {
		t.Fatalf("load message: ok=%v err=%v", ok, err)
	}
	if got.MediaURL != first.MediaURL || got.FileName != first.FileName || got.FileSize != first.FileSize {
		t.Fatalf("media metadata was clobbered: %+v", got)
	}

	second := MessageRow{
		ID: "message-2", SessionID: "session-a", ChatJID: first.ChatJID,
		SenderJID: first.SenderJID, Ts: 2000, Kind: "text", Body: "newest",
	}
	if err := store.Insert(ctx, second); err != nil {
		t.Fatal(err)
	}
	rows, err := store.ListMessages(ctx, "session-a", first.ChatJID, 50, 0)
	if err != nil {
		t.Fatal(err)
	}
	if len(rows) != 2 || rows[0].ID != "message-1" || rows[1].ID != "message-2" {
		t.Fatalf("messages must be returned oldest-first: %+v", rows)
	}

	other := first
	other.SessionID = "session-b"
	other.Body = "same WhatsApp id, different local session"
	if err := store.Insert(ctx, other); err != nil {
		t.Fatal(err)
	}
	if _, ok, err := store.Get(ctx, "session-b", first.ID); err != nil || !ok {
		t.Fatalf("composite session/message key changed: ok=%v err=%v", ok, err)
	}
}

func TestPhase0SessionStoreCharacterizationOwnershipAndIntegrationToken(t *testing.T) {
	ctx := context.Background()
	store, err := newSessionStore(ctx, newPhase0DB(t))
	if err != nil {
		t.Fatal(err)
	}

	if err := store.insertWithOwner(ctx, "session-owned", "Central", "owner-1"); err != nil {
		t.Fatal(err)
	}
	if err := store.insert(ctx, "session-unowned", "Legacy"); err != nil {
		t.Fatal(err)
	}
	rows, err := store.list(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if len(rows) != 2 || rows[0].OwnerID != "owner-1" || rows[1].OwnerID != "" {
		t.Fatalf("legacy owner contract changed: %+v", rows)
	}
	if rows[0].IntegrationToken == "" || rows[1].IntegrationToken == "" {
		t.Fatal("every legacy connection is expected to receive an integration token")
	}
	old := rows[0].IntegrationToken
	rotated, err := store.regenerateToken(ctx, "session-owned")
	if err != nil || rotated == "" || rotated == old {
		t.Fatalf("integration token rotation failed: old=%q new=%q err=%v", old, rotated, err)
	}
}

func TestPhase0HTTPCharacterizationCORSAndSSEContracts(t *testing.T) {
	t.Setenv("WACALLS_ALLOWED_ORIGINS", "")
	base := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusNoContent) })
	req := httptest.NewRequest(http.MethodGet, "http://wacalls.local/api/test", nil)
	req.Header.Set("Origin", "https://evil.example")
	res := httptest.NewRecorder()
	withCORS(base).ServeHTTP(res, req)
	if got := res.Header().Get("Access-Control-Allow-Origin"); got != "" {
		t.Fatalf("default CORS must remain same-origin, got %q", got)
	}

	t.Setenv("WACALLS_ALLOWED_ORIGINS", "https://app.example")
	req = httptest.NewRequest(http.MethodGet, "http://wacalls.local/api/test", nil)
	req.Header.Set("Origin", "https://app.example")
	res = httptest.NewRecorder()
	withCORS(base).ServeHTTP(res, req)
	if got := res.Header().Get("Access-Control-Allow-Origin"); got != "https://app.example" {
		t.Fatalf("configured origin was not echoed, got %q", got)
	}
	if got := res.Header().Get("Access-Control-Allow-Credentials"); got != "true" {
		t.Fatalf("credentialed CORS contract changed, got %q", got)
	}

	// The current SSE implementation explicitly emits a wildcard header even
	// though the normal API uses an allowlist. This test intentionally records
	// that legacy behavior so the migration can remove it deliberately.
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	req = httptest.NewRequest(http.MethodGet, "http://wacalls.local/api/events", nil).WithContext(ctx)
	res = httptest.NewRecorder()
	NewBroker().serveSSE(res, req, "client", "user", "tenant", false)
	if got := res.Header().Get("Access-Control-Allow-Origin"); got != "*" {
		t.Fatalf("legacy SSE wildcard contract changed unexpectedly, got %q", got)
	}
}

func TestPhase0TokenExpiryCharacterization(t *testing.T) {
	ctx := context.Background()
	store, err := newAuthStore(ctx, newPhase0DB(t))
	if err != nil {
		t.Fatal(err)
	}
	user, err := store.Signup(ctx, SignupInput{Email: "owner@example.test", Password: "correct-horse-battery-staple"})
	if err != nil {
		t.Fatal(err)
	}
	token, err := store.IssueToken(ctx, user.ID)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := store.db.ExecContext(ctx, `UPDATE auth_tokens SET expires_at = ? WHERE token = ?`, time.Now().Add(-time.Minute).Unix(), token); err != nil {
		t.Fatal(err)
	}
	if _, err := store.UserByToken(ctx, token); !errors.Is(err, ErrUserNotFound) {
		t.Fatalf("expired token must be rejected, got %v", err)
	}
}
