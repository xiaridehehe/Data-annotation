-- MySQL 8.0.16+; select database before running.

CREATE TABLE IF NOT EXISTS users (
	id BIGINT NOT NULL AUTO_INCREMENT,
	username VARCHAR(64) NOT NULL,
	display_name VARCHAR(128) NOT NULL,
	password_hash VARCHAR(256) NOT NULL,
	role VARCHAR(16) NOT NULL DEFAULT 'ANNOTATOR',
	active BOOL NOT NULL,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	PRIMARY KEY (id),
	UNIQUE (username),
	CONSTRAINT ck_user_role CHECK (role IN ('ANNOTATOR','REVIEWER','ADMIN'))
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

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
	actor_user_id BIGINT,
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
	FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE RESTRICT,
	INDEX ix_change_log_entity (workspace_id, entity_type, entity_key),
	INDEX ix_change_logs_actor_user_id (actor_user_id),
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

CREATE TABLE IF NOT EXISTS user_sessions (
	id BIGINT NOT NULL AUTO_INCREMENT,
	user_id BIGINT NOT NULL,
	token_hash VARCHAR(64) NOT NULL,
	expires_at DATETIME(6) NOT NULL,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	PRIMARY KEY (id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT,
	UNIQUE (token_hash),
	INDEX ix_user_sessions_user_id (user_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS studies (
	id BIGINT NOT NULL AUTO_INCREMENT,
	workspace_id BIGINT NOT NULL,
	patient_id BIGINT NOT NULL,
	study_uid VARCHAR(64) NOT NULL,
	accession_number VARCHAR(128),
	description VARCHAR(512) NOT NULL,
	source_patient_folder VARCHAR(512),
	source_study_folder VARCHAR(512),
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

CREATE TABLE IF NOT EXISTS submissions (
	id BIGINT NOT NULL AUTO_INCREMENT,
	workspace_id BIGINT NOT NULL,
	study_id BIGINT NOT NULL,
	submitter_user_id BIGINT NOT NULL,
	reviewer_user_id BIGINT,
	status VARCHAR(16) NOT NULL,
	rejection_reason VARCHAR(1000),
	submitted_at DATETIME NOT NULL,
	reviewed_at DATETIME,
	revision INTEGER NOT NULL DEFAULT 1,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	PRIMARY KEY (id),
	UNIQUE (workspace_id, study_id),
	CONSTRAINT ck_submission_status CHECK (status IN ('SUBMITTED','APPROVED','REJECTED')),
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE RESTRICT,
	FOREIGN KEY(study_id) REFERENCES studies (id) ON DELETE RESTRICT,
	FOREIGN KEY(submitter_user_id) REFERENCES users (id) ON DELETE RESTRICT,
	FOREIGN KEY(reviewer_user_id) REFERENCES users (id) ON DELETE RESTRICT,
	INDEX ix_submissions_workspace_id (workspace_id),
	INDEX ix_submissions_study_id (study_id),
	INDEX ix_submissions_submitter_user_id (submitter_user_id),
	INDEX ix_submissions_reviewer_user_id (reviewer_user_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE IF NOT EXISTS submission_review_history (
	id BIGINT NOT NULL AUTO_INCREMENT,
	submission_id BIGINT NOT NULL,
	actor_user_id BIGINT NOT NULL,
	action VARCHAR(16) NOT NULL,
	status VARCHAR(16) NOT NULL,
	revision INTEGER NOT NULL,
	reason VARCHAR(1000),
	snapshot JSON,
	created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
	PRIMARY KEY (id),
	CONSTRAINT ck_review_history_action CHECK (action IN ('SUBMIT','RESUBMIT','APPROVE','REJECT')),
	CONSTRAINT ck_review_history_status CHECK (status IN ('SUBMITTED','APPROVED','REJECTED')),
	FOREIGN KEY(submission_id) REFERENCES submissions (id) ON DELETE RESTRICT,
	FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE RESTRICT,
	INDEX ix_submission_review_history_submission_id (submission_id),
	INDEX ix_submission_review_history_actor_user_id (actor_user_id),
	INDEX ix_review_history_submission_created (submission_id, created_at)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

