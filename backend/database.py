import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

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
        "ALTER TABLE patients ADD COLUMN IF NOT EXISTS owner_user_id INTEGER REFERENCES users(id);",
        "CREATE INDEX IF NOT EXISTS ix_patients_owner_user_id ON patients(owner_user_id);",
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
        """
        CREATE TABLE IF NOT EXISTS neuro_posts (
            id SERIAL PRIMARY KEY,
            author_id INTEGER NOT NULL REFERENCES users(id),
            post_type VARCHAR NOT NULL,
            content TEXT,
            image_id INTEGER REFERENCES images(id),
            patient_id INTEGER REFERENCES patients(id),
            anonymous_case_code VARCHAR UNIQUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_neuro_posts_author_id ON neuro_posts(author_id);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_posts_post_type ON neuro_posts(post_type);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_posts_image_id ON neuro_posts(image_id);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_posts_patient_id ON neuro_posts(patient_id);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_posts_created_at ON neuro_posts(created_at);",
        """
        CREATE TABLE IF NOT EXISTS neuro_post_attachments (
            id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL REFERENCES neuro_posts(id) ON DELETE CASCADE,
            object_path VARCHAR NOT NULL,
            content_type VARCHAR NOT NULL,
            original_name VARCHAR,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_neuro_post_attachments_post_id ON neuro_post_attachments(post_id);",
        """
        CREATE TABLE IF NOT EXISTS neuro_post_reactions (
            id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL REFERENCES neuro_posts(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            reaction_type VARCHAR NOT NULL DEFAULT 'like',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_neuro_reaction_post_user UNIQUE (post_id, user_id)
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_neuro_post_reactions_post_id ON neuro_post_reactions(post_id);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_post_reactions_user_id ON neuro_post_reactions(user_id);",
        """
        CREATE TABLE IF NOT EXISTS neuro_post_comments (
            id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL REFERENCES neuro_posts(id) ON DELETE CASCADE,
            author_id INTEGER NOT NULL REFERENCES users(id),
            parent_id INTEGER REFERENCES neuro_post_comments(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_neuro_post_comments_post_id ON neuro_post_comments(post_id);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_post_comments_author_id ON neuro_post_comments(author_id);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_post_comments_parent_id ON neuro_post_comments(parent_id);",
        """
        CREATE TABLE IF NOT EXISTS neuro_post_saves (
            id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL REFERENCES neuro_posts(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_neuro_save_post_user UNIQUE (post_id, user_id)
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_neuro_post_saves_post_id ON neuro_post_saves(post_id);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_post_saves_user_id ON neuro_post_saves(user_id);",
        """
        CREATE TABLE IF NOT EXISTS neuro_roi_comments (
            id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL REFERENCES neuro_posts(id) ON DELETE CASCADE,
            author_id INTEGER REFERENCES users(id),
            reply_to_id INTEGER REFERENCES neuro_roi_comments(id) ON DELETE CASCADE,
            visual_label VARCHAR NOT NULL,
            x FLOAT NOT NULL,
            y FLOAT NOT NULL,
            width FLOAT NOT NULL,
            height FLOAT NOT NULL,
            content TEXT NOT NULL,
            is_ai BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_neuro_roi_comments_post_id ON neuro_roi_comments(post_id);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_roi_comments_author_id ON neuro_roi_comments(author_id);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_roi_comments_reply_to_id ON neuro_roi_comments(reply_to_id);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_roi_comments_is_ai ON neuro_roi_comments(is_ai);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_roi_comments_created_at ON neuro_roi_comments(created_at);",
        """
        CREATE TABLE IF NOT EXISTS neuro_conversations (
            id SERIAL PRIMARY KEY,
            user_1_id INTEGER NOT NULL REFERENCES users(id),
            user_2_id INTEGER NOT NULL REFERENCES users(id),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_neuro_conversation_pair UNIQUE (user_1_id, user_2_id)
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_neuro_conversations_user_1_id ON neuro_conversations(user_1_id);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_conversations_user_2_id ON neuro_conversations(user_2_id);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_conversations_created_at ON neuro_conversations(created_at);",
        """
        CREATE TABLE IF NOT EXISTS neuro_second_opinion_requests (
            id SERIAL PRIMARY KEY,
            case_image_id INTEGER NOT NULL REFERENCES images(id),
            requester_doctor_id INTEGER NOT NULL REFERENCES users(id),
            reviewer_doctor_id INTEGER NOT NULL REFERENCES users(id),
            conversation_id INTEGER NOT NULL REFERENCES neuro_conversations(id),
            message_id INTEGER,
            request_message TEXT,
            status VARCHAR NOT NULL DEFAULT 'Pending',
            opinion TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_neuro_second_opinion_requests_case_image_id ON neuro_second_opinion_requests(case_image_id);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_second_opinion_requests_requester_doctor_id ON neuro_second_opinion_requests(requester_doctor_id);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_second_opinion_requests_reviewer_doctor_id ON neuro_second_opinion_requests(reviewer_doctor_id);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_second_opinion_requests_conversation_id ON neuro_second_opinion_requests(conversation_id);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_second_opinion_requests_message_id ON neuro_second_opinion_requests(message_id);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_second_opinion_requests_status ON neuro_second_opinion_requests(status);",
        """
        CREATE TABLE IF NOT EXISTS neuro_messages (
            id SERIAL PRIMARY KEY,
            conversation_id INTEGER NOT NULL REFERENCES neuro_conversations(id) ON DELETE CASCADE,
            sender_id INTEGER NOT NULL REFERENCES users(id),
            reply_to_id INTEGER REFERENCES neuro_messages(id) ON DELETE SET NULL,
            message_type VARCHAR NOT NULL DEFAULT 'text',
            content TEXT,
            image_path VARCHAR,
            image_content_type VARCHAR,
            image_original_name VARCHAR,
            case_image_id INTEGER REFERENCES images(id),
            second_opinion_request_id INTEGER REFERENCES neuro_second_opinion_requests(id),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            read_at TIMESTAMP
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_neuro_messages_conversation_id ON neuro_messages(conversation_id);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_messages_sender_id ON neuro_messages(sender_id);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_messages_reply_to_id ON neuro_messages(reply_to_id);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_messages_message_type ON neuro_messages(message_type);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_messages_case_image_id ON neuro_messages(case_image_id);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_messages_second_opinion_request_id ON neuro_messages(second_opinion_request_id);",
        "CREATE INDEX IF NOT EXISTS ix_neuro_messages_created_at ON neuro_messages(created_at);",
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
