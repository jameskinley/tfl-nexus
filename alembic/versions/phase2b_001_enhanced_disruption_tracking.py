"""Phase 2B: Enhanced disruption tracking with adaptive learning

Revision ID: phase2b_001
Revises: 
Create Date: 2026-02-03 14:00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision: str = 'phase2b_001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('TRUNCATE TABLE live_disruptions CASCADE')
    
    op.add_column('live_disruptions', sa.Column('category_description', sa.Text(), nullable=True))
    op.add_column('live_disruptions', sa.Column('disruption_type', sa.String(100), nullable=True))
    op.add_column('live_disruptions', sa.Column('summary', sa.Text(), nullable=True))
    op.add_column('live_disruptions', sa.Column('additional_info', sa.Text(), nullable=True))
    op.add_column('live_disruptions', sa.Column('closure_text', sa.Text(), nullable=True))
    
    op.add_column('live_disruptions', sa.Column('severity_level', sa.Integer(), nullable=True))
    op.add_column('live_disruptions', sa.Column('severity_description', sa.Text(), nullable=True))
    op.alter_column('live_disruptions', 'severity', nullable=True)
    
    op.add_column('live_disruptions', sa.Column('is_full_suspension', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('live_disruptions', sa.Column('is_partial_suspension', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('live_disruptions', sa.Column('affected_section_start_naptan', sa.String(100), nullable=True))
    op.add_column('live_disruptions', sa.Column('affected_section_end_naptan', sa.String(100), nullable=True))
    
    op.add_column('live_disruptions', sa.Column('affected_stops_json', JSON(), nullable=True))
    op.add_column('live_disruptions', sa.Column('affected_routes_json', JSON(), nullable=True))
    op.drop_column('live_disruptions', 'affected_stops')
    
    op.add_column('live_disruptions', sa.Column('created', sa.DateTime(), nullable=True))
    op.add_column('live_disruptions', sa.Column('last_update', sa.DateTime(), nullable=True))
    op.add_column('live_disruptions', sa.Column('valid_from', sa.DateTime(), nullable=True))
    op.add_column('live_disruptions', sa.Column('valid_to', sa.DateTime(), nullable=True))
    
    op.alter_column('live_disruptions', 'created_at', server_default=sa.func.now())
    op.alter_column('live_disruptions', 'updated_at', server_default=sa.func.now(), onupdate=sa.func.now())
    op.alter_column('live_disruptions', 'category', nullable=False)
    
    op.create_index('idx_suspension_flags', 'live_disruptions', ['is_full_suspension', 'is_partial_suspension'])
    op.create_index('idx_category_type', 'live_disruptions', ['category', 'disruption_type'])
    op.create_index('idx_last_update', 'live_disruptions', ['last_update'])
    op.create_index('idx_valid_from', 'live_disruptions', ['valid_from'])
    op.create_index('idx_actual_end_time', 'live_disruptions', ['actual_end_time'])
    
    op.create_table(
        'severity_levels',
        sa.Column('severity_id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('mode_name', sa.String(50), nullable=False),
        sa.Column('severity_level', sa.Integer(), nullable=False),
        sa.Column('description', sa.String(255), nullable=False),
        sa.Column('estimated_delay_minutes', sa.Float(), nullable=True),
        sa.Column('is_suspension', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('sample_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('confidence_score', sa.Float(), server_default='0.3', nullable=False),
        sa.Column('last_updated', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('mode_name', 'severity_level', name='uq_mode_severity')
    )
    
    op.create_index('idx_severity_mode_level', 'severity_levels', ['mode_name', 'severity_level'])
    
    op.create_table(
        'disruption_categories',
        sa.Column('category_id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('category_name', sa.String(100), unique=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False)
    )
    
    op.create_index('idx_category_name', 'disruption_categories', ['category_name'])
    
    op.create_table(
        'realtime_delay_samples',
        sa.Column('sample_id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('service_id', sa.Integer(), sa.ForeignKey('services.service_id'), nullable=False),
        sa.Column('stop_id', sa.Integer(), sa.ForeignKey('stops.stop_id'), nullable=False),
        sa.Column('severity_at_time', sa.String(50), nullable=False),
        sa.Column('disruption_id', sa.Integer(), sa.ForeignKey('live_disruptions.disruption_id'), nullable=True),
        sa.Column('vehicle_id', sa.String(50), nullable=True),
        sa.Column('expected_arrival', sa.DateTime(), nullable=False),
        sa.Column('measured_delay_seconds', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('platform_name', sa.String(100), nullable=True),
        sa.Column('direction', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False)
    )
    
    op.create_index('idx_sample_service_id', 'realtime_delay_samples', ['service_id'])
    op.create_index('idx_sample_stop_id', 'realtime_delay_samples', ['stop_id'])
    op.create_index('idx_sample_disruption_id', 'realtime_delay_samples', ['disruption_id'])
    op.create_index('idx_sample_timestamp', 'realtime_delay_samples', ['timestamp'])
    op.create_index('idx_sample_service_time', 'realtime_delay_samples', ['service_id', 'timestamp'])
    op.create_index('idx_sample_severity', 'realtime_delay_samples', ['severity_at_time', 'timestamp'])


def downgrade() -> None:
    op.drop_table('realtime_delay_samples')
    op.drop_table('disruption_categories')
    op.drop_table('severity_levels')
    
    op.drop_index('idx_actual_end_time', 'live_disruptions')
    op.drop_index('idx_valid_from', 'live_disruptions')
    op.drop_index('idx_last_update', 'live_disruptions')
    op.drop_index('idx_category_type', 'live_disruptions')
    op.drop_index('idx_suspension_flags', 'live_disruptions')
    
    op.add_column('live_disruptions', sa.Column('affected_stops', sa.Text(), nullable=True))
    op.drop_column('live_disruptions', 'affected_routes_json')
    op.drop_column('live_disruptions', 'affected_stops_json')
    
    op.drop_column('live_disruptions', 'valid_to')
    op.drop_column('live_disruptions', 'valid_from')
    op.drop_column('live_disruptions', 'last_update')
    op.drop_column('live_disruptions', 'created')
    
    op.drop_column('live_disruptions', 'affected_section_end_naptan')
    op.drop_column('live_disruptions', 'affected_section_start_naptan')
    op.drop_column('live_disruptions', 'is_partial_suspension')
    op.drop_column('live_disruptions', 'is_full_suspension')
    
    op.alter_column('live_disruptions', 'severity', nullable=False)
    op.drop_column('live_disruptions', 'severity_description')
    op.drop_column('live_disruptions', 'severity_level')
    
    op.drop_column('live_disruptions', 'closure_text')
    op.drop_column('live_disruptions', 'additional_info')
    op.drop_column('live_disruptions', 'summary')
    op.drop_column('live_disruptions', 'disruption_type')
    op.drop_column('live_disruptions', 'category_description')
