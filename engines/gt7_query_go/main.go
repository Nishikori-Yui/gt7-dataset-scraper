package main

import (
	"database/sql"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"sort"
	"strconv"
	"strings"

	_ "modernc.org/sqlite"
)

type idName struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

type labelCount struct {
	Label string `json:"label"`
	Count int64  `json:"count"`
}

type overviewPayload struct {
	Cars          int64    `json:"cars"`
	Manufacturers int64    `json:"manufacturers"`
	Specs         int64    `json:"specs"`
	Images        int64    `json:"images"`
	Locales       []string `json:"locales"`
}

type manufacturerPayload struct {
	ID   *string `json:"id"`
	Name *string `json:"name"`
}

type countryPayload struct {
	CountryID *string `json:"country_id"`
	ISO3      *string `json:"iso3"`
	Name      *string `json:"name"`
}

type codeLabelPayload struct {
	Code  *string `json:"code"`
	Label *string `json:"label"`
}

type specPayload struct {
	SpecKey   *string `json:"spec_key"`
	SpecLabel *string `json:"spec_label"`
	SpecValue *string `json:"spec_value"`
	SpecUnit  *string `json:"spec_unit"`
	SpecRaw   *string `json:"spec_raw"`
	SortOrder *int64  `json:"sort_order"`
}

type imagePayload struct {
	ImageType *string `json:"image_type"`
	ImagePath *string `json:"image_path"`
	SortOrder *int64  `json:"sort_order"`
}

type carPayload struct {
	ID           string               `json:"id"`
	Name         string               `json:"name"`
	Manufacturer manufacturerPayload  `json:"manufacturer"`
	Country      countryPayload       `json:"country"`
	Drivetrain   codeLabelPayload     `json:"drivetrain"`
	Aspiration   codeLabelPayload     `json:"aspiration"`
	Intro        *string              `json:"intro"`
	Detail       *string              `json:"detail"`
	Specs        []specPayload        `json:"specs"`
	Images       []imagePayload       `json:"images"`
}

func fail(err error) {
	fmt.Fprintln(os.Stderr, err)
	os.Exit(1)
}

func parseNumber(v sql.NullString) *float64 {
	if !v.Valid {
		return nil
	}
	text := strings.TrimSpace(v.String)
	if text == "" {
		return nil
	}
	text = strings.ReplaceAll(text, "\u00a0", "")
	text = strings.ReplaceAll(text, " ", "")
	if strings.Contains(text, ",") && strings.Contains(text, ".") && strings.LastIndex(text, ",") > strings.LastIndex(text, ".") {
		text = strings.ReplaceAll(text, ".", "")
		text = strings.ReplaceAll(text, ",", ".")
	} else {
		text = strings.ReplaceAll(text, ",", "")
	}
	var b strings.Builder
	for _, ch := range text {
		if (ch >= '0' && ch <= '9') || ch == '.' || ch == '-' {
			b.WriteRune(ch)
		}
	}
	numText := b.String()
	if numText == "" || numText == "-" {
		return nil
	}
	n, err := strconv.ParseFloat(numText, 64)
	if err != nil {
		return nil
	}
	return &n
}

func writeJSON(v any) {
	enc := json.NewEncoder(os.Stdout)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(v); err != nil {
		fail(err)
	}
}

func ptrString(v sql.NullString) *string {
	if !v.Valid {
		return nil
	}
	value := v.String
	return &value
}

func ptrInt64(v sql.NullInt64) *int64 {
	if !v.Valid {
		return nil
	}
	value := v.Int64
	return &value
}

func cmdList(args []string) {
	fs := flag.NewFlagSet("list", flag.ExitOnError)
	dbPath := fs.String("db", "./output/gt7.db", "db path")
	locale := fs.String("locale", "gb", "locale")
	sortBy := fs.String("sort", "manufacturer", "sort")
	limit := fs.Int("limit", 0, "limit")
	_ = fs.Parse(args)

	db, err := sql.Open("sqlite", *dbPath)
	if err != nil {
		fail(err)
	}
	defer db.Close()

	var query string
	switch *sortBy {
	case "manufacturer":
		query = `SELECT c.id, COALESCE(ct.name,c.name) AS name
		         FROM cars c
		         LEFT JOIN car_texts ct ON ct.car_id=c.id AND ct.locale=?
		         LEFT JOIN manufacturers m ON m.id=c.manufacturer_id
		         LEFT JOIN manufacturer_i18n mi ON mi.id=m.id AND mi.locale=?
		         ORDER BY COALESCE(mi.name,m.name) COLLATE NOCASE, name COLLATE NOCASE`
	case "country":
		query = `SELECT c.id, COALESCE(ct.name,c.name) AS name
		         FROM cars c
		         LEFT JOIN car_texts ct ON ct.car_id=c.id AND ct.locale=?
		         LEFT JOIN manufacturers m ON m.id=c.manufacturer_id
		         LEFT JOIN country_iso_map cim ON cim.country_id=m.country_id
		         LEFT JOIN country_i18n ci ON ci.iso3=cim.iso3 AND ci.locale=?
		         LEFT JOIN country_i18n cigb ON cigb.iso3=cim.iso3 AND cigb.locale='gb'
		         ORDER BY COALESCE(ci.name,cigb.name,cim.iso3,m.country_id) COLLATE NOCASE, name COLLATE NOCASE`
	case "drivetrain":
		query = `SELECT c.id, COALESCE(ct.name,c.name) AS name
		         FROM cars c
		         LEFT JOIN car_texts ct ON ct.car_id=c.id AND ct.locale=?
		         LEFT JOIN drivetrain_i18n di ON di.code=c.drivetrain_code AND di.locale=?
		         ORDER BY COALESCE(di.label,c.drivetrain_code) COLLATE NOCASE, name COLLATE NOCASE`
	case "max_power", "weight":
		specKey := *sortBy
		rows, err := db.Query(`SELECT c.id, COALESCE(ct.name,c.name) AS name, s.spec_value
			FROM cars c
			LEFT JOIN car_texts ct ON ct.car_id=c.id AND ct.locale=?
			LEFT JOIN car_specs s ON s.car_id=c.id AND s.locale='gb' AND s.spec_key=?`, *locale, specKey)
		if err != nil {
			fail(err)
		}
		defer rows.Close()
		type row struct {
			ID    string `json:"id"`
			Name  string `json:"name"`
			Value *float64
		}
		var out []row
		for rows.Next() {
			var r row
			var spec sql.NullString
			if err := rows.Scan(&r.ID, &r.Name, &spec); err != nil {
				fail(err)
			}
			r.Value = parseNumber(spec)
			out = append(out, r)
		}
		if err := rows.Err(); err != nil {
			fail(err)
		}
		if *sortBy == "max_power" {
			// Match Python behavior: sorted(key=(is_none, value), reverse=True)
			// which effectively places nil values first, then descending numbers.
			sort.SliceStable(out, func(i, j int) bool {
				a, b := out[i].Value, out[j].Value
				aNil, bNil := a == nil, b == nil
				if aNil != bNil {
					return aNil && !bNil
				}
				if aNil && bNil {
					return false
				}
				return *a > *b
			})
		} else {
			// Match Python behavior: sorted(key=(is_none, value), reverse=False)
			// non-nil values ascending, nil values last.
			sort.SliceStable(out, func(i, j int) bool {
				a, b := out[i].Value, out[j].Value
				aNil, bNil := a == nil, b == nil
				if aNil != bNil {
					return !aNil && bNil
				}
				if aNil && bNil {
					return false
				}
				return *a < *b
			})
		}
		var payload []idName
		for _, r := range out {
			payload = append(payload, idName{ID: r.ID, Name: r.Name})
		}
		if *limit > 0 && *limit < len(payload) {
			payload = payload[:*limit]
		}
		writeJSON(payload)
		return
	default:
		fail(fmt.Errorf("unsupported sort: %s", *sortBy))
	}

	rows, err := db.Query(query, *locale, *locale)
	if err != nil {
		fail(err)
	}
	defer rows.Close()
	var payload []idName
	for rows.Next() {
		var id, name string
		if err := rows.Scan(&id, &name); err != nil {
			fail(err)
		}
		payload = append(payload, idName{ID: id, Name: name})
	}
	if err := rows.Err(); err != nil {
		fail(err)
	}
	if *limit > 0 && *limit < len(payload) {
		payload = payload[:*limit]
	}
	writeJSON(payload)
}

func cmdCar(args []string) {
	fs := flag.NewFlagSet("car", flag.ExitOnError)
	dbPath := fs.String("db", "./output/gt7.db", "db path")
	locale := fs.String("locale", "gb", "locale")
	carID := fs.String("car-id", "", "car id")
	_ = fs.Parse(args)
	if *carID == "" {
		fail(fmt.Errorf("--car-id is required"))
	}

	db, err := sql.Open("sqlite", *dbPath)
	if err != nil {
		fail(err)
	}
	defer db.Close()

	row := db.QueryRow(`SELECT c.id, COALESCE(ct.name,c.name), COALESCE(ct.intro,c.intro), COALESCE(ct.detail,c.detail),
		c.manufacturer_id, c.aspiration_code, c.drivetrain_code
		FROM cars c LEFT JOIN car_texts ct ON ct.car_id=c.id AND ct.locale=? WHERE c.id=?`, *locale, *carID)
	var id, name, intro, detail, manufacturerID, aspirationCode, drivetrainCode sql.NullString
	if err := row.Scan(&id, &name, &intro, &detail, &manufacturerID, &aspirationCode, &drivetrainCode); err != nil {
		fail(err)
	}

	var manufacturerName sql.NullString
	if manufacturerID.Valid {
		_ = db.QueryRow(
			`SELECT COALESCE(mi.name,m.name)
			 FROM manufacturers m
			 LEFT JOIN manufacturer_i18n mi ON mi.id=m.id AND mi.locale=?
			 WHERE m.id=?`,
			*locale,
			manufacturerID.String,
		).Scan(&manufacturerName)
	}

	var aspirationLabel sql.NullString
	if aspirationCode.Valid {
		_ = db.QueryRow(
			"SELECT label FROM aspiration_i18n WHERE code=? AND locale=?",
			aspirationCode.String,
			*locale,
		).Scan(&aspirationLabel)
	}
	if !aspirationLabel.Valid {
		aspirationLabel = aspirationCode
	}

	var drivetrainLabel sql.NullString
	if drivetrainCode.Valid {
		_ = db.QueryRow(
			"SELECT label FROM drivetrain_i18n WHERE code=? AND locale=?",
			drivetrainCode.String,
			*locale,
		).Scan(&drivetrainLabel)
	}
	if !drivetrainLabel.Valid {
		drivetrainLabel = drivetrainCode
	}

	var countryID, iso3, countryName sql.NullString
	if manufacturerID.Valid {
		_ = db.QueryRow(
			`SELECT m.country_id, cim.iso3, COALESCE(ci.name, cigb.name, cim.iso3, m.country_id)
			 FROM manufacturers m
			 LEFT JOIN country_iso_map cim ON cim.country_id=m.country_id
			 LEFT JOIN country_i18n ci ON ci.iso3=cim.iso3 AND ci.locale=?
			 LEFT JOIN country_i18n cigb ON cigb.iso3=cim.iso3 AND cigb.locale='gb'
			 WHERE m.id=?`,
			*locale,
			manufacturerID.String,
		).Scan(&countryID, &iso3, &countryName)
	}

	specRows, err := db.Query(
		`SELECT s.spec_key, i.label, s.spec_value, s.spec_unit, s.spec_raw, s.sort_order
		 FROM car_specs s
		 LEFT JOIN spec_code_i18n i ON i.code=s.spec_key AND i.locale=s.locale
		 WHERE s.car_id=? AND s.locale=?
		 ORDER BY s.sort_order`,
		*carID,
		*locale,
	)
	if err != nil {
		fail(err)
	}
	defer specRows.Close()
	specs := make([]specPayload, 0, 32)
	for specRows.Next() {
		var specKey, specLabel, specValue, specUnit, specRaw sql.NullString
		var sortOrder sql.NullInt64
		if err := specRows.Scan(&specKey, &specLabel, &specValue, &specUnit, &specRaw, &sortOrder); err != nil {
			fail(err)
		}
		specs = append(specs, specPayload{
			SpecKey:   ptrString(specKey),
			SpecLabel: ptrString(specLabel),
			SpecValue: ptrString(specValue),
			SpecUnit:  ptrString(specUnit),
			SpecRaw:   ptrString(specRaw),
			SortOrder: ptrInt64(sortOrder),
		})
	}
	if err := specRows.Err(); err != nil {
		fail(err)
	}

	images := make([]imagePayload, 0, 16)
	var imageTableExists int
	if err := db.QueryRow("SELECT 1 FROM sqlite_master WHERE type='table' AND name='car_images' LIMIT 1").Scan(&imageTableExists); err == nil {
		imageRows, err := db.Query(
			`SELECT image_type, image_path, sort_order
			 FROM car_images
			 WHERE car_id=?
			 ORDER BY image_type, sort_order`,
			*carID,
		)
		if err != nil {
			fail(err)
		}
		defer imageRows.Close()
		for imageRows.Next() {
			var imageType, imagePath sql.NullString
			var sortOrder sql.NullInt64
			if err := imageRows.Scan(&imageType, &imagePath, &sortOrder); err != nil {
				fail(err)
			}
			images = append(images, imagePayload{
				ImageType: ptrString(imageType),
				ImagePath: ptrString(imagePath),
				SortOrder: ptrInt64(sortOrder),
			})
		}
		if err := imageRows.Err(); err != nil {
			fail(err)
		}
	}

	payload := carPayload{
		ID:   id.String,
		Name: name.String,
		Manufacturer: manufacturerPayload{
			ID:   ptrString(manufacturerID),
			Name: ptrString(manufacturerName),
		},
		Country: countryPayload{
			CountryID: ptrString(countryID),
			ISO3:      ptrString(iso3),
			Name:      ptrString(countryName),
		},
		Drivetrain: codeLabelPayload{
			Code:  ptrString(drivetrainCode),
			Label: ptrString(drivetrainLabel),
		},
		Aspiration: codeLabelPayload{
			Code:  ptrString(aspirationCode),
			Label: ptrString(aspirationLabel),
		},
		Intro:  ptrString(intro),
		Detail: ptrString(detail),
		Specs:  specs,
		Images: images,
	}
	writeJSON(payload)
}

func cmdStats(args []string) {
	fs := flag.NewFlagSet("stats", flag.ExitOnError)
	dbPath := fs.String("db", "./output/gt7.db", "db path")
	locale := fs.String("locale", "gb", "locale")
	by := fs.String("by", "manufacturer", "by")
	_ = fs.Parse(args)

	db, err := sql.Open("sqlite", *dbPath)
	if err != nil {
		fail(err)
	}
	defer db.Close()

	var query string
	switch *by {
	case "manufacturer":
		query = `SELECT COALESCE(mi.name,m.name) AS label, COUNT(*) AS count
		         FROM cars c LEFT JOIN manufacturers m ON m.id=c.manufacturer_id
		         LEFT JOIN manufacturer_i18n mi ON mi.id=m.id AND mi.locale=?
		         GROUP BY m.id ORDER BY label COLLATE NOCASE`
	case "country":
		query = `SELECT COALESCE(ci.name,cigb.name,cim.iso3,m.country_id) AS label, COUNT(*) AS count
		         FROM cars c LEFT JOIN manufacturers m ON m.id=c.manufacturer_id
		         LEFT JOIN country_iso_map cim ON cim.country_id=m.country_id
		         LEFT JOIN country_i18n ci ON ci.iso3=cim.iso3 AND ci.locale=?
		         LEFT JOIN country_i18n cigb ON cigb.iso3=cim.iso3 AND cigb.locale='gb'
		         GROUP BY cim.iso3, m.country_id ORDER BY label COLLATE NOCASE`
	case "drivetrain":
		query = `SELECT COALESCE(di.label,c.drivetrain_code) AS label, COUNT(*) AS count
		         FROM cars c LEFT JOIN drivetrain_i18n di ON di.code=c.drivetrain_code AND di.locale=?
		         GROUP BY c.drivetrain_code ORDER BY label COLLATE NOCASE`
	default:
		fail(fmt.Errorf("unsupported stats by: %s", *by))
	}
	rows, err := db.Query(query, *locale)
	if err != nil {
		fail(err)
	}
	defer rows.Close()
	var out []labelCount
	for rows.Next() {
		var label sql.NullString
		var count int64
		if err := rows.Scan(&label, &count); err != nil {
			fail(err)
		}
		out = append(out, labelCount{Label: label.String, Count: count})
	}
	if err := rows.Err(); err != nil {
		fail(err)
	}
	writeJSON(out)
}

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

func main() {
	if len(os.Args) < 2 {
		fail(fmt.Errorf("usage: gt7-query-go <list|car|stats|overview> [args]"))
	}
	cmd := os.Args[1]
	args := os.Args[2:]
	switch cmd {
	case "list":
		cmdList(args)
	case "car":
		cmdCar(args)
	case "stats":
		cmdStats(args)
	case "overview":
		cmdOverview(args)
	default:
		fail(fmt.Errorf("unknown command: %s", cmd))
	}
}
