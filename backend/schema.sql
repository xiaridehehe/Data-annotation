-- MySQL 8.0.16+; select database before running.

CREATE TABLE IF NOT EXISTS workspaces (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	public_id VARCHAR(36) NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), 
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), 
	PRIMARY KEY (id), 
	UNIQUE (public_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS change_logs (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	workspace_id BIGINT NOT NULL, 
	actor VARCHAR(128) NOT NULL, 
	entity_type VARCHAR(32) NOT NULL, 
	entity_key VARCHAR(512) NOT NULL, 
	action VARCHAR(32) NOT NULL, 
	before_value JSON, 
	after_value JSON, 
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), 
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), 
	PRIMARY KEY (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE RESTRICT,
	INDEX ix_change_log_entity (workspace_id, entity_type, entity_key),
	INDEX ix_change_logs_workspace_id (workspace_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS diseases (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	workspace_id BIGINT NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	box_policy VARCHAR(16) NOT NULL, 
	overall_schema JSON NOT NULL, 
	lesion_schema JSON NOT NULL, 
	target_keys JSON NOT NULL, 
	active BOOL NOT NULL, 
	version INTEGER NOT NULL DEFAULT '1', 
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), 
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), 
	PRIMARY KEY (id), 
	UNIQUE (workspace_id, code), 
	CONSTRAINT ck_box_policy CHECK (box_policy IN ('NONE','OPTIONAL','REQUIRED')), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE RESTRICT,
	INDEX ix_diseases_workspace_id (workspace_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS patients (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	workspace_id BIGINT NOT NULL, 
	client_id VARCHAR(128) NOT NULL, 
	patient_code VARCHAR(128), 
	issuer VARCHAR(128), 
	version INTEGER NOT NULL DEFAULT '1', 
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), 
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), 
	PRIMARY KEY (id), 
	UNIQUE (workspace_id, client_id), 
	UNIQUE (id, workspace_id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE RESTRICT,
	INDEX ix_patient_identity (workspace_id, patient_code, issuer),
	INDEX ix_patients_workspace_id (workspace_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS studies (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	workspace_id BIGINT NOT NULL, 
	patient_id BIGINT NOT NULL, 
	study_uid VARCHAR(64) NOT NULL, 
	accession_number VARCHAR(128), 
	description VARCHAR(512) NOT NULL, 
	study_date DATE, 
	study_time TIME(6), 
	deleted_at DATETIME(6), 
	version INTEGER NOT NULL DEFAULT '1', 
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), 
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), 
	PRIMARY KEY (id), 
	FOREIGN KEY(patient_id, workspace_id) REFERENCES patients (id, workspace_id), 
	UNIQUE (workspace_id, study_uid), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE RESTRICT,
	INDEX ix_studies_patient_id (patient_id),
	INDEX ix_studies_workspace_id (workspace_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS series (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	study_id BIGINT NOT NULL, 
	series_uid VARCHAR(64) NOT NULL, 
	series_number INTEGER, 
	description VARCHAR(512) NOT NULL, 
	modality VARCHAR(16) NOT NULL, 
	plane VARCHAR(16) NOT NULL, 
	deleted_at DATETIME(6), 
	version INTEGER NOT NULL DEFAULT '1', 
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), 
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), 
	PRIMARY KEY (id), 
	UNIQUE (study_id, series_uid), 
	FOREIGN KEY(study_id) REFERENCES studies (id) ON DELETE RESTRICT,
	INDEX ix_series_study_id (study_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS assessments (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	series_id BIGINT NOT NULL, 
	disease_id BIGINT NOT NULL, 
	target_key VARCHAR(64) NOT NULL, 
	attributes JSON NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	deleted_at DATETIME(6), 
	version INTEGER NOT NULL DEFAULT '1', 
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), 
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), 
	PRIMARY KEY (id), 
	UNIQUE (series_id, disease_id, target_key), 
	CONSTRAINT ck_assessment_status CHECK (status IN ('DRAFT','COMPLETE')), 
	FOREIGN KEY(series_id) REFERENCES series (id) ON DELETE RESTRICT, 
	FOREIGN KEY(disease_id) REFERENCES diseases (id) ON DELETE RESTRICT,
	INDEX ix_assessments_disease_id (disease_id),
	INDEX ix_assessments_series_id (series_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS images (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	series_id BIGINT NOT NULL, 
	sop_instance_uid VARCHAR(64) NOT NULL, 
	instance_number INTEGER, 
	width INTEGER NOT NULL, 
	height INTEGER NOT NULL, 
	sort_order DOUBLE NOT NULL, 
	position_x DOUBLE, 
	position_y DOUBLE, 
	position_z DOUBLE, 
	row_cosine_x DOUBLE, 
	row_cosine_y DOUBLE, 
	row_cosine_z DOUBLE, 
	column_cosine_x DOUBLE, 
	column_cosine_y DOUBLE, 
	column_cosine_z DOUBLE, 
	pixel_spacing_row DOUBLE, 
	pixel_spacing_column DOUBLE, 
	version INTEGER NOT NULL DEFAULT '1', 
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), 
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), 
	PRIMARY KEY (id), 
	UNIQUE (series_id, sop_instance_uid), 
	UNIQUE (id, series_id), 
	CONSTRAINT ck_image_size CHECK (width > 0 AND height > 0), 
	FOREIGN KEY(series_id) REFERENCES series (id) ON DELETE RESTRICT,
	INDEX ix_image_order (series_id, sort_order, id),
	INDEX ix_images_series_id (series_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS lesions (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	series_id BIGINT NOT NULL, 
	disease_id BIGINT NOT NULL, 
	public_id VARCHAR(36) NOT NULL, 
	target_key VARCHAR(64) NOT NULL, 
	attributes JSON NOT NULL, 
	color VARCHAR(7) NOT NULL, 
	deleted_at DATETIME(6), 
	version INTEGER NOT NULL DEFAULT '1', 
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), 
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), 
	PRIMARY KEY (id), 
	UNIQUE (series_id, public_id), 
	UNIQUE (id, series_id), 
	FOREIGN KEY(series_id) REFERENCES series (id) ON DELETE RESTRICT, 
	FOREIGN KEY(disease_id) REFERENCES diseases (id) ON DELETE RESTRICT,
	INDEX ix_lesions_disease_id (disease_id),
	INDEX ix_lesions_series_id (series_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS boxes (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	series_id BIGINT NOT NULL, 
	lesion_id BIGINT NOT NULL, 
	image_id BIGINT NOT NULL, 
	public_id VARCHAR(36) NOT NULL, 
	x_min DOUBLE NOT NULL, 
	y_min DOUBLE NOT NULL, 
	x_max DOUBLE NOT NULL, 
	y_max DOUBLE NOT NULL, 
	source_box_id BIGINT, 
	deleted_at DATETIME(6), 
	version INTEGER NOT NULL DEFAULT '1', 
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), 
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), 
	PRIMARY KEY (id), 
	UNIQUE (lesion_id, image_id), 
	UNIQUE (series_id, public_id), 
	FOREIGN KEY(lesion_id, series_id) REFERENCES lesions (id, series_id), 
	FOREIGN KEY(image_id, series_id) REFERENCES images (id, series_id), 
	CONSTRAINT ck_box_coordinates CHECK (x_min >= 0 AND y_min >= 0 AND x_max > x_min AND y_max > y_min), 
	FOREIGN KEY(source_box_id) REFERENCES boxes (id) ON DELETE SET NULL,
	INDEX ix_boxes_image_id (image_id),
	INDEX ix_boxes_lesion_id (lesion_id),
	INDEX ix_boxes_series_id (series_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

