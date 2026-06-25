import os
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Lấy URL kết nối từ biến môi trường trong docker-compose
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:password123@db:5432/neuro_db")

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def run_migrations():
    """
    Hàm thực hiện quét và chạy các câu lệnh SQL migration để nâng cấp cơ sở dữ liệu.
    Bổ sung các cột còn thiếu trong bảng analysis_results nếu chúng chưa tồn tại.

    Input:
        Không có.
    Output:
        Không có.
    """
    # Định nghĩa các câu lệnh ALTER TABLE để thêm các cột còn thiếu
    migrations = [
        "ALTER TABLE analysis_results ADD COLUMN IF NOT EXISTS finer_cam_path VARCHAR;",
        "ALTER TABLE analysis_results ADD COLUMN IF NOT EXISTS seg_eigen_cam_path VARCHAR;",
        "ALTER TABLE analysis_results ADD COLUMN IF NOT EXISTS odam_path VARCHAR;",
        "ALTER TABLE analysis_results ADD COLUMN IF NOT EXISTS xai_3_panel_path VARCHAR;",
        "ALTER TABLE analysis_results ADD COLUMN IF NOT EXISTS survival_curve_data JSON;",
        "ALTER TABLE analysis_results ADD COLUMN IF NOT EXISTS no_tumor_detected BOOLEAN DEFAULT FALSE;",
        """
        CREATE TABLE IF NOT EXISTS patient_history_reports (
            id SERIAL PRIMARY KEY,
            patient_id INTEGER REFERENCES patients(id),
            report_type VARCHAR DEFAULT 'diagnosis_history',
            status VARCHAR DEFAULT 'not_created',
            data_hash VARCHAR,
            summary_text TEXT,
            classification_trend_text TEXT,
            risk_trend_text TEXT,
            conclusion_text TEXT,
            llm_model VARCHAR,
            prompt_version VARCHAR,
            source_metadata JSON,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_patient_history_reports_patient_id ON patient_history_reports(patient_id);",
        "CREATE INDEX IF NOT EXISTS ix_patient_history_reports_report_type ON patient_history_reports(report_type);",
        "CREATE INDEX IF NOT EXISTS ix_patient_history_reports_data_hash ON patient_history_reports(data_hash);",
        """
        CREATE TABLE IF NOT EXISTS classification_reviews (
            id SERIAL PRIMARY KEY,
            image_id INTEGER REFERENCES images(id),
            patient_id INTEGER REFERENCES patients(id),
            user_id INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ai_tumor_label VARCHAR,
            ai_confidence FLOAT,
            expert_tumor_label VARCHAR NOT NULL,
            expert_comment TEXT,
            review_action VARCHAR NOT NULL
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_classification_reviews_image_id ON classification_reviews(image_id);",
        "CREATE INDEX IF NOT EXISTS ix_classification_reviews_patient_id ON classification_reviews(patient_id);",
        "CREATE INDEX IF NOT EXISTS ix_classification_reviews_user_id ON classification_reviews(user_id);",
        """
        CREATE TABLE IF NOT EXISTS agent_conversations (
            id SERIAL PRIMARY KEY,
            thread_id VARCHAR UNIQUE NOT NULL,
            user_id INTEGER REFERENCES users(id),
            patient_id INTEGER REFERENCES patients(id),
            image_id INTEGER REFERENCES images(id),
            title TEXT,
            status VARCHAR DEFAULT 'active',
            summary TEXT,
            metadata_json JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_agent_conversations_thread_id ON agent_conversations(thread_id);",
        "CREATE INDEX IF NOT EXISTS ix_agent_conversations_user_id ON agent_conversations(user_id);",
        "CREATE INDEX IF NOT EXISTS ix_agent_conversations_patient_id ON agent_conversations(patient_id);",
        "CREATE INDEX IF NOT EXISTS ix_agent_conversations_image_id ON agent_conversations(image_id);",
        "CREATE INDEX IF NOT EXISTS ix_agent_conversations_status ON agent_conversations(status);",
        """
        CREATE TABLE IF NOT EXISTS agent_messages (
            id SERIAL PRIMARY KEY,
            thread_id VARCHAR NOT NULL,
            user_id INTEGER REFERENCES users(id),
            role VARCHAR NOT NULL,
            content TEXT,
            message_type VARCHAR DEFAULT 'text',
            metadata_json JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_agent_messages_thread_id ON agent_messages(thread_id);",
        "CREATE INDEX IF NOT EXISTS ix_agent_messages_user_id ON agent_messages(user_id);",
        "CREATE INDEX IF NOT EXISTS ix_agent_messages_created_at ON agent_messages(created_at);",
        """
        CREATE TABLE IF NOT EXISTS agent_audit_logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            patient_id INTEGER REFERENCES patients(id),
            image_id INTEGER REFERENCES images(id),
            thread_id VARCHAR,
            action VARCHAR NOT NULL,
            tool_name VARCHAR,
            before_value JSON,
            after_value JSON,
            metadata_json JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_agent_audit_logs_user_id ON agent_audit_logs(user_id);",
        "CREATE INDEX IF NOT EXISTS ix_agent_audit_logs_patient_id ON agent_audit_logs(patient_id);",
        "CREATE INDEX IF NOT EXISTS ix_agent_audit_logs_image_id ON agent_audit_logs(image_id);",
        "CREATE INDEX IF NOT EXISTS ix_agent_audit_logs_thread_id ON agent_audit_logs(thread_id);",
        "CREATE INDEX IF NOT EXISTS ix_agent_audit_logs_action ON agent_audit_logs(action);",
        "CREATE INDEX IF NOT EXISTS ix_agent_audit_logs_created_at ON agent_audit_logs(created_at);",
    ]
    with engine.begin() as conn:
        for query in migrations:
            try:
                conn.execute(text(query))
            except Exception as e:
                # Không sử dụng bất kỳ biểu tượng icon nào trong câu lệnh hiển thị
                print(f"[DATABASE MIGRATION] Error running query '{query}': {e}")


# Tự động thực thi migration khi module cơ sở dữ liệu được nạp
try:
    run_migrations()
except Exception as e:
    print(f"[DATABASE MIGRATION] Cannot run auto migrations: {e}")


# Dependency để lấy DB session cho các API sau này
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
