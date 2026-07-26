package storage

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestPhase0StorageDefaultsToSingleWriterSQLiteWAL(t *testing.T) {
	db, driver, err := Open(Config{SQLitePath: filepath.Join(t.TempDir(), "wacalls.db")})
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	if driver != "sqlite3" {
		t.Fatalf("expected whatsmeow sqlite3 dialect, got %q", driver)
	}
	if got := db.Stats().MaxOpenConnections; got != 1 {
		t.Fatalf("expected single-writer pool, got %d", got)
	}
	var mode string
	if err := db.QueryRow(`PRAGMA journal_mode`).Scan(&mode); err != nil {
		t.Fatal(err)
	}
	if !strings.EqualFold(mode, "wal") {
		t.Fatalf("expected WAL mode, got %q", mode)
	}
}

func TestPhase0StorageRejectsMariaDBAndUnknownDrivers(t *testing.T) {
	for _, driver := range []string{"mysql", "mariadb", "oracle"} {
		db, dialect, err := Open(Config{Driver: driver, DSN: "must-not-be-used"})
		if db != nil {
			_ = db.Close()
			t.Fatalf("driver %q unexpectedly returned a database", driver)
		}
		if dialect != "" || err == nil {
			t.Fatalf("driver %q should be rejected: dialect=%q err=%v", driver, dialect, err)
		}
	}
}
