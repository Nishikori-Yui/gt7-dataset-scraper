package main

import (
	"database/sql"
	"flag"
	"fmt"
)

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
