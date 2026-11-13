"""Nine relational tables used by the browser annotation application."""
from sqlalchemy.dialects.mysql import DATETIME, TIME
from sqlalchemy import (MetaData, Table, Column, BigInteger, Integer, String, Double,
    DateTime, Date, Time, Boolean, JSON, ForeignKey, ForeignKeyConstraint,
    UniqueConstraint, CheckConstraint, Index)

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement

class CurrentTime(FunctionElement):
    type = DateTime()
    inherit_cache = True

@compiles(CurrentTime)
def default_now(element, compiler, **kw):
    return 'CURRENT_TIMESTAMP'

@compiles(CurrentTime, 'mysql')
def mysql_now(element, compiler, **kw):
    return 'CURRENT_TIMESTAMP(6)'

metadata = MetaData()
ID = BigInteger().with_variant(Integer, 'sqlite')
OPTIONS = dict(mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_bin')

def table(name, *columns):
    return Table(name, metadata,
        Column('id', ID, primary_key=True, autoincrement=True),
        *columns,
        Column('created_at', DateTime().with_variant(DATETIME(fsp=6), 'mysql'), nullable=False, server_default=CurrentTime()),
        Column('updated_at', DateTime().with_variant(DATETIME(fsp=6), 'mysql'), nullable=False, server_default=CurrentTime()),
        **OPTIONS)

def ref(name, target):
    return Column(name, ID, ForeignKey(target, ondelete='RESTRICT'), nullable=False, index=True)

def version():
    return Column('version', Integer, nullable=False, default=1, server_default='1')

def deleted():
    return Column('deleted_at', DateTime().with_variant(DATETIME(fsp=6), 'mysql'), nullable=True)

workspaces = table('workspaces', Column('public_id', String(36), nullable=False, unique=True),
    Column('name', String(128), nullable=False, default='标注空间'))
patients = table('patients', ref('workspace_id', 'workspaces.id'),
    Column('client_id', String(128), nullable=False),
    Column('patient_code', String(128)), Column('issuer', String(128)), version(),
    UniqueConstraint('workspace_id', 'client_id'), UniqueConstraint('id', 'workspace_id'),
    Index('ix_patient_identity', 'workspace_id', 'patient_code', 'issuer'))
studies = table('studies', ref('workspace_id', 'workspaces.id'), Column('patient_id', ID, nullable=False, index=True),
    Column('study_uid', String(64), nullable=False), Column('accession_number', String(128)),
    Column('description', String(512), nullable=False, default=''), Column('study_date', Date),
    Column('study_time', Time().with_variant(TIME(fsp=6), 'mysql')), deleted(), version(),
    ForeignKeyConstraint(['patient_id','workspace_id'], ['patients.id','patients.workspace_id']),
    UniqueConstraint('workspace_id','study_uid'))
series = table('series', ref('study_id','studies.id'), Column('series_uid', String(64), nullable=False),
    Column('series_number', Integer), Column('description', String(512), nullable=False, default=''),
    Column('modality', String(16), nullable=False, default='MR'),
    Column('plane', String(16), nullable=False, default='UNKNOWN'), deleted(), version(),
    UniqueConstraint('study_id','series_uid'))
images = table('images', ref('series_id','series.id'), Column('sop_instance_uid', String(64), nullable=False),
    Column('instance_number', Integer), Column('width', Integer, nullable=False), Column('height', Integer, nullable=False),
    Column('sort_order', Double, nullable=False, default=0),
    *[Column(n, Double) for n in ('position_x','position_y','position_z','row_cosine_x','row_cosine_y','row_cosine_z',
       'column_cosine_x','column_cosine_y','column_cosine_z','pixel_spacing_row','pixel_spacing_column')],
    version(), UniqueConstraint('series_id','sop_instance_uid'), UniqueConstraint('id','series_id'),
    CheckConstraint('width > 0 AND height > 0', name='ck_image_size'),
    Index('ix_image_order','series_id','sort_order','id'))
diseases = table('diseases', ref('workspace_id','workspaces.id'), Column('code', String(64), nullable=False),
    Column('name', String(128), nullable=False), Column('box_policy', String(16), nullable=False),
    Column('overall_schema', JSON, nullable=False), Column('lesion_schema', JSON, nullable=False),
    Column('target_keys', JSON, nullable=False), Column('active', Boolean, nullable=False, default=True), version(),
    UniqueConstraint('workspace_id','code'),
    CheckConstraint("box_policy IN ('NONE','OPTIONAL','REQUIRED')", name='ck_box_policy'))
assessments = table('assessments', ref('series_id','series.id'), ref('disease_id','diseases.id'),
    Column('target_key', String(64), nullable=False, default='OVERALL'), Column('attributes', JSON, nullable=False),
    Column('status', String(16), nullable=False, default='DRAFT'), deleted(), version(),
    UniqueConstraint('series_id','disease_id','target_key'),
    CheckConstraint("status IN ('DRAFT','COMPLETE')", name='ck_assessment_status'))
lesions = table('lesions', ref('series_id','series.id'), ref('disease_id','diseases.id'),
    Column('public_id', String(36), nullable=False), Column('target_key', String(64), nullable=False),
    Column('attributes', JSON, nullable=False), Column('color', String(7), nullable=False), deleted(), version(),
    UniqueConstraint('series_id','public_id'), UniqueConstraint('id','series_id'))
boxes = table('boxes', Column('series_id', ID, nullable=False, index=True),
    Column('lesion_id', ID, nullable=False, index=True), Column('image_id', ID, nullable=False, index=True),
    Column('public_id', String(36), nullable=False),
    *[Column(n, Double, nullable=False) for n in ('x_min','y_min','x_max','y_max')],
    Column('source_box_id', ID, ForeignKey('boxes.id', ondelete='SET NULL')),
    deleted(), version(), UniqueConstraint('lesion_id','image_id'), UniqueConstraint('series_id','public_id'),
    ForeignKeyConstraint(['lesion_id','series_id'], ['lesions.id','lesions.series_id']),
    ForeignKeyConstraint(['image_id','series_id'], ['images.id','images.series_id']),
    CheckConstraint('x_min >= 0 AND y_min >= 0 AND x_max > x_min AND y_max > y_min', name='ck_box_coordinates'))
TABLES = dict(patients=patients, studies=studies, series=series, instances=images,
              diseases=diseases, assessments=assessments, lesions=lesions, boxes=boxes)

# Append-only audit trail; current tables remain the latest state.
change_logs = table('change_logs', ref('workspace_id','workspaces.id'),
    Column('actor',String(128),nullable=False), Column('entity_type',String(32),nullable=False),
    Column('entity_key',String(512),nullable=False), Column('action',String(32),nullable=False),
    Column('before_value',JSON), Column('after_value',JSON),
    Index('ix_change_log_entity','workspace_id','entity_type','entity_key'))
