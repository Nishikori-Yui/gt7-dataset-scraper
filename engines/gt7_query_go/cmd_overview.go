package main

import (
	"database/sql"
	"flag"
)

func cmdOverview(args []string) {
	fs := flag.NewFlagSet("overview", flag.ExitOnError)
	dbPath := fs.String("db", "./output/gt7.db", "db path")
	_ = fs.Parse(args)

	db, err := sql.Open("sqlite", *dbPath)
	if err != nil {
		fail(err)
	}
	defer db.Close()
	var cars int64
	if err := db.QueryRow("SELECT COUNT(*) FROM cars").Scan(&cars); err != nil {
		fail(err)
	}
	var manufacturers int64
	if err := db.QueryRow("SELECT COUNT(*) FROM manufacturers").Scan(&manufacturers); err != nil {
		fail(err)
	}
	var specs int64
	if err := db.QueryRow("SELECT COUNT(*) FROM car_specs").Scan(&specs); err != nil {
		fail(err)
	}
	images := int64(0)
	var hasImages int64
	if err := db.QueryRow("SELECT 1 FROM sqlite_master WHERE type='table' AND name='car_images' LIMIT 1").Scan(&hasImages); err == nil {
		if err := db.QueryRow("SELECT COUNT(*) FROM car_images").Scan(&images); err != nil {
			fail(err)
		}
	}
	rows, err := db.Query("SELECT DISTINCT locale FROM car_texts ORDER BY locale")
	if err != nil {
		fail(err)
	}
	defer rows.Close()
	locales := make([]string, 0, 16)
	for rows.Next() {
		var locale string
		if err := rows.Scan(&locale); err != nil {
			fail(err)
		}
		locales = append(locales, locale)
	}
	if err := rows.Err(); err != nil {
		fail(err)
	}
	writeJSON(overviewPayload{
		Cars:          cars,
		Manufacturers: manufacturers,
		Specs:         specs,
		Images:        images,
		Locales:       locales,
	})
}
